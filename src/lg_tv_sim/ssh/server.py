"""AsyncSSH transport: password auth for the simulated ``root``, exec requests only, virtual SFTP.

``root`` is a protocol detail; the server runs as an ordinary user and never
starts a host shell.  The host key is generated for the simulator only.
"""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import itertools
import os
from pathlib import Path
from typing import TYPE_CHECKING

import asyncssh

from lg_tv_sim.ssh.sftp import SimSFTPServer

if TYPE_CHECKING:
    from lg_tv_sim.app import Simulator

_ids = itertools.count(1)


def load_or_create_host_key(path: Path) -> asyncssh.SSHKey:
    path = Path(path)
    if path.exists():
        return asyncssh.read_private_key(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    key = asyncssh.generate_private_key('ssh-ed25519', comment='lg-tv-simulator')
    key.write_private_key(str(path))
    os.chmod(path, 0o600)
    key.write_public_key(str(path) + '.pub')
    return key


def _is_wildcard(host: str) -> bool:
    try:
        return not host or ipaddress.ip_address(host).is_unspecified
    except ValueError:
        return False


def known_hosts_line(key: asyncssh.SSHKey, host: str, port: int) -> str:
    public = key.export_public_key('openssh').decode().split()
    if _is_wildcard(host):    # wildcard listen (container): clients connect via loopback
        host = '127.0.0.1'
    name = host if port == 22 else f'[{host}]:{port}'
    return f'{name} {public[0]} {public[1]}'


class SimSSHServer(asyncssh.SSHServer):
    def __init__(self, simulator: Simulator):
        self.sim = simulator
        self.conn_id = f'ssh-{next(_ids)}'

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        conn.set_extra_info(sim_connection_id=self.conn_id)
        self.sim.connection_opened(self.conn_id, conn.get_extra_info('peername'))

    def connection_lost(self, exc: Exception | None) -> None:
        self.sim.connection_closed(self.conn_id)

    def begin_auth(self, username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def public_key_auth_supported(self) -> bool:
        return False

    def kbdint_auth_supported(self) -> bool:
        return False

    def validate_password(self, username: str, password: str) -> bool:
        ok = (hmac.compare_digest(username.encode(), self.sim.username.encode())
              and hmac.compare_digest(password.encode(), self.sim.password.encode()))
        self.sim.journal.record('auth', username=username, accepted=ok, connection=self.conn_id)
        return ok


async def handle_process(simulator: Simulator, process: asyncssh.SSHServerProcess) -> None:
    conn_id = process.get_extra_info('sim_connection_id') or '?'
    command = process.command
    if command is None:
        process.stderr.write(b'lg-tv-sim: interactive shells are not supported (SIMULATOR)\n')
        simulator.journal.record('command', command='<shell request>', connection=conn_id, exit_status=126,
                                 effect='SHELL_DENIED')
        process.exit(126)
        return
    result = await asyncio.to_thread(simulator.router.execute, command, conn_id)
    if result.mutated:
        simulator.connection_mutated(conn_id)
    if result.hang_ms:
        await asyncio.sleep(result.hang_ms / 1000)
    if result.disconnect:
        process.channel.get_connection().abort()
        return
    if result.stdout:
        process.stdout.write(result.stdout)
    if result.stderr:
        process.stderr.write(result.stderr)
    process.exit(result.exit_status)


async def start_server(simulator: Simulator, host: str, port: int, host_key: asyncssh.SSHKey) -> asyncssh.SSHAcceptor:
    return await asyncssh.create_server(
        lambda: SimSSHServer(simulator), host, port,
        server_host_keys=[host_key],
        process_factory=lambda process: handle_process(simulator, process),
        sftp_factory=lambda chan: SimSFTPServer(chan, simulator),
        allow_scp=False, allow_pty=False, agent_forwarding=False, x11_forwarding=False,
        encoding=None, login_timeout=30, keepalive_interval=0,
        server_version='LG-TV-Simulator',
    )
