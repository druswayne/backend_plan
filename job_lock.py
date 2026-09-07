"""Межпроцессная блокировка для фоновых задач (Windows и Linux)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


class _LockHandle:
    __slots__ = ("path", "_fh")

    def __init__(self, path: str, fh):
        self.path = path
        self._fh = fh

    def release(self) -> None:
        fh = self._fh
        self._fh = None
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            fh.close()


def _ensure_lock_file(path: str):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    # На Windows msvcrt.locking требует непустой файл.
    with open(path, "a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"0")
            fh.flush()


def _open_lock(path: str) -> _LockHandle:
    _ensure_lock_file(path)
    fh = open(path, "r+b")
    fh.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    return _LockHandle(path, fh)


def try_open_lock(path: str) -> _LockHandle | None:
    _ensure_lock_file(path)
    fh = open(path, "r+b")
    try:
        fh.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return _LockHandle(path, fh)


@contextmanager
def exclusive_lock(path: str) -> Iterator[None]:
    handle = _open_lock(path)
    try:
        yield
    finally:
        handle.release()
