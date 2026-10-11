"""``com.webos.service.iepg`` methods used by the current editor (v0.6.1).

Request shapes are CURRENT_CLIENT_CONFIRMED (tv_write.py / tv_groups.py).  The
exact response layout of the real TV is not available as a trace; the field
set below is what the editor's parser reads (SIMULATOR_ASSUMPTION for the rest).
"""
from __future__ import annotations

from lg_tv_sim.domain.engine import EngineResult, TvEngine
from lg_tv_sim.domain.models import (
    FAVORITE_GROUP_ID_BASE,
    GROUPS,
    ChannelEntry,
    LunaError,
    UnsupportedOperation,
)

SERVICE = 'com.webos.service.iepg'


class Params:
    """Strict accessors for JSON parameters: wrong types are rejected, never coerced."""

    def __init__(self, params: dict, allowed: set[str]):
        if not isinstance(params, dict):
            raise LunaError('ERROR_INVALID_PARAMETER', 'parameters must be a JSON object')
        unknown = set(params) - allowed
        if unknown:
            raise UnsupportedOperation(f'unsupported parameters: {", ".join(sorted(unknown))}')
        self.params = params

    def get(self, name, kind, required=True, default=None):
        if name not in self.params:
            if required:
                raise LunaError('ERROR_MISSING_PARAMETER', f'missing parameter {name!r}')
            return default
        value = self.params[name]
        if kind is int and (type(value) is not int):
            raise LunaError('ERROR_INVALID_PARAMETER', f'{name!r} must be an integer')
        if kind is not int and not isinstance(value, kind):
            raise LunaError('ERROR_INVALID_PARAMETER', f'{name!r} has the wrong type')
        return value

    def string_list(self, name) -> list[str]:
        value = self.get(name, list)
        if not value or not all(isinstance(v, str) and v for v in value):
            raise LunaError('ERROR_INVALID_PARAMETER', f'{name!r} must be a non-empty list of strings')
        return value


def channel_json(entry: ChannelEntry) -> dict:
    data = {
        'channelId': entry.channel_id,
        'channelNumber': str(entry.number),
        'channelName': entry.name,
        'channelMode': entry.mode,
        'channelType': entry.channel_type,
        'satelliteName': entry.satellite,
        'ONID': entry.dvb.onid,
        'TSID': entry.dvb.tsid,
        'SVCID': entry.dvb.sid,
        'signalChannelId': entry.signal_id,
        'Radio': entry.radio,
        'Invisible': entry.invisible,
        'satelliteLcn': entry.satellite_lcn,
        'favoriteGroup': entry.member_of,
    }
    for g in GROUPS:
        data[f'favoriteIdx{g}'] = entry.index[g]
    return data


def get_channel_list(engine: TvEngine, params: dict, **_) -> EngineResult:
    p = Params(params, {'dataType', 'sort', 'channelMode', 'channelType', 'channelGroup', 'acceptEmptyGroupName',
                        'attribute', 'compressed'})
    if p.get('compressed', int, required=False, default=0) != 0:
        raise UnsupportedOperation('compressed channel lists are not simulated (current editor does not request them)')
    if p.get('dataType', int, required=False, default=0) != 0 or p.get('sort', int, required=False, default=0) != 0:
        raise UnsupportedOperation('only dataType 0 and sort 0 are simulated')
    mode = p.get('channelMode', str)
    channel_type = p.get('channelType', str, required=False)
    groups = p.get('channelGroup', list, required=False, default=['All'])
    if groups != ['All']:
        raise UnsupportedOperation('only channelGroup ["All"] is simulated')
    p.get('acceptEmptyGroupName', bool, required=False)
    hide_invisible = False
    for item in p.get('attribute', list, required=False, default=[]):
        if item != {'filterType': 'Invisible', 'value': False}:
            raise UnsupportedOperation(f'unsupported attribute filter {item!r}')
        hide_invisible = True
    entries, stale = engine.visible_entries()
    selected = [e for e in entries
                if e.mode.lower() == mode.lower()
                and (channel_type is None or e.channel_type == channel_type)
                and not (hide_invisible and e.invisible)]
    selected.sort(key=lambda e: (e.number, e.channel_id))
    channels = [channel_json(e) for e in selected]
    return EngineResult(value={'returnValue': True, 'channelList': channels, 'channelListCount': len(channels)},
                        effect='STALE_READ' if stale else 'READ')


