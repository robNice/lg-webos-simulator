"""Isolated run directories: ``<base>/<run_id>/{tv,tmp,snapshots}``.

The simulated ``/mnt/lg/cmn_data/iepg/db/channel.sql`` lives in ``tv/channel.sqlite``;
virtual ``/tmp`` maps to ``tmp/``.  Snapshots use the SQLite backup API.
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from lg_tv_sim import __version__
from lg_tv_sim.domain.identity import IdentityRegistry
from lg_tv_sim.storage import database
from lg_tv_sim.storage.fixtures import Fixture

SNAPSHOT_ID = re.compile(r'snap-\d{4}')


@dataclass
class Run:
    id: str
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / 'tv' / 'channel.sqlite'

    @property
    def tmp_dir(self) -> Path:
        return self.root / 'tmp'

    @property
    def snapshots_dir(self) -> Path:
        return self.root / 'snapshots'

    @property
    def identity_path(self) -> Path:
        return self.root / 'identity.json'

    @property
    def journal_path(self) -> Path:
        return self.root / 'journal.jsonl'

    @property
    def meta(self) -> dict:
        return json.loads((self.root / 'meta.json').read_text(encoding='utf-8'))

    def snapshots(self) -> list[str]:
        return sorted(p.name for p in self.snapshots_dir.iterdir() if SNAPSHOT_ID.fullmatch(p.name))

    def save_snapshot(self, conn, identity: IdentityRegistry, label: str = '') -> str:
        existing = self.snapshots()
        snap_id = f'snap-{len(existing) + 1:04d}'
        target = self.snapshots_dir / snap_id
        target.mkdir(parents=True)
        database.backup(conn, target / 'channel.sqlite')
        identity.save(target / 'identity.json')
        (target / 'label.txt').write_text(label[:200], encoding='utf-8')
        return snap_id

    def snapshot_files(self, snap_id: str) -> tuple[Path, Path]:
        if not SNAPSHOT_ID.fullmatch(snap_id or '') or not (self.snapshots_dir / snap_id).is_dir():
            raise KeyError(f'unknown snapshot {snap_id!r}')
        return self.snapshots_dir / snap_id / 'channel.sqlite', self.snapshots_dir / snap_id / 'identity.json'


class RunManager:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def create(self, fixture: Fixture, profile: str, seed: int) -> tuple[Run, str]:
        """Materialise ``fixture`` into a fresh run; returns the run and the fixture content hash."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        number = 1 + sum(1 for p in self.base_dir.iterdir() if p.is_dir())
        run = Run(f'{stamp}-{number:04d}-{fixture.name}'[:96], self.base_dir / f'{stamp}-{number:04d}-{fixture.name}'[:96])
        for directory in (run.root / 'tv', run.tmp_dir, run.snapshots_dir):
            directory.mkdir(parents=True, exist_ok=False)
        fixture.materialize(run.db_path)
        conn = database.connect(run.db_path, readonly=True)
        try:
            if not database.integrity_ok(conn):
                raise RuntimeError('materialised fixture failed PRAGMA integrity_check')
            problems = database.schema_problems(conn)
            if problems:
                raise RuntimeError('fixture schema incompatible: ' + '; '.join(problems))
            base_hash = database.content_hash(conn)
            tables = ['tuner_on'] + [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ip'")]   # LG Channels get sim IDs too
            keys = sorted((r[0], r[1]) for table in tables for r in conn.execute(
                f'SELECT dvc_chan_id, mso_prdt_itm_code FROM {table}'))
        finally:
            conn.close()
        IdentityRegistry.build(base_hash, keys, fixture.tags).save(run.identity_path)
        meta = {'run_id': run.id, 'fixture': fixture.name, 'fixture_kind': fixture.kind,
                'fixture_content_hash': base_hash, 'profile': profile, 'seed': seed,
                'simulator_version': __version__,
                'created': datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')}
        (run.root / 'meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        return run, base_hash

    def prune(self, keep: int = 20) -> None:
        runs = sorted((p for p in self.base_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
        for old in runs[:-keep]:
            shutil.rmtree(old, ignore_errors=True)
