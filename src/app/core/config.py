import math
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def _llm_timeout() -> float:
    try:
        return float(os.environ.get("APP_LLM_TIMEOUT_SECONDS", "30"))
    except ValueError:
        raise ValueError("APP_LLM_TIMEOUT_SECONDS") from None



def _bool_env(name: str, default: str) -> bool:
    value = os.environ.get(name, default).casefold()
    if value not in ("true", "false"):
        raise ValueError(name)
    return value == "true"


def _int_env(name: str, default: str, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        raise ValueError(name) from None
    if not lower <= value <= upper:
        raise ValueError(name)
    return value


@dataclass(frozen=True)
class Settings:
    log_level: str = field(
        default_factory=lambda: os.environ.get("APP_LOG_LEVEL", "INFO").upper()
    )
    db_path: str = field(default_factory=lambda: os.environ.get("APP_DB_PATH", "healthcare_agent.db"))
    llm_base_url: str | None = field(default_factory=lambda: os.environ.get("APP_LLM_BASE_URL") or None)
    llm_api_key: str | None = field(default_factory=lambda: os.environ.get("APP_LLM_API_KEY") or None, repr=False)
    llm_model: str | None = field(default_factory=lambda: os.environ.get("APP_LLM_MODEL") or None)
    llm_timeout_seconds: float = field(default_factory=_llm_timeout)
    codex_home: str | None = field(default_factory=lambda: os.environ.get("APP_CODEX_HOME") or None, repr=False)
    codex_model: str | None = field(default_factory=lambda: os.environ.get("APP_CODEX_MODEL") or None)

    cookie_secure: bool = field(default_factory=lambda: _bool_env("APP_COOKIE_SECURE", "false"))
    session_ttl_hours: int = field(default_factory=lambda: _int_env("APP_SESSION_TTL_HOURS", "12", 1, 168))
    demo_doctor_password: str | None = field(default_factory=lambda: os.environ.get("APP_DEMO_DOCTOR_PASSWORD") or None, repr=False)
    doctor_auto_verify: bool = field(default_factory=lambda: _bool_env("APP_DOCTOR_AUTO_VERIFY", "false"))
    request_ttl_minutes: int = field(default_factory=lambda: _int_env("APP_REQUEST_TTL_MINUTES", "30", 1, 1440))
    admin_username: str | None = field(default_factory=lambda: os.environ.get("APP_ADMIN_USERNAME") or None, repr=False)
    admin_password: str | None = field(default_factory=lambda: os.environ.get("APP_ADMIN_PASSWORD") or None, repr=False)

    def __post_init__(self) -> None:
        for name, value in (("APP_CODEX_HOME", self.codex_home), ("APP_CODEX_MODEL", self.codex_model)):
            if value is not None and (not value.strip() or any(ord(char) < 32 for char in value)):
                raise ValueError(name)
        if bool(self.admin_username) != bool(self.admin_password):
            raise ValueError("APP_ADMIN_USERNAME and APP_ADMIN_PASSWORD")
        if self.admin_username is not None and not re.fullmatch(r"[a-z0-9_.-]{3,32}", self.admin_username):
            raise ValueError("APP_ADMIN_USERNAME")
        if self.admin_password is not None and not 12 <= len(self.admin_password) <= 128:
            raise ValueError("APP_ADMIN_PASSWORD")
        if self.demo_doctor_password is not None and not 8 <= len(self.demo_doctor_password) <= 128:
            raise ValueError("APP_DEMO_DOCTOR_PASSWORD")
        if not self.db_path.strip():
            raise ValueError("APP_DB_PATH must be non-empty")
        if self.log_level not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("APP_LOG_LEVEL must be INFO, WARNING, ERROR, or CRITICAL")
        if self.llm_base_url is not None:
            try:
                url = urlsplit(self.llm_base_url)
                valid = (
                    url.scheme in ("http", "https") and url.hostname and url.port != 0
                    and not url.username and not url.password and not url.query and not url.fragment
                    and not any(char.isspace() or ord(char) < 32 for char in self.llm_base_url)
                    and "\\" not in self.llm_base_url
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("APP_LLM_BASE_URL") from None
        for name, value in (("APP_LLM_MODEL", self.llm_model), ("APP_LLM_API_KEY", self.llm_api_key)):
            if value is not None and (not value.strip() or any(ord(char) < 32 for char in value)):
                raise ValueError(name)
        if self.llm_api_key is not None and not self.llm_api_key.isascii():
            raise ValueError("APP_LLM_API_KEY")
        if not math.isfinite(self.llm_timeout_seconds) or not 1 <= self.llm_timeout_seconds <= 120:
            raise ValueError("APP_LLM_TIMEOUT_SECONDS")

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)
