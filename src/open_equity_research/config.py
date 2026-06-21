from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError
from .io_utils import atomic_write_text


@dataclass(frozen=True)
class Settings:
    workspace: Path = Path("research")
    sec_user_agent: str = ""
    request_interval_seconds: float = 0.15
    request_timeout_seconds: float = 30.0
    cache_ttl_hours: float = 12.0
    max_retries: int = 3

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        *,
        workspace: Path | None = None,
        sec_user_agent: str | None = None,
    ) -> "Settings":
        data: dict[str, Any] = {}
        selected_path = config_path or Path("oer.toml")
        if selected_path.exists():
            with selected_path.open("rb") as handle:
                parsed = tomllib.load(handle)
            data = parsed.get("open_equity_research", parsed)
            if not isinstance(data, dict):
                raise ConfigurationError(f"Invalid configuration table in {selected_path}")

        settings = cls(
            workspace=Path(data.get("workspace", "research")),
            sec_user_agent=str(data.get("sec_user_agent", "")),
            request_interval_seconds=float(data.get("request_interval_seconds", 0.15)),
            request_timeout_seconds=float(data.get("request_timeout_seconds", 30.0)),
            cache_ttl_hours=float(data.get("cache_ttl_hours", 12.0)),
            max_retries=int(data.get("max_retries", 3)),
        )

        env_user_agent = os.getenv("SEC_USER_AGENT")
        if env_user_agent:
            settings = replace(settings, sec_user_agent=env_user_agent)
        if workspace is not None:
            settings = replace(settings, workspace=workspace)
        if sec_user_agent is not None:
            settings = replace(settings, sec_user_agent=sec_user_agent)
        return settings

    def validate_network_access(self) -> None:
        value = self.sec_user_agent.strip()
        placeholders = ("your name", "your@email", "example.com", "replace me")
        if not value or any(token in value.lower() for token in placeholders):
            raise ConfigurationError(
                "SEC user agent is required. Set sec_user_agent in oer.toml or SEC_USER_AGENT "
                "to a descriptive value such as 'Your Name contact@domain.com'."
            )
        if self.request_interval_seconds < 0.11:
            raise ConfigurationError(
                "request_interval_seconds must be at least 0.11 to stay below the SEC's "
                "10 requests/second fair-access ceiling."
            )
        if self.max_retries < 1:
            raise ConfigurationError("max_retries must be at least 1")


def write_example_config(path: Path, workspace: str = "research") -> None:
    content = f'''# Open Equity Research configuration\n\n[open_equity_research]\nworkspace = "{workspace}"\n# SEC requests must identify the requester and a contact address.\nsec_user_agent = "Your Name your@email.com"\n# 0.15 seconds is about 6.7 requests/second, below the SEC ceiling.\nrequest_interval_seconds = 0.15\nrequest_timeout_seconds = 30\ncache_ttl_hours = 12\nmax_retries = 3\n'''
    atomic_write_text(path, content)
