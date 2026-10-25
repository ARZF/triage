import logging

from app.core.config import Settings


def disable_access_logging() -> None:
    # Access logs are disabled because request URLs contain patient ids.
    logging.getLogger("uvicorn.access").disabled = True


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Keep HTTP client diagnostics from logging headers at DEBUG level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    disable_access_logging()
