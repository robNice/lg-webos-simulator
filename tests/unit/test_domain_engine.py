"""Domain semantics through the Luna dispatcher (same path as SSH, without the network)."""
import pytest

from lg_tv_sim.domain.models import InvariantViolation, NumberEffect
from tests.helpers import IEPG, LEGACY, call, entry, find, last_event, live, order, renumber


def test_t08_same_name_different_dvb_are_separate(sim):
    hse = [c for c in live(sim) if c['channelName'] == 'HSE HD']
    assert len(hse) == 2 and hse[0]['TSID'] != hse[1]['TSID'] and hse[0]['channelId'] != hse[1]['channelId']


def test_t09_welt_hd_triple_same_dvb(sim):
    welt = [c for c in live(sim) if c['channelName'] == 'WELT HD']
    assert sorted(int(c['channelNumber']) for c in welt) == [13, 403, 1015]
    assert {(c['ONID'], c['TSID'], c['SVCID']) for c in welt} == {(1, 1053, 21108)}
    assert len({c['channelId'] for c in welt}) == 3
    assert find(welt, 'WELT HD', 13)['channelId'] == '7_32_13_13_1053_21108_1'


def test_t10_number_maps_to_set_of_entries(sim):
    on_101 = [c for c in live(sim) if c['channelNumber'] == '101']
    assert {c['channelName'] for c in on_101} == {'NDR FS HH HD', 'NDR 2'}


def test_t11_move_to_free_slot_changes_id_keeps_favorites(sim):
    qvc = find(live(sim), 'QVC HD', 21)
    assert renumber(sim, qvc['channelId'], 40) == {'returnValue': True}
    moved = find(live(sim), 'QVC HD')
    assert moved['channelNumber'] == '40' and moved['channelId'] != qvc['channelId']
    assert moved['channelId'].split('_')[-3:] == qvc['channelId'].split('_')[-3:]
    assert moved['favoriteGroup'] == ['A'] and moved['favoriteIdxA'] == qvc['favoriteIdxA']
    # the old ID is no longer valid (no hidden alias, spec §8.3)
    assert call(sim, 'getChannel', {'channelId': qvc['channelId']}, LEGACY)['errorCode'] == 'CHANNEL_ERROR_NOT_FOUND'
    assert renumber(sim, qvc['channelId'], 41)['errorCode'] == 'CHANNEL_ERROR_NOT_FOUND'


def test_t12_swap_changes_both_ids_groups_stay_with_entries(sim):
    before = live(sim)
    qvc, shop = find(before, 'QVC HD', 21), find(before, 'ShopLC HD', 20)
    assert renumber(sim, qvc['channelId'], 20) == {'returnValue': True}
    after = live(sim)
    qvc2, shop2 = find(after, 'QVC HD'), find(after, 'ShopLC HD')
    assert (qvc2['channelNumber'], shop2['channelNumber']) == ('20', '21')
    assert qvc2['channelId'] not in (qvc['channelId'], shop['channelId'])
    assert shop2['channelId'] not in (qvc['channelId'], shop['channelId'])
    assert qvc2['favoriteGroup'] == qvc['favoriteGroup'] and shop2['favoriteGroup'] == shop['favoriteGroup']
    assert last_event(sim)['effect'] == 'SWAP' and len(last_event(sim)['mutations']) == 2


def test_t13_three_swap_chain_with_new_ids(sim):
    names = ['Das Erste HD', 'ZDF HD', 'RTL HD']
    for step in range(3):
        channels = live(sim)
        source = find(channels, names[step])
        target = (int(source['channelNumber']) % 3) + 1
        assert renumber(sim, source['channelId'], target) == {'returnValue': True}
    numbers = {n: find(live(sim), n)['channelNumber'] for n in names}
    # E1 Z2 R3 -> (E->2) E2 Z1 -> (Z->2) Z2 E1 -> (R->1) R1 E3
    assert numbers == {'Das Erste HD': '3', 'ZDF HD': '2', 'RTL HD': '1'}
    assert not sim.engine.invariant_violations()


def test_t14_chain_of_36_swaps_is_deterministic(sim_factory):
    hashes = set()
    for _ in range(2):
        sim = sim_factory('synthetic_favorites_47')
        for step in range(36):
            channels = live(sim)
            source = find(channels, 'Regional 61' if step % 2 == 0 else 'Regional 62')
            target = 62 if source['channelNumber'] == '61' else 61
            assert renumber(sim, source['channelId'], target) == {'returnValue': True}
        assert not sim.engine.invariant_violations()
        hashes.add((sim.engine.content_hash(), sim.journal.event_hash()))
    assert len(hashes) == 1


