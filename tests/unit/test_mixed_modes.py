"""Editor v0.6.4: all reception modes and LG Channels (IP) in favorite lists (ARBEITSANWEISUNG_editor_v0.6.4).

Evidence: E2-E8 (real TV reads, E8 confirmed transfer). Assumptions: U1 (block boundary), U2 (index on add),
U3 (compaction on release) - see docs/evidence-register.md.
"""
import sqlite3

import pytest

from tests.conftest import LIVE_PAYLOAD
from tests.helpers import call

TUNER_IP = {**LIVE_PAYLOAD, 'channelMode': ['Tuner', 'IP']}


@pytest.fixture
def sim(sim_factory):
    return sim_factory('mixed_modes')


def live(sim, mode=('Tuner', 'IP')):
    response = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': list(mode) if isinstance(mode, tuple)
                                            else mode})
    assert response['returnValue'] is True, response
    return response['channelList']


def by_name(sim, name):
    found = [c for c in live(sim) if c['channelName'] == name]
    assert len(found) == 1, (name, found)
    return found[0]


def rows(sim, sql, *args):
    with sqlite3.connect(f'file:{sim.run.db_path}?mode=ro', uri=True) as conn:
        return conn.execute(sql, args).fetchall()


def ip_index(sim, group, name):
    return rows(sim, f'SELECT fav_chan_gr_{group.lower()}, favoriteIdx{group}, user_fav_chan_gr FROM ip '
                     'WHERE chan_std_name=?', name)[0]


def favorite_idx(sim, group, name):
    return rows(sim, f'SELECT f.fav_chan_gr_{group.lower()}, f.favoriteIdx{group} FROM favorite_idx f '
                     'JOIN ip USING (dvc_chan_id) WHERE ip.chan_std_name=?', name)


def order(sim, group):
    members = [c for c in live(sim) if group in c['favoriteGroup']]
    return [c['channelName'] for c in sorted(members, key=lambda c: c[f'favoriteIdx{group}'])]


def tuner_rows(sim):
    return rows(sim, 'SELECT * FROM tuner_on ORDER BY dvc_chan_id'), rows(sim, 'SELECT * FROM tuner_off ORDER BY 1')


# ------------------------------------------------------------------ fixture

def test_fixture_shape(sim):
    channels = live(sim)
    modes = {}
    for c in channels:
        modes[c['channelMode']] = modes.get(c['channelMode'], 0) + 1
    assert modes['Satellite'] >= 10 and 2 <= modes['Cable'] <= 3 and 3 <= modes['IP'] <= 5
    assert modes.get('Terrestrial', 0) >= 1
    cable_numbers = {c['channelNumber'] for c in channels if c['channelMode'] == 'Cable'}
    assert cable_numbers & {c['channelNumber'] for c in channels if c['channelMode'] == 'Satellite'}
    assert order(sim, 'D') == ['LG 1', 'LG 1: Film', 'Stream News']               # pure IP list from 251 (E5)
    assert [c['favoriteIdxD'] for c in channels if 'D' in c['favoriteGroup']] == [251, 252, 253]
    mixed = {c['channelMode'] for c in channels if 'A' in c['favoriteGroup']}
    assert {'Satellite', 'IP'} <= mixed                                              # tuner + IP members
    for name in ('LG 1', 'Stream Kino'):
        assert favorite_idx(sim, 'A' if name == 'Stream Kino' else 'D', name)        # E6: favorite_idx row


# ------------------------------------------------------------------ getChannelList (E2, E3, E7)

def test_channel_mode_list_and_strings(sim):
    everything = live(sim)
    tuner = live(sim, ('Tuner',))
    ip = live(sim, ('IP',))
    assert {c['channelMode'] for c in tuner} == {'Satellite', 'Cable', 'Terrestrial'}
    assert {c['channelMode'] for c in ip} == {'IP'}
    assert len(everything) == len(tuner) + len(ip)
    assert live(sim, 'Satellite') == live(sim, ('Satellite',)) == live(sim, 'satellite')
    assert len(live(sim, ('Satellite', 'Cable', 'Terrestrial'))) == len(tuner)


@pytest.mark.parametrize('mode', [7, {'mode': 'IP'}, [], ['IP', 3], None])
def test_invalid_channel_mode_type(sim, mode):
    payload = {**LIVE_PAYLOAD, 'channelMode': mode}
    response = call(sim, 'getChannelList', payload)
    assert response['returnValue'] is False and response['errorCode'] == 'ERROR_INVALID_PARAMETER'


def test_unknown_channel_mode_fails_closed(sim):
    response = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': ['Tuner', 'Antenna']})
    assert response['returnValue'] is False and response['errorCode'] == 'SIM_UNSUPPORTED'


