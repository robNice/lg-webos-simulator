"""Scenario files (YAML): fixture, seed and deterministic fault rules.  Unknown keys are errors."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from lg_tv_sim.domain.models import GROUPS, NumberEffect


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


CommandKind = Literal['login_check', 'backup', 'select', 'rm', 'luna', 'sftp_read']


class FaultMatch(Strict):
    command: CommandKind | None = None
    service: str | None = None
    method: str | None = None
    nth_call: int | None = Field(default=None, ge=1, description='1-based count among calls matching the other fields')
    channel_id: str | None = None
    sim_tag: str | None = None
    target_number: int | None = None
    group: str | None = None

    @model_validator(mode='after')
    def _check(self):
        if self.group is not None and self.group not in GROUPS:
            raise ValueError(f'group must be one of {GROUPS}')
        if self.method is not None and self.command not in (None, 'luna'):
            raise ValueError('method only applies to luna commands')
        return self


class FaultAction(Strict):
    mutate: bool = True
    effect: NumberEffect | None = None
    response: dict[str, Any] | None = None
    response_mode: Literal['merge', 'replace'] = 'replace'
    stale_reads: int | None = Field(default=None, ge=0)
    stale_ms: int | None = Field(default=None, ge=0)
    disconnect: Literal['before', 'after'] | None = None
    exit_status: int | None = Field(default=None, ge=0, le=255)
    stderr: str | None = None
    hang_ms: int = Field(default=0, ge=0, le=120000)
    sftp_abort_after_bytes: int | None = Field(default=None, ge=0)


class FaultRule(Strict):
    id: str
    description: str = ''
    match: FaultMatch = FaultMatch()
    action: FaultAction = FaultAction()
    times: int | None = Field(default=1, ge=1, description='how often the rule fires; null = unlimited')


class Scenario(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    description: str = ''
    fixture: str | None = None
    profile: str | None = None
    seed: int = 1001
    read_after_write_stale_reads: int | None = Field(default=None, ge=0)
    rules: list[FaultRule] = Field(default_factory=list)
    # Documentation of what a client test should observe; checked by tests, not by the simulator.
    expectations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: str = 'SIMULATOR_ASSUMPTION'

    @classmethod
    def load(cls, path: Path) -> Scenario:
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding='utf-8')))


EMPTY_SCENARIO = Scenario(id='none', description='no fault injection')


def load_directory(directory: Path) -> dict[str, Scenario]:
    scenarios = {}
    for path in sorted(Path(directory).glob('*.yaml')):
        scenario = Scenario.load(path)
        if scenario.id in scenarios:
            raise ValueError(f'duplicate scenario id {scenario.id!r}')
        scenarios[scenario.id] = scenario
    return scenarios
