"""Historical failure classes (spec §7.5, §17): API answer and real state are modelled separately."""
import pytest

from lg_tv_sim.faults.engine import CallInfo, FaultEngine
from lg_tv_sim.faults.schema import Scenario, load_directory
from tests.conftest import REPO
from tests.helpers import call, find, last_event, live, order, renumber


def test_all_shipped_scenarios_validate():
    scenarios = load_directory(REPO / 'fixtures' / 'scenarios')
    assert len(scenarios) >= 10


def test_unknown_scenario_keys_are_rejected(tmp_path):
    path = tmp_path / 's.yaml'
    path.write_text('id: x\nrules:\n  - id: r\n    match: {methd: changeChannelNumber}\n')
    with pytest.raises(ValueError):
        Scenario.load(path)


def test_t27_return_false_but_order_changed(sim_factory):
    sim = sim_factory('mini', scenario='return_false_but_favorite_moved')
    a = order(sim, 'A')
    first = call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 0, 'channelId': [a[2]],
                                                      'destinationChannelId': a[0], 'direction': 'up'})
    assert first == {'returnValue': True}
    a = order(sim, 'A')
    second = call(sim, 'moveChannelFavoritePriority', {'favoriteGroupId': 0, 'channelId': [a[3]],
                                                       'destinationChannelId': a[0], 'direction': 'up'})
    assert second == {'returnValue': False}
    assert order(sim, 'A')[0] == a[3]                          # the state DID change
    event = last_event(sim)
    assert event['fault'] == 'move-2-false' and event['true_response'] == {'returnValue': True}
    assert event['mutations']


def test_t28_false_without_mutation_keeps_state(sim_factory):
    sim = sim_factory('mini', scenario='add_favorite_false_no_mutation')
    sat1 = find(live(sim), 'SAT.1 HD')
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [sat1['channelId']], 'favoriteGroup': ['A']}) == \
        {'returnValue': False}
    assert find(live(sim), 'SAT.1 HD')['favoriteGroup'] == []
    assert last_event(sim)['suppressed_mutations'] and not last_event(sim)['mutations']


def test_false_with_mutation(sim_factory):
    sim = sim_factory('mini', scenario='add_favorite_false_with_mutation')
    sat1 = find(live(sim), 'SAT.1 HD')
    assert call(sim, 'setChannelFavoriteGroup', {'channelId': [sat1['channelId']], 'favoriteGroup': ['A']}) == \
        {'returnValue': False}
    assert find(live(sim), 'SAT.1 HD')['favoriteGroup'] == ['A']


def test_t29_delayed_visibility_then_consistent(sim_factory):
    sim = sim_factory('mini', scenario='delayed_visibility')
    qvc = find(live(sim), 'QVC HD', 21)
    assert renumber(sim, qvc['channelId'], 40) == {'returnValue': True}
    assert find(live(sim), 'QVC HD')['channelNumber'] == '21'    # stale read 1
    assert find(live(sim), 'QVC HD')['channelNumber'] == '21'    # stale read 2
    assert find(live(sim), 'QVC HD')['channelNumber'] == '40'
    # truth was written immediately; a client retry must not cause a second mutation
    assert sim.engine.stale_status() is None


def test_stale_by_virtual_time(sim_factory):
    sim = sim_factory('mini')
    qvc = find(live(sim), 'QVC HD', 21)
    sim.engine.change_number(qvc['channelId'], 40, stale_reads=0, stale_ms=250)
    assert find(live(sim), 'QVC HD')['channelNumber'] == '21'    # +100 ms
    assert find(live(sim), 'QVC HD')['channelNumber'] == '21'    # +200 ms
    assert find(live(sim), 'QVC HD')['channelNumber'] == '40'    # +300 ms


def test_t30_true_but_copy_instead_of_move(sim_factory):
    sim = sim_factory('mini', scenario='copy_instead_of_move')
    qvc = find(live(sim), 'QVC HD', 21)
    assert renumber(sim, qvc['channelId'], 40) == {'returnValue': True}
    entries = [c for c in live(sim) if c['channelName'] == 'QVC HD']
    assert sorted(c['channelNumber'] for c in entries) == ['21', '40']
    assert find(entries, 'QVC HD', 21)['channelId'] == qvc['channelId']


def test_t31_disconnect_before_mutation(sim_factory):
    sim = sim_factory('mini', scenario='timeout_before_mutation')
    state = sim.engine.content_hash()
    outcome = sim.dispatcher.call('com.webos.service.iepg', 'changeChannelNumber',
                                  {'channelId': find(live(sim), 'QVC HD')['channelId'], 'channelNumber': 40})
    assert outcome.disconnect and outcome.response is None and sim.engine.content_hash() == state


def test_t32_disconnect_after_mutation(sim_factory):
    sim = sim_factory('mini', scenario='timeout_after_mutation')
    outcome = sim.dispatcher.call('com.webos.service.iepg', 'changeChannelNumber',
                                  {'channelId': find(live(sim), 'QVC HD')['channelId'], 'channelNumber': 40})
    assert outcome.disconnect and outcome.response is None and outcome.mutated
    assert find(live(sim), 'QVC HD')['channelNumber'] == '40'


def test_t33_failure_in_third_step_keeps_first_two(sim_factory):
    sim = sim_factory('mini', scenario='fail_after_second_step')
    for name, target in (('QVC HD', 40), ('HSE HD', 41)):
        assert renumber(sim, find(live(sim), name, None if name == 'QVC HD' else 30)['channelId'], target)['returnValue']
    outcome = sim.dispatcher.call('com.webos.service.iepg', 'changeChannelNumber',
                                  {'channelId': find(live(sim), 'SAT.1 HD')['channelId'], 'channelNumber': 42})
    assert outcome.disconnect
    channels = live(sim)
    assert find(channels, 'QVC HD')['channelNumber'] == '40' and find(channels, 'HSE HD', 41)
    assert find(channels, 'SAT.1 HD')['channelNumber'] == '4'


def test_fault_rules_are_deterministic_and_counted():
    scenario = Scenario.model_validate({'id': 's', 'rules': [
        {'id': 'r1', 'match': {'method': 'changeChannelNumber', 'nth_call': 2}, 'action': {'mutate': False}},
        {'id': 'r2', 'match': {'method': 'changeChannelNumber'}, 'action': {'stale_reads': 1}, 'times': None}]})
    engine = FaultEngine(scenario)
    call_info = CallInfo('luna', 'com.webos.service.iepg', 'changeChannelNumber')
    fired = [(engine.select(call_info) or None) for _ in range(3)]
    assert [f.rule_id for f in fired] == ['r2', 'r1', 'r2']
    assert engine.status()['rules'][0] == {'id': 'r1', 'description': '', 'matched': 3, 'fired': 1}


def test_swap_does_not_change_groups_of_either_entry(sim_factory):
    """v0.5.24 lesson: compare both swapped entries directly before/after, not with the final target."""
    sim = sim_factory('synthetic_favorites_47')
    before = {c['sim_entry_id']: c['groups'] for c in sim.channels()}
    src = find(live(sim), 'Regional 61')
    renumber(sim, src['channelId'], 1)
    after = {c['sim_entry_id']: c['groups'] for c in sim.channels()}
    assert after == before
