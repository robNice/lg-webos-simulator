"""Simulator facade: wires run storage, domain engine, Luna dispatcher, faults, journal and transports."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
import signal
import socket
import threading
import time
from dataclasses import asdict
from pathlib import Path

from lg_tv_sim import __version__
from lg_tv_sim.config import SimulatorConfig
from lg_tv_sim.domain.engine import TvEngine
from lg_tv_sim.domain.numbers import Profile
from lg_tv_sim.faults.engine import FaultEngine
from lg_tv_sim.faults.schema import EMPTY_SCENARIO, Scenario, load_directory
from lg_tv_sim.luna.dispatcher import LunaDispatcher
from lg_tv_sim.ssh.commands import CommandRouter
from lg_tv_sim.ssh.paths import VirtualFileSystem
from lg_tv_sim.storage.fixtures import FixtureCatalog
from lg_tv_sim.storage.snapshots import Run, RunManager
from lg_tv_sim.traces.recorder import Journal, VirtualClock

log = logging.getLogger('lg_tv_sim')


class BusyError(RuntimeError):
    """A reset/restore would interrupt an SSH session that already wrote to the simulated TV."""


class Simulator:
    def __init__(self, config: SimulatorConfig, password: str | None = None):
        self.config = config
        self.lock = threading.RLock()
        storage = config.storage
        self.catalog = FixtureCatalog(config.path(storage.fixtures_dir), config.path(storage.private_fixtures_dir),
                                      config.path(storage.recorded_fixtures_dir))
        self.runs = RunManager(config.path(storage.base_dir))
        self.username = config.authentication.username
        self.password = password if password is not None else resolve_password(config)
        self.clock = VirtualClock(config.behavior.virtual_ms_per_call)
        self.journal = Journal(clock=self.clock)
        self.faults = FaultEngine()
        self.connections: dict[str, dict] = {}
        self.engine: TvEngine | None = None
        self.vfs = VirtualFileSystem(lambda: self.run)
        self.fixture_name = storage.initial_fixture
        self.fixture_hash = ''
        self.scenario: Scenario = EMPTY_SCENARIO
        self.started = time.time()
        self.ssh_address: tuple[str, int] | None = None
        self.reset(scenario=config.behavior.scenario)

    # ------------------------------------------------------------ scenarios / reset
    def scenarios(self) -> dict[str, Scenario]:
        directory = self.config.path(self.config.storage.scenarios_dir)
        return load_directory(directory) if directory.is_dir() else {}

    def _scenario(self, scenario_id: str | None) -> Scenario:
        if not scenario_id or scenario_id == 'none':
            return EMPTY_SCENARIO
        found = self.scenarios().get(scenario_id)
        if found is None:
            raise KeyError(f'unknown scenario {scenario_id!r}')
        return found

    def reset(self, fixture: str | None = None, scenario: str | None = None, force: bool = False,
              keep_scenario: bool = False) -> dict:
        """Fresh run from the (unchanged) fixture.  Refused while a writing SSH session is open."""
        with self.lock:
            if not force and self.active_writers():
                raise BusyError('an SSH session that wrote to the simulator is still open; '
                                'close it or reset with force')
            chosen = self.scenario if keep_scenario else self._scenario(scenario)
            fixture_name = fixture or chosen.fixture or self.fixture_name
            fixture_obj = self.catalog.get(fixture_name)
            profile = Profile.load(chosen.profile or self.config.behavior.profile)
            stale = chosen.read_after_write_stale_reads
            if stale is None:
                stale = self.config.behavior.read_after_write_stale_reads or profile.read_after_write_stale_reads
            run, content_hash = self.runs.create(fixture_obj, profile.id, chosen.seed)
            self.runs.prune()
            self.journal.clear(run.journal_path)
            if self.engine is None:
                self.engine = TvEngine(run, profile, self.clock, stale_reads_default=stale)
                self.dispatcher = LunaDispatcher(self.engine, self.faults, self.journal, self.config.device)
                self.router = CommandRouter(self.engine, self.dispatcher, self.vfs, self.faults, self.journal)
            else:
                self.engine.profile, self.engine.stale_reads_default = profile, stale
                self.engine.open(run)
            self.faults.activate(chosen)
            self.scenario, self.fixture_name, self.fixture_hash = chosen, fixture_obj.name, content_hash
            self.journal.record('reset', fixture=fixture_obj.name, fixture_hash=content_hash, run_id=run.id,
                                scenario=chosen.id, profile=profile.id, seed=chosen.seed)
            log.info('reset: run %s, fixture %s (%s), scenario %s', run.id, fixture_obj.name, content_hash[:12],
                     chosen.id)
            return self.status()

    def activate_scenario(self, scenario_id: str, reset: bool = True, force: bool = False) -> dict:
        with self.lock:
            if reset:
                return self.reset(scenario=scenario_id, force=force)
            self.scenario = self._scenario(scenario_id)
            self.faults.activate(self.scenario)
            self.journal.record('scenario', scenario=self.scenario.id)
            return self.status()

    @property
    def run(self) -> Run:
        return self.engine.run

    # ------------------------------------------------------------ snapshots
    def snapshot(self, label: str = '') -> str:
        with self.lock, self.engine.lock:
            snap = self.run.save_snapshot(self.engine.conn, self.engine.identity, label)
            self.journal.record('snapshot', snapshot=snap, label=label[:200])
            return snap

    def restore(self, snap_id: str, force: bool = False) -> dict:
        with self.lock:
            if not force and self.active_writers():
                raise BusyError('an SSH session that wrote to the simulator is still open')
            db_file, identity_file = self.run.snapshot_files(snap_id)
            self.engine.restore(db_file, identity_file)
            self.journal.record('restore', snapshot=snap_id, state_hash=self.engine.content_hash())
            return self.status()

    # ------------------------------------------------------------ connections
    def connection_label(self, conn) -> str:
        return conn.get_extra_info('sim_connection_id') if conn is not None else '?'

    def connection_opened(self, conn_id: str, peer) -> None:
        with self.lock:
            self.connections[conn_id] = {'peer': str(peer[0]) if peer else '?', 'opened': time.time(), 'writes': 0}

    def connection_closed(self, conn_id: str) -> None:
        with self.lock:
            self.connections.pop(conn_id, None)

    def connection_mutated(self, conn_id: str) -> None:
        with self.lock:
            if conn_id in self.connections:
                self.connections[conn_id]['writes'] += 1

    def active_writers(self) -> list[str]:
        with self.lock:
            return [cid for cid, info in self.connections.items() if info['writes']]

    # ------------------------------------------------------------ views
    def status(self) -> dict:
        engine = self.engine
        entries = engine.true_entries()
        ip = engine.ip_entries()
        groups = {g: sum(1 for e in (*entries, *ip) if e.groups[g]) for g in 'ABCDEFGH'}   # tuner_on and ip
        return {
            'simulator': 'SIMULATOR – not a real LG TV', 'version': __version__,
            'run_id': self.run.id, 'fixture': self.fixture_name, 'fixture_hash': self.fixture_hash,
            'state_hash': engine.content_hash(), 'event_hash': self.journal.event_hash(),
            'profile': engine.profile.id, 'scenario': self.scenario.id, 'faults': self.faults.status(),
            'ssh': {'host': self.ssh_address[0], 'port': self.ssh_address[1]} if self.ssh_address else None,
            'username': self.username, 'channels': len(entries),
            'modes': {m: sum(1 for e in entries if e.mode == m) for m in sorted({e.mode for e in entries})},
            'favorites': groups, 'group_names': engine.group_names(),
            'ip': {'channels': len(ip), 'favorites': {g: n for g in 'ABCDEFGH'
                                                      if (n := sum(1 for e in ip if e.groups[g]))}},
            'connections': len(self.connections), 'active_writers': self.active_writers(),
            'stale_view': engine.stale_status(), 'virtual_ms': self.clock.now_ms,
            'snapshots': self.run.snapshots(), 'events': len(self.journal.events()),
        }

    def channels(self, include_ip: bool = False) -> list[dict]:
        """Tuner entries (what Luna knows); with ``include_ip`` also the read-only LG Channels (table ip)."""
        engine = self.engine
        result = []
        for entry in engine.true_entries():
            record = engine.identity.find(entry.channel_id, entry.mso)
            result.append({**asdict(entry), 'dvb': str(entry.dvb), 'groups': entry.member_of,
                           'index': {g: entry.index[g] for g in entry.member_of},
                           'sim_entry_id': record.sim_entry_id if record else None,
                           'copy_of': record.copy_of if record else None,
                           'id_history': record.id_history if record else [],
                           'tags': record.tags if record else [], 'read_only': False})
        if include_ip:
            for entry in engine.ip_entries():
                result.append({**asdict(entry), 'dvb': str(entry.dvb), 'groups': entry.member_of,
                               'index': {g: entry.index[g] for g in entry.member_of},
                               'sim_entry_id': engine.sim_id(entry), 'copy_of': None, 'id_history': [], 'tags': [],
                               'read_only': True})
        return result

    def export_state(self, destination: Path) -> dict:
        state = {'status': self.status(), 'channels': self.channels()}
        Path(destination).write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding='utf-8')
        return state

    def export_trace(self, destination: Path) -> int:
        return self.journal.export(destination)

    # ------------------------------------------------------------ serving
    async def serve(self, ready: asyncio.Event | None = None) -> None:
        import uvicorn

        from lg_tv_sim.admin.api import create_app
        from lg_tv_sim.ssh.server import load_or_create_host_key, start_server

        server_cfg = self.config.server
        host_key = load_or_create_host_key(self.config.path(self.config.authentication.host_key_file))
        # Bind the admin socket ourselves first: a busy port fails cleanly before SSH starts.
        admin_socket = bind_tcp(server_cfg.admin_host, server_cfg.admin_port, 'admin', '--admin-port')
        try:
            acceptor = await start_server(self, server_cfg.ssh_host, server_cfg.ssh_port, host_key)
        except OSError as exc:
            admin_socket.close()
            raise PortInUseError(port_message('SSH', server_cfg.ssh_host, server_cfg.ssh_port, '--ssh-port', exc)) from exc
        port = acceptor.sockets[0].getsockname()[1]
        self.ssh_address = (server_cfg.ssh_host, port)
        token = os.environ.get(self.config.authentication.admin_token_env) or None
        admin = uvicorn.Server(uvicorn.Config(create_app(self, token), log_level='warning', lifespan='off'))
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        self._loop, self._stop = loop, stop
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, stop.set)
        admin_task = asyncio.create_task(admin.serve(sockets=[admin_socket]))
        admin_task.add_done_callback(lambda _: stop.set())      # admin died -> stop everything
        log.info('SSH/SFTP on %s:%s, admin on http://%s:%s', server_cfg.ssh_host, port,
                 server_cfg.admin_host, admin_socket.getsockname()[1])
        if ready is not None:
            ready.set()
        try:
            await stop.wait()
        finally:
            admin.should_exit = True
            acceptor.close()
            await acceptor.wait_closed()
            with contextlib.suppress(SystemExit, asyncio.CancelledError):
                await admin_task
            admin_socket.close()
            self.engine.close()


    def shutdown(self) -> None:
        """Thread-safe stop request for a running ``serve()``."""
        loop, stop = getattr(self, '_loop', None), getattr(self, '_stop', None)
        if loop is not None and stop is not None:
            loop.call_soon_threadsafe(stop.set)


class PortInUseError(RuntimeError):
    pass


def port_message(label: str, host: str, port: int, option: str, exc: OSError) -> str:
    return (f'{label} port {host}:{port} is not available ({exc.strerror or exc}). Another process uses it, '
            f'e.g. an earlier `lg-tv-sim serve` or a Channel Editor browser-test server (`app.py --port {port}`). '
            f'Stop it or choose another port with {option} / config/local.toml.')


def bind_tcp(host: str, port: int, label: str, option: str) -> socket.socket:
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # allows TIME_WAIT leftovers, not a live listener
    try:
        sock.bind((host, port))
        sock.listen(128)
    except OSError as exc:
        sock.close()
        raise PortInUseError(port_message(label, host, port, option, exc)) from exc
    sock.setblocking(False)
    return sock


def resolve_password(config: SimulatorConfig) -> str:
    """Simulator-only password: env var, else a generated one persisted with mode 0600."""
    value = os.environ.get(config.authentication.password_env)
    if value:
        return value
    path = config.path('.simulator/credentials')
    if path.exists():
        return path.read_text(encoding='utf-8').strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(18)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(value + '\n')
    return value