def test_t15_reorder_after_renumber_uses_new_id(sim):
    das_erste = find(live(sim), 'Das Erste HD', 1)
    renumber(sim, das_erste['channelId'], 50)
    new_id = find(live(sim), 'Das Erste HD')['channelId']
    zdf = find(live(sim), 'ZDF HD')['channelId']
    stale = call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 0, 'channelId': [das_erste['channelId']],
                                                      'destinationChannelId': zdf, 'direction': 'up'})
    assert stale['returnValue'] is False
    ok = call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 0, 'channelId': [zdf],
                                                   'destinationChannelId': new_id, 'direction': 'up'})
    assert ok == {'returnValue': True}
    assert order(sim, 'A')[:2] == [zdf, new_id]


def test_t16_t17_welt_hd_denied_high_allowed_99(sim):
    state = sim.engine.content_hash()
    denied = renumber(sim, '7_32_13_13_1053_21108_1', 900)
    assert denied == {'returnValue': False, 'errorCode': 'CHANNEL_ERROR_1003', 'errorText': 'Channel Move Denied'}
    assert sim.engine.content_hash() == state and last_event(sim)['mutations'] == []
    assert renumber(sim, '7_32_13_13_1053_21108_1', 99) == {'returnValue': True}
    assert find(live(sim), 'WELT HD', 99)['channelId'] == '7_32_99_99_1053_21108_1'


def test_t18_api_accepts_numbers_above_99_policy_is_client_side(sim):
    das_erste = find(live(sim), 'Das Erste HD', 1)
    assert renumber(sim, das_erste['channelId'], 4096) == {'returnValue': True}


def test_t19_t20_astra_copy_keeps_original_copy_without_favorites(sim):
    alpha = find(live(sim), 'ARD-alpha HD', 125)
    assert renumber(sim, alpha['channelId'], 27) == {'returnValue': True}
    entries = [c for c in live(sim) if c['channelName'] == 'ARD-alpha HD']
    original, copy = find(entries, 'ARD-alpha HD', 125), find(entries, 'ARD-alpha HD', 27)
    assert original['channelId'] == alpha['channelId'] and original['favoriteGroup'] == ['A']
    assert copy['channelId'] != alpha['channelId'] and copy['favoriteGroup'] == []
    record = entry(sim, 'ARD-alpha HD', 27)
    assert record['copy_of'] == entry(sim, 'ARD-alpha HD', 125)['sim_entry_id']


def test_t21_migrate_a_to_copy_then_release_original(sim):
    alpha = find(live(sim), 'ARD-alpha HD', 125)
    renumber(sim, alpha['channelId'], 27)
    copy = find(live(sim), 'ARD-alpha HD', 27)
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [copy['channelId']], 'favoriteGroup': ['A']}) == \
        {'returnValue': True}
    channels = live(sim)
    assert find(channels, 'ARD-alpha HD', 27)['favoriteGroup'] == ['A']
    assert find(channels, 'ARD-alpha HD', 125)['favoriteGroup'] == ['A']
    call(sim, 'releaseChannelFavoriteGroup', {'channelId': [alpha['channelId']], 'favoriteGroup': ['A']})
    channels = live(sim)
    assert find(channels, 'ARD-alpha HD', 125)['favoriteGroup'] == []
    assert find(channels, 'ARD-alpha HD', 27)['favoriteGroup'] == ['A']


def test_t22_existing_copy_is_reused_not_duplicated(sim):
    hgtv = find(live(sim), 'HGTV HD', 1827)
    count = len(live(sim))
    assert renumber(sim, hgtv['channelId'], 26) == {'returnValue': True}
    assert len(live(sim)) == count and last_event(sim)['effect'] == 'REUSE_COPY'
    assert find(live(sim), 'HGTV HD', 1827)['channelId'] == hgtv['channelId']


def test_t23_add_a_to_copy_keeps_other_groups(sim):
    copy = find(live(sim), 'HGTV HD', 26)
    assert copy['favoriteGroup'] == ['C']
    call(sim, 'setChannelFavoriteGroup', {'channelId': [copy['channelId']], 'favoriteGroup': ['A']})
    assert find(live(sim), 'HGTV HD', 26)['favoriteGroup'] == ['A', 'C']


