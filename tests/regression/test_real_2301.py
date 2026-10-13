"""Real backup 11.10.2026 23:01 (fixtures/recorded/real_20261011_2301): five LG Channels in list D, transferred
by the editor (E5-E8 directly).  Between 14:17 and 23:01 only these five ip rows, five new favorite_idx rows and
the name of list B changed on the TV."""
import sqlite3

import pytest

from lg_tv_sim.domain.models import GROUPS
from tests.conftest import REPO
from tests.helpers import LIVE_PAYLOAD, call

RECORDED = REPO / 'fixtures' / 'recorded'
D_ORDER = ['LG 1: Spotlight', 'LG 1: Film', 'Sony One | Action HITS', 'Sony One | Comedy HITS', 'LG 1']
FAV_COLUMNS = ', '.join(['user_fav_chan_gr'] + [f'fav_chan_gr_{g.lower()}' for g in GROUPS] +
                        [f'favoriteIdx{g}' for g in GROUPS])


def rows(path, sql):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as conn:
        return conn.execute(sql).fetchall()


def d_state(path):
    """ip and favorite_idx values of the D members, in list order."""
    ip = rows(path, f"SELECT dvc_chan_id, chan_std_name, {FAV_COLUMNS} FROM ip WHERE fav_chan_gr_d='1' "
                    'ORDER BY favoriteIdxD')
    fav = rows(path, f"SELECT dvc_chan_id, {FAV_COLUMNS} FROM favorite_idx WHERE dvc_chan_id IN "
                     "(SELECT dvc_chan_id FROM ip WHERE fav_chan_gr_d='1') ORDER BY favoriteIdxD")
    return ip, fav


def test_recorded_2301_holds_the_transferred_lg_channels_list():
    path = RECORDED / 'real_20261011_2301.sqlite'
    ip, fav = d_state(path)
    assert [r[1] for r in ip] == D_ORDER
    assert [r[-5] for r in ip] == [251, 252, 253, 254, 255]           # favoriteIdxD (E5, E8)
    assert [r[0] for r in fav] == [r[0] for r in ip]                    # E6: favorite_idx rows, same index
    assert all(r[1] == '["D"]' for r in fav)
    assert rows(path, "SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id=201") == \
        [('AI-Favoriten',)]
    assert rows(path, "SELECT count(*) FROM ip WHERE call_num<>'' OR ip_chan_service_url<>''") == [(0,)]


def test_live_list_of_2301(sim_factory):
    sim = sim_factory('real_20261011_2301')
    channels = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': ['Tuner', 'IP']})['channelList']
    assert len(channels) == 1072
    d = sorted((c for c in channels if 'D' in c['favoriteGroup']), key=lambda c: c['favoriteIdxD'])
    assert [(c['channelName'], c['favoriteIdxD'], c['satelliteName']) for c in d] == \
        [(name, 251 + i, 'UNKNOWN') for i, name in enumerate(D_ORDER)]


@pytest.mark.parametrize('added', [D_ORDER, list(reversed(D_ORDER))])
def test_simulator_reproduces_the_2301_state_from_1417(sim_factory, added):
    """Add the five LG Channels to D over Luna (any order), reorder like the editor (direction up), and the ip and
    favorite_idx rows equal the real 23:01 backup - including favorite_idx non-members (250)."""
    sim = sim_factory('real_20261011_1417')
    ids = {name: cid for cid, name in rows(sim.run.db_path, 'SELECT dvc_chan_id, chan_std_name FROM ip')}
    for name in added:
        assert call(sim, 'setChannelFavoriteGroup', {'channelId': [ids[name]], 'favoriteGroup': ['D']}) == \
            {'returnValue': False}   # E14
    for position, name in enumerate(D_ORDER):
        current = [r[1] for r in d_state(sim.run.db_path)[0]]
        if current[position] != name:
            assert call(sim, 'moveChannelFavoritePriority', {
                'favoriteGroupId': 3, 'channelId': [ids[name]], 'destinationChannelId': ids[current[position]],
                'direction': 'up'}) == {'returnValue': True}
    assert d_state(sim.run.db_path) == d_state(RECORDED / 'real_20261011_2301.sqlite')
    assert sim.engine.content_hash() != ''        # state stays readable; tuner tables untouched below
    query = 'SELECT * FROM tuner_on ORDER BY dvc_chan_id'
    assert rows(sim.run.db_path, query) == rows(RECORDED / 'real_20261011_2301.sqlite', query)
