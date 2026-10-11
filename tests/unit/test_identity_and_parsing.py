import pytest

from lg_tv_sim.config import ConfigError, SimulatorConfig
from lg_tv_sim.domain.identity import ChannelIdPolicy, IdentityRegistry, SatelliteIdPolicy, UnsupportedChannelId
from lg_tv_sim.ssh.commands import CommandRejected, split_command
from lg_tv_sim.ssh.paths import PathDenied, VirtualFileSystem


class TestChannelIdPolicy:
    def test_satellite_renumber_keeps_technical_tail(self):
        assert SatelliteIdPolicy().renumbered('7_32_13_13_1053_21108_1', 13, 99, '1053_21108_1') == \
            '7_32_99_99_1053_21108_1'

    @pytest.mark.parametrize('channel_id,old', [
        ('3_1_16386_0_5_173_133', 2),          # T37: cable ID layout is not understood
        ('7_32_13_13_1053_21108', 13),          # 6 parts
        ('7_32_13_14_1053_21108_1', 13),        # major != minor
        ('7_32_12_12_1053_21108_1', 13),        # does not encode the current number
        ('abc', 1),
    ])
    def test_unknown_formats_fail_closed(self, channel_id, old):
        with pytest.raises(UnsupportedChannelId):
            ChannelIdPolicy().renumbered('Satellite', channel_id, old, 5)

    def test_tail_must_match_signal_id(self):
        with pytest.raises(UnsupportedChannelId):
            SatelliteIdPolicy().renumbered('7_32_13_13_1053_21108_1', 13, 5, '1_2_3')

    def test_mode_without_policy_fails(self):
        with pytest.raises(UnsupportedChannelId):
            ChannelIdPolicy().renumbered('Cable', '3_1_23_0_5_62_133', 23, 5)


class TestIdentityRegistry:
    def test_ids_are_deterministic_and_follow_renames(self):
        a = IdentityRegistry.build('hash', [('x', ''), ('y', '')])
        b = IdentityRegistry.build('hash', [('x', ''), ('y', '')])
        assert a.to_json() == b.to_json()
        record = a.require('x')
        a.rename(record.sim_entry_id, 'x2')
        assert a.find('x') is None and a.require('x2').sim_entry_id == record.sim_entry_id
        assert a.require('x2').id_history == ['x', 'x2']
        assert IdentityRegistry.from_json(a.to_json()).to_json() == a.to_json()


class TestCommandSplitting:
    def test_editor_luna_command(self):
        words = split_command("""luna-send -n 1 luna://com.webos.service.iepg/setGroupName '{"channelGroupName":"A;B|C $x"}'""")
        assert words == ['luna-send', '-n', '1', 'luna://com.webos.service.iepg/setGroupName',
                         '{"channelGroupName":"A;B|C $x"}']

    def test_shlex_quoted_single_quote(self):
        assert split_command("echo 'it'\"'\"'s'") == ['echo', "it's"]

    def test_double_quoted_select(self):
        words = split_command('sqlite3 -readonly /db "SELECT a FROM t WHERE id=1"')
        assert words[-1] == 'SELECT a FROM t WHERE id=1'

    @pytest.mark.parametrize('command', [
        'rm -f /tmp/x; rm -rf /', 'ls | sh', 'cat /etc/passwd > /tmp/x', 'echo $(id)', 'echo `id`',
        'luna-send -n 1 x "$HOME"', 'a && b', 'sleep 1 &', 'echo \\x', "unterminated 'quote", 'x\ny',
    ])
    def test_shell_syntax_is_rejected(self, command):
        with pytest.raises(CommandRejected):
            split_command(command)


class TestVirtualPaths:
    def test_tmp_mapping_and_traversal(self, sim):
        vfs = VirtualFileSystem(lambda: sim.run)
        assert vfs.tmp_file('/tmp/lg-favoriten-abc.sqlite').parent == sim.run.tmp_dir.resolve()
        for bad in ('/tmp/../etc/passwd', '/etc/passwd', '/tmp/a/b', '/tmp/.hidden', '/tmp/', 'relative'):
            with pytest.raises(PathDenied):
                vfs.tmp_file(bad)

    def test_symlink_is_refused(self, sim, tmp_path):
        (tmp_path / 'secret').write_text('x')
        (sim.run.tmp_dir / 'link.sqlite').symlink_to(tmp_path / 'secret')
        with pytest.raises(PathDenied):
            VirtualFileSystem(lambda: sim.run).tmp_file('/tmp/link.sqlite')


class TestConfig:
    def test_external_bind_refused_by_default(self):
        with pytest.raises(ConfigError, match='loopback'):
            SimulatorConfig().with_overrides(server={'ssh_host': '0.0.0.0'})
        SimulatorConfig().with_overrides(server={'ssh_host': '0.0.0.0'}, security={'allow_external_bind': True})

    @pytest.mark.parametrize('port', [22, 8765, 8766])
    def test_reserved_ports(self, port):
        with pytest.raises(ConfigError):
            SimulatorConfig().with_overrides(server={'ssh_port': port})

    def test_unknown_keys_are_errors(self, tmp_path):
        path = tmp_path / 'c.toml'
        path.write_text('[server]\nssh_prot = 2222\n')
        with pytest.raises(ConfigError, match='unknown keys'):
            SimulatorConfig.load(path)
        path.write_text('[serverx]\n')
        with pytest.raises(ConfigError, match='unknown config section'):
            SimulatorConfig.load(path)

    def test_fail_open_options_rejected(self):
        with pytest.raises(ConfigError):
            SimulatorConfig().with_overrides(behavior={'unknown_commands': 'allow'})
        with pytest.raises(ConfigError):
            SimulatorConfig().with_overrides(security={'allow_sftp_write': True})

    def test_example_config_loads(self):
        from tests.conftest import REPO
        config = SimulatorConfig.load(REPO / 'config' / 'example.toml')
        assert config.server.ssh_port == 2222 and config.server.admin_port == 8767


def test_default_admin_port_avoids_editor_ports():
    """8765 = editor, 8766 = editor development/browser tests (2026-10-11)."""
    config = SimulatorConfig()
    assert config.server.admin_port == 8767
    with pytest.raises(ConfigError, match='8766'):
        config.with_overrides(server={'admin_port': 8766})
