"""Deterministic fault selection.  No randomness without an explicit seed (and none is needed so far)."""
from __future__ import annotations

import random
import threading
from collections import Counter
from dataclasses import dataclass

from lg_tv_sim.faults.schema import EMPTY_SCENARIO, FaultAction, FaultMatch, FaultRule, Scenario


@dataclass(frozen=True)
class CallInfo:
    command: str
    service: str | None = None
    method: str | None = None
    channel_ids: tuple[str, ...] = ()
    sim_tags: tuple[str, ...] = ()
    target_number: int | None = None
    groups: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppliedFault:
    rule_id: str
    action: FaultAction


class FaultEngine:
    def __init__(self, scenario: Scenario = EMPTY_SCENARIO):
        self._lock = threading.Lock()
        self.activate(scenario)

    def activate(self, scenario: Scenario) -> None:
        with self._lock:
            self.scenario = scenario
            self.random = random.Random(scenario.seed)
            self._matches: Counter[str] = Counter()
            self._fired: Counter[str] = Counter()

    def reset_counters(self) -> None:
        self.activate(self.scenario)

    def select(self, call: CallInfo) -> AppliedFault | None:
        """Count the call against every rule's match and return the first rule that fires."""
        with self._lock:
            chosen = None
            for rule in self.scenario.rules:
                if not _matches_static(rule.match, call):
                    continue
                self._matches[rule.id] += 1
                if chosen is not None:
                    continue
                if rule.match.nth_call is not None and self._matches[rule.id] != rule.match.nth_call:
                    continue
                if rule.times is not None and self._fired[rule.id] >= rule.times:
                    continue
                self._fired[rule.id] += 1
                chosen = rule
            return AppliedFault(chosen.id, chosen.action) if chosen else None

    def status(self) -> dict:
        with self._lock:
            return {'scenario': self.scenario.id, 'rules': [_rule_status(r, self._matches, self._fired)
                                                            for r in self.scenario.rules]}


def _rule_status(rule: FaultRule, matches: Counter, fired: Counter) -> dict:
    return {'id': rule.id, 'description': rule.description, 'matched': matches[rule.id], 'fired': fired[rule.id]}


def _matches_static(match: FaultMatch, call: CallInfo) -> bool:
    command = match.command or ('luna' if (match.service or match.method) else None)
    return all((
        command is None or command == call.command,
        match.service is None or match.service == call.service,
        match.method is None or match.method == call.method,
        match.channel_id is None or match.channel_id in call.channel_ids,
        match.sim_tag is None or match.sim_tag in call.sim_tags,
        match.target_number is None or match.target_number == call.target_number,
        match.group is None or match.group in call.groups,
    ))
