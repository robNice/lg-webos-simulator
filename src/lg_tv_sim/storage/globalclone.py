"""Convert an LG GlobalClone USB export (``GlobalClone00001.TLL``) into a fixture spec for ``build_from_spec``.

Two formats: JSON inside ``<legacybroadcast>`` (clone version 200, webOS 5 and later) and the older XML with
``<ITEM>`` entries (clone version 100).  The export is the legacybroadcast view, not the iepg database the
editor reads, so only the channel content is taken over (name, number, reception mode, DVB triplet, physical
channel, frequency, satellite, service type, scrambled/invisible).  Cross-checked against the real backup:
frequency units (satellite MHz, cable/antenna kHz), radio numbers carry 0x4000 like ``maj_no``, satellite names
match ``sat_name``.  The export's Invisible flag becomes ``invisible_flag`` (same meaning assumed: hidden
entries, typically also skipped).  Not in the export (always 0/false there): ``min_no`` and the LCN flag; the builder rules
apply, as does the ``dvc_chan_id`` layout for satellites other than Astra 19.2E (SIMULATOR_ASSUMPTION, G10).

Skipped: deleted entries, analog services, IP services, and entries whose derived channel ID repeats.
Unknown or unevidenced source codes fail closed; ``mode_map`` assigns them explicitly.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from lg_tv_sim.storage.fixtures import MODE_CODES, FixtureError, channel_id_for

RADIO_FLAG = 0x4000
RADIO_SERVICE_TYPES = {2, 10}   # as in the real backup (svc_type 2 and 10 = '... Digital Radio')

JSON_MODES = {'SATELLITE DIGITAL': 'Satellite', 'CABLE DIGITAL': 'Cable', 'ANTENNA DIGITAL': 'Terrestrial'}
JSON_ANALOG = {'ANTENNA ANALOG', 'CABLE ANALOG'}
# Old XML: 7 = satellite (consistent in every export and in ChanSort), 1 = antenna (ONID 0x2028, DVB-T Austria).
# ChanSort reads 2 as cable, while exports show 3 in cable surroundings: neither is evidenced, so mode_map.
XML_MODES = {'7': 'Satellite', '1': 'Terrestrial'}

# LG's built-in satellite names by satelliteId (position in tenths of a degree, west = 3600 - position), as
# listed in the satelliteList of webOS 5 and webOS 22 GlobalClone exports.
SATELLITE_NAMES = {
    '0050': 'SES ASTRA 5.0E', '0070': 'EUTELSAT 7 A/B 7.0E', '0090': 'EUTELSAT 9A 9.0E', '0100': 'EUTELSAT 10A 10.0E',
    '0130': 'EUTELSAT HOTBIRD 13.0E', '0160': 'EUTELSAT 16A 16.0E', '0192': 'ASTRA 19.2E',
    '0200': 'ARABSAT 5C 20.0E', '0215': 'EUTELSAT 21B 21.5E', '0235': 'ASTRA 23.5E', '0260': 'BADR 26.0E',
    '0282': 'ASTRA 28.2E', '0305': 'ARABSAT 5A 30.5E', '0315': 'ASTRA 5B 31.5E', '0330': 'EUTELSAT 33B 33.0E',
    '0360': 'EUTELSAT 36 B/C 36.0E', '0390': 'HELLAS SAT2 39.0E', '0400': 'EXPRESS AM7 40.0E',
    '0420': 'TURKSAT 42.0E', '0560': 'EXPRESS AT1 56.0E', '0570': 'NSS12 57.0E', '0585': 'KAZSAT 3 58.5E',
    '0600': 'INTELSAT904 60.0E', '0685': 'INTELSAT20 68.5E', '0721': 'INTELSAT22 72.1E', '0750': 'ABS2A 75.0E',
    '0800': 'EXPRESS 80.0E', '0852': 'INTELSAT15 85.2E', '0900': 'YAMAL 300K 90.0E', '0950': 'NSS 6 95.0E',
    '0965': 'EXPRESS AM33 96.5E', '1055': 'ASIASAT3S 105.5E', '1082': 'SES 7 & SES 9 108.2E',
    '1318': 'VINASAT2 131.8E', '1400': 'EXPRESS AM5/AT2 140.0E', '1600': 'OPTUS D1 160.0E',
    '3100': 'INTELSAT1R 50.0W', '3255': 'INTELSAT903 34.5W', '3300': 'HISPASAT 1 D/E 30.0W',
    '3520': 'EUTELSAT 8A 8.0W', '3527': 'EUTELSAT 7A/8C 7.3W', '3530': 'NILESAT 7.0W', '3550': 'EUTELSAT 5A 5.0W',
    '3560': 'AMOS 4.0W', '3592': 'THOR 0.8W',
}


@dataclass
class Conversion:
    meta: dict
    channels: list[dict]
    report: dict = field(default_factory=dict)


def parse_globalclone(path: Path, mode_map: dict[str, str] | None = None, satellite: str | None = None,
                      ignore_invisible: bool = False) -> Conversion:
    """Read an export without modifying it.  ``mode_map``: source code -> reception mode for codes without
    evidence; ``satellite``: satellite name for every satellite entry (exports with a wrong satellite slot);
    ``ignore_invisible``: drop the export's Invisible flag (e.g. an export in which every entry is hidden)."""
    mode_map = dict(mode_map or {})
    for code, mode in mode_map.items():
        if mode not in MODE_CODES or mode == 'IP':
            raise FixtureError(f'mode_map {code}={mode!r}: mode must be Satellite, Cable or Terrestrial')
    text = Path(path).read_bytes().decode('utf-8', errors='replace')
    meta = {'model': _tag(text, 'ModelName'), 'country': _tag(text, 'BroadcastCountrySetting'),
            'clone_version': _tag(text, 'MajorVersion')}
    if '<legacybroadcast>' in text:
        meta['format'] = 'json'
        raw = _json_channels(text, mode_map)
    elif re.search(r'<DTV>.*?<ITEM>', text, re.S):
        meta['format'] = 'xml'
        raw = _xml_channels(text, mode_map)
    else:
        raise FixtureError('no channel list found (neither <legacybroadcast> JSON nor <DTV><ITEM> entries)')
    channels, skipped, seen, hidden = [], Counter(), set(), Counter()
    for reason, spec in raw:
        if reason:
            skipped[reason] += 1
            continue
        if satellite and spec['mode'] == 'Satellite':
            spec['satellite'] = satellite
        if spec.get('invisible'):
            hidden['invisible_ignored' if ignore_invisible else 'invisible'] += 1
            if ignore_invisible:
                del spec['invisible']
        key = channel_id_for(spec)
        if key in seen:
            skipped['duplicate_id'] += 1
            continue
        seen.add(key)
        channels.append(spec)
    report = {'converted': len(channels), 'by_mode': dict(Counter(c['mode'] for c in channels)),
              'satellites': dict(Counter(c['satellite'] for c in channels if c['mode'] == 'Satellite')),
              'skipped': dict(skipped), **hidden}
    if mode_map:
        report['mode_map'] = mode_map
    if satellite:
        report['satellite_override'] = satellite
    if not channels:
        raise FixtureError('the export contains no convertible channel')
    return Conversion(meta, channels, report)


