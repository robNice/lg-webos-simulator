"""Favorite membership calls as measured on the real TV (OLED55C27LA, 13.10.2026, list H, real_20261011_2301).

E13: setChannelFavoriteGroup takes a hidden entry (Bibel TV 790) into a list like a visible one (tagesschau24 HD
126): live favoriteGroup ["H"], favoriteIdxH 0 and 1 in call order, the entry stays hidden (Invisible true) and the
TV shows it in list H; releaseChannelFavoriteGroup removes both again.
E14: every one of these calls answered {"returnValue": false} although it took effect (10 of 10 calls).
"""
import pytest

from lg_tv_sim.domain.numbers import FavoriteLayout
from tests.helpers import LIVE_PAYLOAD, call

FIXTURE = 'real_20261011_2301'
HIDDEN = '7_1_790_790_1108_12122_1'       # Bibel TV 790
CONTROL = '7_12_126_126_1039_10375_1'     # tagesschau24 HD 126
SHOWN = [{'filterType': 'Invisible', 'value': False}]


@pytest.fixture
def sim(sim_factory):
    return sim_factory(FIXTURE)


def live(sim, attribute=()):
    payload = {**LIVE_PAYLOAD, 'channelMode': 'Satellite', 'attribute': list(attribute)}
    return {c['channelId']: c for c in call(sim, 'getChannelList', payload)['channelList']}


def membership(sim, channel_id):
    entry = live(sim)[channel_id]
    return entry['favoriteGroup'], entry['favoriteIdxH'], entry['Invisible']


def favorite(sim, method, channel_id):
    return call(sim, method, {'channelId': [channel_id], 'favoriteGroup': ['H']})


def test_hidden_entries_join_and_leave_lists_and_the_tv_answers_false(sim):
    assert membership(sim, CONTROL) == ([], 250, False) and membership(sim, HIDDEN) == ([], 250, True)
    assert favorite(sim, 'setChannelFavoriteGroup', CONTROL) == {'returnValue': False}
    assert favorite(sim, 'setChannelFavoriteGroup', HIDDEN) == {'returnValue': False}
    assert membership(sim, CONTROL) == (['H'], 0, False)
    assert membership(sim, HIDDEN) == (['H'], 1, True)
    assert HIDDEN not in live(sim, SHOWN) and CONTROL in live(sim, SHOWN)
    events = [e for e in sim.journal.events() if e.get('method') == 'setChannelFavoriteGroup']
    assert all(e['mutations'] for e in events)
    assert favorite(sim, 'releaseChannelFavoriteGroup', CONTROL) == {'returnValue': False}
    assert favorite(sim, 'releaseChannelFavoriteGroup', HIDDEN) == {'returnValue': False}
    assert membership(sim, CONTROL) == ([], 250, False) and membership(sim, HIDDEN) == ([], 250, True)


def test_profile_can_answer_true_for_other_firmware(sim):
    sim.engine.profile = sim.engine.profile.model_copy(
        update={'favorites': FavoriteLayout(membership_return_value=True)})
    assert favorite(sim, 'setChannelFavoriteGroup', CONTROL) == {'returnValue': True}
    assert membership(sim, CONTROL) == (['H'], 0, False)
