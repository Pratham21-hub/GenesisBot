"""Unit tests for MockGameAdapter."""

import pytest

from core.models import GameState, ProposedAction
from game.mock_adapter import MockGameAdapter


class TestMockGameAdapter:
    def test_deterministic_turn_progression(self):
        adapter = MockGameAdapter(initial_turn=1, initial_score=0.0)
        assert adapter.is_connected() is True

        state1 = adapter.read_game_state()
        assert state1.turn_number == 1
        assert state1.raw_state["adapter_mode"] == "MOCK"

        action = ProposedAction(action_type="move", parameters={"x": 1, "y": 2})
        result = adapter.submit_action(action)
        assert result.success is True
        assert "[MOCK]" in result.message
        assert result.action_id.startswith("MOCK-ACT-")
        assert result.raw_response["mode"] == "MOCK"

        # Turn should have advanced deterministically
        state2 = adapter.read_game_state()
        assert state2.turn_number == 2
        assert state2.score == 10.0
        assert len(adapter.submitted_actions) == 1

    def test_rejection_mode(self):
        adapter = MockGameAdapter(
            reject_submissions=True,
            rejection_code=422,
            rejection_message="[MOCK] Illegal move in mock arena.",
        )
        action = ProposedAction(action_type="invalid_spell")
        result = adapter.submit_action(action)

        assert result.success is False
        assert result.response_code == 422
        assert "Illegal move" in result.message
        assert adapter.check_submission_result(result) is False

    def test_simulated_network_error(self):
        adapter = MockGameAdapter(simulate_network_error=True)
        action = ProposedAction(action_type="attack")

        with pytest.raises(ConnectionError) as excinfo:
            adapter.submit_action(action)
        assert "[MOCK]" in str(excinfo.value)
        assert len(adapter.submitted_actions) == 1

    def test_simulated_timeout(self):
        adapter = MockGameAdapter(simulate_timeout=True)
        action = ProposedAction(action_type="defend")

        with pytest.raises(TimeoutError) as excinfo:
            adapter.submit_action(action)
        assert "[MOCK]" in str(excinfo.value)

    def test_predefined_states_queue(self):
        s1 = GameState(turn_number=10, score=50.0)
        s2 = GameState(turn_number=11, score=60.0)
        adapter = MockGameAdapter(predefined_states=[s1, s2])

        read1 = adapter.read_game_state()
        assert read1.turn_number == 10

        read2 = adapter.read_game_state()
        assert read2.turn_number == 11
