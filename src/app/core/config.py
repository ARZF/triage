import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    log_level: str = field(
        default_factory=lambda: os.environ.get("APP_LOG_LEVEL", "INFO").upper()
    )

    db_path: str = field(default_factory=lambda: os.environ.get("APP_DB_PATH", "healthcare_agent.db"))

    def __post_init__(self) -> None:
        if not self.db_path.strip():
            raise ValueError("APP_DB_PATH must be non-empty")
        if self.log_level not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("APP_LOG_LEVEL must be INFO, WARNING, ERROR, or CRITICAL")