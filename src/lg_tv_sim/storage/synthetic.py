"""Deterministic generators for the committed synthetic fixture specs.

Names are public broadcaster names used as labels only; DVB triplets are
synthetic except where a historical case needs the documented structure
(WELT HD ``1053/21108/1``).  Run ``lg-tv-sim build-synthetic`` to regenerate.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SATELLITE_NAMES = [
    'Das Erste HD', 'ZDF HD', 'RTL HD', 'SAT.1 HD', 'ProSieben HD', 'VOX HD', 'kabel eins HD', 'RTLZWEI HD',
    'arte HD', '3sat HD', 'phoenix HD', 'ZDFneo HD', 'WELT HD', 'n-tv HD', 'tagesschau24 HD', 'ONE HD',
    'ZDFinfo HD', 'KiKA HD', 'SUPER RTL HD', 'Nickelodeon', 'ShopLC HD', 'QVC HD', 'HSE HD', 'DMAX HD',
    'TLC HD', 'SIXX HD', 'ProSieben MAXX', 'Tele 5 HD', 'Comedy Central', 'Disney Channel HD',
    'BR Fernsehen Süd HD', 'hr-fernsehen HD', 'MDR Sachsen HD', 'rbb Berlin HD', 'SWR BW HD', 'WDR HD Köln',
    'Radio Bremen TV', 'SR Fernsehen HD', 'NITRO HD', 'RTLup HD', 'kabel eins Doku HD', 'SAT.1 Gold HD',
    'Deluxe Music HD', 'Bibel TV HD', 'EWTN', 'Euronews', 'BBC World', 'CNN Int.', 'France 24', 'Al Jazeera',
    'TV5MONDE', 'Rai 1', 'ORF2E', 'SRF info', 'Bloomberg', 'CGTN', 'NHK World', 'Sky News', 'DW', 'TRT World',
]


def _sat(name, number, tsid, sid, *, phy=None, favorites=None, tags=None, **extra):
    channel = {'name': name, 'number': number, 'mode': 'Satellite', 'phy': phy if phy is not None else 10 + tsid % 40,
               'tsid': tsid, 'sid': sid, 'onid': 1}
    if favorites:
        channel['favorites'] = favorites
    if tags:
        channel['tags'] = tags
    channel.update(extra)
    return channel


def _cable(name, number, tsid, sid, phy, **extra):
    return {'name': name, 'number': number, 'mode': 'Cable', 'phy': phy, 'tsid': tsid, 'sid': sid, 'onid': 133,
            'satellite': ' ', **extra}


def mini() -> dict:
    channels = [
        _sat('Das Erste HD', 1, 1019, 10301, favorites={'A': 0}),
        _sat('ZDF HD', 2, 1011, 11110, favorites={'A': 1, 'B': 0}),
        _sat('RTL HD', 3, 1017, 61200, favorites={'A': 2}),
        _sat('SAT.1 HD', 4, 1107, 17500),
        _sat('ProSieben HD', 5, 1107, 17501, favorites={'A': 3, 'C': 0}),
        _sat('WELT HD', 13, 1053, 21108, phy=32, favorites={'A': 4}, tags=['deny_above_99', 'welt_hd']),
        _sat('ShopLC HD', 20, 1031, 4401, favorites={'B': 1}),
        _sat('QVC HD', 21, 1031, 4402, favorites={'A': 5}),
        _sat('HSE HD', 30, 1031, 4403),
        _sat('HSE HD', 31, 1093, 4403),   # same name, different DVB service
        _sat('ARD-alpha HD', 125, 1051, 28487, lcn=1, favorites={'A': 6}),
        _sat('HGTV HD', 1827, 1115, 5011, favorites={'A': 7}),
        _sat('HGTV HD', 26, 1115, 5011, favorites={'C': 1}),  # existing LCN copy of 1827 at 26 (same DVB)
        _sat('WELT HD', 403, 1053, 21108, phy=32, tags=['deny_above_99', 'welt_hd']),
        _sat('WELT HD', 1015, 1053, 21108, phy=32, tags=['deny_above_99', 'welt_hd']),
        _sat('NDR FS HH HD', 101, 1073, 28226),
        _sat('NDR 2', 101, 1093, 28426, radio=True),
        _cable('Das Erste HD', 1, 5, 62, 23),
        _cable('RTL HD', 13, 5, 1793, 24),
    ]
    return {'name': 'mini', 'version': 1, 'seed': 1,
            'description': 'Small synthetic list: WELT HD triple, shared number 101, swap pair 20/21, '
                           'existing Astra copy (HGTV HD 1827/26), same-name services, cable mode.',
            'channels': channels}


def favorites_47(seed: int = 47) -> dict:
    """~95 entries, 47 favorites in A in an order that needs moves, swaps and Astra copies to renumber 1..47."""
    rng = random.Random(seed)
    channels = []
    for number, name in enumerate(SATELLITE_NAMES, start=1):
        tsid, sid = 1001 + number % 23, 10000 + number * 7
        tags = None
        phy = None
        if name == 'WELT HD':
            number_fixed, tsid, sid, phy, tags = 13, 1053, 21108, 32, ['deny_above_99', 'welt_hd']
            assert number == number_fixed
        channels.append(_sat(name, number, tsid, sid, phy=phy, tags=tags))
    by_number = {c['number']: c for c in channels}
    # 43 favorites from the regular block 1..60, deliberately shuffled, never ShopLC HD (21).
    # Positions 1-5 form closed cycles (3->1, 1->2, 2->3 and 5<->4): only native swaps resolve them.
    cycles = [3, 1, 2, 5, 4]
    pool = [n for n in range(1, 61) if n != 21 and n not in cycles]
    rng.shuffle(pool)
    regular = cycles + pool[:38]
    extra = [
        _sat('ProSieben MAXX HD', 418, 1107, 17510, lcn=1, tags=['astra_copy']),
        _sat('ARD-alpha HD', 125, 1051, 28487, lcn=1, tags=['astra_copy']),
        _sat('NDR FS HH HD', 101, 1073, 28226, tags=['astra_copy']),
        _sat('HGTV HD', 1827, 1115, 5011, tags=['astra_copy']),
    ]
    order = [by_number[n] for n in regular[:10]] + [extra[0]] + [by_number[n] for n in regular[10:25]] + \
            [extra[1], extra[2]] + [by_number[n] for n in regular[25:]] + [extra[3]]
    for position, channel in enumerate(order):
        channel.setdefault('favorites', {})['A'] = position
    # B-H memberships, including channels that will be displaced or swapped.
    for group, count in (('B', 9), ('C', 5), ('D', 3), ('H', 4)):
        picks = rng.sample(range(1, 61), count)
        for position, n in enumerate(picks):
            by_number[n].setdefault('favorites', {})[group] = position
    by_number[21].setdefault('favorites', {})['B'] = 20   # ShopLC HD (displaced outsider) is in list B
    channels += extra
    channels += [
        _sat('WELT HD', 403, 1053, 21108, phy=32, tags=['deny_above_99', 'welt_hd']),
        _sat('WELT HD', 1015, 1053, 21108, phy=32, tags=['deny_above_99', 'welt_hd']),
        _sat('NDR 2', 101, 1093, 28426, radio=True),
        _sat('hr1', 101, 1093, 28419, radio=True),
        _sat('Bayern 1', 102, 1093, 28400, radio=True),
        _sat('Deutschlandfunk', 103, 1093, 28420, radio=True, favorites={'E': 0}),
        _sat('HSE HD', 160, 1093, 40003),       # same name as 23, different DVB service
        _sat('4mediathek', 4096, 1041, 51003),
    ]
    # Dense block 61..95: only 96..99 stay free, so renumbering needs native swap chains.
    for number in range(61, 96):
        channels.append(_sat(f'Regional {number:02d}', number, 1061 + number % 7, 30000 + number))
    for i, (name, number) in enumerate((('Das Erste HD', 1), ('ZDF HD', 2), ('RTL HD', 13), ('VOX HD', 30),
                                        ('Sky Sport News', 101))):
        channels.append(_cable(name, number, 5, 600 + i, 100 + i))
    return {'name': 'synthetic_favorites_47', 'version': 1, 'seed': seed,
            'description': '47 favorites in A in shuffled order, slots 1-95 occupied '
                           '(renumbering needs moves, swap chains and Astra copies), '
                           'WELT HD 13/403/1015, three entries on 101, B-H lists, same-name services, cable mode.',
            'channels': channels}


GENERATORS = {'mini': mini, 'synthetic_favorites_47': favorites_47}


def write_all(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, generator in GENERATORS.items():
        path = directory / f'{name}.json'
        path.write_text(json.dumps(generator(), indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        written.append(path)
    return written
