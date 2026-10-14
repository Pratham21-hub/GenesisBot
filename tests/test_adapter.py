"""Unit tests for BaseGameAdapter interface contract."""

import pytest

from core.models import ActionSubmissionResult, GameState, ProposedAction
from game.base_adapter import BaseGameAdapter


class TestBaseGameAdapterContract:
    def test_cannot_instantiate_abstract_adapter(self):
        with pytest.raises(TypeError) as excinfo:
            BaseGameAdapter()  # type: ignore
        assert "abstract method" in str(excinfo.value)

    def test_incomplete_subclass_raises_type_error(self):
        class IncompleteAdapter(BaseGameAdapter):
            def read_game_state(self) -> GameState:
                return GameState()

        with pytest.raises(TypeError) as excinfo:
            IncompleteAdapter()  # type: ignore
        assert "abstract method" in str(excinfo.value)

    def test_concrete_adapter_implementation(self):
        class MockGameAdapter(BaseGameAdapter):
            def __init__(self):
                self._current_turn = 1
                self.submitted_actions = []

            def read_game_state(self) -> GameState:
                return GameState(
                    turn_number=self._current_turn,
                    is_active=True,
                    score=100.0,
                    raw_state={"mock": True},
                )

            def submit_action(self, action: ProposedAction) -> ActionSubmissionResult:
                self.submitted_actions.append(action)
                self._current_turn += 1
                return ActionSubmissionResult(
                    success=True,
                    action_id=f"act-{len(self.submitted_actions)}",
                    response_code=200,
                    latency_ms=12.5,
                )

            def check_submission_result(self, result: ActionSubmissionResult) -> bool:
                return result.success and result.response_code == 200

        adapter = MockGameAdapter()
        assert adapter.is_connected() is True
        assert adapter.connect() is True

        state = adapter.read_game_state()
        assert isinstance(state, GameState)
        assert state.turn_number == 1
        assert state.raw_state == {"mock": True}

        action = ProposedAction(action_type="scout", parameters={"radius": 3})
        result = adapter.submit_action(action)
        assert isinstance(result, ActionSubmissionResult)
        assert result.success is True
        assert result.action_id == "act-1"
        assert adapter.check_submission_result(result) is True

        # Turn should have advanced in mock state
        next_state = adapter.read_game_state()
        assert next_state.turn_number == 2

        adapter.close()