def test_t24_duplicate_a_membership_merge(sim):
    copy = find(live(sim), 'HGTV HD', 26)
    original = find(live(sim), 'HGTV HD', 1827)
    call(sim, 'setChannelFavoriteGroup', {'channelId': [copy['channelId']], 'favoriteGroup': ['A']})
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [copy['channelId']], 'favoriteGroup': ['A']}) == \
        {'returnValue': True}
    assert last_event(sim)['mutations'] == []          # already a member: no second entry
    call(sim, 'releaseChannelFavoriteGroup', {'channelId': [original['channelId']], 'favoriteGroup': ['A']})
    channels = live(sim)
    assert find(channels, 'HGTV HD', 26)['favoriteGroup'] == ['A', 'C']
    assert find(channels, 'HGTV HD', 1827)['favoriteGroup'] == []
    a_ids = order(sim, 'A')
    assert len(a_ids) == len(set(a_ids))


def test_t25_ambiguous_target_is_rejected_without_mutation(sim):
    ndr = find(live(sim), 'NDR FS HH HD', 101)
    other = find(live(sim), 'HSE HD', 30)
    state = sim.engine.content_hash()
    reply = renumber(sim, other['channelId'], 101)
    assert reply['returnValue'] is False and reply['errorCode'] == 'SIM_TARGET_AMBIGUOUS'
    assert sim.engine.content_hash() == state
    assert ndr['channelNumber'] == '101'


def test_t26_foreign_service_on_target_is_never_overwritten(sim):
    hse = find(live(sim), 'HSE HD', 30)
    sat = find(live(sim), 'SAT.1 HD', 4)
    renumber(sim, hse['channelId'], 4)
    channels = live(sim)
    assert find(channels, 'SAT.1 HD')['channelNumber'] == '30'   # swapped, not deleted
    assert len([c for c in channels if c['channelNumber'] == '4']) == 1
    assert sat['channelId'] != find(channels, 'SAT.1 HD')['channelId']


def test_t35_t43_move_priority_only_touches_target_group(sim):
    before = {c['channel_id']: c['groups'] for c in sim.channels()}
    a = order(sim, 'A')
    assert call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 0, 'channelId': [a[3]],
                                                     'destinationChannelId': a[0], 'direction': 'up'}) == \
        {'returnValue': True}
    assert order(sim, 'A') == [a[3], a[0], a[1], a[2], *a[4:]]
    assert call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 0, 'channelId': [a[3]],
                                                     'destinationChannelId': a[2], 'direction': 'down'}) == \
        {'returnValue': True}
    assert order(sim, 'A') == a
    assert {c['channel_id']: c['groups'] for c in sim.channels()} == before
    assert order(sim, 'B') == [entry(sim, 'ZDF HD')['channel_id'], entry(sim, 'ShopLC HD')['channel_id']]


def test_t36_modes_have_separate_number_spaces(sim):
    cable_before = [c['channelId'] for c in live(sim, 'Cable')]
    # cable 'RTL HD' is on 13; a satellite move to 13 must not swap with it (WELT HD 13 is the occupant)
    rtl = find(live(sim), 'RTL HD', 3)
    renumber(sim, rtl['channelId'], 13)
    assert find(live(sim), 'WELT HD', 3)
    assert [c['channelId'] for c in live(sim, 'Cable')] == cable_before


def test_t37_unknown_id_format_is_reported(sim):
    cable = find(live(sim, 'Cable'), 'RTL HD', 13)
    reply = renumber(sim, cable['channelId'], 50)
    assert reply['returnValue'] is False and reply['errorCode'] == 'SIM_UNSUPPORTED_CHANNEL_ID'


def test_t38_reset_restores_identical_state(sim):
    base = sim.engine.content_hash()
    renumber(sim, find(live(sim), 'QVC HD')['channelId'], 20)
    call(sim, 'setChannelFavoriteGroup', {'channelId': [find(live(sim), 'SAT.1 HD')['channelId']],
                                          'favoriteGroup': ['H']})
    assert sim.engine.content_hash() != base
    sim.reset()
    assert sim.engine.content_hash() == base == sim.fixture_hash


def test_t39_same_seed_same_event_and_state_hash(sim_factory):
    results = set()
    for _ in range(2):
        sim = sim_factory('mini', scenario='return_false_but_favorite_moved')
        a = order(sim, 'A')
        for i in range(3):
            call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 0, 'channelId': [a[-1 - i]],
                                                      'destinationChannelId': a[0], 'direction': 'up'})
        renumber(sim, find(live(sim), 'QVC HD')['channelId'], 20)
        results.add((sim.engine.content_hash(), sim.journal.event_hash()))
    assert len(results) == 1


