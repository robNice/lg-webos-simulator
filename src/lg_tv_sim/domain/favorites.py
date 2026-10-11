"""Favorite groups A–H on the simulated channel database.

Membership lives redundantly per entry in its channel table – ``tuner_on`` and ``tuner_off`` for tuner
channels, ``ip`` for LG Channels – and per channel ID in ``favorite_idx``: flag ``fav_chan_gr_<g>`` ('1'/'0'),
position ``favoriteIdx<G>`` and the JSON list ``user_fav_chan_gr``.  All are kept consistent here.

Positions (``FavoriteLayout``): tuner members 0.., LG Channels members from 251 (E5, E8); tuner non-members
carry 250, IP non-members 255 in ``ip`` but 250 in ``favorite_idx`` (real backups 14:17 and 23:01).
Positions are compacted after every change (SIMULATOR_ASSUMPTION; the real TV keeps gaps in tuner lists,
list C even starts at 8).  With ``ip_block_after_tuner`` the IP block
stays behind the tuner members (U1, assumption); otherwise one joint order 0..n-1.
"""
from __future__ import annotations

import sqlite3

from lg_tv_sim.domain.models import CHANNEL_TABLES, GROUPS, NOT_MEMBER_INDEX, is_member_flag, user_fav_json
from lg_tv_sim.domain.numbers import FavoriteLayout

Key = tuple[str, str]   # (dvc_chan_id, mso_prdt_itm_code)
IP_TABLE = 'ip'
DEFAULT_LAYOUT = FavoriteLayout()


def check_group(group: str) -> str:
    if not isinstance(group, str) or group not in GROUPS or len(group) != 1:
        raise ValueError(f'invalid favorite group {group!r}')
    return group


def has_ip_table(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (IP_TABLE,)).fetchone() is not None