def _tag(text: str, name: str) -> str | None:
    match = re.search(rf'<{name}[^>]*>([^<]*)</{name}>', text)
    return match.group(1).strip() if match else None


def _spec(name, mode, major, phy, tsid, sid, onid, frequency, service_type, satellite, scrambled, invisible):
    radio = service_type in RADIO_SERVICE_TYPES
    number = major - RADIO_FLAG if major >= RADIO_FLAG else major
    spec = {'name': name, 'mode': mode, 'number': number, 'phy': phy, 'tsid': tsid, 'sid': sid, 'onid': onid,
            'frequency': frequency, 'satellite': satellite if mode == 'Satellite' else ' ', 'svc_type': service_type}
    if radio:
        spec['radio'] = True
    if scrambled:
        spec['scrambled'] = 1
    if invisible:
        spec['invisible'] = 1
    return spec


def _satellite_name(satellite_id: str | None, names: dict[str, str]) -> str:
    if not satellite_id:
        raise FixtureError('satellite entry without satelliteId')
    return names.get(satellite_id) or SATELLITE_NAMES.get(satellite_id) or f'SAT {satellite_id}'


def _json_channels(text: str, mode_map: dict[str, str]):
    start = text.index('<legacybroadcast>') + len('<legacybroadcast>')
    try:
        data, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise FixtureError(f'JSON in <legacybroadcast> is incomplete or damaged ({exc.msg} at {exc.pos}); '
                           'some firmware writes a binary block instead') from exc
    if not isinstance(data, dict) or not isinstance(data.get('channelList'), list):
        raise FixtureError('no channel list in <legacybroadcast>')
    names = {s.get('satelliteId'): s.get('satelliteName', '').replace('&amp;', '&')
             for s in data.get('satelliteList', []) if isinstance(s, dict)}
    for c in data['channelList']:
        source = str(c.get('sourceIndex'))
        mode = JSON_MODES.get(source) or mode_map.get(source)
        if c.get('deleted'):
            yield 'deleted', None
        elif c.get('ipChannel'):
            yield 'ip', None
        elif source in JSON_ANALOG:
            yield 'analog', None
        elif not mode:
            raise FixtureError(f'unknown sourceIndex {source!r}; assign it with mode_map if its meaning is known')
        else:
            satellite = _satellite_name(c.get('satelliteId'), names) if mode == 'Satellite' else None
            yield None, _spec(str(c.get('channelName', '')).strip(), mode, int(c['majorNumber']),
                              int(c.get('physicalNumber', 0)), int(c['TSID']), int(c['SVCID']), int(c['ONID']),
                              int(c.get('frequency', 0)), int(c.get('serviceType', 1)), satellite,
                              c.get('scrambled'), c.get('Invisible'))


