"""TV domain engine: the single place where simulated LG write semantics live (spec §3.2).

SSH/Luna and the admin API both go through this class.  Every mutation runs in
one SQLite transaction under one lock, is checked against invariants and is
returned as before/after records keyed by the internal ``sim_entry_id``.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lg_tv_sim.domain import favorites
from lg_tv_sim.domain.identity import ChannelIdPolicy, IdentityRegistry
from lg_tv_sim.domain.models import (
    CHANNEL_TABLES,
    FAVORITE_GROUP_ID_BASE,
    GROUPS,
    NOT_MEMBER_INDEX,
    ChannelEntry,
    InvariantViolation,
    LunaError,
    Mutation,
    NumberEffect,
    UnsupportedIpChannel,
    is_member_flag,
    user_fav_json,
)
from lg_tv_sim.domain.numbers import NumberContext, Profile, decide
from lg_tv_sim.storage import database
from lg_tv_sim.storage.snapshots import Run
from lg_tv_sim.traces.recorder import VirtualClock

MAJMIN = re.compile(r'(\d+)-(\d{5})-(\d{3})-(\d+)')


@dataclass
class StaleView:
    """Pre-mutation list returned to Luna reads until N reads or T virtual ms have passed."""
    entries: list[ChannelEntry]
    remaining_reads: int
    until_ms: int

    def active(self, now_ms: int) -> bool:
        return self.remaining_reads > 0 or now_ms < self.until_ms


@dataclass
class EngineResult:
    value: object = None
    mutations: list[Mutation] = field(default_factory=list)
    effect: str | None = None
    rule: str | None = None
    suppressed: list[Mutation] = field(default_factory=list)


class TvEngine:
    def __init__(self, run: Run, profile: Profile, clock: VirtualClock | None = None,
                 id_policy: ChannelIdPolicy | None = None, stale_reads_default: int | None = None):
        self.lock = threading.RLock()
        self.profile = profile
        self.clock = clock or VirtualClock()
        self.id_policy = id_policy or ChannelIdPolicy()
        self.stale_reads_default = (profile.read_after_write_stale_reads
                                    if stale_reads_default is None else stale_reads_default)
        self.conn: sqlite3.Connection | None = None
        self.open(run)

    # ------------------------------------------------------------ lifecycle
    def open(self, run: Run) -> None:
        with self.lock:
            self.close()
            self.run = run
            self.conn = database.connect(run.db_path)
            self.identity = IdentityRegistry.load(run.identity_path)
            self._stale: StaleView | None = None
            self._copy_seq = sum(1 for r in self.identity.records.values() if r.copy_of)

    def close(self) -> None:
        with self.lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def restore(self, db_file: Path, identity_file: Path) -> None:
        """Replace the live state by a snapshot (admin only; never exposed as a TV feature)."""
        with self.lock:
            source = database.connect(db_file, readonly=True)
            try:
                source.backup(self.conn)
            finally:
                source.close()
            self.identity = IdentityRegistry.load(identity_file)
            self.identity.save(self.run.identity_path)
            self._stale = None

    # ------------------------------------------------------------ reads
    def true_entries(self) -> list[ChannelEntry]:
        with self.lock:
            rows = self.conn.execute('SELECT * FROM tuner_on ORDER BY chan_mode_name, chan_no_int, dvc_chan_id, '
                                     'mso_prdt_itm_code').fetchall()
            return [ChannelEntry.from_row(r) for r in rows]

    def ip_entries(self) -> list[ChannelEntry]:
        """LG Channels (table ip), read-only; empty if the fixture has no ip table."""
        with self.lock:
            if not self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ip'").fetchone():
                return []
            rows = self.conn.execute('SELECT * FROM ip ORDER BY chan_no_int, dvc_chan_id').fetchall()
            return [ChannelEntry.from_row(r) for r in rows]

    def all_entries(self) -> list[ChannelEntry]:
        """Tuner entries and LG Channels: everything getChannelList can report (E2)."""
        return self.true_entries() + self.ip_entries()

    def visible_entries(self, consume: bool = True) -> tuple[list[ChannelEntry], bool]:
        """Entries (tuner and IP) as the Luna read API currently shows them; second value: stale view."""
        with self.lock:
            stale = self._stale
            if stale is not None and stale.active(self.clock.now_ms):
                if consume and stale.remaining_reads > 0:
                    stale.remaining_reads -= 1
                return stale.entries, True
            self._stale = None
            return self.all_entries(), False

    def stale_status(self) -> dict | None:
        with self.lock:
            if self._stale is None or not self._stale.active(self.clock.now_ms):
                return None
            return {'remaining_reads': self._stale.remaining_reads, 'until_virtual_ms': self._stale.until_ms}

    def sim_id(self, entry: ChannelEntry) -> str | None:
        record = self.identity.find(entry.channel_id, entry.mso)
        return record.sim_entry_id if record else None

    def tags(self, entry: ChannelEntry) -> list[str]:
        return self.identity.tags_of(entry.channel_id, entry.mso)

    def group_names(self) -> dict[str, dict]:
        with self.lock:
            rows = self.conn.execute('SELECT channel_group_id, channel_group_name, user_edited_name, user_edited '
                                     'FROM channel_group_tuner WHERE is_favorite_group=1').fetchall()
        result = {}
        for row in rows:
            index = int(row['channel_group_id']) - FAVORITE_GROUP_ID_BASE
            if 0 <= index < len(GROUPS):
                result[GROUPS[index]] = {'id': int(row['channel_group_id']), 'default': row['channel_group_name'],
                                         'name': row['user_edited_name'] or row['channel_group_name'],
                                         'edited': bool(row['user_edited'])}
        return result

    def backup_to(self, destination: Path) -> None:
        with self.lock:
            database.backup(self.conn, destination)

    def readonly_query(self, sql: str) -> list[tuple]:
        """Run one SELECT on a read-only connection with an authorizer that allows reading only."""
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}

        def authorizer(action, *_):
            return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

        with self.lock:
            conn = database.connect(self.run.db_path, readonly=True)
            try:
                conn.set_authorizer(authorizer)
                return [tuple(r) for r in conn.execute(sql).fetchall()]
            finally:
                conn.close()

    def content_hash(self) -> str:
        with self.lock:
            return database.content_hash(self.conn)

    # ------------------------------------------------------------ mutation frame
    def _mutate(self, body: Callable[[], EngineResult], *, mutate: bool = True,
                stale_reads: int | None = None, stale_ms: int | None = None) -> EngineResult:
        with self.lock:
            visible_before, _ = self.visible_entries(consume=False)
            violations_before = self.invariant_violations()
            identity_before = self.identity.to_json()
            self.conn.execute('BEGIN IMMEDIATE')
            try:
                result = body()
                new_violations = self.invariant_violations() - violations_before
                if new_violations:
                    raise InvariantViolation('; '.join(sorted(new_violations)[:5]))
            except BaseException:
                self.conn.execute('ROLLBACK')
                self.identity = IdentityRegistry.from_json(identity_before)
                raise
            if not result.mutations or not mutate:
                self.conn.execute('ROLLBACK')
                self.identity = IdentityRegistry.from_json(identity_before)
                if not mutate:
                    result.suppressed, result.mutations = result.mutations, []
                return result
            self.conn.execute('COMMIT')
            self.identity.save(self.run.identity_path)
            reads = self.stale_reads_default if stale_reads is None else stale_reads
            delay = stale_ms or 0
            if reads or delay:
                self._stale = StaleView(visible_before, reads, self.clock.now_ms + delay)
            return result

    def _entry_by_key(self, key: tuple[str, str]) -> ChannelEntry | None:
        table = favorites.table_of(self.conn, key)
        if table is None:
            return None
        row = self.conn.execute(f'SELECT * FROM {table} WHERE dvc_chan_id=? AND mso_prdt_itm_code=?', key).fetchone()
        return ChannelEntry.from_row(row)

    def reject_ip_channel(self, channel_id: str) -> None:
        """LG Channels (table ``ip``) cannot be renumbered (E9); refuse with a simulator code (U4)."""
        with self.lock:
            has_ip = self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ip'").fetchone()
            if has_ip and self.conn.execute('SELECT 1 FROM ip WHERE dvc_chan_id=?', (channel_id,)).fetchone():
                raise UnsupportedIpChannel(channel_id)

    def resolve(self, channel_id: str, allow_ip: bool = False) -> ChannelEntry:
        """The real entry for a current channel ID; old IDs are not silently accepted.

        LG Channels are found only with ``allow_ip`` (favorite calls, getChannel); number changes refuse them.
        """
        matches = [e for e in (self.all_entries() if allow_ip else self.true_entries()) if e.channel_id == channel_id]
        if not matches:
            self.reject_ip_channel(channel_id)
            raise LunaError('CHANNEL_ERROR_NOT_FOUND', f'Channel not found: {channel_id}')
        if len(matches) > 1:
            raise LunaError('SIM_CHANNEL_ID_AMBIGUOUS', f'Channel ID is used by {len(matches)} entries: {channel_id}')
        return matches[0]

    def _record(self, entry_key: tuple[str, str], before: ChannelEntry | None, note: str = '',
                sim_entry_id: str | None = None) -> Mutation:
        after = self._entry_by_key(entry_key)
        sim = sim_entry_id or (self.sim_id(after) if after else None) or '?'
        return Mutation(sim, before.snapshot() if before else None, after.snapshot() if after else None, note)

    # ------------------------------------------------------------ number changes
    def change_number(self, channel_id: str, number: int, *, effect: NumberEffect | None = None,
                      mutate: bool = True, stale_reads: int | None = None, stale_ms: int | None = None) -> EngineResult:
        if type(number) is not int or not self.profile.number_min <= number <= self.profile.number_max:
            raise LunaError('CHANNEL_ERROR_INVALID_NUMBER', f'Invalid channel number: {number!r}')

        def body() -> EngineResult:
            source = self.resolve(channel_id)
            if source.number == number:
                return EngineResult(effect='NOOP')
            occupants = [e for e in self.true_entries()
                         if e.mode == source.mode and e.number == number and e.channel_id != source.channel_id]
            rule = decide(self.profile, NumberContext(source, number, occupants, self.tags(source)))
            chosen = effect or rule.effect
            rule_id = rule.id if effect is None else f'fault-override:{effect}'
            if chosen == NumberEffect.DENY:
                raise LunaError(rule.error_code if effect is None else 'CHANNEL_ERROR_1003',
                                rule.error_text if effect is None else 'Channel Move Denied')
            if chosen == NumberEffect.REUSE_COPY:
                return EngineResult(effect=chosen, rule=rule_id)
            if chosen == NumberEffect.MOVE:
                mutations = [self._renumber(source, number, note='move')]
            elif chosen == NumberEffect.SWAP:
                if len(occupants) != 1:
                    raise LunaError('SIM_SWAP_NOT_POSSIBLE', f'swap needs exactly one occupant, found {len(occupants)}')
                mutations = self._swap(source, occupants[0])
            elif chosen == NumberEffect.COPY:
                mutations = [self._copy(source, number)]
            else:   # pragma: no cover - enum exhausted
                raise LunaError('SIM_UNSUPPORTED', f'unknown effect {chosen}')
            return EngineResult(mutations=mutations, effect=chosen, rule=rule_id)

        return self._mutate(body, mutate=mutate, stale_reads=stale_reads, stale_ms=stale_ms)

    def _new_id(self, entry: ChannelEntry, number: int) -> str:
        return self.id_policy.renumbered(entry.mode, entry.channel_id, entry.number, number, entry.signal_id)

    def _set_number_columns(self, key: tuple[str, str], new_id: str, number: int) -> None:
        row = self.conn.execute('SELECT channelMajMinNo, online_chan_id FROM tuner_on '
                                'WHERE dvc_chan_id=? AND mso_prdt_itm_code=?', key).fetchone()
        majmin = row['channelMajMinNo'] or ''
        match = MAJMIN.fullmatch(majmin)
        if match:
            majmin = f'{match.group(1)}-{number:05d}-{match.group(3)}-{match.group(4)}'
        online = row['online_chan_id'] or ''
        if online.startswith(key[0] + '_'):
            online = new_id + online[len(key[0]):]
        for table in CHANNEL_TABLES:
            self.conn.execute(f'UPDATE {table} SET dvc_chan_id=?, chan_no=?, chan_no_int=?, maj_no=?, min_no=?, '
                              'channelMajMinNo=?, online_chan_id=? WHERE dvc_chan_id=? AND mso_prdt_itm_code=?',
                              (new_id, str(number), number, number, number, majmin, online, *key))

    def _renumber(self, entry: ChannelEntry, number: int, note: str) -> Mutation:
        new_id = self._new_id(entry, number)
        if new_id != entry.channel_id and self.conn.execute(
                'SELECT 1 FROM tuner_on WHERE dvc_chan_id=? AND mso_prdt_itm_code=?', (new_id, entry.mso)).fetchone():
            raise LunaError('SIM_CHANNEL_ID_COLLISION', f'new channel ID {new_id} already exists')
        record = self.identity.require(entry.channel_id, entry.mso)
        self._set_number_columns((entry.channel_id, entry.mso), new_id, number)
        favorites.rename_channel(self.conn, entry.channel_id, new_id)
        self.identity.rename(record.sim_entry_id, new_id)
        return self._record((new_id, entry.mso), entry, note, record.sim_entry_id)

    def _swap(self, source: ChannelEntry, partner: ChannelEntry) -> list[Mutation]:
        source_id, partner_id = self._new_id(source, partner.number), self._new_id(partner, source.number)
        if source_id == partner_id:
            raise LunaError('SIM_CHANNEL_ID_COLLISION', 'swap would give both entries the same ID')
        source_rec = self.identity.require(source.channel_id, source.mso)
        partner_rec = self.identity.require(partner.channel_id, partner.mso)
        temp = f'__sim_swap__{source_rec.sim_entry_id}'
        # Two-phase rename: the new ID of one entry may equal the old ID of the other.
        self._set_number_columns((source.channel_id, source.mso), temp, partner.number)
        favorites.rename_channel(self.conn, source.channel_id, temp)
        self._set_number_columns((partner.channel_id, partner.mso), partner_id, source.number)
        favorites.rename_channel(self.conn, partner.channel_id, partner_id)
        self._set_number_columns((temp, source.mso), source_id, partner.number)
        favorites.rename_channel(self.conn, temp, source_id)
        self.identity.rename(source_rec.sim_entry_id, source_id)
        self.identity.rename(partner_rec.sim_entry_id, partner_id)
        return [self._record((source_id, source.mso), source, 'swap: moved', source_rec.sim_entry_id),
                self._record((partner_id, partner.mso), partner, 'swap: displaced', partner_rec.sim_entry_id)]

    def _copy(self, source: ChannelEntry, number: int) -> Mutation:
        """Astra LCN copy: additional entry with own ID and no favorites; original unchanged."""
        new_id = self._new_id(source, number)
        if self.conn.execute('SELECT 1 FROM tuner_on WHERE dvc_chan_id=?', (new_id,)).fetchone():
            raise LunaError('SIM_CHANNEL_ID_COLLISION', f'copy ID {new_id} already exists')
        for table in CHANNEL_TABLES:
            row = dict(self.conn.execute(f'SELECT * FROM {table} WHERE dvc_chan_id=? AND mso_prdt_itm_code=?',
                                         (source.channel_id, source.mso)).fetchone())
            row['dvc_chan_id'], row['user_fav_chan_gr'] = '__sim_copy__', user_fav_json([])
            for g in GROUPS:
                row[f'fav_chan_gr_{g.lower()}'], row[f'favoriteIdx{g}'] = '0', NOT_MEMBER_INDEX
            names = list(row)
            self.conn.execute(f'INSERT INTO {table} ({", ".join(chr(34) + n + chr(34) for n in names)}) '
                              f'VALUES ({", ".join("?" * len(names))})', [row[n] for n in names])
        self._set_number_columns(('__sim_copy__', source.mso), new_id, number)
        self._copy_seq += 1
        parent = self.identity.require(source.channel_id, source.mso)
        record = self.identity.add_copy(parent, new_id, self._copy_seq)
        return self._record((new_id, source.mso), None, f'copy of {source.channel_id}', record.sim_entry_id)

    # ------------------------------------------------------------ favorites
    def set_favorites(self, channel_ids: list[str], groups: list[str], member: bool, *, mutate: bool = True,
                      stale_reads: int | None = None, stale_ms: int | None = None) -> EngineResult:
        def body() -> EngineResult:
            mutations = []
            layout = self.profile.favorites
            for channel_id in channel_ids:
                entry = self.resolve(channel_id, allow_ip=True)
                key = (entry.channel_id, entry.mso)
                changed = False
                for group in groups:
                    changed |= (favorites.add if member else favorites.release)(self.conn, group, key, layout)
                if changed:
                    mutations.append(self._record(key, entry, ('add ' if member else 'release ') + ','.join(groups)))
            return EngineResult(mutations=mutations, effect='FAVORITE_ADD' if member else 'FAVORITE_RELEASE')

        return self._mutate(body, mutate=mutate, stale_reads=stale_reads, stale_ms=stale_ms)

    def move_favorite(self, group: str, channel_id: str, destination_id: str, direction: str, *,
                      mutate: bool = True, stale_reads: int | None = None, stale_ms: int | None = None) -> EngineResult:
        def body() -> EngineResult:
            source = self.resolve(channel_id, allow_ip=True)
            destination = self.resolve(destination_id, allow_ip=True)
            layout = self.profile.favorites
            before_order = favorites.members(self.conn, group)
            source_key, destination_key = (source.channel_id, source.mso), (destination.channel_id, destination.mso)
            if source_key not in before_order or destination_key not in before_order:
                raise LunaError('FAVORITE_ERROR_NOT_MEMBER', 'source or destination is not a member of the group')
            if favorites.crosses_ip_block(self.conn, source_key, destination_key, layout):
                # U1 (SIMULATOR_ASSUMPTION): the IP block stays behind the tuner members; the TV answer is
                # modelled as success, so only reading back reveals that nothing moved.
                return EngineResult(effect='FAVORITE_ORDER_BLOCKED_IP')
            changed = favorites.move(self.conn, group, source_key, destination_key, direction, layout)
            if not changed:
                return EngineResult(effect='FAVORITE_ORDER_UNCHANGED')
            after_order = favorites.members(self.conn, group)
            moved = {k for k in after_order if before_order.index(k) != after_order.index(k)}
            entries = {(e.channel_id, e.mso): e for e in self.all_entries()}
            mutations = [Mutation(self.sim_id(entries[k]) or '?', None, entries[k].snapshot(), f'order {group}')
                         for k in sorted(moved)]
            return EngineResult(mutations=mutations, effect='FAVORITE_MOVE')

        return self._mutate(body, mutate=mutate, stale_reads=stale_reads, stale_ms=stale_ms)

    def set_group_name(self, group_id: int, name: str, *, mutate: bool = True) -> EngineResult:
        def body() -> EngineResult:
            row = self.conn.execute('SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id=? '
                                    'AND is_favorite_group=1', (group_id,)).fetchone()
            if row is None:
                raise LunaError('GROUP_ERROR_NOT_FOUND', f'Unknown channel group {group_id}')
            if row['user_edited_name'] == name:
                return EngineResult(effect='GROUP_RENAME_UNCHANGED')
            self.conn.execute('UPDATE channel_group_tuner SET user_edited_name=?, user_edited=1 '
                              'WHERE channel_group_id=?', (name, group_id))
            group = GROUPS[group_id - FAVORITE_GROUP_ID_BASE]
            return EngineResult(mutations=[Mutation(f'group:{group}', {'name': row['user_edited_name']},
                                                    {'name': name}, 'rename group')], effect='GROUP_RENAME')

        return self._mutate(body, mutate=mutate)

    # ------------------------------------------------------------ invariants
    def invariant_violations(self) -> set[str]:
        problems: set[str] = set()
        rows = {}
        for table in CHANNEL_TABLES:
            rows[table] = {(r['dvc_chan_id'], r['mso_prdt_itm_code']): r
                           for r in self.conn.execute(f'SELECT * FROM {table}')}
        on, off = rows['tuner_on'], rows['tuner_off']
        for key in set(on) ^ set(off):
            problems.add(f'tuner_on/tuner_off differ in entry {key}')
        compared = ['chan_no', 'chan_no_int', *(f'fav_chan_gr_{g.lower()}' for g in GROUPS),
                    *(f'favoriteIdx{g}' for g in GROUPS)]
        for key in set(on) & set(off):
            for column in compared:
                if on[key][column] != off[key][column]:
                    problems.add(f'tuner_off.{column} differs for {key}')
        ip = ({(r['dvc_chan_id'], r['mso_prdt_itm_code']): r for r in self.conn.execute('SELECT * FROM ip')}
              if favorites.has_ip_table(self.conn) else {})
        for key, row in on.items():
            if str(row['chan_no']) != str(row['chan_no_int']):
                problems.add(f'chan_no/chan_no_int mismatch for {key}')
        for key, row in (*on.items(), *ip.items()):
            groups = [g for g in GROUPS if is_member_flag(row[f'fav_chan_gr_{g.lower()}'])]
            stored = row['user_fav_chan_gr']
            if stored and stored != user_fav_json(groups):
                problems.add(f'user_fav_chan_gr inconsistent for {key}')
        layout = self.profile.favorites
        fav_rows = {r['dvc_chan_id']: r for r in self.conn.execute('SELECT * FROM favorite_idx')}
        for g in GROUPS:
            flag, idx = f'fav_chan_gr_{g.lower()}', f'favoriteIdx{g}'
            tuner = sorted(int(r[idx]) for r in on.values() if is_member_flag(r[flag]))
            ip_positions = sorted(int(r[idx]) for r in ip.values() if is_member_flag(r[flag]))
            if len(set(tuner + ip_positions)) != len(tuner) + len(ip_positions):
                problems.add(f'duplicate favorite positions in {g} (tuner_on and ip)')
            if layout.ip_block_after_tuner:
                if tuner != list(range(len(tuner))):
                    problems.add(f'favorite positions of {g} are not 0..n-1')
                first = layout.ip_first_index
                if any(i < first for i in ip_positions):
                    problems.add(f'IP favorite positions of {g} below {first}')
                if ip_positions != list(range(first, first + len(ip_positions))):
                    problems.add(f'IP favorite positions of {g} are not {first}..')
            elif sorted(tuner + ip_positions) != list(range(len(tuner) + len(ip_positions))):
                problems.add(f'favorite positions of {g} are not 0..n-1 (joint order)')
            if any(r[idx] not in (NOT_MEMBER_INDEX, None) for r in on.values() if not is_member_flag(r[flag])):
                problems.add(f'non-members of {g} carry a position')
            if any(r[idx] not in (layout.ip_not_member_index, NOT_MEMBER_INDEX, None) for r in ip.values()
                   if not is_member_flag(r[flag])):
                problems.add(f'IP non-members of {g} carry a position')
            for (channel_id, _), row in ip.items():    # E6: IP member <=> favorite_idx row with the same index
                member, mirror = is_member_flag(row[flag]), fav_rows.get(channel_id)
                mirrored = mirror is not None and is_member_flag(mirror[flag])
                if member != mirrored or (member and int(mirror[idx]) != int(row[idx])):
                    problems.add(f'favorite_idx out of sync with ip for {channel_id} in {g}')
        registry = {(r.channel_id, r.mso) for r in self.identity.records.values()}
        if registry != set(on) | set(ip):
            problems.add('identity registry does not match tuner_on and ip')
        return problems
