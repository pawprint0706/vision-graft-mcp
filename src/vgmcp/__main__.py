"""Enable `python -m vgmcp` (and `pythonw -m vgmcp` for console-less autostart)."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
