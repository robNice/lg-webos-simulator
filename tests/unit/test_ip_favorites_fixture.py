"""real_20261011_1417_ipfav: the real list plus 15 LG Channels services in the previously empty list B,
stored like on the TV (E5, E6): ip flags/indices from 251, user_fav_chan_gr and a favorite_idx row each."""
import sqlite3

from lg_tv_sim.storage import database
from lg_tv_sim.storage.fixtures import IP_FAVORITES, derive_ip_favorites
from tests.conftest import REPO

RECORDED = REPO / 'fixtures' / 'recorded'
BASE, DERIVED = RECORDED / 'real_20261011_1417.sqlite', RECORDED / 'real_20261011_1417_ipfav.sqlite'


def rows(path, sql):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as conn:
        return conn.execute(sql).fetchall()


def test_list_b_was_empty_and_now_holds_15_ip_services():
    assert IP_FAVORITES == {'base': 'real_20261011_1417', 'group': 'B', 'count': 15}
    assert rows(BASE, "SELECT count(*) FROM ip WHERE fav_chan_gr_b='1'") == [(0,)]
    assert rows(BASE, "SELECT count(*) FROM tuner_on WHERE fav_chan_gr_b='1'") == [(0,)]
    members = rows(DERIVED, "SELECT favoriteIdxB, chan_no_int, user_fav_chan_gr FROM ip "
                            "WHERE fav_chan_gr_b='1' ORDER BY favoriteIdxB")
    assert [m[0] for m in members] == list(range(251, 266))
    assert [m[1] for m in members] == sorted(m[1] for m in members)        # list order = programme order
    assert all(m[2] == '["B"]' for m in members)
    assert len({m[1] // 100 for m in members}) > 3                          # spread over the 100-999 range


def test_nothing_else_differs_from_the_recording():
    for table in ('tuner_on', 'tuner_off', 'channel_group_tuner', 'pbs_genre_base'):
        query = f'SELECT * FROM {table} ORDER BY 1, 2'
        assert rows(DERIVED, query) == rows(BASE, query), table
    columns = 'dvc_chan_id, chan_no_int, chan_std_name, fav_chan_gr_a, favoriteIdxA, fav_chan_gr_c, favoriteIdxC'
    assert rows(DERIVED, f'SELECT {columns} FROM ip ORDER BY 1') == rows(BASE, f'SELECT {columns} FROM ip ORDER BY 1')
    assert rows(DERIVED, "SELECT count(*) FROM ip WHERE favoriteIdxB <> 255 AND fav_chan_gr_b <> '1'") == [(0,)]
    base_rows = rows(BASE, 'SELECT * FROM favorite_idx ORDER BY 1')
    derived_rows = rows(DERIVED, 'SELECT * FROM favorite_idx ORDER BY 1')
    assert set(base_rows) <= set(derived_rows) and len(derived_rows) == len(base_rows) + 15
    added = rows(DERIVED, "SELECT f.favoriteIdxB, ip.favoriteIdxB FROM favorite_idx f JOIN ip USING (dvc_chan_id) "
                          "WHERE f.fav_chan_gr_b='1'")
    assert len(added) == 15 and all(a == b for a, b in added)


def test_committed_file_matches_the_generator(tmp_path):
    target = tmp_path / 'derived.sqlite'
    derive_ip_favorites(BASE, target, 'B', 15)
    hashes = []
    for path in (target, DERIVED):
        conn = database.connect(path, readonly=True)
        hashes.append(database.content_hash(conn))
        conn.close()
    assert hashes[0] == hashes[1], 'run `lg-tv-sim build-synthetic`'


def test_simulator_and_backup_carry_the_ip_favorites(sim_factory, tmp_path):
    sim = sim_factory('real_20261011_1417_ipfav')
    sim.engine.backup_to(tmp_path / 'b.sqlite')
    assert rows(tmp_path / 'b.sqlite', "SELECT count(*) FROM ip WHERE fav_chan_gr_b='1'") == [(15,)]
