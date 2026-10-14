"""Integration and safety tests for the GenesisBot V2 GameLoop.

Tests every required behavioral mode:
1. Successful mock flow
2. Laya timeout
3. Malformed Laya response
4. Invalid action
5. Game submission rejection
6. Ambiguous submission failure
7. Explicit prevention of submission after any failed Laya decision
8. Inactive/game-over handling
9. Multi-turn autonomous progression
"""

import pytest

from agent.decision_service import DecisionService, InvalidActionError
from agent.laya_client import (
    LayaClient,
    LayaConnectionError,
    LayaError,
    LayaMalformedResponseError,
    LayaResponseError,
    LayaTimeoutError,
)
from core.game_loop import GameLoop, TurnStatus
from core.models import GameState, LayaDecision, ProposedAction, SessionInfo
from game.mock_adapter import MockGameAdapter


def create_valid_decision(action_type: str = "move") -> LayaDecision:
    """Helper to generate a valid LayaDecision for testing."""
    return LayaDecision(
        selected_action=ProposedAction(
            action_type=action_type,
            parameters={"direction": "east"},
            priority=5,
        ),
        confidence_score=0.9,
        rationale=f"Valid {action_type} action selected",
    )


class TestGameLoop:
    def test_successful_mock_flow(self):
        """Verify full 8-step execution under healthy mock conditions."""
        adapter = MockGameAdapter(initial_turn=1, initial_score=10.0)
        client = LayaClient(provider=lambda st, si: create_valid_decision("move"))
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.SUCCESS
        assert record.turn_number == 1
        assert record.action_submitted.action_type == "move"
        assert record.submission_result.success is True
        assert record.resulting_state is not None
        assert record.resulting_state.turn_number == 2
        assert len(adapter.submitted_actions) == 1

    def test_laya_timeout_prevents_submission(self):
        """Verify that Laya timeout halts turn and NEVER submits an action."""
        adapter = MockGameAdapter(initial_turn=1)

        def timing_out_provider(st, si):
            raise LayaTimeoutError("Laya service timed out after 3.0s.")

        client = LayaClient(provider=timing_out_provider)
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.FAILED_LAYA
        assert "timed out" in record.error_message
        assert len(adapter.submitted_actions) == 0  # CRITICAL: zero submissions!

    def test_malformed_laya_response_prevents_submission(self):
        """Verify that malformed Laya output halts turn and NEVER submits an action."""
        adapter = MockGameAdapter(initial_turn=1)

        def malformed_provider(st, si):
            raise LayaMalformedResponseError("Missing selected_action field.")

        client = LayaClient(provider=malformed_provider)
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.FAILED_LAYA
        assert "Missing selected_action" in record.error_message
        assert len(adapter.submitted_actions) == 0  # CRITICAL: zero submissions!

    def test_invalid_action_prevents_submission(self):
        """Verify that an invalid proposed action halts turn and NEVER submits."""
        adapter = MockGameAdapter(initial_turn=1)

        # Action with empty type
        bad_action = ProposedAction(action_type="   ")
        bad_decision = LayaDecision(selected_action=bad_action)
        client = LayaClient(provider=lambda st, si: bad_decision)
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.FAILED_ACTION_VALIDATION
        assert "Action type cannot be empty" in record.error_message
        assert len(adapter.submitted_actions) == 0  # CRITICAL: zero submissions!

    def test_game_submission_rejection_no_blind_retries(self):
        """Verify server rejection is recorded and no blind duplicate retries occur."""
        adapter = MockGameAdapter(
            initial_turn=1,
            reject_submissions=True,
            rejection_code=400,
            rejection_message="[MOCK] Invalid coordinates for move.",
        )
        client = LayaClient(provider=lambda st, si: create_valid_decision("move"))
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.FAILED_SUBMISSION
        assert record.submission_result.success is False
        assert record.submission_result.response_code == 400
        assert "Invalid coordinates" in record.error_message
        assert len(adapter.submitted_actions) == 1  # Exactly 1 submission, NO blind retry!

    def test_ambiguous_submission_failure_no_blind_retries(self):
        """Verify ambiguous network failure during submission is marked UNCERTAIN without blind retries."""
        adapter = MockGameAdapter(
            initial_turn=1,
            simulate_network_error=True,
        )
        client = LayaClient(provider=lambda st, si: create_valid_decision("scout"))
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.AMBIGUOUS_SUBMISSION
        assert "UNCERTAIN" in record.error_message
        assert "Refraining from blind retry" in record.error_message
        assert len(adapter.submitted_actions) == 1  # Exactly 1 attempt, NO duplicate retry!

    @pytest.mark.parametrize(
        "laya_exception",
        [
            LayaTimeoutError("Timeout contacting Laya"),
            LayaConnectionError("Network connection reset"),
            LayaResponseError("HTTP 500 Internal Error"),
            LayaMalformedResponseError("Invalid JSON from Laya"),
            LayaError("General strategic failure"),
        ],
    )
    def test_prevention_of_submission_across_all_laya_failure_modes(self, laya_exception):
        """Exhaustively verify that NO action is ever submitted if Laya fails for ANY reason."""
        adapter = MockGameAdapter(initial_turn=1)

        def failing_provider(st, si):
            raise laya_exception

        client = LayaClient(provider=failing_provider)
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.FAILED_LAYA
        assert len(adapter.submitted_actions) == 0  # Adapter was NEVER called!

    def test_game_over_state_halts_immediately(self):
        """Verify that game loop detects game over state and submits no actions."""
        adapter = MockGameAdapter(initial_turn=10, is_active=False)
        client = LayaClient(provider=lambda st, si: create_valid_decision("move"))
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        record = loop.execute_turn()

        assert record.status == TurnStatus.GAME_OVER
        assert len(adapter.submitted_actions) == 0

    def test_multi_turn_run_progression(self):
        """Verify multi-turn progression across consecutive turns."""
        adapter = MockGameAdapter(initial_turn=1)
        client = LayaClient(provider=lambda st, si: create_valid_decision(f"act_{st.turn_number}"))
        decision_service = DecisionService(laya_client=client)

        loop = GameLoop(adapter=adapter, decision_service=decision_service)
        history = loop.run(max_turns=3)

        assert len(history) == 3
        assert [r.turn_number for r in history] == [1, 2, 3]
        assert all(r.status == TurnStatus.SUCCESS for r in history)
        assert len(adapter.submitted_actions) == 3
