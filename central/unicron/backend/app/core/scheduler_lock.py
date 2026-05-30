"""Linux/POSIX scheduler lock utilities (fcntl-only).

Ensures only one process instance starts the APScheduler in multi-worker setups.

Usage:
    from app.core.scheduler_lock import acquire_scheduler_lock, release_scheduler_lock
    if acquire_scheduler_lock("/tmp/herald_health_scheduler.lock"):
        scheduler.start()

On Linux/POSIX, uses fcntl.flock. The file handle is kept open for the life of
the process to hold the lock. This module intentionally does not support
Windows; run Herald in Docker/WSL/Linux.
"""

import errno
import os
import tempfile
from typing import Optional, TextIO

from app.core.config import settings

try:
    import fcntl

    _HAS_FCNTL = True
except Exception:
    _HAS_FCNTL = False

# Keep a module-level reference so the lock is held while process runs
_lock_fp: TextIO | None = None

# Enforce Linux/POSIX only: require fcntl to be available
if not _HAS_FCNTL:
    raise RuntimeError("Backend scheduler locking requires Linux/POSIX (fcntl). " "Run Backend in Docker/WSL/Linux.")


def _default_lock_path(name: str = "unicron_backend_scheduler.lock") -> str:
    """Resolve a default lock path.

    Preference order:
    1) UNICRON_DATA_DIR/locks/<name> when UNICRON_DATA_DIR is set
    2) POSIX /tmp for container environments
    3) System temp directory
    """
    data_dir = settings.UNICRON_DATA_DIR if settings is not None else None
    if data_dir:
        return os.path.join(data_dir, "locks", name)

    posix_tmp = "/tmp"
    if os.path.isdir(posix_tmp) and os.access(posix_tmp, os.W_OK):
        return os.path.join(posix_tmp, name)

    return os.path.join(tempfile.gettempdir(), name)


def acquire_scheduler_lock(lock_path: Optional[str] = None) -> bool:
    """Acquire a process-wide exclusive lock for starting schedulers.

    Returns True if this process acquired the lock, False if another process owns it.
    Safe to call multiple times; subsequent calls will return True if already held.
    """
    global _lock_fp

    if _lock_fp is not None:
        return True

    path = lock_path or _default_lock_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Open file in append/update mode so it exists and is writable
    fp: TextIO = open(path, "a+")
    try:
        # Linux/POSIX non-blocking exclusive file lock
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        except OSError as le:  # another owner has the lock
            if le.errno in (errno.EACCES, errno.EAGAIN):
                fp.close()
                return False
            fp.close()
            raise

        # Write PID for observability
        try:
            fp.seek(0)
            fp.truncate()
            fp.write(str(os.getpid()))
            fp.flush()
            os.fsync(fp.fileno())
        except Exception:
            # Non-fatal; lock still held
            pass

        _lock_fp = fp
        return True
    except Exception:
        # Best-effort cleanup on unexpected errors
        try:
            fp.close()
        except Exception:
            pass
        return False


def release_scheduler_lock() -> None:
    """Release the scheduler lock if held. Safe to call multiple times."""
    global _lock_fp
    if _lock_fp is None:
        return
    try:
        try:
            fcntl.flock(_lock_fp.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        except Exception:
            pass
    finally:
        try:
            _lock_fp.close()
        except Exception:
            pass
        _lock_fp = None


def is_scheduler_lock_held() -> bool:
    return _lock_fp is not None
