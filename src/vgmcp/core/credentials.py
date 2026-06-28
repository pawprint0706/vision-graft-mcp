"""API-key storage via the OS credential store (plan §7.6).

Keys are NEVER written to config.json. We store them in the OS keychain
(macOS Keychain / Windows Credential Manager) through `keyring`, and the
config only keeps a `key_ref` identifier.

Environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY)
are honored as a fallback for headless/CI scenarios.
"""

from __future__ import annotations

import os

_SERVICE = "vgmcp"

# Provider type -> conventional env var fallback (plan §7.6).
_ENV_FALLBACK: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _keyring():
    """Import keyring lazily so the package imports without it installed."""
    import keyring  # noqa: PLC0415

    return keyring


def set_key(key_ref: str, api_key: str) -> None:
    _keyring().set_password(_SERVICE, key_ref, api_key)


def delete_key(key_ref: str) -> None:
    try:
        _keyring().delete_password(_SERVICE, key_ref)
    except Exception:  # noqa: BLE001 — deleting a non-existent key is fine
        pass


def get_key(key_ref: str | None, *, provider_type: str | None = None) -> str | None:
    """Resolve an API key: keychain first, then env-var fallback by type."""
    if key_ref:
        try:
            value = _keyring().get_password(_SERVICE, key_ref)
        except Exception:  # noqa: BLE001 — keyring backend may be unavailable
            value = None
        if value:
            return value
    if provider_type and provider_type in _ENV_FALLBACK:
        return os.environ.get(_ENV_FALLBACK[provider_type])
    return None


def has_env_fallback(provider_type: str) -> bool:
    var = _ENV_FALLBACK.get(provider_type)
    return bool(var and os.environ.get(var))