def _xml_positions(text: str) -> dict[str, str]:
    """usSatelliteHandle -> LG satelliteId from the export's satellite database (index order)."""
    block = re.search(r'<SatRecordInfo>(.*?)</SatRecordInfo>', text, re.S)
    result = {}
    for index, body in re.findall(r'<idx(\d+)>(.*?)</idx\1>', block.group(1) if block else '', re.S):
        value = {k: int(_tag(body, k) or 0) for k in ('Angle', 'AnglePrec', 'DirEastWest')}
        tenths = value['Angle'] * 10 + value['AnglePrec']
        result[index] = f'{tenths if value["DirEastWest"] == 1 else 3600 - tenths:04d}'
    return result


def _xml_channels(text: str, mode_map: dict[str, str]):
    positions = _xml_positions(text)
    atv = re.search(r'<ATV>(.*?)</ATV>', text, re.S)
    for _ in re.findall(r'<ITEM>', atv.group(1) if atv else ''):
        yield 'analog', None
    dtv = re.search(r'<DTV>(.*?)</DTV>', text, re.S)
    for item in re.findall(r'<ITEM>(.*?)</ITEM>', dtv.group(1) if dtv else '', re.S):
        f = dict(re.findall(r'<(\w+)>([^<]*)</\1>', item))
        source = f.get('sourceIndex', '')
        mode = XML_MODES.get(source) or mode_map.get(source)
        if f.get('isDeleted') == '1':
            yield 'deleted', None
            continue
        if not mode:
            raise FixtureError(f'sourceIndex {source} has no evidenced mode in the old XML format; '
                               f'pass it via mode_map (e.g. {source}=Cable) after checking the export')
        satellite = None
        if mode == 'Satellite':
            satellite = _satellite_name(positions.get(f.get('usSatelliteHandle', '')), {})
        name = f.get('vchName', '').strip() or _hex_name(f.get('hexVchName', ''))
        yield None, _spec(name, mode, int(f['prNum']), int(f.get('physicalNum', 0)), int(f['transport_id']),
                          int(f['service_id']), int(f['original_network_id']), int(f.get('frequency', 0)),
                          int(f.get('serviceType', 1)), satellite, False, f.get('isInvisable') == '1')


def _hex_name(value: str) -> str:
    """DVB name bytes in hex; a leading byte below 0x20 selects the character table (dropped here)."""
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        return ''
    if raw[:1] and raw[0] < 0x20:
        raw = raw[1:]
    return raw.split(b'\0')[0].decode('latin-1').strip()
