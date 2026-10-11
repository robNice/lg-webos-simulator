"""Favorite groups A–H on the simulated channel database.

Membership lives redundantly in ``tuner_on``, ``tuner_off`` (per entry) and
``favorite_idx`` (per channel ID) as flag ``fav_chan_gr_<g>`` ('1'/'0'),
position ``favoriteIdx<G>`` (0-based, 250 = not a member) and the JSON list
``user_fav_chan_gr``.  All three are kept consistent here.  Positions are
compacted to 0..n-1 after every change (SIMULATOR_ASSUMPTION).
"""
from __future__ import annotations

import sqlite3

from lg_tv_sim.domain.models import CHANNEL_TABLES, GROUPS, NOT_MEMBER_INDEX, is_member_flag, user_fav_json

Key = tuple[str, str]   # (dvc_chan_id, mso_prdt_itm_code)


def check_group(group: str) -> str:
    if not isinstance(group, str) or group not in GROUPS or len(group) != 1:
        raise ValueError(f'invalid favorite group {group!r}')
    return group


def members(conn: sqlite3.Connection, group: str) -> list[Key]:
    g = check_group(group)
    rows = conn.execute(f'SELECT dvc_chan_id, mso_prdt_itm_code, fav_chan_gr_{g.lower()} AS flag, favoriteIdx{g} AS idx '
                        'FROM tuner_on').fetchall()
    selected = [r for r in rows if is_member_flag(r['flag'])]
    selected.sort(key=lambda r: (int(r['idx'] if r['idx'] is not None else NOT_MEMBER_INDEX), r['dvc_chan_id']))
    return [(str(r['dvc_chan_id']), str(r['mso_prdt_itm_code'])) for r in selected]


def groups_of(conn: sqlite3.Connection, key: Key) -> list[str]:
    row = conn.execute('SELECT * FROM tuner_on WHERE dvc_chan_id=? AND mso_prdt_itm_code=?', key).fetchone()
    return [g for g in GROUPS if is_member_flag(row[f'fav_chan_gr_{g.lower()}'])] if row else []


def write_order(conn: sqlite3.Connection, group: str, ordered: list[Key]) -> None:
    """Make exactly ``ordered`` the members of ``group`` with positions 0..n-1."""
    g = check_group(group)
    flag, idx = f'fav_chan_gr_{g.lower()}', f'favoriteIdx{g}'
    wanted = {key: position for position, key in enumerate(ordered)}
    current = set(members(conn, g))
    affected = current | set(wanted)
    for key in affected:
        member = key in wanted
        values = ('1' if member else '0', wanted[key] if member else NOT_MEMBER_INDEX)
        for table in CHANNEL_TABLES:
            conn.execute(f'UPDATE {table} SET {flag}=?, {idx}=? WHERE dvc_chan_id=? AND mso_prdt_itm_code=?',
                         (*values, *key))
        _sync_favorite_idx_row(conn, key)


def _sync_favorite_idx_row(conn: sqlite3.Connection, key: Key) -> None:
    """Mirror the entry's memberships into favorite_idx and user_fav_chan_gr."""
    row = conn.execute('SELECT * FROM tuner_on WHERE dvc_chan_id=? AND mso_prdt_itm_code=?', key).fetchone()
    if row is None:
        return
    groups = [g for g in GROUPS if is_member_flag(row[f'fav_chan_gr_{g.lower()}'])]
    for table in CHANNEL_TABLES:
        conn.execute(f'UPDATE {table} SET user_fav_chan_gr=? WHERE dvc_chan_id=? AND mso_prdt_itm_code=?',
                     (user_fav_json(groups), *key))
    exists = conn.execute('SELECT 1 FROM favorite_idx WHERE dvc_chan_id=?', (key[0],)).fetchone()
    if not groups and not exists:
        return
    columns = ['user_fav_chan_gr'] + [f'fav_chan_gr_{g.lower()}' for g in GROUPS] + [f'favoriteIdx{g}' for g in GROUPS]
    values = [user_fav_json(groups)] + [('1' if g in groups else '0') for g in GROUPS] + \
             [int(row[f'favoriteIdx{g}']) if g in groups else NOT_MEMBER_INDEX for g in GROUPS]
    if exists:
        conn.execute('UPDATE favorite_idx SET ' + ', '.join(f'{c}=?' for c in columns) + ' WHERE dvc_chan_id=?',
                     (*values, key[0]))
    else:
        conn.execute(f'INSERT INTO favorite_idx (dvc_chan_id, {", ".join(columns)}) VALUES '
                     f'(?{", ?" * len(columns)})', (key[0], *values))


def add(conn: sqlite3.Connection, group: str, key: Key) -> bool:
    """Append ``key`` to ``group``.  Returns False if it already was a member."""
    order = members(conn, group)
    if key in order:
        return False
    write_order(conn, group, order + [key])
    return True


def release(conn: sqlite3.Connection, group: str, key: Key) -> bool:
    order = members(conn, group)
    if key not in order:
        return False
    order.remove(key)
    write_order(conn, group, order)
    return True


def move(conn: sqlite3.Connection, group: str, source: Key, destination: Key, direction: str) -> bool:
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
    write_order(conn, group, order)
    return True


def rename_channel(conn: sqlite3.Connection, old_id: str, new_id: str) -> None:
    """Carry favorite_idx along when an entry's channel ID changes."""
    conn.execute('UPDATE favorite_idx SET dvc_chan_id=? WHERE dvc_chan_id=?', (new_id, old_id))


def clear_all(conn: sqlite3.Connection, key: Key) -> None:
    for g in GROUPS:
        if key in members(conn, g):
            release(conn, g, key)
