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


@pytest.mark.parametrize('service', ['com.webos.service.iepg', 'com.webos.service.legacybroadcast.channel'])
def test_renumbering_an_ip_channel_is_refused_without_change(sim, service):
    state, ip = sim.engine.content_hash(), ip_rows(sim)
    response = call(sim, 'changeChannelNumber', {'channelId': ip_id(sim), 'channelNumber': 5}, service=service)
    assert response['returnValue'] is False and response['errorCode'] == CODE, response
    assert sim.engine.content_hash() == state and ip_rows(sim) == ip
    event = [e for e in sim.journal.events() if e.get('method') == 'changeChannelNumber'][-1]
    assert not event.get('mutations')
