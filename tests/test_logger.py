"""Unit tests for structured standard-library JSONL logging."""

import json
import logging
import pytest

from core.logger import JSONLFormatter, log_jsonl_event, setup_jsonl_logger
from core.models import GameState, ProposedAction


class TestJSONLFormatter:
    def test_basic_formatting(self):
        formatter = JSONLFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Test log message",
            args=(),
            exc_info=None,
        )
        line = formatter.format(record)
        parsed = json.loads(line)

        assert parsed["logger"] == "test_logger"
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test log message"
        assert "timestamp" in parsed

    def test_formatting_with_pydantic_extra_data(self):
        formatter = JSONLFormatter()
        state = GameState(turn_number=5, score=250.0)
        action = ProposedAction(action_type="jump", priority=3)

        record = logging.LogRecord(
            name="genesis.bot",
            level=logging.INFO,
            pathname=__file__,
            lineno=25,
            msg="Decided action for turn",
            args=(),
            exc_info=None,
        )
        record.extra_data = {
            "current_state": state,
            "chosen_action": action,
            "custom_flag": "alpha",
        }

        line = formatter.format(record)
        parsed = json.loads(line)

        assert parsed["message"] == "Decided action for turn"
        assert "data" in parsed
        assert parsed["data"]["custom_flag"] == "alpha"
        assert parsed["data"]["current_state"]["turn_number"] == 5
        assert parsed["data"]["current_state"]["score"] == 250.0
        assert parsed["data"]["chosen_action"]["action_type"] == "jump"

    def test_formatting_with_exception(self):
        formatter = JSONLFormatter()
        try:
            raise ValueError("Simulated network timeout")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="error_logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=50,
            msg="Adapter error",
            args=(),
            exc_info=exc_info,
        )
        line = formatter.format(record)
        parsed = json.loads(line)

        assert parsed["level"] == "ERROR"
        assert "exception" in parsed
        assert "Simulated network timeout" in parsed["exception"]


class TestSetupJSONLLogger:
    def test_file_logging(self, tmp_path):
        log_file = tmp_path / "subfolder" / "test_audit.jsonl"
        logger_name = f"test_jsonl_{tmp_path.name}"
        logger = setup_jsonl_logger(
            name=logger_name,
            log_file=log_file,
            level="DEBUG",
            console_output=False,
        )

        logger.info("First line of JSONL")
        log_jsonl_event(logger, logging.DEBUG, "Second line with data", tick=1, status="ok")

        # Flush and read file
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1["message"] == "First line of JSONL"
        assert entry1["level"] == "INFO"

        entry2 = json.loads(lines[1])
        assert entry2["message"] == "Second line with data"
        assert entry2["level"] == "DEBUG"
        assert entry2["data"]["tick"] == 1
        assert entry2["data"]["status"] == "ok"
