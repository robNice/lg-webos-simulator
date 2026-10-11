"""SQLite access helpers for the simulated ``channel.sql``."""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from lg_tv_sim.domain.models import CHANNEL_TABLES, GROUPS

# Tables/columns the current editor validates (app.validate_database, v0.6.1).
REQUIRED_COLUMNS: dict[str, set[str]] = {
    'tuner_on': {'dvc_chan_id', 'chan_std_name', 'chan_no_int', 'mso_prdt_itm_code', 'chan_no', 'sat_name',
                 'chan_mode_name', *(f'fav_chan_gr_{g.lower()}' for g in GROUPS), *(f'favoriteIdx{g}' for g in GROUPS)},
    'tuner_off': {'dvc_chan_id', 'mso_prdt_itm_code', *(f'fav_chan_gr_{g.lower()}' for g in GROUPS),
                  *(f'favoriteIdx{g}' for g in GROUPS)},
    'favorite_idx': {'dvc_chan_id', *(f'fav_chan_gr_{g.lower()}' for g in GROUPS), *(f'favoriteIdx{g}' for g in GROUPS)},
    'channel_group_tuner': {'channel_group_id', 'user_edited_name', 'is_favorite_group', 'channel_group_name'},
}
# Additional columns the simulator's own write semantics need.
SIMULATION_COLUMNS: dict[str, set[str]] = {
    'tuner_on': {'maj_no', 'min_no', 'signal_chan_id', 'dvb_chan_nw_id', 'dvb_chan_transf_strm_id',
                 'dvb_chan_svc_id', 'chan_type_name', 'user_fav_chan_gr', 'invisible_flag'},
}


def connect(path: Path | str, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path).resolve()
    if readonly:
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=10, check_same_thread=False)
    else:
        conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.isolation_level = None   # explicit transactions only
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    else:
        conn.execute('COMMIT')


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]


def schema_problems(conn: sqlite3.Connection, strict: bool = True) -> list[str]:
    """Missing tables/columns compared with the editor contract (and simulator needs)."""
    problems = []
    needed = {t: set(c) for t, c in REQUIRED_COLUMNS.items()}
    if strict:
        for table, columns in SIMULATION_COLUMNS.items():
            needed[table] |= columns
    for table, columns in needed.items():
        available = set(table_columns(conn, table))
        if not available:
            problems.append(f'missing table {table}')
            continue
        missing = sorted(columns - available)
        if missing:
            problems.append(f'{table}: missing columns {", ".join(missing)}')
    return problems


def integrity_ok(conn: sqlite3.Connection) -> bool:
    return conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def backup(src: sqlite3.Connection, destination: Path | str) -> None:
    """Consistent copy through the SQLite online backup API (never a raw file copy)."""
    destination = Path(destination)
    if destination.exists():
        destination.unlink()
    with sqlite3.connect(str(destination)) as dst:
        src.backup(dst)
    dst.close()


def backup_file(source: Path | str, destination: Path | str) -> None:
    src = connect(source, readonly=True)
    try:
        backup(src, destination)
    finally:
        src.close()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(conn: sqlite3.Connection) -> str:
    """Hash over schema and all rows in a canonical order (independent of page layout)."""
    digest = hashlib.sha256()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for table in tables:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
        digest.update(sql.encode())
        columns = table_columns(conn, table)
        order = ','.join(f'"{c}"' for c in columns)
        for row in conn.execute(f'SELECT {order} FROM "{table}" ORDER BY {order}'):
            digest.update(repr(tuple(row)).encode())
    return digest.hexdigest()


def channel_tables_present(conn: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(t for t in CHANNEL_TABLES if table_columns(conn, t))
