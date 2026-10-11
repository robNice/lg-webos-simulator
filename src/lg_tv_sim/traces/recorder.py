"""Operation journal: request, client-visible response and real mutations, kept apart.

Every event has a deterministic ``operation_id`` and virtual timestamp; the
``event_hash`` ignores wall-clock and transport details so identical runs
(same fixture, profile, scenario, seed, calls) produce identical hashes.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import threading
from pathlib import Path

from lg_tv_sim.traces.sanitizer import sanitize

VOLATILE_KEYS = {'wall_time', 'connection', 'peer', 'temp_name', 'run_id'}


class VirtualClock:
    def __init__(self, ms_per_tick: int = 100):
        self.ms_per_tick = ms_per_tick
        self.now_ms = 0

    def tick(self) -> int:
        self.now_ms += self.ms_per_tick
        return self.now_ms

    def reset(self) -> None:
        self.now_ms = 0


class Journal:
    def __init__(self, path: Path | None = None, clock: VirtualClock | None = None, limit: int = 20000):
        self.path = path
        self.clock = clock or VirtualClock()
        self.limit = limit
        self._events: list[dict] = []
        self._seq = 0
        self._lock = threading.Lock()

    def record(self, kind: str, **fields) -> dict:
        with self._lock:
            self._seq += 1
            event = {'seq': self._seq, 'operation_id': f'op-{self._seq:06d}', 'virtual_ms': self.clock.now_ms,
                     'wall_time': datetime.datetime.now(datetime.UTC).isoformat(timespec='milliseconds'),
                     'kind': kind, **sanitize(fields)}
            self._events.append(event)
            if len(self._events) > self.limit:
                del self._events[: len(self._events) - self.limit]
            if self.path is not None:
                with open(self.path, 'a', encoding='utf-8') as handle:
                    handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n')
            return event

    def events(self, since: int = 0) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e['seq'] > since]

    def clear(self, path: Path | None = None) -> None:
        with self._lock:
            self._events.clear()
            self._seq = 0
            self.path = path
            self.clock.reset()

    def event_hash(self) -> str:
        return hashlib.sha256(json.dumps([normalize(e) for e in self.events()], sort_keys=True,
                                         ensure_ascii=False).encode()).hexdigest()

    def export(self, destination: Path) -> int:
        events = self.events()
        Path(destination).write_text('\n'.join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in events)
                                     + ('\n' if events else ''), encoding='utf-8')
        return len(events)


def normalize(event: dict) -> dict:
    """Event without volatile fields (wall clock, peer, generated temp names)."""
    return {k: v for k, v in event.items() if k not in VOLATILE_KEYS}
