"""
Structured logging configuration.

Sets up JSON-formatted logs with timestamps and log levels.
Optionally integrates Sentry for error tracking.

Usage:
    from logging_config import setup_logging
    setup_logging()  # call once at startup
"""

import logging
import logging.config
import os
import sys

try:
    from pythonjsonlogger import jsonlogger
    _JSON_LOGGER_AVAILABLE = True
except ImportError:
    _JSON_LOGGER_AVAILABLE = False

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    _SENTRY_AVAILABLE = True
except ImportError:
    _SENTRY_AVAILABLE = False


class _CustomJsonFormatter(jsonlogger.JsonFormatter if _JSON_LOGGER_AVAILABLE else logging.Formatter):
    """Adds 'service' and 'env' fields to every log record."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["service"] = "crm-agent"
        log_record["env"] = os.getenv("ENV", "development")
        log_record["level"] = record.levelname


def setup_logging() -> None:
    """
    Configure the root logger.

    - JSON output when python-json-logger is installed (production).
    - Human-readable output otherwise (development / CI).
    - Initialises Sentry when SENTRY_DSN is set in the environment.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    if _JSON_LOGGER_AVAILABLE:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            _CustomJsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "googleapiclient"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── Sentry ───────────────────────────────────────────────────────────────
    sentry_dsn = os.getenv("SENTRY_DSN", "")
    if sentry_dsn and _SENTRY_AVAILABLE:
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=os.getenv("ENV", "development"),
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(
                    level=logging.WARNING,       # breadcrumbs from WARNING+
                    event_level=logging.ERROR,   # send events for ERROR+
                ),
            ],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        )
        logging.getLogger(__name__).info("Sentry initialised")
    elif sentry_dsn and not _SENTRY_AVAILABLE:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk is not installed — "
            "run: pip install sentry-sdk"
        )

    logging.getLogger(__name__).info(
        "Logging configured level=%s json=%s sentry=%s",
        log_level,
        _JSON_LOGGER_AVAILABLE,
        bool(sentry_dsn and _SENTRY_AVAILABLE),
    )
