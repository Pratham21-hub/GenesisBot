"""Unit tests for GenesisBot V2 configuration loader and AppConfig schema."""

import pytest
from pydantic import ValidationError

from config import AppConfig, load_config


class TestAppConfig:
    def test_default_values(self):
        config = AppConfig()
        assert config.env == "development"
        assert config.bot_name == "GenesisBot"
        assert config.bot_version == "2.0.0"
        assert config.api_base_url is None
        assert config.api_key is None
        assert config.session_id is None
        assert config.poll_interval_sec == 1.0
        assert config.request_timeout_sec == 5.0
        assert config.max_retries == 3
        assert config.log_level == "INFO"
        assert config.log_file == "logs/bot_audit.jsonl"

    def test_invalid_poll_interval(self):
        with pytest.raises(ValidationError):
            AppConfig(poll_interval_sec=0.0)

    def test_invalid_request_timeout(self):
        with pytest.raises(ValidationError):
            AppConfig(request_timeout_sec=-1.0)

    def test_invalid_max_retries(self):
        with pytest.raises(ValidationError):
            AppConfig(max_retries=-1)


class TestLoadConfig:
    def test_load_from_environment(self, monkeypatch):
        monkeypatch.setenv("GENESIS_ENV", "production")
        monkeypatch.setenv("GENESIS_BOT_NAME", "AlphaGenesis")
        monkeypatch.setenv("GENESIS_BOT_VERSION", "2.1.0")
        monkeypatch.setenv("GENESIS_API_BASE_URL", "https://api.test-hackathon.org")
        monkeypatch.setenv("GENESIS_API_KEY", "secret-test-token")
        monkeypatch.setenv("GENESIS_SESSION_ID", "sess-999")
        monkeypatch.setenv("GENESIS_POLL_INTERVAL_SEC", "0.5")
        monkeypatch.setenv("GENESIS_REQUEST_TIMEOUT_SEC", "2.5")
        monkeypatch.setenv("GENESIS_MAX_RETRIES", "5")
        monkeypatch.setenv("GENESIS_LOG_LEVEL", "debug")
        monkeypatch.setenv("GENESIS_LOG_FILE", "logs/custom.jsonl")

        config = load_config()

        assert config.env == "production"
        assert config.bot_name == "AlphaGenesis"
        assert config.bot_version == "2.1.0"
        assert config.api_base_url == "https://api.test-hackathon.org"
        assert config.api_key == "secret-test-token"
        assert config.session_id == "sess-999"
        assert config.poll_interval_sec == 0.5
        assert config.request_timeout_sec == 2.5
        assert config.max_retries == 5
        assert config.log_level == "DEBUG"
        assert config.log_file == "logs/custom.jsonl"
