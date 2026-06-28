"""Thin stdio<->HTTP adapter (plan §2.4.1).

Registered as the MCP server in clients (Cursor/Windsurf). It is stateless and
just proxies stdio MCP calls to the resident HTTP host, so the client can spawn
it freely while the real shared core lives in the tray process.
"""
