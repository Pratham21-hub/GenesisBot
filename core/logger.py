"""Structured JSONL logging using Python's standard library.

Provides a JSONLFormatter and logger configuration utility that serializes
log events into JSON Lines format. This provides a transparent, machine-readable
audit trail for game states, Laya decisions, action submissions, and errors.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel


class JSONLFormatter(logging.Formatter):
    """Custom logging formatter that emits one valid JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a LogRecord instance into a single-line JSON string."""
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include structured extra data if provided
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            # Convert any nested Pydantic models to serializable dicts
            clean_extra: Dict[str, Any] = {}
            for key, val in record.extra_data.items():
                if isinstance(val, BaseModel):
                    clean_extra[key] = val.model_dump(mode="json")
                else:
                    clean_extra[key] = val
            log_entry["data"] = clean_extra

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_jsonl_logger(
    name: str = "genesis_bot",
    log_file: Optional[str | Path] = None,
    level: str = "INFO",
    console_output: bool = True,
) -> logging.Logger:
    """Configure and return a standard library logger configured for JSONL output.

    Args:
        name: Logger hierarchy name.
        log_file: Optional path to write JSONL logs. If provided, parent directories
            are created automatically.
        level: Minimum log level string (e.g. 'DEBUG', 'INFO').
        console_output: Whether to also attach a console stream handler.

    Returns:
        logging.Logger configured with JSONLFormatter.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Prevent duplicate handlers on repeated setup calls
    if not logger.handlers:
        formatter = JSONLFormatter()

        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger


def log_jsonl_event(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra_data: Any,
) -> None:
    """Helper to log an event with structured extra data for JSONL serialization.

    Args:
        logger: Target logger instance.
        level: Integer logging level (e.g. logging.INFO).
        message: Log message string.
        **extra_data: Arbitrary structured key-value data to serialize in the record.
    """
    logger.log(level, message, extra={"extra_data": extra_data})
