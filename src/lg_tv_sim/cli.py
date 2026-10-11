"""Command line interface: ``lg-tv-sim <command>`` (or ``python -m lg_tv_sim``)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from lg_tv_sim import __version__
from lg_tv_sim.config import ConfigError, SimulatorConfig, check_container_binding, resolve_config_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='lg-tv-sim', description='LG webOS TV simulator (SIMULATOR – not a real TV)')
    parser.add_argument('--config', help='TOML config (default: config/local.toml if present)')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)

    serve = sub.add_parser('serve', help='start SSH/SFTP and admin servers')
    serve.add_argument('--fixture')
    serve.add_argument('--scenario')
    serve.add_argument('--listen', help='override SSH host (non-loopback needs allow_external_bind)')
    serve.add_argument('--ssh-port', type=int, help='override the SSH/SFTP port (default 2222)')
    serve.add_argument('--admin-port', type=int, help='override the admin port (default 8767)')

    for name in ('inspect-fixture', 'validate-fixture'):
        p = sub.add_parser(name, help=f'{name.split("-")[0]} an SQLite channel database or a fixture name')
        p.add_argument('target')

    imp = sub.add_parser('import-fixture', help='import a channel.sql backup (read-only; private unless --public)')
    imp.add_argument('file')
    imp.add_argument('--name', required=True)
    imp.add_argument('--public', action='store_true',
                     help='sanitise (blank ip contacts/stream URLs, refuse e-mail/URL/key data) into fixtures/recorded')

    reset = sub.add_parser('reset', help='reset a running simulator via its admin API')
    reset.add_argument('--fixture')
    reset.add_argument('--scenario')
    reset.add_argument('--force', action='store_true')

    scen = sub.add_parser('scenarios', help='list or activate scenarios')
    scen_sub = scen.add_subparsers(dest='action', required=True)
    scen_sub.add_parser('list')
    act = scen_sub.add_parser('activate')
    act.add_argument('scenario_id')

    for name in ('export-state', 'export-trace'):
        p = sub.add_parser(name, help=f'write the running simulator\'s {name.split("-")[1]} to a file')
        p.add_argument('path')

    hosts = sub.add_parser('known-hosts', help='print the known_hosts line for the simulator host key')
    hosts.add_argument('--host', help='host name the client uses (default: SSH listen address)')
    hosts.add_argument('--port', type=int, help='port the client uses (default: SSH port, e.g. a different Docker mapping)')
    hosts.add_argument('--install', metavar='FILE', help='append the line to FILE (e.g. ~/.ssh/known_hosts)')

    sub.add_parser('build-synthetic', help='regenerate the synthetic fixture specs and derived recorded fixtures')
    return parser


def load_config(args) -> SimulatorConfig:
    return SimulatorConfig.load(resolve_config_path(args.config))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    try:
        config = load_config(args)
        return COMMANDS[args.command](config, args)
    except ConfigError as exc:
        print(f'config error: {exc}', file=sys.stderr)
        return 2
    except (ValueError, KeyError, RuntimeError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


def cmd_serve(config: SimulatorConfig, args) -> int:
    from lg_tv_sim.app import Simulator
    server = {k: v for k, v in (('ssh_host', args.listen), ('ssh_port', args.ssh_port),
                                ('admin_port', args.admin_port)) if v is not None}
    if server:
        config = config.with_overrides(server=server)
    check_container_binding(config)
    if args.fixture or args.scenario:
        config = config.with_overrides(storage={'initial_fixture': args.fixture or config.storage.initial_fixture},
                                       behavior={'scenario': args.scenario or config.behavior.scenario})
    sim = Simulator(config)
    from lg_tv_sim.ssh.server import known_hosts_line, load_or_create_host_key
    key = load_or_create_host_key(config.path(config.authentication.host_key_file))

    async def run() -> None:
        ready = asyncio.Event()
        task = asyncio.create_task(sim.serve(ready))
        waiter = asyncio.create_task(ready.wait())
        await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        if ready.is_set():          # banner only once both servers are really listening
            host, port = sim.ssh_address
            print('=' * 72)
            print(' SIMULATOR – kein echter LG-TV')
            print(f' SSH/SFTP : {config.authentication.username}@{host}:{port}')
            print(f' Passwort : aus ${config.authentication.password_env} bzw. .simulator/credentials')
            print(f' Admin    : http://{config.server.admin_host}:{config.server.admin_port}')
            print(f' Fixture  : {sim.fixture_name}  Run: {sim.run.id}')
            print(f' known_hosts: {known_hosts_line(key, host, port)}')
            print('=' * 72, flush=True)
        else:
            waiter.cancel()
        await task

    asyncio.run(run())
    return 0


def cmd_inspect(config: SimulatorConfig, args) -> int:
    report = _inspect_target(config, args.target)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_validate(config: SimulatorConfig, args) -> int:
    report = _inspect_target(config, args.target)
    if report['problems']:
        print('INVALID: ' + '; '.join(report['problems']))
        return 1
    print(f'OK: {report["path"]} (content hash {report["content_hash"][:16]})')
    return 0


def _inspect_target(config: SimulatorConfig, target: str) -> dict:
    from lg_tv_sim.storage.fixtures import FixtureCatalog, inspect_sqlite
    path = Path(target)
    if path.is_file():
        return inspect_sqlite(path)
    catalog = FixtureCatalog(config.path(config.storage.fixtures_dir), config.path(config.storage.private_fixtures_dir),
                             config.path(config.storage.recorded_fixtures_dir))
    fixture = catalog.get(target)
    scratch = config.path('.simulator/tmp') / f'inspect-{fixture.name}.sqlite'
    scratch.parent.mkdir(parents=True, exist_ok=True)
    fixture.materialize(scratch)
    try:
        report = inspect_sqlite(scratch)
        report['path'] = str(fixture.source)
        return report
    finally:
        scratch.unlink(missing_ok=True)


def cmd_import(config: SimulatorConfig, args) -> int:
    from lg_tv_sim.storage.fixtures import FixtureCatalog
    catalog = FixtureCatalog(config.path(config.storage.fixtures_dir), config.path(config.storage.private_fixtures_dir),
                             config.path(config.storage.recorded_fixtures_dir))
    meta = catalog.import_sqlite(Path(args.file), args.name, public=args.public)
    print(json.dumps(meta, indent=2))
    return 0


def _admin(config: SimulatorConfig, path: str, body: dict | None = None) -> bytes:
    import os
    url = f'http://{config.server.admin_host}:{config.server.admin_port}{path}'
    headers = {'Content-Type': 'application/json'}
    token = os.environ.get(config.authentication.admin_token_env)
    if token:
        headers['X-Sim-Token'] = token
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method='POST' if data else 'GET')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - loopback admin URL
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'admin API {exc.code}: {exc.read().decode(errors="replace")}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'simulator not reachable at {url} ({exc.reason}); is `lg-tv-sim serve` running?') from exc


def cmd_reset(config: SimulatorConfig, args) -> int:
    result = json.loads(_admin(config, '/api/reset', {'confirm': True, 'fixture': args.fixture,
                                                      'scenario': args.scenario, 'force': args.force}))
    print(f'reset: run {result["run_id"]}, fixture {result["fixture"]}, scenario {result["scenario"]}')
    return 0


def cmd_scenarios(config: SimulatorConfig, args) -> int:
    if args.action == 'list':
        from lg_tv_sim.faults.schema import load_directory
        for scenario in load_directory(config.path(config.storage.scenarios_dir)).values():
            print(f'{scenario.id:42} {scenario.description}')
        return 0
    result = json.loads(_admin(config, '/api/scenarios/activate', {'confirm': True, 'scenario': args.scenario_id}))
    print(f'activated {result["scenario"]} (run {result["run_id"]})')
    return 0


def cmd_export(config: SimulatorConfig, args) -> int:
    kind = 'state' if args.command == 'export-state' else 'trace'
    Path(args.path).write_bytes(_admin(config, f'/api/export/{kind}'))
    print(f'wrote {args.path}')
    return 0


def cmd_known_hosts(config: SimulatorConfig, args) -> int:
    from lg_tv_sim.ssh.server import known_hosts_line, load_or_create_host_key
    key = load_or_create_host_key(config.path(config.authentication.host_key_file))
    line = known_hosts_line(key, args.host or config.server.ssh_host, args.port or config.server.ssh_port)
    if args.install:
        target = Path(args.install).expanduser()
        existing = target.read_text(encoding='utf-8') if target.exists() else ''
        name = line.split()[0]
        if any(entry.split()[:1] == [name] for entry in existing.splitlines()):
            raise RuntimeError(f'{target} already has an entry for {name}; remove it first')
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'a', encoding='utf-8') as handle:
            handle.write(('' if not existing or existing.endswith('\n') else '\n') + line + '\n')
        print(f'appended to {target}: {line}')
    else:
        print(line)
    return 0


def cmd_build_synthetic(config: SimulatorConfig, args) -> int:
    from lg_tv_sim.storage.fixtures import write_ip_favorites
    from lg_tv_sim.storage.synthetic import write_all
    for path in write_all(config.path(config.storage.fixtures_dir)):
        print(f'wrote {path}')
    derived = write_ip_favorites(config.path(config.storage.recorded_fixtures_dir))
    if derived:
        print(f'wrote {derived}')
    return 0


COMMANDS = {
    'serve': cmd_serve, 'inspect-fixture': cmd_inspect, 'validate-fixture': cmd_validate,
    'import-fixture': cmd_import, 'reset': cmd_reset, 'scenarios': cmd_scenarios,
    'export-state': cmd_export, 'export-trace': cmd_export, 'known-hosts': cmd_known_hosts,
    'build-synthetic': cmd_build_synthetic,
}
