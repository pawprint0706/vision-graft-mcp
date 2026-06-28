"""Shared core logic.

Both the MCP tool layer (server) and the tray UI layer call into this package,
so capture / vision / clipboard / environment-checking is implemented exactly
once (plan §2.2, §2.3).
"""
