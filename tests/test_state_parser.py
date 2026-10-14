"""Unit tests for GameStateParser and state validation."""

import pytest

from core.models import GameState
from game.state_parser import GameStateParser, StateValidationError


class TestGameStateParser:
    def test_parse_valid_raw_dict(self):
        raw = {
            "turn_number": 3,
            "is_active": True,
            "score": 45.0,
            "time_remaining_ms": 500,
            "raw_state": {"board": [[0, 1], [1, 0]]},
        }
        state = GameStateParser.parse_raw(raw)
        assert isinstance(state, GameState)
        assert state.turn_number == 3
        assert state.score == 45.0
        assert state.raw_state["board"] == [[0, 1], [1, 0]]

    def test_parse_non_dict_raises(self):
        with pytest.raises(StateValidationError) as excinfo:
            GameStateParser.parse_raw("invalid json string")  # type: ignore
        assert "Expected dictionary payload" in str(excinfo.value)

    def test_parse_invalid_payload_raises(self):
        with pytest.raises(StateValidationError) as excinfo:
            GameStateParser.parse_raw({"turn_number": -5})
        assert "Invalid game state payload" in str(excinfo.value)

    def test_validate_none_state_raises(self):
        with pytest.raises(StateValidationError) as excinfo:
            GameStateParser.validate_state(None)  # type: ignore
        assert "cannot be None" in str(excinfo.value)

    def test_validate_non_gamestate_raises(self):
        with pytest.raises(StateValidationError) as excinfo:
            GameStateParser.validate_state({"turn_number": 1})  # type: ignore
        assert "Expected GameState instance" in str(excinfo.value)

    def test_monotonic_turn_transition(self):
        prev = GameState(turn_number=5)
        curr = GameState(turn_number=6)
        assert GameStateParser.validate_state(curr, previous_state=prev) == curr

        regressed = GameState(turn_number=4)
        with pytest.raises(StateValidationError) as excinfo:
            GameStateParser.validate_state(regressed, previous_state=prev)
        assert "Turn number decreased" in str(excinfo.value)

    def test_infinite_score_validation(self):
        state = GameState(turn_number=1)
        state.score = float("inf")
        with pytest.raises(StateValidationError) as excinfo:
            GameStateParser.validate_state(state)
        assert "finite number" in str(excinfo.value)

    def test_sanitize_for_logging_redacts_keys(self):
        state = GameState(
            turn_number=1,
            raw_state={
                "public_info": 123,
                "api_key": "super_secret_token",
                "auth_header": "Bearer xyz",
            },
        )
        sanitized = GameStateParser.sanitize_for_logging(state)
        assert sanitized["raw_state"]["public_info"] == 123
        assert sanitized["raw_state"]["api_key"] == "******"
        assert sanitized["raw_state"]["auth_header"] == "******"