def get_channel(engine: TvEngine, params: dict, **_) -> EngineResult:
    p = Params(params, {'channelId'})
    channel_id = p.get('channelId', str)
    entries, stale = engine.visible_entries()
    found = [e for e in entries if e.channel_id == channel_id]
    if len(found) != 1:
        raise LunaError('CHANNEL_ERROR_NOT_FOUND', f'Channel not found: {channel_id}')
    return EngineResult(value={'returnValue': True, 'channel': channel_json(found[0])},
                        effect='STALE_READ' if stale else 'READ')


def change_channel_number(engine: TvEngine, params: dict, fault=None, **_) -> EngineResult:
    p = Params(params, {'channelId', 'channelNumber'})
    channel_id, number = p.get('channelId', str), p.get('channelNumber', int)
    action = fault.action if fault else None
    result = engine.change_number(channel_id, number, effect=action.effect if action else None,
                                  **_write_options(action))
    result.value = {'returnValue': True}
    return result


def _favorite(member: bool):
    def handler(engine: TvEngine, params: dict, fault=None, **_) -> EngineResult:
        p = Params(params, {'channelId', 'favoriteGroup'})
        channel_ids, groups = p.string_list('channelId'), p.string_list('favoriteGroup')
        if not all(g in GROUPS and len(g) == 1 for g in groups):
            raise LunaError('ERROR_INVALID_PARAMETER', 'favoriteGroup must contain letters A-H')
        result = engine.set_favorites(channel_ids, groups, member, **_write_options(fault.action if fault else None))
        result.value = {'returnValue': True}
        return result
    return handler


def move_channel_favorite_priority(engine: TvEngine, params: dict, fault=None, **_) -> EngineResult:
    p = Params(params, {'favoriteGroupId', 'channelId', 'destinationChannelId', 'direction'})
    group_id = p.get('favoriteGroupId', int)
    if not 0 <= group_id < len(GROUPS):
        raise LunaError('ERROR_INVALID_PARAMETER', 'favoriteGroupId must be 0..7')
    channel_ids = p.string_list('channelId')
    if len(channel_ids) != 1:
        raise UnsupportedOperation('moving several channels at once is not simulated')
    destination = p.get('destinationChannelId', str)
    direction = p.get('direction', str)
    if direction not in ('up', 'down'):
        raise LunaError('ERROR_INVALID_PARAMETER', 'direction must be "up" or "down"')
    result = engine.move_favorite(GROUPS[group_id], channel_ids[0], destination, direction,
                                  **_write_options(fault.action if fault else None))
    result.value = {'returnValue': True}
    return result


def set_group_name(engine: TvEngine, params: dict, fault=None, **_) -> EngineResult:
    p = Params(params, {'channelMode', 'channelGroupId', 'channelGroupName'})
    if p.get('channelMode', str) != 'TUNER':
        raise UnsupportedOperation('only channelMode "TUNER" is simulated')
    group_id = p.get('channelGroupId', int)
    name = p.get('channelGroupName', str)
    if not FAVORITE_GROUP_ID_BASE <= group_id < FAVORITE_GROUP_ID_BASE + len(GROUPS):
        raise LunaError('GROUP_ERROR_NOT_FOUND', f'Unknown channel group {group_id}')
    if not 0 < len(name) <= 64:
        raise LunaError('ERROR_INVALID_PARAMETER', 'channelGroupName must have 1-64 characters')
    action = fault.action if fault else None
    result = engine.set_group_name(group_id, name, mutate=action.mutate if action else True)
    result.value = {'returnValue': True}
    return result


def get_favorite_group_list(engine: TvEngine, params: dict, **_) -> EngineResult:
    """Returns the DEFAULT names even after setGroupName (HARDWARE_CONFIRMED per tv_groups.py, 2026-10-11)."""
    Params(params, {'channelMode'})
    groups = engine.group_names()
    return EngineResult(value={'returnValue': True, 'favoriteGroupList': [
        {'channelGroupId': info['id'], 'channelGroupName': info['default']} for _, info in sorted(groups.items())]},
        effect='READ')


def _write_options(action) -> dict:
    if action is None:
        return {}
    return {'mutate': action.mutate, 'stale_reads': action.stale_reads, 'stale_ms': action.stale_ms}


HANDLERS = {
    'getChannelList': get_channel_list,
    'getChannel': get_channel,
    'changeChannelNumber': change_channel_number,
    'setChannelFavoriteGroup': _favorite(True),
    'releaseChannelFavoriteGroup': _favorite(False),
    'moveChannelFavoritePriority': move_channel_favorite_priority,
    'setGroupName': set_group_name,
    'getFavoriteGroupList': get_favorite_group_list,
}
