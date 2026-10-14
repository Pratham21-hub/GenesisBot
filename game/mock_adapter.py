"""Deterministic mock game adapter for GenesisBot V2.

This adapter is strictly for local automated tests, CI pipelines, and offline
agent development. ALL activity is explicitly tagged as [MOCK] and must never
be represented as live tournament results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.models import ActionSubmissionResult, GameState, ProposedAction
from game.base_adapter import BaseGameAdapter


class MockGameAdapter(BaseGameAdapter):
    """Deterministic mock adapter implementing BaseGameAdapter.

    Attributes:
        current_turn: Active turn index in the mock environment.
        is_active: Whether the mock game is ongoing.
        submitted_actions: Audit list of all actions received during the session.
    """

    def __init__(
        self,
        initial_turn: int = 1,
        initial_score: float = 0.0,
        is_active: bool = True,
        reject_submissions: bool = False,
        rejection_code: int = 400,
        rejection_message: str = "[MOCK] Action rejected by mock server rules.",
        simulate_network_error: bool = False,
        simulate_timeout: bool = False,
        predefined_states: Optional[List[GameState]] = None,
    ) -> None:
        """Initialize deterministic mock adapter.

        Args:
            initial_turn: Starting turn number.
            initial_score: Starting mock score.
            is_active: Whether mock match is ongoing.
            reject_submissions: If True, `submit_action` returns a rejection result.
            rejection_code: HTTP/protocol error code returned on rejection.
            rejection_message: Explanatory error message for rejection.
            simulate_network_error: If True, raises ConnectionError during submission.
            simulate_timeout: If True, raises TimeoutError during submission.
            predefined_states: Optional list of states to return in sequence for `read_game_state`.
        """
        self.current_turn = initial_turn
        self.score = initial_score
        self.is_active = is_active
        self.reject_submissions = reject_submissions
        self.rejection_code = rejection_code
        self.rejection_message = rejection_message
        self.simulate_network_error = simulate_network_error
        self.simulate_timeout = simulate_timeout
        self.predefined_states = list(predefined_states) if predefined_states else []
        self._state_read_count = 0

        self.submitted_actions: List[ProposedAction] = []
        self._connected = True

    def read_game_state(self) -> GameState:
        """Read the current state of the mock game.

        Returns:
            GameState: Current mock game state explicitly tagged with mock metadata.
        """
        self._state_read_count += 1
        if self.predefined_states:
            state = self.predefined_states.pop(0)
            self.current_turn = state.turn_number
            self.is_active = state.is_active
            return state

        return GameState(
            turn_number=self.current_turn,
            is_active=self.is_active,
            score=self.score,
            time_remaining_ms=1000,
            raw_state={
                "adapter_mode": "MOCK",
                "mock_environment": True,
                "read_count": self._state_read_count,
            },
            timestamp=datetime.now(timezone.utc),
        )

    def submit_action(self, action: ProposedAction) -> ActionSubmissionResult:
        """Submit a proposed action to the mock environment.

        Raises:
            ConnectionError: If `simulate_network_error` is True.
            TimeoutError: If `simulate_timeout` is True.

        Returns:
            ActionSubmissionResult: Explicitly marked with MOCK tags.
        """
        # Record submission for test assertions
        self.submitted_actions.append(action)

        if self.simulate_timeout:
            raise TimeoutError("[MOCK] Simulated network timeout during action submission.")

        if self.simulate_network_error:
            raise ConnectionError("[MOCK] Simulated transport drop during action submission.")

        action_index = len(self.submitted_actions)
        mock_action_id = f"MOCK-ACT-{action_index:04d}"

        if self.reject_submissions:
            return ActionSubmissionResult(
                success=False,
                action_id=mock_action_id,
                response_code=self.rejection_code,
                message=self.rejection_message,
                latency_ms=1.5,
                raw_response={
                    "mode": "MOCK",
                    "status": "REJECTED",
                    "reason": self.rejection_message,
                },
                timestamp=datetime.now(timezone.utc),
            )

        # Successful submission: advance mock turn and score
        self.current_turn += 1
        self.score += 10.0

        return ActionSubmissionResult(
            success=True,
            action_id=mock_action_id,
            response_code=200,
            message="[MOCK] Action successfully accepted by mock environment.",
            latency_ms=2.0,
            raw_response={
                "mode": "MOCK",
                "status": "ACCEPTED",
                "simulated_turn_advanced_to": self.current_turn,
            },
            timestamp=datetime.now(timezone.utc),
        )

    def check_submission_result(self, result: ActionSubmissionResult) -> bool:
        """Verify mock submission result."""
        return result.success and (result.response_code == 200)

    def connect(self) -> bool:
        """Establish mock connection."""
        self._connected = True
        return True

    def close(self) -> None:
        """Close mock connection."""
        self._connected = False

    def is_connected(self) -> bool:
        """Return mock connection status."""
        return self._connected
