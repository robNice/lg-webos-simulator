"""Virtual TV paths mapped into the run sandbox.  Nothing outside the run directory is ever touched."""
from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

from lg_tv_sim.storage.snapshots import Run

TV_CHANNEL_DB = '/mnt/lg/cmn_data/iepg/db/channel.sql'
TMP_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')


class PathDenied(PermissionError):
    pass


class VirtualFileSystem:
    def __init__(self, run: Callable[[], Run]):
        self._run = run

    @staticmethod
    def is_database(path: str) -> bool:
        return path == TV_CHANNEL_DB

    @staticmethod
    def tmp_name(path: str) -> str:
        if not isinstance(path, str) or not path.startswith('/tmp/'):
            raise PathDenied(f'path outside the simulated /tmp: {path!r}')
        name = path[len('/tmp/'):]
        if not TMP_NAME.fullmatch(name) or '..' in name:
            raise PathDenied(f'invalid temporary file name: {path!r}')
        return name

    def tmp_file(self, path: str) -> Path:
        """Local file for a virtual ``/tmp/<name>``; refuses traversal and symlinks."""
        tmp_dir = self._run().tmp_dir.resolve()
        local = tmp_dir / self.tmp_name(path)
        if local.is_symlink() or local.resolve().parent != tmp_dir:
            raise PathDenied(f'refusing symlink or escaping path: {path!r}')
        return local

    def normalize(self, path: str) -> str:
        normalized = os.path.normpath('/' + path.lstrip('/')) if path else '/'
        return normalized.replace('//', '/')
