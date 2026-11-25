"""Single-host ownership for the cooperating reference Core processes.

The database and its persistent sidecar must reside on a trusted local
filesystem with working OS file locking. External writes, replacement of
either file, shared network filesystems and forked Core instances are outside
this reference trust model. Never delete the sidecar to recover authority.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import threading

import portalocker


class OwnershipError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_registry: set[str] = set()
_registry_lock = threading.Lock()


def canonical_database(path: str | Path) -> Path:
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or raw == ":memory:" or raw.startswith("file:"):
        raise ValueError("Persistent SQLite database required for Core fencing")
    resolved = Path(raw).resolve()
    if os.name == "nt" and str(resolved).startswith("\\\\"):
        raise OwnershipError("unsupported_database_path")
    _check_regular(resolved)
    return resolved


def _check_regular(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise OwnershipError("unsupported_database_path")


class CoreOwnership:
    """Hold a non-blocking exclusive OS lock until explicit Core shutdown."""

    def __init__(self, database: Path):
        self.pid = os.getpid()
        self.key = os.path.normcase(str(database))
        self.path = database.with_name(database.name + ".core.lock")
        self.handle = None
        with _registry_lock:
            if self.key in _registry:
                raise OwnershipError("core_already_running")
            _registry.add(self.key)
        try:
            _check_regular(self.path)
            handle = self.path.open("a+b")
            try:
                handle.seek(0)
                portalocker.lock(
                    handle, portalocker.LockFlags.EXCLUSIVE | portalocker.LockFlags.NON_BLOCKING
                )
                _check_regular(database)
                _check_regular(self.path)
            except BaseException:
                handle.close()
                raise
            self.handle = handle
        except BaseException as error:
            with _registry_lock:
                _registry.discard(self.key)
            if isinstance(error, portalocker.exceptions.AlreadyLocked):
                raise OwnershipError("core_already_running") from error
            if isinstance(error, (OSError, portalocker.exceptions.LockException)):
                raise OwnershipError("core_lock_unavailable") from error
            raise

    def require(self) -> None:
        if self.pid != os.getpid():
            raise OwnershipError("forked_core_not_supported")
        if self.handle is None or self.handle.closed:
            raise OwnershipError("core_closed")

    def close(self) -> None:
        if self.pid != os.getpid():
            raise OwnershipError("forked_core_not_supported")
        handle = self.handle
        if handle is None:
            return
        self.handle = None
        try:
            handle.seek(0)
            portalocker.unlock(handle)
        finally:
            try:
                handle.close()
            finally:
                with _registry_lock:
                    _registry.discard(self.key)
