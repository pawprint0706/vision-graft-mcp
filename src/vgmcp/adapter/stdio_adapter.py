"""stdio -> HTTP proxy adapter (plan §2.4.1).

`vgmcp-adapter` entry point. Clients run this over stdio; it proxies to the
resident tray host. Implemented as a FastMCP proxy so tool listings and calls
pass through transparently.

If the resident host isn't reachable, we still expose a single diagnostic tool
so the LLM gets an actionable message instead of a hard transport failure.
"""

from __future__ import annotations

import os

from ..server.host import DEFAULT_HOST, DEFAULT_PATH, DEFAULT_PORT, server_url


def _resolve_url() -> str:
    override = os.environ.get("VGMCP_SERVER_URL")
    if override:
        return override
    host = os.environ.get("VGMCP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("VGMCP_PORT", str(DEFAULT_PORT)))
    path = os.environ.get("VGMCP_PATH", DEFAULT_PATH)
    return server_url(host, port, path)


def _is_reachable(url: str, timeout: float = 1.5) -> bool:
    import httpx  # noqa: PLC0415

    base = url.rsplit("/", 1)[0] or url
    try:
        # Any response (even 4xx/405) means the host is up.
        httpx.get(base, timeout=timeout)
        return True
    except httpx.HTTPError:
        try:
            httpx.get(url, timeout=timeout)
            return True
        except httpx.HTTPError:
            return False


def _fallback_server(url: str):
    """A minimal MCP server that explains the host is down (plan §2.4.1)."""
    from fastmcp import FastMCP  # noqa: PLC0415

    fb: FastMCP = FastMCP(name="vgmcp-adapter")

    @fb.tool
    def vgmcp_status() -> dict:
        """VGMCP 상주 호스트 연결 상태를 반환한다."""
        return {
            "status": "host_unreachable",
            "server_url": url,
            "message": "VGMCP 트레이 앱(상주 호스트)이 실행 중이지 않습니다.",
            "next_action": "VGMCP 트레이 앱을 실행한 뒤(`vgmcp`) 동일 도구를 재호출하십시오.",
        }

    return fb


def main() -> None:
    url = _resolve_url()
    if _is_reachable(url):
        from fastmcp import FastMCP  # noqa: PLC0415

        proxy = FastMCP.as_proxy(url, name="vgmcp-adapter")
        proxy.run(transport="stdio")
    else:
        _fallback_server(url).run(transport="stdio")


if __name__ == "__main__":
    main()
