"""Fixtures: synthetic JSON specs (committed) and imported private SQLite backups (never committed).

A fixture is materialised into a run directory via the SQLite backup API; the
fixture source itself is never modified (``reset`` re-materialises it).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from lg_tv_sim.domain.models import (
    GROUPS,
    IP_FIRST_INDEX,
    IP_MODE,
    IP_NOT_MEMBER_INDEX,
    NOT_MEMBER_INDEX,
    user_fav_json,
)
from lg_tv_sim.storage import database

SCHEMA_FILE = Path(__file__).resolve().parent / 'schema' / 'lg_webos22.sql'
NAME_PATTERN = re.compile(r'[A-Za-z0-9_.-]{1,64}')
RADIO_FLAG = 0x4000   # maj_no of radio services = number + 0x4000 (observed in a real backup, sat and cable)

# Per reception mode: chan_src_type, chan_mode_id, chan_type_id (TV, radio). Satellite and cable observed in a
# real backup; the terrestrial codes are a SIMULATOR_ASSUMPTION (no antenna backup available).
MODE_CODES = {'Satellite': (7, 2, (6, 7)), 'Cable': (3, 1, (4, 5)), 'Terrestrial': (2, 0, (2, 3)),
              IP_MODE: (11, 7, (20, 20))}   # IP: src 11, mode id 7, type 20 'IP Digital TV' (real backup, E3)

# Columns blanked before a real backup may be committed: in ``ip`` (LG Channels streaming services) ``call_num``
# holds contact e-mails of content-provider staff and ``ip_chan_service_url`` stream URLs (some with keys).
# Names, numbers, IDs, favorites and logo paths stay.
PUBLIC_BLANKED_COLUMNS = {'ip': ('call_num', 'ip_chan_service_url')}
PERSONAL_DATA = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https?://|[?&](?:key|token|did)=[^&\s\[]',
                           re.I)

DEFAULT_GROUP_ROWS = [  # channel_group_tuner layout observed in a real backup (names neutralised)
    (0, 'All', 0, 0, 1), (1, 'DTV', 0, 2, 0), (2, 'Radio', 0, 2, 0), (5, 'FTA', 0, 5, 0), (6, 'PAID', 0, 5, 0),
    (7, 'HD', 0, 5, 0), (100, 'lgChannels', 0, 1, 0), (300, 'Public Value', 0, 2, 0),
]


class FixtureError(ValueError):
    pass


@dataclass
class Fixture:
    name: str
    kind: str                      # 'synthetic' | 'sqlite'
    source: Path
    description: str = ''
    tags: dict[str, list[str]] = field(default_factory=dict)   # channel_id -> simulator tags

    def materialize(self, destination: Path) -> None:
        if self.kind == 'synthetic':
            spec = json.loads(self.source.read_text(encoding='utf-8'))
            build_from_spec(spec, destination)
        else:
            database.backup_file(self.source, destination)

    def content_hash(self, scratch: Path) -> str:
        scratch.parent.mkdir(parents=True, exist_ok=True)
        self.materialize(scratch)
        try:
            conn = database.connect(scratch, readonly=True)
            try:
                return database.content_hash(conn)
            finally:
                conn.close()
        finally:
            scratch.unlink(missing_ok=True)


# ---------------------------------------------------------------- synthetic specs

def _default_value(declared_type: str):
    return '' if 'text' in declared_type.lower() else 0


def maj_min(c: dict) -> tuple[int, int]:
    """maj = number (+0x4000 for radio). min: given in the spec, else the number for satellite TV and LCN
    radio, else 0 (as in the real backup; non-LCN satellite entries there carry other values).
    LG Channels: maj = number, min = 65535 (E4)."""
    if c.get('mode') == IP_MODE:
        return int(c['number']), 65535
    n, radio = int(c['number']), bool(c.get('radio'))
    satellite = c.get('mode', 'Satellite') == 'Satellite'
    default_minor = n if satellite and (not radio or c.get('lcn')) else 0
    return n + (RADIO_FLAG if radio else 0), int(c.get('min', default_minor))


def channel_id_for(c: dict) -> str:
    """``<src>_<phy>_<maj>_<min>_<tsid>_<sid>_<onid>`` as in real backups (satellite and cable)."""
    if c.get('id'):
        return str(c['id'])
    mode = c.get('mode', 'Satellite')
    if mode not in MODE_CODES:
        raise FixtureError(f'unknown reception mode {mode!r}')
    major, minor = maj_min(c)
    src = c.get('src', MODE_CODES[mode][0])
    if mode == IP_MODE:                                   # 11_3_<number>_65535_0_0_0 (E4)
        return f'{src}_{c.get("phy", 3)}_{major}_{minor}_0_0_0'
    return f'{src}_{c.get("phy", 1)}_{major}_{minor}_{c["tsid"]}_{c["sid"]}_{c.get("onid", 1)}'


def build_from_spec(spec: dict, destination: Path) -> None:
    """Create an LG-schema SQLite database from a synthetic JSON fixture spec."""
    channels = spec.get('channels')
    if not isinstance(channels, list) or not channels:
        raise FixtureError('fixture spec needs a non-empty "channels" list')
    destination = Path(destination)
    destination.unlink(missing_ok=True)
    conn = sqlite3.connect(str(destination))
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding='utf-8'))
        columns = {t: [(r[1], r[2]) for r in conn.execute(f'PRAGMA table_info({t})')]
                   for t in ('tuner_on', 'favorite_idx')}
        positions = {g: _positions(channels, g) for g in GROUPS}
        seen = set()
        for c in channels:
            row = _channel_row(c, columns['tuner_on'], positions)
            key = (row['dvc_chan_id'], row['mso_prdt_itm_code'])
            if key in seen:
                raise FixtureError(f'duplicate channel id {key[0]!r}')
            seen.add(key)
            names = list(row)
            sql = f'INSERT INTO {{}} ({", ".join(names)}) VALUES ({", ".join("?" * len(names))})'
            for table in (('ip',) if c.get('mode') == IP_MODE else ('tuner_on', 'tuner_off')):
                conn.execute(sql.format(table), [row[n] for n in names])
            groups = [g for g in GROUPS if row[f'fav_chan_gr_{g.lower()}'] == '1']
            if groups:
                fav = {name: row[name] for name, _ in columns['favorite_idx'] if name in row}
                fav_names = list(fav)
                conn.execute(f'INSERT INTO favorite_idx ({", ".join(fav_names)}) VALUES '
                             f'({", ".join("?" * len(fav_names))})', [fav[n] for n in fav_names])
        names = spec.get('group_names', {})
        for gid, name, fav, gtype, current in DEFAULT_GROUP_ROWS:
            conn.execute('INSERT INTO channel_group_tuner VALUES (?,?,?,?,?,?,?)', (gid, name, name, fav, 0, gtype, current))
        for i, g in enumerate(GROUPS):
            conn.execute('INSERT INTO channel_group_tuner VALUES (?,?,?,?,?,?,?)',
                         (200 + i, g, names.get(g, g), 1, 1 if g in names else 0, 4, 0))
        conn.commit()
    finally:
        conn.close()


def _positions(channels: list[dict], group: str) -> dict[str, int]:
    """Tuner members 0.., LG Channels members from 251 (E5), each block in spec order."""
    members = [(int(c['favorites'][group]), i) for i, c in enumerate(channels) if group in c.get('favorites', {})]
    result, tuner, ip = {}, 0, IP_FIRST_INDEX
    for _, i in sorted(members):
        if channels[i].get('mode') == IP_MODE:
            result[channel_id_for(channels[i])], ip = ip, ip + 1
        else:
            result[channel_id_for(channels[i])], tuner = tuner, tuner + 1
    return result


def _channel_row(c: dict, columns: list[tuple[str, str]], positions: dict[str, dict[str, int]]) -> dict:
    row = {name: _default_value(declared) for name, declared in columns}
    mode = c.get('mode', 'Satellite')
    n = int(c['number'])
    cid = channel_id_for(c)
    radio = bool(c.get('radio', False))
    phy = int(c.get('phy', 1))
    src_type, mode_id, type_ids = MODE_CODES[mode]
    type_id = type_ids[radio]
    major, minor = maj_min(c)
    code = 'SIM-' + hashlib.sha1(cid.encode(), usedforsecurity=False).hexdigest()[:16].upper()
    groups = [g for g in GROUPS if cid in positions[g]]
    kind = 'Radio' if radio else 'TV'
    row.update({
        'dvc_chan_id': cid, 'mso_prdt_itm_code': str(c.get('mso', '')), 'chan_no': str(n), 'chan_no_int': n,
        'maj_no': major, 'min_no': minor, 'chan_code': code,
        'chan_std_name': c['name'], 'phy_chan_no': phy, 'chan_src_type': src_type,
        'chan_type_name': f'{mode} Digital {kind}', 'chan_type_id': type_id,
        'chan_mode_name': mode, 'chan_mode_id': mode_id,
        'signal_chan_id': f'{c.get("tsid", 0)}_{c.get("sid", 0)}_{c.get("onid", 1)}', 'online_chan_id': f'{cid}_{code}',
        'user_fav_chan_gr': user_fav_json(groups), 'descrambled_flag': 1, 'satelliteLcn_flag': int(c.get('lcn', 0)),
        'scrambled_flag': int(c.get('scrambled', 0)), 'valid_svc_flag': 1, 'svc_type': 2 if radio else 25,
        'svc_display_flag': 1, 'dvb_chan_nw_id': int(c.get('onid', 1)), 'dvb_chan_transf_strm_id': int(c.get('tsid', 0)),
        'dvb_chan_svc_id': int(c.get('sid', 0)), 'hdtv_flag': int(not radio), 'invisible_flag': int(c.get('invisible', 0)),
        'dtv_flag': 1, 'radio_flag': int(radio), 'tv_flag': int(not radio), 'primary_channel_flag': 1,
        'sat_name': c.get('satellite', 'ASTRA 19.2E' if mode == 'Satellite' else ' '),
        'frequency': int(c.get('frequency', 11000 + phy)), 'chan_gr_list': '[0,1,200]', 'ca_sysid_list': '{}',
        'channelMajMinNo': f'{type_id:02d}-{n:05d}-000-{phy:03d}', 'last_chg_date': '[]', 'sortIndex': '0000',
        'reserved_3': 'com.webos.service.legacybroadcast', 'reserved_4': '0',
    })
    if mode == IP_MODE:   # LG Channels as in the real ip table (E3, E4); no DVB triplet, no tuner data
        row.update({'signal_chan_id': cid, 'sat_name': 'UNKNOWN', 'dvb_chan_nw_id': 0, 'dvb_chan_transf_strm_id': 0,
                    'dvb_chan_svc_id': 0, 'svc_type': 0, 'hdtv_flag': 0, 'dtv_flag': 0, 'tv_flag': 0,
                    'frequency': 0, 'chan_gr_list': '[0,100]', 'channelMajMinNo': f'{n:05d}-{minor}',
                    'reserved_3': 'com.webos.service.dmost'})
    not_member = IP_NOT_MEMBER_INDEX if mode == IP_MODE else NOT_MEMBER_INDEX
    for g in GROUPS:
        member = cid in positions[g]
        row[f'fav_chan_gr_{g.lower()}'] = '1' if member else '0'
        row[f'favoriteIdx{g}'] = positions[g][cid] if member else not_member
    return row


def spec_tags(spec: dict) -> dict[str, list[str]]:
    return {channel_id_for(c): list(c['tags']) for c in spec['channels'] if c.get('tags')}


# ---------------------------------------------------------------- catalog

class FixtureCatalog:
    """synthetic JSON specs, recorded (sanitised, committed) and private (never committed) SQLite backups."""

    def __init__(self, synthetic_dir: Path, private_dir: Path, recorded_dir: Path | None = None):
        self.synthetic_dir, self.private_dir = Path(synthetic_dir), Path(private_dir)
        self.recorded_dir = Path(recorded_dir) if recorded_dir is not None else None

    def _sqlite_dirs(self) -> list[Path]:
        return [d for d in (self.recorded_dir, self.private_dir) if d is not None]

    def names(self) -> list[str]:
        names = {p.stem for p in self.synthetic_dir.glob('*.json')}
        for directory in self._sqlite_dirs():
            names |= {p.stem for p in directory.glob('*.sqlite')}
        return sorted(names)

    def get(self, name: str) -> Fixture:
        if not NAME_PATTERN.fullmatch(name or ''):
            raise FixtureError(f'invalid fixture name {name!r}')
        spec_path = self.synthetic_dir / f'{name}.json'
        if spec_path.is_file():
            spec = json.loads(spec_path.read_text(encoding='utf-8'))
            return Fixture(name, 'synthetic', spec_path, spec.get('description', ''), spec_tags(spec))
        for directory in self._sqlite_dirs():
            db_path = directory / f'{name}.sqlite'
            if db_path.is_file():
                meta_path = db_path.with_suffix('.json')
                meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.is_file() else {}
                return Fixture(name, 'sqlite', db_path, meta.get('description', 'imported SQLite backup'),
                               meta.get('tags', {}))
        raise FixtureError(f'unknown fixture {name!r}; available: {", ".join(self.names()) or "none"}')

    def import_sqlite(self, source: Path, name: str, public: bool = False) -> dict:
        """Import a backup read-only; refuse to overwrite any existing fixture.

        Private (default): copied as is into the git-ignored private directory.  Public: copied into the
        recorded directory (committed) with ``PUBLIC_CLEARED_TABLES`` emptied, and refused if any e-mail
        address, URL or key parameter remains anywhere in the database.
        """
        if not NAME_PATTERN.fullmatch(name or ''):
            raise FixtureError(f'invalid fixture name {name!r}')
        if name in self.names():
            raise FixtureError(f'fixture {name!r} already exists; choose another name')
        report = inspect_sqlite(source)
        if report['problems']:
            raise FixtureError('fixture rejected: ' + '; '.join(report['problems']))
        directory = self.recorded_dir if public else self.private_dir
        if directory is None:
            raise FixtureError('no directory configured for recorded fixtures')
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f'{name}.sqlite'
        database.backup_file(source, target)
        meta = {'name': name, 'source_sha256': report['sha256'],
                'imported': datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds'), 'tags': {}}
        if public:
            try:
                blanked = _blank_columns(target, PUBLIC_BLANKED_COLUMNS)
                findings = personal_data_findings(target)
                if findings:
                    raise FixtureError('possible personal data remains, not importing publicly: '
                                       + '; '.join(findings[:5]))
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            meta.update(source=Path(source).name, blanked_columns=blanked,
                        description='recorded real TV backup (sanitised: ' + ', '.join(blanked) + ' blanked)')
        else:
            meta.update(source=str(Path(source).resolve()),
                        description='imported SQLite backup (private, never commit)')
        conn = database.connect(target, readonly=True)
        try:
            meta['content_hash'] = database.content_hash(conn)
        finally:
            conn.close()
        target.with_suffix('.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
        return meta


# Derived recorded fixture: LG Channels services in a list that is empty in the recording, stored like on the
# TV (E5, E6): ip flag/index from 251, user_fav_chan_gr, and a favorite_idx row with the same index.
IP_FAVORITES = {'base': 'real_20261011_1417', 'group': 'B', 'count': 15}


def derive_ip_favorites(base: Path, target: Path, group: str, count: int) -> list[str]:
    """Copy ``base`` to ``target`` and put ``count`` IP services, spread evenly over the programme numbers and
    in programme order, into the empty favorite list ``group``.  Returns the chosen channel IDs."""
    if group not in GROUPS:
        raise FixtureError(f'unknown favorite group {group!r}')
    Path(target).unlink(missing_ok=True)
    database.backup_file(Path(base), Path(target))
    conn = sqlite3.connect(str(target))
    try:
        g = group.lower()
        taken = conn.execute(f"SELECT (SELECT count(*) FROM ip WHERE fav_chan_gr_{g}='1') + "
                             f"(SELECT count(*) FROM tuner_on WHERE fav_chan_gr_{g}='1')").fetchone()[0]
        if taken:
            raise FixtureError(f'favorite list {group} is not empty in {base}')
        ids = [r[0] for r in conn.execute('SELECT dvc_chan_id FROM ip ORDER BY chan_no_int, dvc_chan_id')]
        if len(ids) < count:
            raise FixtureError(f'only {len(ids)} IP services available')
        step = len(ids) / count
        chosen = [ids[int(i * step)] for i in range(count)]
        for position, channel_id in enumerate(chosen, start=IP_FIRST_INDEX):
            conn.execute(f"UPDATE ip SET fav_chan_gr_{g}='1', favoriteIdx{group}=?, user_fav_chan_gr=? "
                         'WHERE dvc_chan_id=?', (position, user_fav_json([group]), channel_id))
            columns = ['dvc_chan_id', 'user_fav_chan_gr'] + [f'fav_chan_gr_{x.lower()}' for x in GROUPS] + \
                      [f'favoriteIdx{x}' for x in GROUPS]
            values = [channel_id, user_fav_json([group])] + [('1' if x == group else '0') for x in GROUPS] + \
                     [(position if x == group else NOT_MEMBER_INDEX) for x in GROUPS]
            conn.execute(f'INSERT INTO favorite_idx ({", ".join(columns)}) VALUES ({", ".join("?" * len(columns))})',
                         values)
        conn.commit()
        conn.execute('VACUUM')
    finally:
        conn.close()
    return chosen


def write_ip_favorites(recorded_dir: Path) -> Path | None:
    """(Re)build the derived IP-favorites fixture next to its base; None if the base is missing."""
    base = Path(recorded_dir) / f'{IP_FAVORITES["base"]}.sqlite'
    if not base.is_file():
        return None
    name = f'{IP_FAVORITES["base"]}_ipfav'
    target = base.with_name(f'{name}.sqlite')
    chosen = derive_ip_favorites(base, target, IP_FAVORITES['group'], IP_FAVORITES['count'])
    meta = {'name': name, 'derived_from': IP_FAVORITES['base'], 'tags': {},
            'description': f'{IP_FAVORITES["base"]} plus {len(chosen)} LG Channels services in the empty list '
                           f'{IP_FAVORITES["group"]} (indices from 251 and favorite_idx rows as on the TV, E5/E6)',
            'ip_favorites': {IP_FAVORITES['group']: chosen}}
    target.with_suffix('.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    return target


def _blank_columns(path: Path, columns: dict[str, tuple[str, ...]]) -> list[str]:
    conn = sqlite3.connect(str(path))
    try:
        blanked = []
        for table, names in columns.items():
            available = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            for column in (c for c in names if c in available):
                conn.execute(f'UPDATE "{table}" SET "{column}" = \'\'')
                blanked.append(f'{table}.{column}')
        conn.commit()
        conn.execute('VACUUM')        # no old values left in free pages
    finally:
        conn.close()
    return blanked


def personal_data_findings(path: Path) -> list[str]:
    """Text cells that look like e-mail addresses, URLs or key/token parameters (``table.column: value``)."""
    conn = database.connect(Path(path), readonly=True)
    findings = []
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                for column, value in zip(columns, row, strict=True):
                    if isinstance(value, str) and PERSONAL_DATA.search(value):
                        findings.append(f'{table}.{column}: {value[:60]}')
    finally:
        conn.close()
    return findings


def inspect_sqlite(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FixtureError(f'file not found: {path}')
    with open(path, 'rb') as handle:
        if handle.read(16) != b'SQLite format 3\x00':
            raise FixtureError(f'not an SQLite database: {path}')
    conn = database.connect(path, readonly=True)
    try:
        problems = [] if database.integrity_ok(conn) else ['PRAGMA integrity_check failed']
        problems += database.schema_problems(conn)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        modes = {}
        if 'tuner_on' in tables:
            modes = dict(conn.execute('SELECT chan_mode_name, COUNT(*) FROM tuner_on GROUP BY 1').fetchall())
        favorites = {}
        if not problems:
            for g in GROUPS:
                favorites[g] = conn.execute(f"SELECT COUNT(*) FROM tuner_on WHERE fav_chan_gr_{g.lower()} IN ('1','true')"
                                            ).fetchone()[0]
        content = database.content_hash(conn)
    finally:
        conn.close()
    return {'path': str(path), 'sha256': database.file_sha256(path), 'content_hash': content,
            'tables': counts, 'modes': modes, 'favorites': favorites, 'problems': problems}
