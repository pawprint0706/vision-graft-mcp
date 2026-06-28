"""Tiny platform helpers."""

from __future__ import annotations

import importlib.util
import sys


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def module_available(name: str) -> bool:
    """True if a module can be imported without actually importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False
