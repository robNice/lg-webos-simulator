"""Release/container rules (same scheme as the editor): one version source, :dev on dev, vX.Y.Z on main."""
import os
import re
import subprocess
import tomllib

import pytest

from lg_tv_sim import __version__
from lg_tv_sim.cli import main
from lg_tv_sim.config import SimulatorConfig
from lg_tv_sim.ssh.server import known_hosts_line, load_or_create_host_key
from tests.conftest import REPO

WORKFLOWS = REPO / '.github' / 'workflows'


def test_version_has_a_single_source():
    project = tomllib.loads((REPO / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'version' not in project['project']
    assert 'version' in project['project']['dynamic']
    assert project['tool']['setuptools']['dynamic']['version'] == {'attr': 'lg_tv_sim.version.__version__'}
    version_file = (REPO / 'src' / 'lg_tv_sim' / 'version.py').read_text(encoding='utf-8')
    assert re.search(rf"^__version__ = '{re.escape(__version__)}'$", version_file, re.M)
    init = (REPO / 'src' / 'lg_tv_sim' / '__init__.py').read_text(encoding='utf-8')
    assert 'from lg_tv_sim.version import __version__' in init and "__version__ = '" not in init
    assert re.fullmatch(r'\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?', __version__)


def test_changelog_documents_current_version():
    path = REPO / 'CHANGELOG.md'
    if not path.is_file():   # local working file, git-ignored: absent in CI checkouts
        pytest.skip('CHANGELOG.md is not part of the repository')
    changelog = path.read_text(encoding='utf-8')
    assert re.search(rf'^## v{re.escape(__version__)} – ', changelog, re.M)


def test_docker_config_binds_container_interfaces_deliberately():
    config = SimulatorConfig.load(REPO / 'config' / 'docker.toml')
    assert (config.server.ssh_host, config.server.ssh_port) == ('0.0.0.0', 2222)
    assert (config.server.admin_host, config.server.admin_port) == ('0.0.0.0', 8767)
    assert config.security.allow_external_bind is True


def test_dockerfile_provisions_config_and_drops_privileges():
    dockerfile = (REPO / 'Dockerfile').read_text(encoding='utf-8')
    assert 'LG_TV_SIM_CONFIG=/config/simulator.toml' in dockerfile
    assert 'LG_TV_SIM_CONFIG_TEMPLATE=/app/config/docker.toml' in dockerfile
    assert 'LG_TV_SIM_CONTAINER=1' in dockerfile
    assert re.search(r'^VOLUME \["/config", "/app/.simulator"\]$', dockerfile, re.M)
    assert re.search(r'^EXPOSE 2222 8767$', dockerfile, re.M)
    assert re.search(r'^ENTRYPOINT \["/usr/local/bin/docker-entrypoint.sh"\]$', dockerfile, re.M)
    assert re.search(r'^CMD \["lg-tv-sim", "serve"\]$', dockerfile, re.M)
    assert 'HEALTHCHECK' in dockerfile
    entrypoint = (REPO / 'docker-entrypoint.sh').read_text(encoding='utf-8')
    assert 'exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"' in entrypoint
    ignored = (REPO / '.dockerignore').read_text(encoding='utf-8').split()
    for entry in ('.simulator', 'fixtures/private', '.env', 'config/local.toml', 'tests'):
        assert entry in ignored


def test_entrypoint_is_valid_and_passes_through_when_not_root():
    script = REPO / 'docker-entrypoint.sh'
    assert os.access(script, os.X_OK)
    subprocess.run(['sh', '-n', str(script)], check=True)
    if os.getuid() == 0:
        pytest.skip('pass-through check needs a non-root user')
    result = subprocess.run(['sh', str(script), 'echo', 'started'], capture_output=True, text=True, check=True)
    assert result.stdout == 'started\n'


def test_docker_template_covers_every_setting_of_the_example():
    def keys(path):
        data = tomllib.loads(path.read_text(encoding='utf-8'))
        return {(section, key) for section, values in data.items() for key in values}
    assert keys(REPO / 'config' / 'docker.toml') == keys(REPO / 'config' / 'example.toml')


def test_config_env_provisions_template_once_and_never_overwrites(tmp_path, monkeypatch, capsys):
    target = tmp_path / 'mapped' / 'simulator.toml'
    template = REPO / 'config' / 'docker.toml'
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('LG_TV_SIM_CONFIG', str(target))
    monkeypatch.setenv('LG_TV_SIM_CONFIG_TEMPLATE', str(template))
    assert main(['known-hosts']) == 0
    assert target.read_text(encoding='utf-8') == template.read_text(encoding='utf-8')
    assert '[127.0.0.1]:2222 ' in capsys.readouterr().out
    edited = template.read_text(encoding='utf-8').replace('ssh_port = 2222', 'ssh_port = 2223')
    target.write_text(edited, encoding='utf-8')
    assert main(['known-hosts']) == 0
    assert target.read_text(encoding='utf-8') == edited
    assert '[127.0.0.1]:2223 ' in capsys.readouterr().out


def test_config_env_without_template_requires_the_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('LG_TV_SIM_CONFIG', str(tmp_path / 'missing.toml'))
    monkeypatch.delenv('LG_TV_SIM_CONFIG_TEMPLATE', raising=False)
    assert main(['known-hosts']) == 2
    assert 'config file not found' in capsys.readouterr().err


def test_container_refuses_loopback_bind(tmp_path, monkeypatch, capsys):
    config = tmp_path / 'simulator.toml'
    config.write_text('[server]\nssh_host = "127.0.0.1"\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('LG_TV_SIM_CONTAINER', '1')
    assert main(['--config', str(config), 'serve']) == 2
    assert 'unreachable from outside the container' in capsys.readouterr().err


def test_release_workflow_requires_tag_on_main_matching_version():
    text = (WORKFLOWS / 'docker-image.yml').read_text(encoding='utf-8')
    assert '- "v*"' in text
    assert 'origin/main' in text
    assert 'from lg_tv_sim.version import __version__' in text
    assert 'pytest' in text and 'ruff check' in text
    assert ':latest' in text and 'is_prerelease' in text


def test_dev_workflow_publishes_dev_tag_from_dev_branch():
    text = (WORKFLOWS / 'docker-image-dev.yml').read_text(encoding='utf-8')
    assert re.search(r'branches:\s*\n\s*- dev\b', text)
    assert ':dev' in text and ':latest' not in text
    assert 'pytest' in text and 'ruff check' in text


def test_known_hosts_line_for_wildcard_listen_names_loopback(tmp_path):
    key = load_or_create_host_key(tmp_path / 'key')
    assert known_hosts_line(key, '0.0.0.0', 2222).startswith('[127.0.0.1]:2222 ssh-ed25519 ')
    assert known_hosts_line(key, '::', 22).startswith('127.0.0.1 ssh-ed25519 ')


def test_cli_known_hosts_host_and_port_override(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(['known-hosts', '--host', 'nas.local', '--port', '2223']) == 0
    assert capsys.readouterr().out.startswith('[nas.local]:2223 ssh-ed25519 ')
