"""Compare a recorded trace with a replayed one; report the first divergence explicitly."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lg_tv_sim.traces.recorder import normalize

COMPARED_KEYS = ('kind', 'command', 'service', 'method', 'params', 'response', 'exit_status', 'effect', 'fault')


@dataclass
class Divergence:
    index: int
    field: str
    expected: object
    actual: object

    def __str__(self) -> str:
        return f'event #{self.index}: {self.field} differs (expected {self.expected!r}, got {self.actual!r})'


def load(path: Path) -> list[dict]:
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def compare(expected: list[dict], actual: list[dict]) -> Divergence | None:
    for index, (want, got) in enumerate(zip(expected, actual, strict=False)):
        want, got = normalize(want), normalize(got)
        for key in COMPARED_KEYS:
            if want.get(key) != got.get(key):
                return Divergence(index, key, want.get(key), got.get(key))
    if len(expected) != len(actual):
        index = min(len(expected), len(actual))
        return Divergence(index, 'length', len(expected), len(actual))
    return None
