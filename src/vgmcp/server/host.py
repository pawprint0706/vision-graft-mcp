"""Resident HTTP/SSE host for the MCP server (plan §2.4.1, §2.4.2).

The tray app owns this. It binds to loopback only. The server runs on a
background thread so the macOS main thread is free for the Cocoa run loop and
capture calls (plan §2.4.2).
"""

from __future__ import annotations

import threading

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PATH = "/mcp"


def server_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, path: str = DEFAULT_PATH) -> str:
    return f"http://{host}:{port}{path}"


def run_http(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, path: str = DEFAULT_PATH) -> None:
    """Run the MCP server over streamable HTTP (blocking)."""
    from .app import get_app  # noqa: PLC0415

    app = get_app()
    app.run(transport="http", host=host, port=port, path=path)


def start_background(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, path: str = DEFAULT_PATH
) -> threading.Thread:
    """Start the host on a daemon thread and return it (plan §2.4.2)."""
    thread = threading.Thread(
        target=run_http,
        kwargs={"host": host, "port": port, "path": path},
        name="vgmcp-http-host",
        daemon=True,
    )
    thread.start()
    return thread
