"""Configuration persistence + provider registry (plan §4.2.4, §7.3).

Stored at ~/.config/vgmcp/config.json (XDG-style). Only provider metadata and
key references live here — never raw API keys (plan §7.6).

Writes are atomic (temp file + os.replace) and guarded by a file lock so the
two entry points (tray + MCP server) can update concurrently (plan review §9).
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, Field

from .models import ProviderConfig

# Default provider base URLs (plan §7.2).
DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "vgmcp"


def default_target_folder() -> Path:
    return Path.home() / "Pictures" / "vgmcp"


class AppConfig(BaseModel):
    """Top-level persisted configuration."""

    target_folder: str = Field(default_factory=lambda: str(default_target_folder()))
    copy_original: bool = True  # plan §4.2.3 toggle: copy opened images into target folder

    providers: list[ProviderConfig] = Field(default_factory=list)
    default_provider_id: str | None = None   # plan §7.3: first-registered, then last-used
    last_used_provider_id: str | None = None

    # Clipboard supporter (plan §8)
    clipboard_auto: bool = False
    clipboard_template: str | None = None

    # Image preprocessing (plan §7.5)
    max_long_edge: int = 1568
    downscale: str = "auto"  # "auto" | "off"

    # Privacy consent already shown during onboarding (plan §7.9)
    onboarding_consent_shown: bool = False

    # ---- provider registry helpers (plan §7.3) ----------------------------- #
    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        return next((p for p in self.providers if p.id == provider_id), None)

    def add_provider(self, provider: ProviderConfig) -> None:
        if self.get_provider(provider.id):
            raise ValueError(f"provider id already exists: {provider.id}")
        self.providers.append(provider)
        # First registered provider becomes the default (plan §7.3 rule 2).
        if self.default_provider_id is None:
            self.default_provider_id = provider.id

    def remove_provider(self, provider_id: str) -> None:
        self.providers = [p for p in self.providers if p.id != provider_id]
        if self.default_provider_id == provider_id:
            self.default_provider_id = self.providers[0].id if self.providers else None
        if self.last_used_provider_id == provider_id:
            self.last_used_provider_id = None

    def mark_used(self, provider_id: str) -> None:
        """Last-used becomes the effective default going forward (plan §7.3 rule 3)."""
        self.last_used_provider_id = provider_id
        self.default_provider_id = provider_id

    def effective_default(self) -> ProviderConfig | None:
        """Resolve the default provider: last-used wins, else stored default."""
        for pid in (self.last_used_provider_id, self.default_provider_id):
            if pid:
                p = self.get_provider(pid)
                if p:
                    return p
        return self.providers[0] if self.providers else None


# --------------------------------------------------------------------------- #
# Load / save (atomic + locked)
# --------------------------------------------------------------------------- #
def config_path() -> Path:
    return config_dir() / "config.json"


@contextmanager
def _file_lock(target: Path):
    """Best-effort cross-process lock via a sibling .lock file (fcntl)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_file = target.with_suffix(target.suffix + ".lock")
    try:
        import fcntl  # noqa: PLC0415 — POSIX only; Windows uses a different path later

        with open(lock_file, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except ImportError:
        # No fcntl (e.g. Windows) — proceed without locking for now.
        yield


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppConfig()
    return AppConfig.model_validate(data)


def save_config(config: AppConfig) -> None:
    path = config_path()
    with _file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = config.model_dump_json(indent=2, exclude_none=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
