"""Restrictive remote command router – deny by default, no host shell, no subprocess.

Supported commands (CURRENT_CLIENT_CONFIRMED, editor v0.6.1):

* ``command -v sqlite3 >/dev/null && command -v luna-send >/dev/null``  (tv_login.py, exact text)
* ``sqlite3 -readonly /mnt/lg/cmn_data/iepg/db/channel.sql '.backup /tmp/<name>'``  (app.py)
* ``sqlite3 -readonly /mnt/lg/cmn_data/iepg/db/channel.sql "SELECT ..."``  (tv_groups.py)
* ``luna-send -n 1 luna://<service>/<method> '<json>'``  (tv_write.py)
* ``luna-send -n 1 -f luna://com.webos.service.tv.systemproperty/getSystemInfo '<json>'``  (tv_identity.py, v0.6.4)
* ``rm -f /tmp/<name>``  (app.py)
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from lg_tv_sim.domain.engine import TvEngine
from lg_tv_sim.faults.engine import CallInfo, FaultEngine
from lg_tv_sim.luna.dispatcher import LunaDispatcher
from lg_tv_sim.ssh.paths import PathDenied, VirtualFileSystem
from lg_tv_sim.traces.recorder import Journal

LOGIN_CHECK = 'command -v sqlite3 >/dev/null && command -v luna-send >/dev/null'
LUNA_URI = re.compile(r'luna://([A-Za-z][A-Za-z0-9.]{0,127})/([A-Za-z][A-Za-z0-9]{0,63})')
BACKUP_ARG = re.compile(r'\.backup (/tmp/\S+)')
UNQUOTED_META = set(';&|<>()$`*?[]{}~#!\n\r\t\x00')
MAX_COMMAND = 1 << 20


class CommandRejected(ValueError):
    pass


@dataclass
class CommandResult:
    stdout: bytes = b''
    stderr: bytes = b''
    exit_status: int = 0
    disconnect: bool = False
    hang_ms: int = 0
    mutated: bool = False


def split_command(command: str) -> list[str]:
    """POSIX-like word splitting that rejects every unquoted shell operator or expansion."""
    if len(command) > MAX_COMMAND or '\x00' in command:
        raise CommandRejected('command too long or contains NUL')
    words, current, has_word, i = [], [], False, 0
    while i < len(command):
        ch = command[i]
        if ch == ' ':
            if has_word:
                words.append(''.join(current))
                current, has_word = [], False
            i += 1
        elif ch == "'":
            end = command.find("'", i + 1)
            if end < 0:
                raise CommandRejected('unterminated single quote')
            current.append(command[i + 1:end])
            has_word, i = True, end + 1
        elif ch == '"':
            i += 1
            while True:
                if i >= len(command):
                    raise CommandRejected('unterminated double quote')
                c = command[i]
                if c == '"':
                    i += 1
                    break
                if c in '$`':
                    raise CommandRejected('expansion inside double quotes is not allowed')
                if c == '\\' and i + 1 < len(command) and command[i + 1] in '"\\$`':
                    current.append(command[i + 1])
                    i += 2
                    continue
                current.append(c)
                i += 1
            has_word = True
        elif ch == '\\':
            raise CommandRejected('unquoted backslash is not allowed')
        elif ch in UNQUOTED_META:
            raise CommandRejected(f'shell operator {ch!r} is not allowed')
        else:
            current.append(ch)
            has_word, i = True, i + 1
    if has_word:
        words.append(''.join(current))
    return words


class CommandRouter:
    def __init__(self, engine: TvEngine, dispatcher: LunaDispatcher, vfs: VirtualFileSystem,
                 faults: FaultEngine, journal: Journal):
        self.engine, self.dispatcher, self.vfs = engine, dispatcher, vfs
        self.faults, self.journal = faults, journal

    def execute(self, command: str, connection: str = '') -> CommandResult:
        self.engine.clock.tick()
        try:
            if command == LOGIN_CHECK:
                return self._simple('login_check', command, connection, CommandResult())
            words = split_command(command)
            if words[:3] == ['luna-send', '-n', '1'] and len(words) == 5:
                return self._luna(words[3], words[4], connection)
            if words[:4] == ['luna-send', '-n', '1', '-f'] and len(words) == 6:     # -f: formatted (tv_identity.py)
                return self._luna(words[4], words[5], connection, formatted=True)
            if len(words) == 4 and words[:2] == ['sqlite3', '-readonly']:
                if not self.vfs.is_database(words[2]):
                    raise CommandRejected(f'unknown database {words[2]!r}')
                backup = BACKUP_ARG.fullmatch(words[3])
                if backup:
                    return self._backup(command, backup.group(1), connection)
                if re.match(r'\s*select\s', words[3], re.IGNORECASE):
                    return self._select(command, words[3], connection)
                raise CommandRejected('only .backup and SELECT are supported for sqlite3')
            if words[:2] == ['rm', '-f'] and len(words) == 3:
                return self._remove(command, words[2], connection)
            raise CommandRejected('unsupported command')
        except (CommandRejected, PathDenied) as exc:
            result = CommandResult(stderr=f'lg-tv-sim: {exc} (SIMULATOR, no host shell)\n'.encode(), exit_status=127)
            self.journal.record('command', command=command[:2000], connection=connection, exit_status=127,
                                effect='UNSUPPORTED_COMMAND', error=str(exc))
            return result

    # ------------------------------------------------------------ helpers
    def _apply_fault(self, kind: str, result_factory) -> tuple[CommandResult, str | None]:
        fault = self.faults.select(CallInfo(kind))
        action = fault.action if fault else None
        if action and action.disconnect == 'before':
            return CommandResult(disconnect=True, hang_ms=action.hang_ms), fault.rule_id
        result = result_factory()
        if action:
            if action.exit_status is not None:
                result.exit_status = action.exit_status
            if action.stderr is not None:
                result.stderr = action.stderr.encode()
            result.hang_ms = action.hang_ms
            result.disconnect = action.disconnect == 'after'
        return result, fault.rule_id if fault else None

    def _simple(self, kind: str, command: str, connection: str, result: CommandResult) -> CommandResult:
        result, fault = self._apply_fault(kind, lambda: result)
        self.journal.record('command', command=command, connection=connection, exit_status=result.exit_status,
                            fault=fault, effect=kind.upper())
        return result

    def _backup(self, command: str, target: str, connection: str) -> CommandResult:
        local = self.vfs.tmp_file(target)

        def run() -> CommandResult:
            self.engine.backup_to(local)
            return CommandResult()

        result, fault = self._apply_fault('backup', run)
        self.journal.record('command', command='sqlite3 -readonly <tv-db> .backup <tmp>', temp_name=target,
                            connection=connection, exit_status=result.exit_status, fault=fault, effect='BACKUP')
        return result

    def _select(self, command: str, sql: str, connection: str) -> CommandResult:
        def run() -> CommandResult:
            try:
                rows = self.engine.readonly_query(sql)
            except sqlite3.Error as exc:
                return CommandResult(stderr=f'Error: {exc}\n'.encode(), exit_status=1)
            text = ''.join('|'.join('' if v is None else str(v) for v in row) + '\n' for row in rows)
            return CommandResult(stdout=text.encode())

        result, fault = self._apply_fault('select', run)
        self.journal.record('command', command=command[:2000], connection=connection,
                            exit_status=result.exit_status, fault=fault, effect='SELECT')
        return result

    def _remove(self, command: str, target: str, connection: str) -> CommandResult:
        local = self.vfs.tmp_file(target)

        def run() -> CommandResult:
            local.unlink(missing_ok=True)
            return CommandResult()

        result, fault = self._apply_fault('rm', run)
        self.journal.record('command', command='rm -f <tmp>', temp_name=target, connection=connection,
                            exit_status=result.exit_status, fault=fault, effect='REMOVE_TEMP')
        return result

    def _luna(self, uri: str, payload: str, connection: str, formatted: bool = False) -> CommandResult:
        match = LUNA_URI.fullmatch(uri)
        if not match:
            raise CommandRejected(f'invalid luna URI {uri!r}')
        try:
            params = json.loads(payload)
        except json.JSONDecodeError:
            self.journal.record('luna', command='luna-send', uri=uri, connection=connection, exit_status=1,
                                effect='INVALID_JSON')
            return CommandResult(stderr=b'luna-send: invalid JSON payload\n', exit_status=1)
        outcome = self.dispatcher.call(match.group(1), match.group(2), params, connection)
        mutated = outcome.mutated
        if outcome.disconnect:
            return CommandResult(disconnect=True, hang_ms=outcome.hang_ms, mutated=mutated)
        if formatted:   # layout of luna-send -f output is a SIMULATOR_ASSUMPTION (indented JSON)
            text = json.dumps(outcome.response, indent=4, ensure_ascii=False) + '\n'
        else:
            text = json.dumps(outcome.response, separators=(',', ':'), ensure_ascii=False) + '\n'
        return CommandResult(stdout=text.encode(), stderr=outcome.stderr.encode(), exit_status=outcome.exit_status,
                             hang_ms=outcome.hang_ms, mutated=mutated)
