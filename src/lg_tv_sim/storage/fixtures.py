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

from lg_tv_sim.domain.models import GROUPS, NOT_MEMBER_INDEX, user_fav_json
from lg_tv_sim.storage import database

SCHEMA_FILE = Path(__file__).resolve().parent / 'schema' / 'lg_webos22.sql'
NAME_PATTERN = re.compile(r'[A-Za-z0-9_.-]{1,64}')

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


def channel_id_for(c: dict) -> str:
    if c.get('id'):
        return str(c['id'])
    n, tail = int(c['number']), f'{c["tsid"]}_{c["sid"]}_{c.get("onid", 1)}'
    if c.get('mode', 'Satellite') == 'Satellite':
        return f'{c.get("src", 7)}_{c.get("phy", 1)}_{n}_{n}_{tail}'
    return f'{c.get("src", 3)}_1_{c.get("phy", n)}_0_{tail}'


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
            for table in ('tuner_on', 'tuner_off'):
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
    members = [(int(c['favorites'][group]), i) for i, c in enumerate(channels) if group in c.get('favorites', {})]
    return {channel_id_for(channels[i]): pos for pos, (_, i) in enumerate(sorted(members))}


def _channel_row(c: dict, columns: list[tuple[str, str]], positions: dict[str, dict[str, int]]) -> dict:
    row = {name: _default_value(declared) for name, declared in columns}
    mode = c.get('mode', 'Satellite')
    n = int(c['number'])
    cid = channel_id_for(c)
    radio = bool(c.get('radio', False))
    phy = int(c.get('phy', 1))
    code = 'SIM-' + hashlib.sha1(cid.encode(), usedforsecurity=False).hexdigest()[:16].upper()
    groups = [g for g in GROUPS if cid in positions[g]]
    kind = 'Radio' if radio else 'TV'
    row.update({
        'dvc_chan_id': cid, 'mso_prdt_itm_code': str(c.get('mso', '')), 'chan_no': str(n), 'chan_no_int': n,
        'maj_no': n, 'min_no': n if mode == 'Satellite' else 0, 'chan_code': code,
        'chan_std_name': c['name'], 'phy_chan_no': phy, 'chan_src_type': 7 if mode == 'Satellite' else 3,
        'chan_type_name': f'{mode} Digital {kind}', 'chan_type_id': 6 if mode == 'Satellite' else 3,
        'chan_mode_name': mode, 'chan_mode_id': 2 if mode == 'Satellite' else 1,
        'signal_chan_id': f'{c["tsid"]}_{c["sid"]}_{c.get("onid", 1)}', 'online_chan_id': f'{cid}_{code}',
        'user_fav_chan_gr': user_fav_json(groups), 'descrambled_flag': 1, 'satelliteLcn_flag': int(c.get('lcn', 0)),
        'scrambled_flag': int(c.get('scrambled', 0)), 'valid_svc_flag': 1, 'svc_type': 2 if radio else 25,
        'svc_display_flag': 1, 'dvb_chan_nw_id': int(c.get('onid', 1)), 'dvb_chan_transf_strm_id': int(c['tsid']),
        'dvb_chan_svc_id': int(c['sid']), 'hdtv_flag': int(not radio), 'invisible_flag': int(c.get('invisible', 0)),
        'dtv_flag': 1, 'radio_flag': int(radio), 'tv_flag': int(not radio), 'primary_channel_flag': 1,
        'sat_name': c.get('satellite', 'ASTRA 19.2E' if mode == 'Satellite' else ' '),
        'frequency': int(c.get('frequency', 11000 + phy)), 'chan_gr_list': '[0,1,200]', 'ca_sysid_list': '{}',
        'channelMajMinNo': f'06-{n:05d}-000-{phy:03d}', 'last_chg_date': '[]', 'sortIndex': '0000',
        'reserved_3': 'com.webos.service.legacybroadcast', 'reserved_4': '0',
    })
    for g in GROUPS:
        member = cid in positions[g]
        row[f'fav_chan_gr_{g.lower()}'] = '1' if member else '0'
        row[f'favoriteIdx{g}'] = positions[g][cid] if member else NOT_MEMBER_INDEX
    return row


def spec_tags(spec: dict) -> dict[str, list[str]]:
    return {channel_id_for(c): list(c['tags']) for c in spec['channels'] if c.get('tags')}


# ---------------------------------------------------------------- catalog

class FixtureCatalog:
    def __init__(self, synthetic_dir: Path, private_dir: Path):
        self.synthetic_dir, self.private_dir = Path(synthetic_dir), Path(private_dir)

    def names(self) -> list[str]:
        names = {p.stem for p in self.synthetic_dir.glob('*.json')}
        names |= {p.stem for p in self.private_dir.glob('*.sqlite')}
        return sorted(names)

    def get(self, name: str) -> Fixture:
        if not NAME_PATTERN.fullmatch(name or ''):
            raise FixtureError(f'invalid fixture name {name!r}')
        spec_path = self.synthetic_dir / f'{name}.json'
        if spec_path.is_file():
            spec = json.loads(spec_path.read_text(encoding='utf-8'))
            return Fixture(name, 'synthetic', spec_path, spec.get('description', ''), spec_tags(spec))
        db_path = self.private_dir / f'{name}.sqlite'
        if db_path.is_file():
            meta_path = db_path.with_suffix('.json')
            meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.is_file() else {}
            return Fixture(name, 'sqlite', db_path, meta.get('description', 'imported SQLite backup'),
                           meta.get('tags', {}))
        raise FixtureError(f'unknown fixture {name!r}; available: {", ".join(self.names()) or "none"}')

    def import_sqlite(self, source: Path, name: str) -> dict:
        """Import a private backup read-only; refuse to overwrite an existing fixture."""
        if not NAME_PATTERN.fullmatch(name or ''):
            raise FixtureError(f'invalid fixture name {name!r}')
        report = inspect_sqlite(source)
        if report['problems']:
            raise FixtureError('fixture rejected: ' + '; '.join(report['problems']))
        self.private_dir.mkdir(parents=True, exist_ok=True)
        target = self.private_dir / f'{name}.sqlite'
        if target.exists() or (self.synthetic_dir / f'{name}.json').exists():
            raise FixtureError(f'fixture {name!r} already exists; choose another name')
        database.backup_file(source, target)
        meta = {'name': name, 'source': str(Path(source).resolve()), 'source_sha256': report['sha256'],
                'content_hash': report['content_hash'],
                'imported': datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds'),
                'description': 'imported SQLite backup (private, never commit)', 'tags': {}}
        target.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        return meta


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