def test_satellite_name_per_mode(sim):
    names = {}
    for c in live(sim):
        names.setdefault(c['channelMode'], set()).add(c['satelliteName'])
    assert names == {'Satellite': {'ASTRA 19.2E'}, 'Cable': {' '}, 'Terrestrial': {' '}, 'IP': {'UNKNOWN'}}


def test_stale_view_includes_ip_entries(sim_factory):
    sim = sim_factory('mixed_modes', read_after_write_stale_reads=1)
    channel = by_name(sim, 'Stream Doku')
    assert 'D' not in channel['favoriteGroup']
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [channel['channelId']], 'favoriteGroup': ['D']}) \
        == {'returnValue': True}
    assert 'D' not in by_name(sim, 'Stream Doku')['favoriteGroup']   # one stale read, IP entry still listed
    assert 'D' in by_name(sim, 'Stream Doku')['favoriteGroup']


def test_get_channel_knows_ip(sim):
    channel = by_name(sim, 'LG 1')
    response = call(sim, 'getChannel', {'channelId': channel['channelId']})
    assert response['returnValue'] is True and response['channel']['channelMode'] == 'IP'


# ------------------------------------------------------------------ IP favorites (E5, E6, E8, U2, U3)

def test_add_ip_to_list_takes_next_index_from_251(sim):
    tuner_before = tuner_rows(sim)
    kino = by_name(sim, 'Stream Kino')['channelId']
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [kino], 'favoriteGroup': ['D']})['returnValue']
    assert ip_index(sim, 'D', 'Stream Kino') == ('1', 254, '["A","D"]')
    assert favorite_idx(sim, 'D', 'Stream Kino') == [('1', 254)]
    news = by_name(sim, 'Stream News')['channelId']
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [news], 'favoriteGroup': ['B']})['returnValue']
    assert ip_index(sim, 'B', 'Stream News')[:2] == ('1', 251)                      # empty list: 251
    assert tuner_rows(sim) == tuner_before                                           # tuner tables untouched


def test_release_ip_compacts_the_ip_block(sim):
    film = by_name(sim, 'LG 1: Film')['channelId']
    assert call(sim, 'releaseChannelFavoriteGroup', {'channelId': [film], 'favoriteGroup': ['D']})['returnValue']
    assert ip_index(sim, 'D', 'LG 1: Film') == ('0', 255, '[]')                     # ip non-member: 255
    assert favorite_idx(sim, 'D', 'LG 1: Film') == [('0', 250)]                     # favorite_idx non-member: 250
    assert [ip_index(sim, 'D', n)[1] for n in ('LG 1', 'Stream News')] == [251, 252]


def test_reorder_inside_ip_block_reassigns_251(sim):
    """E8 (confirmed on the TV): reordering a pure IP list keeps the indices 251..."""
    channels = {c['channelName']: c['channelId'] for c in live(sim)}
    response = call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 3, 'channelId': [channels['Stream News']],
                                                         'destinationChannelId': channels['LG 1'], 'direction': 'up'})
    assert response == {'returnValue': True}
    assert order(sim, 'D') == ['Stream News', 'LG 1', 'LG 1: Film']
    assert [ip_index(sim, 'D', n)[1] for n in ('Stream News', 'LG 1', 'LG 1: Film')] == [251, 252, 253]
    assert [favorite_idx(sim, 'D', n)[0][1] for n in ('Stream News', 'LG 1', 'LG 1: Film')] == [251, 252, 253]


def test_adding_tuner_to_mixed_list_keeps_ip_block(sim):
    a_before = order(sim, 'A')
    cable = [c for c in live(sim) if c['channelMode'] == 'Cable' and 'A' not in c['favoriteGroup']][0]
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [cable['channelId']], 'favoriteGroup': ['A']})['returnValue']
    after = order(sim, 'A')
    tuner_count = sum(1 for c in live(sim) if 'A' in c['favoriteGroup'] and c['channelMode'] != 'IP')
    assert after[tuner_count - 1] == cable['channelName']                    # appended at the end of the tuner block
    assert [n for n in after if n != cable['channelName']] == a_before
    assert rows(sim, "SELECT favoriteIdxA FROM tuner_on WHERE dvc_chan_id=?", cable['channelId']) == [(tuner_count - 1,)]


# ------------------------------------------------------------------ block boundary (U1, profile option)

def _move_ip_before_first_tuner(sim):
    members = sorted((c for c in live(sim) if 'A' in c['favoriteGroup']), key=lambda c: c['favoriteIdxA'])
    first_tuner = next(c for c in members if c['channelMode'] != 'IP')
    ip = next(c for c in members if c['channelMode'] == 'IP')
    return ip['channelName'], call(sim, 'moveChannelFavoritePriority', {
        'favoriteGroupId': 0, 'channelId': [ip['channelId']], 'destinationChannelId': first_tuner['channelId'],
        'direction': 'up'})