def test_t44_journal_tracks_identity_across_id_change(sim):
    qvc = entry(sim, 'QVC HD')
    renumber(sim, qvc['channel_id'], 20)
    mutation = next(m for m in last_event(sim)['mutations'] if m['sim_entry_id'] == qvc['sim_entry_id'])
    assert mutation['before']['channelId'] == qvc['channel_id']
    assert mutation['after']['channelId'] == entry(sim, 'QVC HD')['channel_id'] != qvc['channel_id']
    assert entry(sim, 'QVC HD')['id_history'] == [qvc['channel_id'], mutation['after']['channelId']]


def test_t45_unknown_service_and_method(sim):
    assert call(sim, 'nope', {})['returnValue'] is False
    assert call(sim, 'getChannelList', {}, service='com.example.none')['errorText'].startswith('Service does not exist')
    assert call(sim, 'copyDvbSatelliteChannelForAstra', {}, LEGACY)['errorCode'] == 'SIM_UNSUPPORTED'
    assert last_event(sim)['mutations'] == []


@pytest.mark.parametrize('payload', [
    {'channelId': '7_32_13_13_1053_21108_1', 'channelNumber': '99'},
    {'channelId': '7_32_13_13_1053_21108_1', 'channelNumber': True},
    {'channelId': '7_32_13_13_1053_21108_1', 'channelNumber': 0},
    {'channelId': 7, 'channelNumber': 9},
    {'channelId': '7_32_13_13_1053_21108_1', 'channelNumber': 9, 'force': True},
])
def test_invalid_parameters_never_mutate(sim, payload):
    state = sim.engine.content_hash()
    reply = call(sim, 'changeChannelNumber', payload)
    assert reply['returnValue'] is False and sim.engine.content_hash() == state


def test_channel_list_filters_fail_closed(sim):
    from tests.conftest import LIVE_PAYLOAD
    assert call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'compressed': 1})['errorCode'] == 'SIM_UNSUPPORTED'
    assert call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelGroup': ['A']})['errorCode'] == 'SIM_UNSUPPORTED'
    legacy = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelType': 'Satellite Digital TV', 'compressed': 0})
    assert all(c['channelType'] == 'Satellite Digital TV' for c in legacy['channelList'])
    assert all(not c['Radio'] for c in legacy['channelList'])


def test_group_name_and_favorite_group_list(sim):
    assert call(sim, 'setGroupName', {'channelMode': 'TUNER', 'channelGroupId': 207, 'channelGroupName': 'Radio'}) \
        == {'returnValue': True}
    assert sim.engine.readonly_query('SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id=207') \
        == [('Radio',)]
    listed = call(sim, 'getFavoriteGroupList', {'channelMode': 'TUNER'})['favoriteGroupList']
    assert {'channelGroupId': 207, 'channelGroupName': 'H'} in listed     # default names stay (observed on TV)
    assert call(sim, 'setGroupName', {'channelMode': 'TUNER', 'channelGroupId': 300,
                                      'channelGroupName': 'x'})['returnValue'] is False


def test_readonly_query_cannot_write(sim):
    import sqlite3
    with pytest.raises(sqlite3.Error):
        sim.engine.readonly_query("UPDATE tuner_on SET chan_no='1'")
    with pytest.raises(sqlite3.Error):
        sim.engine.readonly_query("ATTACH DATABASE '/tmp/x' AS x")


def test_invariant_violation_rolls_back(sim, monkeypatch):
    state = sim.engine.content_hash()
    calls = iter([set(), {'boom'}])
    monkeypatch.setattr(type(sim.engine), 'invariant_violations', lambda self: next(calls))
    with pytest.raises(InvariantViolation):
        sim.engine.change_number(find(live(sim), 'QVC HD')['channelId'], 40)
    monkeypatch.undo()
    assert sim.engine.content_hash() == state and not sim.engine.invariant_violations()


def test_fault_effect_override_and_suppressed_mutation(sim):
    result = sim.engine.change_number(find(live(sim), 'QVC HD')['channelId'], 40, effect=NumberEffect.COPY,
                                      mutate=False)
    assert result.effect == NumberEffect.COPY and result.mutations == [] and len(result.suppressed) == 1
    assert len([c for c in live(sim) if c['channelName'] == 'QVC HD']) == 1
    _ = IEPG
