"""Deterministic generators for the committed synthetic fixture specs.

Names are public broadcaster names used as labels only; DVB triplets are
synthetic except where a historical case needs the documented structure
(WELT HD ``1053/21108/1``).  Run ``lg-tv-sim build-synthetic`` to regenerate.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from lg_tv_sim.storage.fixtures import RADIO_FLAG  # noqa: F401  (re-exported for tests)

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


# Invented names for synthetic_realistic (no real channel list is reproduced).
_PLACES = ['Nordlicht', 'Alpenblick', 'Rheinwelle', 'Elbtal', 'Sonnenhang', 'Bergland', 'Küstenland', 'Hansestern',
           'Weserbogen', 'Mainufer', 'Donaublau', 'Heideland', 'Seenplatte', 'Moselgold', 'Harzfeuer', 'Waldmeer',
           'Inselwind', 'Talblick', 'Morgenrot', 'Abendstern', 'Silberfluss', 'Lindenhof', 'Kranich', 'Bernstein',
           'Polarstern', 'Feldberg', 'Ostwind', 'Westpark', 'Südhang', 'Lichtung', 'Sternwarte', 'Leuchtturm']
_GENRES = ['TV', 'Info', 'Kids', 'Sport', 'Doku', 'Musik', 'Kino', 'Shop', 'News', 'Serie', 'Comedy', 'Kultur',
           'Reise', 'Natur', 'Retro', 'Wissen', 'Krimi', 'Family']
_RADIO = ['Welle', 'Radio', 'Funk', 'Klassik', 'Jazz', 'Pop', 'Rock', 'Schlager', 'Talk']
_ANTENNA_TV = ['Antenne Nordsee TV', 'Region Mitte Eins', 'Stadtkanal Hafen', 'Landesblick HD', 'Kanal Talaue',
               'Bürger-TV Lindenau', 'Heimatfenster', 'Turmfunk TV', 'Ostseewelle TV', 'Flachland Info',
               'Allgäu Panorama', 'Kanal Erzgebirge', 'Rheinebene TV', 'Hügelland HD', 'Studio Kranichfeld',
               'Börde Fernsehen', 'Marschland TV', 'Teutoburg Kanal', 'Vulkaneifel TV', 'Spreewald Info',
               'Kanal Neckartal', 'Wattenmeer TV', 'Hochrhein HD', 'Lausitz Live', 'Fichtelblick', 'Uckermark TV']
_ANTENNA_RADIO = ['Antenne Nordsee', 'Radio Talaue', 'Turmfunk', 'Welle Lindenau', 'Radio Marschland',
                  'Klassikwelle Mitte', 'Radio Spreewald', 'Hafenfunk', 'Radio Hochrhein', 'Lausitzwelle']


def realistic(seed: int = 1417) -> dict:
    """Shape of a real LG backup after a confirmed renumbering (counts, ID layouts, lists A and C, Astra
    copies, duplicate numbers, scrambled share), with invented names and DVB triplets, plus antenna services.

    Satellite: 603 TV / 106 radio; cable: 101 TV / 69 radio; antenna: 26 TV / 10 radio (invented, the
    terrestrial LG codes are a SIMULATOR_ASSUMPTION).
    """
    rng = random.Random(seed)
    names = iter(f'{place} {genre}{" HD" if (i + j) % 3 else ""}'
                 for i, place in enumerate(_PLACES) for j, genre in enumerate(_GENRES))
    transponders = [(1001 + t, 10 + t, 1 if t < 38 else 133) for t in range(51)]   # tsid, phy, onid
    sids = iter(range(10001, 20000))

    def sat_service(name=None, radio=False):
        tsid, phy, onid = transponders[rng.randrange(len(transponders))]
        return {'name': name or next(names), 'mode': 'Satellite', 'phy': phy, 'tsid': tsid, 'sid': next(sids),
                'onid': onid, 'frequency': 10744 + 39 * (phy - 10), 'radio': radio}

    def entry(service, number, *, lcn, minor=None, **extra):
        channel = {k: v for k, v in service.items() if k != 'radio' or v}
        channel.update(number=number, **({'lcn': 1} if lcn else {}), **extra)
        if minor is not None:
            channel['min'] = minor
        return channel

    channels = []
    high_numbers = iter(rng.sample(range(100, 1000), 900))
    # 55 Astra copies at 1..55 (A = 1..51), each with its LCN original at 100..999.
    for n in range(1, 56):
        service = sat_service()
        lcn_copy = n % 3 != 0                                  # 37 LCN copies, 18 without LCN (min = old slot)
        favorites = {'A': n - 1} if n <= 51 else None
        channels.append(entry(service, n, lcn=lcn_copy, minor=None if lcn_copy else rng.randrange(6, 22),
                              **({'favorites': favorites} if favorites else {})))
        channels.append(entry(service, next(high_numbers), lcn=True))
    # Further TV: LCN services at 100..999, non-LCN services at >= 1000 (mostly min 0), duplicate entries.
    for _ in range(340):
        channels.append(entry(sat_service(), next(high_numbers), lcn=True))
    high = iter(rng.sample(range(1000, 4097), 300))
    singles = []
    for _ in range(123):
        minor = 0 if rng.random() < 0.65 else rng.randrange(1, 916)
        singles.append(entry(sat_service(), next(high), lcn=False, minor=minor))
    channels += singles
    for source in rng.sample(singles, 30):                       # same service on a second number
        channels.append({**source, 'number': next(high)})
    # Radio: C = 70..77 (LCN), others at 100..629, 21 without LCN (min 0); numbers may coincide with TV.
    for position, n in enumerate(range(70, 78)):
        channels.append(entry(sat_service(f'{_PLACES[position]} {_RADIO[position]}', radio=True), n, lcn=True,
                              favorites={'C': position}))
    radio_numbers = rng.sample(range(100, 630), 98)
    for i, n in enumerate(radio_numbers):
        name = f'{_PLACES[(i + 8) % len(_PLACES)]} {_RADIO[(i + 8) // len(_PLACES) % len(_RADIO)]} {i + 1}'
        channels.append(entry(sat_service(name, radio=True), n, lcn=i >= 21))
    sat_tv = [c for c in channels if not c.get('radio')]
    for c in rng.sample([c for c in sat_tv if c['number'] > 99], 210):
        c['scrambled'] = 1
    # Cable: own number space 1..115, TV and radio share numbers; names partly as on satellite.
    cable_names = [c['name'] for c in sat_tv[:110:2]] + [next(names) for _ in range(46)]
    for i, n in enumerate(sorted(rng.sample(range(1, 116), 101))):
        phy = 1 + i % 17
        channels.append({'name': cable_names[i], 'mode': 'Cable', 'number': n, 'phy': phy, 'tsid': phy + 4,
                         'sid': next(sids), 'onid': 133 if i < 13 else 1, 'frequency': 114000 + 8000 * phy})
    for i, n in enumerate(sorted(rng.sample(range(2, 78), 69))):
        phy = 1 + i % 17
        channels.append({'name': f'{_PLACES[i % len(_PLACES)]} {_RADIO[i % len(_RADIO)]} Kabel', 'mode': 'Cable',
                         'number': n, 'phy': phy, 'tsid': phy + 4, 'sid': next(sids), 'onid': 1,
                         'frequency': 114000 + 8000 * phy, 'radio': True})
    # Antenna (DVB-T2): six multiplexes on UHF 21..48, TV 1..26, radio 27..36.
    muxes = [(21 + 5 * m, 12289 + m) for m in range(6)]
    for i, name in enumerate(_ANTENNA_TV + _ANTENNA_RADIO):
        phy, tsid = muxes[i % len(muxes)]
        radio = i >= len(_ANTENNA_TV)
        channel = {'name': name, 'mode': 'Terrestrial', 'number': i + 1, 'phy': phy, 'tsid': tsid,
                   'sid': 700 + i, 'onid': 8468, 'satellite': ' ', 'frequency': 474000 + 8000 * (phy - 21)}
        if radio:
            channel['radio'] = True
        elif i % 3 == 2:
            channel['scrambled'] = 1
        channels.append(channel)
    return {'name': 'synthetic_realistic', 'version': 1, 'seed': seed,
            'description': 'Structure of a real LG backup after renumbering (603/106 satellite TV/radio, '
                           '101/69 cable, A = 1..51 Astra copies, C = radio 70..77, real ID layouts incl. '
                           'radio flag and non-LCN min values) with invented names, plus 36 antenna services.',
            'channels': channels}


def _ip(name, number, **extra):
    return {'name': name, 'number': number, 'mode': 'IP', **extra}


def mixed_modes() -> dict:
    """Small list with every reception mode (editor v0.6.4): satellite, cable (number 1 also on satellite),
    antenna, LG Channels; list A mixes tuner and IP members, list D is a pure IP list from 251 (E5, E8)."""
    channels = [_sat(name, number, 1001 + number, 10100 + number,
                     favorites={'A': number - 1} if number <= 4 else None)
                for number, name in enumerate(SATELLITE_NAMES[:12], start=1)]
    channels += [
        _cable('Stadtkanal Hafen', 1, 5, 601, 1),                 # same number as satellite 1 (own number space)
        _cable('Kabel Regional', 20, 5, 602, 2),
        _cable('Kabel Klassik', 21, 5, 603, 3, radio=True),
        {'name': 'Antenne Nordsee TV', 'mode': 'Terrestrial', 'number': 1, 'phy': 21, 'tsid': 12289, 'sid': 700,
         'onid': 8468, 'satellite': ' '},
        {'name': 'Radio Talaue', 'mode': 'Terrestrial', 'number': 2, 'phy': 21, 'tsid': 12289, 'sid': 701,
         'onid': 8468, 'satellite': ' ', 'radio': True},
        _ip('LG 1', 100, favorites={'D': 0}),
        _ip('LG 1: Film', 101, favorites={'D': 1}),
        _ip('Stream Kino', 205, favorites={'A': 10}),
        _ip('Stream Doku', 206, favorites={'A': 11}),
        _ip('Stream News', 210, favorites={'D': 2}),
    ]
    return {'name': 'mixed_modes', 'version': 1, 'seed': 0,
            'description': 'Every reception mode: 12 satellite, 3 cable (cable 1 next to satellite 1), 2 antenna, '
                           '5 LG Channels; A = 4 satellite + 2 IP (IP block from 251), D = 3 IP (251-253).',
            'channels': channels}


GENERATORS = {'mini': mini, 'synthetic_favorites_47': favorites_47, 'synthetic_realistic': realistic,
              'mixed_modes': mixed_modes}


def write_all(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, generator in GENERATORS.items():
        path = directory / f'{name}.json'
        path.write_text(json.dumps(generator(), indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        written.append(path)
    return written
