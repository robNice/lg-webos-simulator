"""Recorded fixtures: real TV backups committed after sanitising (ip contact/stream columns blanked)."""
import json
import re
import sqlite3

import pytest

from lg_tv_sim.cli import main
from lg_tv_sim.config import SimulatorConfig
from lg_tv_sim.storage.fixtures import FixtureCatalog, FixtureError, build_from_spec, personal_data_findings
from lg_tv_sim.storage.synthetic import mini
from tests.conftest import REPO

RECORDED = REPO / 'fixtures' / 'recorded'
PERSONAL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https?://|[?&](?:key|token|did)=', re.I)


def backup_with_ip_table(path, extra_sql=''):
    spec = mini()
    spec['channels'].append({'name': 'LG 1', 'number': 100, 'mode': 'IP'})
    build_from_spec(spec, path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE ip SET call_num='jane.doe@example.org', "
                     "ip_chan_service_url='https://stream.example/x.m3u8?key=abc123def'")
        if extra_sql:
            conn.execute(extra_sql)
    return path


def catalog(tmp_path):
    return FixtureCatalog(REPO / 'fixtures' / 'synthetic', tmp_path / 'private', tmp_path / 'recorded')


def test_public_import_blanks_ip_contacts_and_keeps_channels(tmp_path):
    source = backup_with_ip_table(tmp_path / 'backup.sqlite')
    meta = catalog(tmp_path).import_sqlite(source, 'mytv', public=True)
    target = tmp_path / 'recorded' / 'mytv.sqlite'
    with sqlite3.connect(target) as conn, sqlite3.connect(source) as original:
        assert conn.execute('SELECT dvc_chan_id, chan_std_name, call_num, ip_chan_service_url FROM ip').fetchall() \
            == [('11_3_100_65535_0_0_0', 'LG 1', '', '')]
        query = 'SELECT * FROM tuner_on ORDER BY dvc_chan_id'
        assert conn.execute(query).fetchall() == original.execute(query).fetchall()
    assert personal_data_findings(target) == []
    assert meta['source'] == 'backup.sqlite'                     # no local paths in committed metadata
    assert meta['blanked_columns'] == ['ip.call_num', 'ip.ip_chan_service_url']
    assert catalog(tmp_path).get('mytv').kind == 'sqlite'
    assert 'mytv' in catalog(tmp_path).names()


def test_public_import_refuses_remaining_personal_data(tmp_path):
    source = backup_with_ip_table(tmp_path / 'backup.sqlite',
                                  "UPDATE tuner_on SET chan_std_name='call max@example.org' WHERE rowid=1")
    with pytest.raises(FixtureError, match='personal data'):
        catalog(tmp_path).import_sqlite(source, 'mytv', public=True)
    assert not (tmp_path / 'recorded' / 'mytv.sqlite').exists()


def test_name_must_be_unique_across_all_fixture_kinds(tmp_path):
    source = backup_with_ip_table(tmp_path / 'backup.sqlite')
    catalog(tmp_path).import_sqlite(source, 'mytv', public=True)
    with pytest.raises(FixtureError, match='already exists'):
        catalog(tmp_path).import_sqlite(source, 'mytv')


def test_cli_public_import(tmp_path, monkeypatch, capsys):
    source = backup_with_ip_table(tmp_path / 'backup.sqlite')
    monkeypatch.chdir(tmp_path)
    assert main(['import-fixture', str(source), '--name', 'mytv', '--public']) == 0
    assert json.loads(capsys.readouterr().out)['blanked_columns'] == ['ip.call_num', 'ip.ip_chan_service_url']
    assert (tmp_path / 'fixtures' / 'recorded' / 'mytv.sqlite').is_file()


@pytest.mark.parametrize('path', sorted(RECORDED.glob('*.sqlite')), ids=lambda p: p.stem)
def test_committed_recorded_fixtures_are_clean(path):
    assert personal_data_findings(path) == []
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as conn:
        assert conn.execute("SELECT count(*) FROM ip WHERE call_num<>'' OR ip_chan_service_url<>''").fetchone()[0] == 0
        for (text,) in conn.execute("SELECT group_concat(chan_std_name, '|') FROM tuner_on"):
            assert not PERSONAL.search(text or '')
    meta = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    if 'derived_from' in meta:       # generated from another recorded fixture (build-synthetic)
        meta = json.loads((RECORDED / f'{meta["derived_from"]}.json').read_text(encoding='utf-8'))
    if 'format' in meta:             # converted GlobalClone export (import-globalclone --public)
        assert meta['origin'].startswith('https://') and '/' not in meta['source'] and meta['report']['converted']
        return
    assert meta['blanked_columns'] == ['ip.call_num', 'ip.ip_chan_service_url'] and '/' not in meta['source']


def test_real_list_of_2301_is_the_default_fixture():
    default = 'real_20261011_2301'
    assert SimulatorConfig().storage.initial_fixture == default
    for name in ('example.toml', 'docker.toml'):
        assert SimulatorConfig.load(REPO / 'config' / name).storage.initial_fixture == default
    assert (RECORDED / f'{default}.sqlite').is_file()
    dockerfile = (REPO / 'Dockerfile').read_text(encoding='utf-8')
    assert 'COPY fixtures/recorded/ fixtures/recorded/' in dockerfile


def test_simulator_starts_on_the_real_list(sim_factory):
    status = sim_factory('real_20261011_1417').status()
    assert status['channels'] == 879 and status['modes'] == {'Cable': 170, 'Satellite': 709}
    assert status['favorites']['A'] == 51 and status['favorites']['C'] == 8


def test_real_list_keeps_the_streaming_channels():
    with sqlite3.connect(f'file:{RECORDED / "real_20261011_1417.sqlite"}?mode=ro', uri=True) as conn:
        assert conn.execute("SELECT count(*), min(chan_no_int), max(chan_no_int) FROM ip "
                            "WHERE chan_mode_name='IP'").fetchone() == (220, 100, 999)
