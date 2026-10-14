"""GenesisBot V2 Configuration Module.

Provides typed, validated configuration loading from local environment
variables and `.env` files using Pydantic and python-dotenv.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Application configuration schema for GenesisBot V2.

    Validates all runtime settings required by the bot, game adapters,
    and audit logging infrastructure.
    """

    env: str = Field(
        default="development",
        description="Runtime environment name (e.g. development, testing, production).",
    )
    bot_name: str = Field(
        default="GenesisBot",
        description="Display name or identifier for the bot agent.",
    )
    bot_version: str = Field(
        default="2.0.0",
        description="Version string for GenesisBot V2.",
    )
    api_base_url: Optional[str] = Field(
        default=None,
        description=(
            "Base URL for the competition game server API (provisional placeholder). "
            "To be configured when official hackathon API endpoints are announced."
        ),
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Authentication API key or bearer token (never commit real keys).",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Active competition game session identifier.",
    )
    poll_interval_sec: float = Field(
        default=1.0,
        ge=0.01,
        description="Interval in seconds between game state polls.",
    )
    request_timeout_sec: float = Field(
        default=5.0,
        gt=0.0,
        description="HTTP request timeout in seconds for game adapter network calls.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts on transient network or adapter errors.",
    )
    log_level: str = Field(
        default="INFO",
        description="Standard logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    log_file: str = Field(
        default="logs/bot_audit.jsonl",
        description="File path for structured JSONL audit logs.",
    )


def load_config(env_file: Optional[Path | str] = None) -> AppConfig:
    """Load and validate configuration from environment variables and `.env`.

    Args:
        env_file: Optional custom path to a `.env` file. If omitted, default
            `.env` resolution in current working directory or ancestors is used.

    Returns:
        AppConfig: Validated application configuration instance.
    """
    if env_file is not None:
        load_dotenv(dotenv_path=env_file, override=True)
    else:
        load_dotenv(override=False)

    return AppConfig(
        env=os.getenv("GENESIS_ENV", "development"),
        bot_name=os.getenv("GENESIS_BOT_NAME", "GenesisBot"),
        bot_version=os.getenv("GENESIS_BOT_VERSION", "2.0.0"),
        api_base_url=os.getenv("GENESIS_API_BASE_URL"),
        api_key=os.getenv("GENESIS_API_KEY"),
        session_id=os.getenv("GENESIS_SESSION_ID"),
        poll_interval_sec=float(os.getenv("GENESIS_POLL_INTERVAL_SEC", "1.0")),
        request_timeout_sec=float(os.getenv("GENESIS_REQUEST_TIMEOUT_SEC", "5.0")),
        max_retries=int(os.getenv("GENESIS_MAX_RETRIES", "3")),
        log_level=os.getenv("GENESIS_LOG_LEVEL", "INFO").upper(),
        log_file=os.getenv("GENESIS_LOG_FILE", "logs/bot_audit.jsonl"),
    )
