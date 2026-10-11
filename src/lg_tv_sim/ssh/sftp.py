"""Read-only virtual SFTP: only files under the simulated ``/tmp`` can be stat'ed and read.

Paramiko's ``SFTPClient.get`` needs ``stat``, ``open`` (read), ``read``, ``fstat``
and ``close`` (CURRENT_CLIENT_CONFIRMED, app.import_from_tv).  Every write is denied.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import asyncssh

from lg_tv_sim.faults.engine import CallInfo
from lg_tv_sim.ssh.paths import PathDenied

if TYPE_CHECKING:
    from lg_tv_sim.app import Simulator

WRITE_FLAGS = asyncssh.FXF_WRITE | asyncssh.FXF_CREAT | asyncssh.FXF_TRUNC | asyncssh.FXF_APPEND


class _ReadHandle:
    def __init__(self, path: str, handle, abort_after: int | None):
        self.path, self.handle, self.abort_after = path, handle, abort_after
        self.sent = 0


class SimSFTPServer(asyncssh.SFTPServer):
    def __init__(self, chan, simulator: Simulator):
        super().__init__(chan)
        self.sim = simulator
        self.peer = simulator.connection_label(chan.get_extra_info('connection'))

    # ---------------------------------------------------------------- helpers
    def _local(self, path: bytes):
        virtual = self.sim.vfs.normalize(path.decode('utf-8', 'strict'))
        try:
            return virtual, self.sim.vfs.tmp_file(virtual)
        except PathDenied as exc:
            self.sim.journal.record('sftp', op='denied', path=virtual, connection=self.peer, error=str(exc))
            raise asyncssh.SFTPPermissionDenied(f'SIMULATOR: access denied to {virtual}') from None

    @staticmethod
    def _deny(*_, **__):
        raise asyncssh.SFTPPermissionDenied('SIMULATOR: read-only SFTP')

    # ---------------------------------------------------------------- read operations
    def realpath(self, path: bytes) -> bytes:
        return self.sim.vfs.normalize(path.decode('utf-8', 'strict')).encode()

    def stat(self, path: bytes):
        virtual, local = self._local(path)
        if not local.is_file():
            raise asyncssh.SFTPNoSuchFile(f'No such file: {virtual}')
        result = os.stat(local)
        self.sim.journal.record('sftp', op='stat', temp_name=virtual, size=result.st_size, connection=self.peer)
        return result

    lstat = stat

    def open(self, path: bytes, pflags: int, attrs):
        virtual, local = self._local(path)
        if pflags & WRITE_FLAGS:
            self.sim.journal.record('sftp', op='open-write-denied', temp_name=virtual, connection=self.peer)
            raise asyncssh.SFTPPermissionDenied('SIMULATOR: SFTP writes are not supported')
        if not local.is_file():
            raise asyncssh.SFTPNoSuchFile(f'No such file: {virtual}')
        fault = self.sim.faults.select(CallInfo('sftp_read'))
        abort_after = fault.action.sftp_abort_after_bytes if fault else None
        self.sim.journal.record('sftp', op='open', temp_name=virtual, connection=self.peer,
                                fault=fault.rule_id if fault else None)
        return _ReadHandle(virtual, open(local, 'rb'), abort_after)  # noqa: SIM115 - closed in close()

    def read(self, file_obj: _ReadHandle, offset: int, size: int) -> bytes:
        file_obj.handle.seek(offset)
        data = file_obj.handle.read(size)
        if file_obj.abort_after is not None and file_obj.sent + len(data) > file_obj.abort_after:
            self.sim.journal.record('sftp', op='abort', temp_name=file_obj.path, after_bytes=file_obj.abort_after,
                                    connection=self.peer, effect='SFTP_ABORT')
            self.connection.abort()
            raise asyncssh.SFTPFailure('SIMULATOR: transfer aborted by fault injection')
        file_obj.sent += len(data)
        return data

    def fstat(self, file_obj: _ReadHandle):
        return os.fstat(file_obj.handle.fileno())

    def close(self, file_obj: _ReadHandle) -> None:
        file_obj.handle.close()

    # ---------------------------------------------------------------- everything else is denied
    write = remove = rename = posix_rename = mkdir = rmdir = setstat = fsetstat = lsetstat = _deny
    symlink = link = readlink = statvfs = fstatvfs = lock = unlock = fsync = _deny

    def scandir(self, path: bytes):
        raise asyncssh.SFTPPermissionDenied('SIMULATOR: directory listing is not supported')
