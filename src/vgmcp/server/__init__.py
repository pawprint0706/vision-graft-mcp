"""MCP server layer.

A FastMCP server exposing VGMCP tools, hosted by the resident tray app over
loopback HTTP/SSE. MCP clients connect via the thin stdio adapter (plan §2.4.1).
"""
