"""synthetic_realistic: structure of a real LG backup (counts, ID layouts, lists), invented names, plus antenna."""
import json
import sqlite3

import pytest

from lg_tv_sim.storage import database
from lg_tv_sim.storage.fixtures import build_from_spec
from lg_tv_sim.storage.synthetic import RADIO_FLAG, realistic
from tests.conftest import REPO

SPEC = realistic()


@pytest.fixture(scope='module')
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp('realistic') / 'tv.sqlite'
    build_from_spec(SPEC, path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def count(db, sql, *args):
    return db.execute(sql, args).fetchone()[0]


def test_committed_and_schema_compatible(db):
    committed = json.loads((REPO / 'fixtures' / 'synthetic' / 'synthetic_realistic.json').read_text(encoding='utf-8'))
    assert committed == SPEC
    assert database.schema_problems(db) == []


def test_mode_and_type_counts_follow_the_real_backup(db):
    rows = {(r[0], r[1]): r[2] for r in db.execute(
        'SELECT chan_mode_name, chan_type_name, count(*) FROM tuner_on GROUP BY 1, 2')}
    assert rows[('Satellite', 'Satellite Digital TV')] == 603
    assert rows[('Satellite', 'Satellite Digital Radio')] == 106
    assert rows[('Cable', 'Cable Digital TV')] == 101
    assert rows[('Cable', 'Cable Digital Radio')] == 69
    tv, radio = rows[('Terrestrial', 'Terrestrial Digital TV')], rows[('Terrestrial', 'Terrestrial Digital Radio')]
    assert 30 <= tv + radio <= 40 and tv > 0 and radio > 0
    assert count(db, 'SELECT count(*) FROM tuner_off') == count(db, 'SELECT count(*) FROM tuner_on')


@pytest.mark.parametrize('mode,kind,type_id', [('Cable', 'TV', 4), ('Cable', 'Radio', 5), ('Satellite', 'TV', 6),
                                               ('Satellite', 'Radio', 7)])
def test_type_ids_and_majmin_prefix_match_real_backup(db, mode, kind, type_id):
    rows = db.execute('SELECT DISTINCT chan_type_id, substr(channelMajMinNo, 1, 2) FROM tuner_on '
                      'WHERE chan_type_name = ?', (f'{mode} Digital {kind}',)).fetchall()
    assert [tuple(r) for r in rows] == [(type_id, f'{type_id:02d}')]


def test_id_layout_encodes_maj_min_and_radio_flag(db):
    for row in db.execute('SELECT dvc_chan_id, phy_chan_no, maj_no, min_no, chan_no_int, radio_flag, '
                          'chan_mode_name, signal_chan_id FROM tuner_on'):
        parts = row['dvc_chan_id'].split('_')
        assert parts[1:4] == [str(row['phy_chan_no']), str(row['maj_no']), str(row['min_no'])]
        assert '_'.join(parts[4:]) == row['signal_chan_id']
        assert row['maj_no'] == row['chan_no_int'] + (RADIO_FLAG if row['radio_flag'] else 0)
    # satellite variants seen in the backup: LCN maj=min=no, non-LCN min != no, radio with the 0x4000 flag
    assert count(db, "SELECT count(*) FROM tuner_on WHERE chan_mode_name='Satellite' AND satelliteLcn_flag=1 "
                     "AND radio_flag=0 AND min_no=chan_no_int") > 300
    assert count(db, "SELECT count(*) FROM tuner_on WHERE chan_mode_name='Satellite' AND satelliteLcn_flag=0 "
                     "AND min_no<>chan_no_int") > 100


def test_favorite_lists_and_copies(db):
    a = [r[0] for r in db.execute("SELECT chan_no_int FROM tuner_on WHERE fav_chan_gr_a='1' ORDER BY favoriteIdxA")]
    assert a == list(range(1, 52))                                   # A already renumbered 1..51
    c = db.execute("SELECT chan_no_int, radio_flag FROM tuner_on WHERE fav_chan_gr_c='1' ORDER BY favoriteIdxC").fetchall()
    assert [r[0] for r in c] == list(range(70, 78)) and all(r[1] == 1 for r in c)
    assert count(db, "SELECT count(*) FROM favorite_idx") == 59
    copies = count(db, "SELECT count(*) FROM (SELECT signal_chan_id FROM tuner_on WHERE chan_mode_name='Satellite' "
                       "GROUP BY 1 HAVING min(chan_no_int) <= 99 AND max(chan_no_int) > 99)")
    assert 40 <= copies <= 70
    assert count(db, "SELECT count(*) FROM tuner_on WHERE chan_mode_name='Satellite' AND scrambled_flag=1") > 150


def test_names_are_invented():
    names = {c['name'] for c in SPEC['channels']}
    for real in ('Das Erste HD', 'ZDF HD', 'RTL HD', 'WELT HD', 'arte HD'):
        assert real not in names


def test_simulator_runs_on_it(sim_factory):
    sim = sim_factory('synthetic_realistic')
    status = sim.status()
    assert status['channels'] == len(SPEC['channels'])
    assert status['modes']['Terrestrial'] >= 30
    assert status['favorites']['A'] == 51 and status['favorites']['C'] == 8
