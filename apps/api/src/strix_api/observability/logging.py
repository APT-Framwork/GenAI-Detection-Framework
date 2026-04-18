"""structlog configuration.

Every log line is a JSON object carrying the fields enumerated in §8.1:
`ts, level, logger, service, host, pid, traceId, spanId, alertId?, chainId?,
hostId?, message, extra{...}`. Request-scope keys are bound via
`structlog.contextvars.bind_contextvars()` at pipeline entry.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

_HOST = socket.gethostname()
_PID = os.getpid()


def _inject_static_fields(
    _logger: logging.Logger, _method: str, event_dict: EventDict
) -> EventDict:
    event_dict.setdefault("host", _HOST)
    event_dict.setdefault("pid", _PID)
    return event_dict


def _inject_service_name(service_name: str) -> Processor:
    def _processor(_logger: logging.Logger, _method: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service", service_name)
        return event_dict

    return _processor


def configure_logging(*, service_name: str, level: str = "INFO", json_output: bool = True) -> None:
    """Call once at process startup (API + every worker).

    Safe to call repeatedly — later calls overwrite the config.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _inject_service_name(service_name),
        _inject_static_fields,
    ]

    if json_output:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route the stdlib logger into structlog so third-party libs (uvicorn,
    # sqlalchemy, etc.) also emit JSON lines.
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    logger = structlog.get_logger(name) if name else structlog.get_logger()
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger
