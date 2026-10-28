"""Настройки из окружения / .env. Секреты в репозиторий не попадают (.env в .gitignore)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    host: str = os.environ.get("HIDENSEEK_HOST", "127.0.0.1")
    port: int = _int("HIDENSEEK_PORT", 8000)
    data_dir: Path = Path(os.environ.get("HIDENSEEK_DATA_DIR", ROOT / "data"))

    smtp_host: str = os.environ.get("SMTP_HOST", "")
    smtp_port: int = _int("SMTP_PORT", 587)
    smtp_user: str = os.environ.get("SMTP_USER", "")
    smtp_password: str = os.environ.get("SMTP_PASSWORD", "")
    smtp_from: str = os.environ.get("SMTP_FROM", "") or os.environ.get("SMTP_USER", "")

    github_client_id: str = os.environ.get("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.environ.get("GITHUB_CLIENT_SECRET", "")
    github_token: str = os.environ.get("GITHUB_TOKEN", "")
    hibp_api_key: str = os.environ.get("HIBP_API_KEY", "")

    encrypt: bool = os.environ.get("HIDENSEEK_ENCRYPT", "1") not in ("0", "false", "no")
    key_file: Path = Path(os.environ.get("HIDENSEEK_KEY_FILE", Path.home() / ".config" / "hidenseek" / "key"))
    key: str = os.environ.get("HIDENSEEK_KEY", "")
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    assistant_model: str = os.environ.get("HIDENSEEK_ASSISTANT_MODEL", "claude-opus-5-5")
    scheduler_interval: int = _int("SCHEDULER_INTERVAL", 60)

    verify_ttl_days: int = _int("VERIFY_TTL_DAYS", 90)
    max_depth: int = _int("AUDIT_MAX_DEPTH", 2)
    max_facts: int = _int("AUDIT_MAX_FACTS", 30)
    module_retries: int = _int("MODULE_RETRIES", 2)
    module_delay: float = float(os.environ.get("MODULE_DELAY", "1.0"))

    user_agent: str = field(default="HidenSeek-self-audit/0.2")

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)


settings = Settings()