def test_block_mode_keeps_ip_behind_tuner_but_answers_true(sim):
    assert sim.engine.profile.favorites.ip_block_after_tuner is True
    before, state = order(sim, 'A'), sim.engine.content_hash()
    _, response = _move_ip_before_first_tuner(sim)
    assert response == {'returnValue': True}                         # the editor then sees error.order.unconfirmed
    assert order(sim, 'A') == before and sim.engine.content_hash() == state
    event = [e for e in sim.journal.events() if e.get('method') == 'moveChannelFavoritePriority'][-1]
    assert event['effect'] == 'FAVORITE_ORDER_BLOCKED_IP' and not event['mutations']


def test_joint_mode_lets_ip_move_before_tuner(sim):
    favorites = sim.engine.profile.favorites.model_copy(update={'ip_block_after_tuner': False})
    sim.engine.profile = sim.engine.profile.model_copy(update={'favorites': favorites})
    name, response = _move_ip_before_first_tuner(sim)
    assert response == {'returnValue': True}
    after = order(sim, 'A')
    assert after[0] == name
    indices = sorted(c['favoriteIdxA'] for c in live(sim) if 'A' in c['favoriteGroup'])
    assert indices == list(range(len(indices)))                      # one joint order 0..n-1


# ------------------------------------------------------------------ number changes and invariants

def test_ip_number_change_stays_refused(sim):
    state = sim.engine.content_hash()
    response = call(sim, 'changeChannelNumber', {'channelId': by_name(sim, 'LG 1')['channelId'], 'channelNumber': 5})
    assert response['errorCode'] == 'SIM_UNSUPPORTED_IP_CHANNEL' and sim.engine.content_hash() == state


def test_satellite_may_take_a_number_only_cable_holds(sim):
    channels = live(sim)
    cable_only = {int(c['channelNumber']) for c in channels if c['channelMode'] == 'Cable'} - \
        {int(c['channelNumber']) for c in channels if c['channelMode'] == 'Satellite'}
    target = min(n for n in cable_only if n <= 99)
    satellite = next(c for c in channels if c['channelMode'] == 'Satellite' and int(c['channelNumber']) < 99)
    response = call(sim, 'changeChannelNumber', {'channelId': satellite['channelId'], 'channelNumber': target})
    assert response == {'returnValue': True}
    event = [e for e in sim.journal.events() if e.get('method') == 'changeChannelNumber'][-1]
    assert event['effect'] == 'MOVE'                                   # not a swap with the cable entry
    cable = [c for c in live(sim) if c['channelMode'] == 'Cable' and int(c['channelNumber']) == target]
    assert len(cable) == 1


def test_cable_number_change_is_an_honest_error(sim):
    cable = next(c for c in live(sim) if c['channelMode'] == 'Cable')
    response = call(sim, 'changeChannelNumber', {'channelId': cable['channelId'], 'channelNumber': 77})
    assert response['returnValue'] is False and response['errorCode'] == 'SIM_UNSUPPORTED_CHANNEL_ID'


def test_invariants_cover_ip_favorites(sim):
    engine = sim.engine
    assert engine.invariant_violations() == set()
    with engine.lock:
        engine.conn.execute("UPDATE favorite_idx SET favoriteIdxD=260 WHERE dvc_chan_id="
                            "(SELECT dvc_chan_id FROM ip WHERE chan_std_name='LG 1')")
        assert any('favorite_idx' in p for p in engine.invariant_violations())
        engine.conn.execute("UPDATE favorite_idx SET favoriteIdxD=251 WHERE dvc_chan_id="
                            "(SELECT dvc_chan_id FROM ip WHERE chan_std_name='LG 1')")
        engine.conn.execute("UPDATE ip SET favoriteIdxD=7 WHERE chan_std_name='LG 1'")
        problems = engine.invariant_violations()
        assert any('below 251' in p for p in problems)
        engine.conn.execute("UPDATE ip SET favoriteIdxD=251 WHERE chan_std_name='LG 1'")
        engine.conn.execute("UPDATE ip SET favoriteIdxA=0 WHERE chan_std_name='Stream Kino'")
        engine.conn.execute("UPDATE favorite_idx SET favoriteIdxA=0 WHERE dvc_chan_id="
                            "(SELECT dvc_chan_id FROM ip WHERE chan_std_name='Stream Kino')")
        assert any('duplicate' in p for p in engine.invariant_violations())
        engine.conn.rollback()


def test_status_counts_favorites_over_tuner_and_ip(sim):
    status = sim.status()
    assert status['favorites']['D'] == 3
    assert status['favorites']['A'] == sum(1 for c in live(sim) if 'A' in c['favoriteGroup'])