def member_tables(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Tables that hold one row per list entry (``tuner_off`` mirrors ``tuner_on``)."""
    return ('tuner_on', IP_TABLE) if has_ip_table(conn) else ('tuner_on',)


def table_of(conn: sqlite3.Connection, key: Key) -> str | None:
    for table in member_tables(conn):
        if conn.execute(f'SELECT 1 FROM {table} WHERE dvc_chan_id=? AND mso_prdt_itm_code=?', key).fetchone():
            return table
    return None


def is_ip(conn: sqlite3.Connection, key: Key) -> bool:
    return table_of(conn, key) == IP_TABLE


def _row(conn: sqlite3.Connection, key: Key) -> sqlite3.Row | None:
    table = table_of(conn, key)
    if table is None:
        return None
    return conn.execute(f'SELECT * FROM {table} WHERE dvc_chan_id=? AND mso_prdt_itm_code=?', key).fetchone()


def members(conn: sqlite3.Connection, group: str) -> list[Key]:
    """Members of ``group`` over tuner and IP entries, in list order (by favoriteIdx)."""
    g = check_group(group)
    selected = []
    for table in member_tables(conn):
        rows = conn.execute(f'SELECT dvc_chan_id, mso_prdt_itm_code, fav_chan_gr_{g.lower()} AS flag, '
                            f'favoriteIdx{g} AS idx FROM {table}').fetchall()
        selected += [r for r in rows if is_member_flag(r['flag'])]
    selected.sort(key=lambda r: (int(r['idx'] if r['idx'] is not None else NOT_MEMBER_INDEX), r['dvc_chan_id']))
    return [(str(r['dvc_chan_id']), str(r['mso_prdt_itm_code'])) for r in selected]


def groups_of(conn: sqlite3.Connection, key: Key) -> list[str]:
    row = _row(conn, key)
    return [g for g in GROUPS if is_member_flag(row[f'fav_chan_gr_{g.lower()}'])] if row else []


def positions(conn: sqlite3.Connection, ordered: list[Key], layout: FavoriteLayout) -> dict[Key, int]:
    """favoriteIdx for each member of ``ordered``: tuner 0.. and IP from ``ip_first_index`` (block layout),
    or one joint order 0..n-1."""
    if not layout.ip_block_after_tuner:
        return {key: position for position, key in enumerate(ordered)}
    result, tuner, ip = {}, 0, layout.ip_first_index
    for key in ordered:
        if is_ip(conn, key):
            result[key], ip = ip, ip + 1
        else:
            result[key], tuner = tuner, tuner + 1
    return result


def write_order(conn: sqlite3.Connection, group: str, ordered: list[Key],
                layout: FavoriteLayout = DEFAULT_LAYOUT) -> None:
    """Make exactly ``ordered`` the members of ``group`` (positions per ``layout``)."""
    g = check_group(group)
    flag, idx = f'fav_chan_gr_{g.lower()}', f'favoriteIdx{g}'
    wanted = positions(conn, ordered, layout)
    for key in set(members(conn, g)) | set(wanted):
        ip = is_ip(conn, key)
        not_member = layout.ip_not_member_index if ip else NOT_MEMBER_INDEX
        values = ('1', wanted[key]) if key in wanted else ('0', not_member)
        for table in (IP_TABLE,) if ip else CHANNEL_TABLES:
            conn.execute(f'UPDATE {table} SET {flag}=?, {idx}=? WHERE dvc_chan_id=? AND mso_prdt_itm_code=?',
                         (*values, *key))
        _sync_favorite_idx_row(conn, key)


def _sync_favorite_idx_row(conn: sqlite3.Connection, key: Key) -> None:
    """Mirror the entry's flags and positions into favorite_idx and user_fav_chan_gr (E6 for IP entries)."""
    table = table_of(conn, key)
    if table is None:
        return
    row = _row(conn, key)
    groups = [g for g in GROUPS if is_member_flag(row[f'fav_chan_gr_{g.lower()}'])]
    for name in (IP_TABLE,) if table == IP_TABLE else CHANNEL_TABLES:
        conn.execute(f'UPDATE {name} SET user_fav_chan_gr=? WHERE dvc_chan_id=? AND mso_prdt_itm_code=?',
                     (user_fav_json(groups), *key))
    exists = conn.execute('SELECT 1 FROM favorite_idx WHERE dvc_chan_id=?', (key[0],)).fetchone()
    if not groups and not exists:
        return
    columns = ['user_fav_chan_gr'] + [f'fav_chan_gr_{g.lower()}' for g in GROUPS] + [f'favoriteIdx{g}' for g in GROUPS]
    # favorite_idx keeps 250 for lists without the channel, also for IP entries (real backup 23:01; the ip
    # row itself carries 255 there).
    values = [user_fav_json(groups)] + [('1' if g in groups else '0') for g in GROUPS] + \
             [int(row[f'favoriteIdx{g}']) if g in groups else NOT_MEMBER_INDEX for g in GROUPS]
    if exists:
        conn.execute('UPDATE favorite_idx SET ' + ', '.join(f'{c}=?' for c in columns) + ' WHERE dvc_chan_id=?',
                     (*values, key[0]))
    else:
        conn.execute(f'INSERT INTO favorite_idx (dvc_chan_id, {", ".join(columns)}) VALUES '
                     f'(?{", ?" * len(columns)})', (key[0], *values))


def add(conn: sqlite3.Connection, group: str, key: Key, layout: FavoriteLayout = DEFAULT_LAYOUT) -> bool:
    """Append ``key`` to ``group`` (IP: next index of the IP block, U2).  False if it already was a member."""
    order = members(conn, group)
    if key in order:
        return False
    write_order(conn, group, order + [key], layout)
    return True


def release(conn: sqlite3.Connection, group: str, key: Key, layout: FavoriteLayout = DEFAULT_LAYOUT) -> bool:
    order = members(conn, group)
    if key not in order:
        return False
    order.remove(key)
    write_order(conn, group, order, layout)
    return True


def crosses_ip_block(conn: sqlite3.Connection, source: Key, destination: Key, layout: FavoriteLayout) -> bool:
    """A move between a tuner and an IP member while the IP block must stay behind the tuner members (U1)."""
    return layout.ip_block_after_tuner and is_ip(conn, source) != is_ip(conn, destination)


def move(conn: sqlite3.Connection, group: str, source: Key, destination: Key, direction: str,
         layout: FavoriteLayout = DEFAULT_LAYOUT) -> bool:
    """``up``: put ``source`` at the destination's position (before it); ``down``: directly after it.

    The editor uses ``direction:'up'`` to move an entry to the position currently
    held by ``destination`` (CURRENT_CLIENT_CONFIRMED); ``down`` is a SIMULATOR_ASSUMPTION.
    """
    order = members(conn, group)
    if source not in order or destination not in order:
        raise LookupError('source or destination is not a member of the group')
    if source == destination:
        return False
    before = list(order)
    order.remove(source)
    position = order.index(destination) + (1 if direction == 'down' else 0)
    order.insert(position, source)
    if order == before:
        return False
    write_order(conn, group, order, layout)
    return True


def rename_channel(conn: sqlite3.Connection, old_id: str, new_id: str) -> None:
    """Carry favorite_idx along when an entry's channel ID changes."""
    conn.execute('UPDATE favorite_idx SET dvc_chan_id=? WHERE dvc_chan_id=?', (new_id, old_id))


def clear_all(conn: sqlite3.Connection, key: Key, layout: FavoriteLayout = DEFAULT_LAYOUT) -> None:
    for g in GROUPS:
        if key in members(conn, g):
            release(conn, g, key, layout)
