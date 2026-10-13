"""LG Channels (table ip, mode IP) on the real list. Since editor v0.6.4 they are read via getChannelList
["Tuner","IP"] and may be in favorite lists (E2, E7, E8); number changes stay refused (E9, U4)."""
import sqlite3

import pytest

from tests.helpers import LIVE_PAYLOAD, call

FIXTURE = 'real_20261011_1417'
CODE = 'SIM_UNSUPPORTED_IP_CHANNEL'


@pytest.fixture
def sim(sim_factory):
    return sim_factory(FIXTURE)


def ip_rows(sim):
    with sqlite3.connect(f'file:{sim.run.db_path}?mode=ro', uri=True) as conn:
        return conn.execute('SELECT * FROM ip ORDER BY dvc_chan_id').fetchall()


def ip_id(sim):
    return ip_rows(sim)[0][0]


def test_backup_delivers_the_ip_table(sim, tmp_path):
    target = tmp_path / 'backup.sqlite'
    sim.engine.backup_to(target)
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT count(*) FROM ip WHERE chan_mode_name='IP'").fetchone()[0] == 220


def test_live_counts_match_the_real_tv(sim):
    """E2: Tuner+IP 1072 = 682 satellite (709 minus 27 invisible) + 170 cable + 220 IP."""
    def count(mode):
        return call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': mode})['channelListCount']
    assert count(['Tuner', 'IP']) == 1072
    assert (count('Tuner'), count('Satellite'), count('Cable'), count('IP')) == (852, 682, 170, 220)


def test_invisible_filter_both_ways_and_without_filter(sim):
    """E12 (real TV 13.10.2026): without attribute filter the hidden entries come too, each with
    "Invisible": true; {Invisible: true} returns exactly the 27 hidden satellite entries."""
    def satellite(attribute):
        response = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': 'Satellite', 'attribute': attribute})
        assert response['returnValue'] is True, response
        return response['channelList']
    everything = satellite([])
    hidden = satellite([{'filterType': 'Invisible', 'value': True}])
    shown = satellite([{'filterType': 'Invisible', 'value': False}])
    assert (len(everything), len(hidden), len(shown)) == (709, 27, 682)
    assert all(c['Invisible'] is True for c in hidden) and not any(c['Invisible'] for c in shown)
    bibel = [c for c in everything if c['channelId'] == '7_1_790_790_1108_12122_1']
    assert bibel and bibel[0]['Invisible'] is True
    for bad in ([{'filterType': 'Invisible', 'value': 'yes'}], [{'filterType': 'Locked', 'value': False}],
                [{'filterType': 'Invisible', 'value': True}, {'filterType': 'Invisible', 'value': False}]):
        response = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': 'Satellite', 'attribute': bad})
        assert response['returnValue'] is False, bad


@pytest.mark.parametrize('service', ['com.webos.service.iepg', 'com.webos.service.legacybroadcast.channel'])
def test_renumbering_an_ip_channel_is_refused_without_change(sim, service):
    state, ip = sim.engine.content_hash(), ip_rows(sim)
    response = call(sim, 'changeChannelNumber', {'channelId': ip_id(sim), 'channelNumber': 5}, service=service)
    assert response['returnValue'] is False and response['errorCode'] == CODE, response
    assert sim.engine.content_hash() == state and ip_rows(sim) == ip
    event = [e for e in sim.journal.events() if e.get('method') == 'changeChannelNumber'][-1]
    assert not event.get('mutations')
