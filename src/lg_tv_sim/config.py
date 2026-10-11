"""Typed simulator configuration loaded from TOML (see config/example.toml)."""
from __future__ import annotations

import ipaddress
import logging
import os
import re
import shutil
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

# Container: config path, template copied there on first start, and the container marker.
CONFIG_ENV = 'LG_TV_SIM_CONFIG'
TEMPLATE_ENV = 'LG_TV_SIM_CONFIG_TEMPLATE'
CONTAINER_ENV = 'LG_TV_SIM_CONTAINER'

log = logging.getLogger('lg_tv_sim')

# Ports used by the LG WebOS Channel Editor; the simulator must never take them.
RESERVED_EDITOR_PORTS = {8765: 'editor web UI', 8766: 'editor development / browser tests'}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ServerConfig:
    ssh_host: str = '127.0.0.1'
    ssh_port: int = 2222
    admin_host: str = '127.0.0.1'
    admin_port: int = 8767


@dataclass(frozen=True)
class AuthConfig:
    username: str = 'root'
    password_env: str = 'LG_TV_SIM_PASSWORD'
    host_key_file: str = '.simulator/keys/ssh_host_key'
    admin_token_env: str = 'LG_TV_SIM_ADMIN_TOKEN'


@dataclass(frozen=True)
class StorageConfig:
    base_dir: str = '.simulator/runs'
    fixtures_dir: str = 'fixtures/synthetic'
    recorded_fixtures_dir: str = 'fixtures/recorded'
    private_fixtures_dir: str = '.simulator/fixtures'
    scenarios_dir: str = 'fixtures/scenarios'
    initial_fixture: str = 'real_20261011_2301'


@dataclass(frozen=True)
class BehaviorConfig:
    profile: str = 'lg_webos22_historical'
    read_after_write_stale_reads: int = 0
    virtual_ms_per_call: int = 100
    unknown_commands: str = 'deny'
    unknown_luna_methods: str = 'deny'
    seed: int = 1001
    scenario: str | None = None


@dataclass(frozen=True)
class DeviceConfig:
    """Identity reported by getSystemInfo (editor v0.6.4 files backups per model + serial)."""
    model_name: str = 'OLED55C27LA'
    serial_number: str = 'SIM-000000000001'   # must start with "SIM-": never the real TV's serial


@dataclass(frozen=True)
class SecurityConfig:
    allow_external_bind: bool = False
    allow_sftp_write: bool = False


