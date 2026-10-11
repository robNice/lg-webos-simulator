"""Shared test fixtures: isolated simulator instances, a running SSH server and a paramiko client
configured like the current editor (password auth, RejectPolicy, dedicated known_hosts)."""
from __future__ import annotations

import asyncio
import json
import shlex
import socket
import threading
from pathlib import Path

import paramiko
import pytest

from lg_tv_sim.app import Simulator
from lg_tv_sim.config import SimulatorConfig
from lg_tv_sim.ssh.server import known_hosts_line, load_or_create_host_key

REPO = Path(__file__).resolve().parent.parent
PASSWORD = 'sim-test-password'
TV_DB = '/mnt/lg/cmn_data/iepg/db/channel.sql'


def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def make_config(root: Path, fixture: str = 'mini', device: dict | None = None, **behavior) -> SimulatorConfig:
    config = SimulatorConfig(root=root)
    return config.with_overrides(
        **({'device': device} if device else {}),
        server={'ssh_port': 0, 'admin_port': free_port()},
        storage={'fixtures_dir': str(REPO / 'fixtures' / 'synthetic'),
                 'recorded_fixtures_dir': str(REPO / 'fixtures' / 'recorded'),
                 'scenarios_dir': str(REPO / 'fixtures' / 'scenarios'),
                 'initial_fixture': fixture},
        **({'behavior': behavior} if behavior else {}))


@pytest.fixture
def sim_factory(tmp_path):
    created = []

    def factory(fixture: str = 'mini', scenario: str | None = None, device: dict | None = None,
                **behavior) -> Simulator:
        if scenario:
            behavior['scenario'] = scenario
        sim = Simulator(make_config(tmp_path, fixture, device, **behavior), password=PASSWORD)
        created.append(sim)
        return sim

    yield factory
    for sim in created:
        sim.engine.close()


@pytest.fixture
def sim(sim_factory) -> Simulator:
    return sim_factory()


class RunningSimulator:
    def __init__(self, sim: Simulator, known_hosts: Path):
        self.sim, self.known_hosts = sim, known_hosts

    @property
    def port(self) -> int:
        return self.sim.ssh_address[1]

    def client(self, password: str = PASSWORD, timeout: float = 10) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.load_host_keys(str(self.known_hosts))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(hostname='127.0.0.1', port=self.port, username='root', password=password,
                       look_for_keys=False, allow_agent=False, timeout=timeout, auth_timeout=timeout,
                       banner_timeout=timeout)
        return client


@pytest.fixture
def running(sim_factory, tmp_path):
    """Start serve() of a fresh simulator in a background event loop."""
    instances = []

    def start(fixture: str = 'mini', scenario: str | None = None, device: dict | None = None,
              **behavior) -> RunningSimulator:
        sim = sim_factory(fixture, scenario, device, **behavior)
        ready = threading.Event()

        def run():
            async def main():
                event = asyncio.Event()
                task = asyncio.create_task(sim.serve(event))
                await event.wait()
                ready.set()
                await task
            asyncio.run(main())

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        assert ready.wait(15), 'simulator did not start'
        key = load_or_create_host_key(sim.config.path(sim.config.authentication.host_key_file))
        known_hosts = tmp_path / f'known_hosts_{len(instances)}'
        known_hosts.write_text(known_hosts_line(key, '127.0.0.1', sim.ssh_address[1]) + '\n')
        instance = RunningSimulator(sim, known_hosts)
        instances.append((instance, thread))
        return instance

    yield start
    for instance, thread in instances:
        instance.sim.shutdown()
        thread.join(15)


def exec_command(client: paramiko.SSHClient, command: str, timeout: float = 20) -> tuple[int, str, str]:
    _, out, err = client.exec_command(command, timeout=timeout)
    stdout = out.read().decode()
    status = out.channel.recv_exit_status()
    return status, stdout, err.read().decode()


def luna(client: paramiko.SSHClient, method: str, payload: dict,
         service: str = 'com.webos.service.iepg') -> dict:
    """Exactly the command form of tv_write.luna (editor v0.6.1)."""
    command = (f'luna-send -n 1 luna://{service}/{method} '
               + shlex.quote(json.dumps(payload, separators=(',', ':'))))
    status, stdout, stderr = exec_command(client, command)
    assert status == 0, stderr
    return json.loads(stdout)


LIVE_PAYLOAD = {'dataType': 0, 'sort': 0, 'channelMode': 'Satellite', 'channelGroup': ['All'],
                'acceptEmptyGroupName': False, 'attribute': [{'filterType': 'Invisible', 'value': False}]}
