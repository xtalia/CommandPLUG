"""Report whether the optional Command Code CLI is available on PATH.

Nothing is executed and no location is ever returned: callers only learn
``"found"`` or ``"missing"``.
"""

from __future__ import annotations

import ntpath
import os
import posixpath

_FOUND = "found"
_MISSING = "missing"

_WINDOWS_NAMES = ("commandcode.exe", "commandcode.cmd", "cmdc.exe", "cmdc.cmd")
_POSIX_NAMES = ("commandcode",)


def _has_command(directory: str, names: tuple[str, ...], pathmod, windows: bool) -> bool:
    for name in names:
        candidate = pathmod.join(directory, name)
        try:
            if candidate and pathmod.isfile(candidate):
                if windows or os.access(candidate, os.X_OK):
                    return True
        except OSError:
            continue
    return False


def availability(path=None, windows=None) -> str:
    """Return ``"found"`` when the CLI is on ``path``, otherwise ``"missing"``.

    ``path`` defaults to ``os.environ["PATH"]`` and ``windows`` defaults to
    ``os.name == "nt"``. Only absolute, non-empty PATH entries are inspected.
    """
    try:
        if windows is None:
            windows = os.name == "nt"
        windows = bool(windows)
        if path is None:
            path = os.environ.get("PATH", "")

        pathmod = ntpath if windows else posixpath
        names = _WINDOWS_NAMES if windows else _POSIX_NAMES

        for raw in str(path).split(pathmod.pathsep):
            entry = raw.strip()
            if windows:
                entry = entry.strip('"')
            if not entry or not pathmod.isabs(entry):
                continue
            if _has_command(entry, names, pathmod, windows):
                return _FOUND
        return _MISSING
    except Exception:
        return _MISSING