@dataclass(frozen=True)
class SimulatorConfig:
    root: Path = field(default_factory=Path.cwd)
    server: ServerConfig = field(default_factory=ServerConfig)
    authentication: AuthConfig = field(default_factory=AuthConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)

    _SECTIONS = {'server': ServerConfig, 'authentication': AuthConfig, 'storage': StorageConfig,
                 'behavior': BehaviorConfig, 'security': SecurityConfig, 'device': DeviceConfig}

    @classmethod
    def load(cls, path: str | Path | None = None, root: Path | None = None) -> SimulatorConfig:
        """Load a TOML file; unknown sections/keys are errors, not silently ignored."""
        data: dict = {}
        if path is not None:
            path = Path(path)
            if not path.is_file():
                raise ConfigError(f'config file not found: {path}')
            data = tomllib.loads(path.read_text(encoding='utf-8'))
        sections = {}
        for name, value in data.items():
            if name not in cls._SECTIONS:
                raise ConfigError(f'unknown config section [{name}]')
            section_type = cls._SECTIONS[name]
            allowed = {f.name: f.type for f in fields(section_type)}
            unknown = set(value) - set(allowed)
            if unknown:
                raise ConfigError(f'unknown keys in [{name}]: {", ".join(sorted(unknown))}')
            sections[name] = section_type(**value)
        config = cls(root=(root or Path.cwd()).resolve(), **sections)
        config.validate()
        return config

    def with_overrides(self, **sections) -> SimulatorConfig:
        """Return a copy with replaced section fields, e.g. ``server={'ssh_port': 0}``."""
        changes = {name: replace(getattr(self, name), **values) for name, values in sections.items()}
        config = replace(self, **changes)
        config.validate()
        return config

    def validate(self) -> None:
        for host, port, label in ((self.server.ssh_host, self.server.ssh_port, 'ssh'),
                                  (self.server.admin_host, self.server.admin_port, 'admin')):
            if type(port) is not int or not 0 <= port <= 65535:
                raise ConfigError(f'invalid {label} port: {port!r}')
            if port == 22:
                raise ConfigError('the simulator must not use port 22')
            if port in RESERVED_EDITOR_PORTS:
                raise ConfigError(f'port {port} is reserved for the Channel Editor '
                                  f'({RESERVED_EDITOR_PORTS[port]}); choose another port')
            if not self.security.allow_external_bind and not is_loopback(host):
                raise ConfigError(f'{label} host {host!r} is not a loopback address; '
                                  'set [security] allow_external_bind = true to permit it deliberately')
        if self.behavior.unknown_commands != 'deny' or self.behavior.unknown_luna_methods != 'deny':
            raise ConfigError('unknown commands and Luna methods can only be denied (fail closed)')
        if not re.fullmatch(r'SIM-[A-Za-z0-9._-]{1,60}', self.device.serial_number):
            raise ConfigError('device serial_number must look like "SIM-…" (letters, digits, . _ -), so the editor '
                              'never mixes simulator backups with a real TV')
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', self.device.model_name):
            raise ConfigError('device model_name must be 1-64 letters, digits, . _ -')
        if self.security.allow_sftp_write:
            raise ConfigError('SFTP write support is not implemented; the current editor needs none')
        if self.behavior.read_after_write_stale_reads < 0 or self.behavior.virtual_ms_per_call < 0:
            raise ConfigError('behavior values must not be negative')

    def path(self, value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else self.root / candidate


def is_loopback(host: str) -> bool:
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def provision(target: Path, template: Path) -> bool:
    """Copy ``template`` to ``target`` unless it exists; an existing file is never overwritten."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, 'xb') as out, open(template, 'rb') as src:
            shutil.copyfileobj(src, out)
    except FileExistsError:
        return False
    log.info('created %s from template %s', target, template)
    return True


def resolve_config_path(explicit: str | None) -> str | None:
    """--config, else $LG_TV_SIM_CONFIG (provisioned from the template if missing), else config/local.toml."""
    if explicit is not None:
        return explicit
    from_env = os.environ.get(CONFIG_ENV)
    if from_env:
        template = os.environ.get(TEMPLATE_ENV)
        if template:
            provision(Path(from_env), Path(template))
        return from_env
    return 'config/local.toml' if Path('config/local.toml').is_file() else None


def check_container_binding(config: SimulatorConfig) -> None:
    """Inside a container a loopback bind would silently make the simulator unreachable."""
    if os.environ.get(CONTAINER_ENV) != '1':
        return
    for host, label in ((config.server.ssh_host, 'ssh'), (config.server.admin_host, 'admin')):
        if is_loopback(host):
            raise ConfigError(f'{label} host {host!r} is unreachable from outside the container; '
                              'use "0.0.0.0" and publish the port on 127.0.0.1 on the Docker host')



# Docker: the usual settings come from the compose file and override the (optional) config file.
ENVIRONMENT = {
    'LG_TV_SIM_FIXTURE': ('storage', 'initial_fixture'),
    'LG_TV_SIM_SCENARIO': ('behavior', 'scenario'),
    'LG_TV_SIM_MODEL': ('device', 'model_name'),
    'LG_TV_SIM_SERIAL': ('device', 'serial_number'),
}


def apply_environment(config: SimulatorConfig) -> SimulatorConfig:
    """Override config values from set environment variables (validated like the file)."""
    sections: dict[str, dict] = {}
    for variable, (section, key) in ENVIRONMENT.items():
        value = os.environ.get(variable)
        if value:
            sections.setdefault(section, {})[key] = value
    return config.with_overrides(**sections) if sections else config
