import json
import sqlite3

import pytest

from lg_tv_sim.cli import main
from lg_tv_sim.storage import database
from lg_tv_sim.storage.fixtures import FixtureCatalog, FixtureError, build_from_spec, inspect_sqlite
from lg_tv_sim.storage.synthetic import favorites_47, mini
from lg_tv_sim.traces.comparator import compare
from lg_tv_sim.traces.sanitizer import sanitize
from tests.conftest import REPO


def test_committed_specs_match_generators():
    for name, generator in (('mini', mini), ('synthetic_favorites_47', favorites_47)):
        committed = json.loads((REPO / 'fixtures' / 'synthetic' / f'{name}.json').read_text(encoding='utf-8'))
        assert committed == generator(), f'run `lg-tv-sim build-synthetic` ({name})'


def test_build_is_deterministic_and_schema_compatible(tmp_path):
    hashes = set()
    for i in range(2):
        path = tmp_path / f'f{i}.sqlite'
        build_from_spec(favorites_47(), path)
        conn = database.connect(path, readonly=True)
        assert database.schema_problems(conn) == [] and database.integrity_ok(conn)
        hashes.add(database.content_hash(conn))
        conn.close()
    assert len(hashes) == 1
    report = inspect_sqlite(tmp_path / 'f0.sqlite')
    assert report['favorites']['A'] == 47 and report['tables']['tuner_on'] >= 100


def test_duplicate_ids_in_spec_are_rejected(tmp_path):
    spec = mini()
    spec['channels'].append(dict(spec['channels'][0]))
    with pytest.raises(FixtureError, match='duplicate'):
        build_from_spec(spec, tmp_path / 'x.sqlite')


def test_import_private_fixture_read_only_and_no_overwrite(tmp_path):
    source = tmp_path / 'channel.sql'
    build_from_spec(mini(), source)
    digest = database.file_sha256(source)
    catalog = FixtureCatalog(REPO / 'fixtures' / 'synthetic', tmp_path / 'private')
    meta = catalog.import_sqlite(source, 'my_tv')
    assert meta['source_sha256'] == digest == database.file_sha256(source)
    assert 'my_tv' in catalog.names() and catalog.get('my_tv').kind == 'sqlite'
    with pytest.raises(FixtureError, match='already exists'):
        catalog.import_sqlite(source, 'my_tv')
    with pytest.raises(FixtureError, match='already exists'):
        catalog.import_sqlite(source, 'mini')


def test_import_rejects_foreign_database(tmp_path):
    other = tmp_path / 'other.sqlite'
    with sqlite3.connect(other) as conn:
        conn.execute('CREATE TABLE t (x)')
    catalog = FixtureCatalog(REPO / 'fixtures' / 'synthetic', tmp_path / 'private')
    with pytest.raises(FixtureError, match='missing table tuner_on'):
        catalog.import_sqlite(other, 'bad')
    (tmp_path / 'text.sql').write_text('not sqlite')
    with pytest.raises(FixtureError, match='not an SQLite'):
        catalog.import_sqlite(tmp_path / 'text.sql', 'bad2')


def test_simulator_runs_on_imported_fixture(sim_factory, tmp_path):
    source = tmp_path / 'channel.sql'
    build_from_spec(mini(), source)
    sim = sim_factory('mini')
    sim.catalog.private_dir = tmp_path / 'private'
    sim.catalog.import_sqlite(source, 'imported')
    sim.reset(fixture='imported')
    assert sim.fixture_name == 'imported' and len(sim.channels()) == 19


def test_cli_validate_inspect_known_hosts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'local.toml').write_text(
        f'[storage]\nfixtures_dir = "{REPO / "fixtures" / "synthetic"}"\n'
        f'scenarios_dir = "{REPO / "fixtures" / "scenarios"}"\n')
    assert main(['validate-fixture', 'synthetic_favorites_47']) == 0
    assert main(['inspect-fixture', 'mini']) == 0
    assert '"A": 8' in capsys.readouterr().out
    assert main(['scenarios', 'list']) == 0
    assert 'delayed_visibility' in capsys.readouterr().out
    known = tmp_path / 'kh'
    assert main(['known-hosts', '--install', str(known)]) == 0
    line = known.read_text().strip()
    assert line.startswith('[127.0.0.1]:2222 ssh-ed25519 ')
    assert main(['known-hosts', '--install', str(known)]) == 1        # never duplicates/overwrites entries
    assert (tmp_path / '.simulator' / 'keys' / 'ssh_host_key').stat().st_mode & 0o077 == 0
    assert main(['validate-fixture', str(tmp_path / 'kh')]) == 1


def test_cli_rejects_bad_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / 'bad.toml'
    bad.write_text('[server]\nssh_host = "0.0.0.0"\n')
    assert main(['--config', str(bad), 'scenarios', 'list']) == 2


def test_trace_comparator_reports_first_divergence(sim_factory):
    from tests.helpers import call, find, live
    traces = []
    for swap_order in (False, True):
        sim = sim_factory('mini')
        a = find(live(sim), 'QVC HD')['channelId']
        b = find(live(sim), 'SAT.1 HD')['channelId']
        for cid, number in ((b, 50), (a, 40)) if swap_order else ((a, 40), (b, 50)):
            call(sim, 'changeChannelNumber', {'channelId': cid, 'channelNumber': number})
        traces.append(sim.journal.events())
    assert compare(traces[0], traces[0]) is None
    divergence = compare(traces[0], traces[1])
    assert divergence is not None and divergence.field == 'params'
    assert compare(traces[0], traces[0][:-1]).field == 'length'


def test_sanitizer_removes_secrets_and_ips():
    data = sanitize({'password': 'x', 'nested': {'Token': 'y', 'host': 'tv at 192.168.1.20'}, 'ok': '127.0.0.1'})
    assert data == {'password': '<redacted>', 'nested': {'Token': '<redacted>', 'host': 'tv at <ip>'}, 'ok': '127.0.0.1'}
