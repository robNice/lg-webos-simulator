"""In-process helpers: call the Luna dispatcher exactly as the SSH path does, without a network."""
from __future__ import annotations

from tests.conftest import LIVE_PAYLOAD

IEPG = 'com.webos.service.iepg'
LEGACY = 'com.webos.service.legacybroadcast.channel'


def call(sim, method: str, payload: dict, service: str = IEPG) -> dict | None:
    sim.clock.tick()
    return sim.dispatcher.call(service, method, payload).response


def live(sim, mode: str = 'Satellite') -> list[dict]:
    return call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': mode})['channelList']


def find(channels: list[dict], name: str, number: int | None = None) -> dict:
    found = [c for c in channels if c['channelName'] == name and (number is None or int(c['channelNumber']) == number)]
    assert len(found) == 1, (name, number, found)
    return found[0]


def entry(sim, name: str, number: int | None = None, mode: str = 'Satellite') -> dict:
    found = [c for c in sim.channels() if c['name'] == name and c['mode'] == mode
             and (number is None or c['number'] == number)]
    assert len(found) == 1, (name, number, found)
    return found[0]


def renumber(sim, channel_id: str, number: int) -> dict:
    return call(sim, 'changeChannelNumber', {'channelId': channel_id, 'channelNumber': number})


def order(sim, group: str) -> list[str]:
    members = [c for c in sim.channels() if group in c['groups']]
    return [c['channel_id'] for c in sorted(members, key=lambda c: c['index'][group])]


def last_event(sim, kind: str = 'luna') -> dict:
    """Last event of ``kind``; for Luna the last non-read call."""
    return [e for e in sim.journal.events() if e['kind'] == kind
            and not (kind == 'luna' and e.get('method') in ('getChannelList', 'getChannel'))][-1]
