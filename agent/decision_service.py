"""Decision service for GenesisBot V2.

Coordinates fetching decisions from the Laya client and rigorously validating
both the strategic decision and the proposed action against the current game state.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from agent.laya_client import LayaClient
from core.models import GameState, LayaDecision, ProposedAction, SessionInfo

logger = logging.getLogger(__name__)


class InvalidDecisionError(Exception):
    """Raised when Laya returns an invalid decision structure."""
    pass


class InvalidActionError(Exception):
    """Raised when a proposed action is incompatible with the current game state."""
    pass


# Type alias for custom action validation functions
ActionValidator = Callable[[ProposedAction, GameState], bool]


class DecisionService:
    """Orchestrates Laya decision retrieval and action validation.

    Guarantees:
    - Never invents a silent fallback action when Laya fails.
    - Validates that the game is active before accepting an action.
    - Validates that the proposed action conforms to domain invariants.
    - Supports pluggable action validation rules.
    """

    def __init__(
        self,
        laya_client: LayaClient,
        custom_validators: Optional[List[ActionValidator]] = None,
    ) -> None:
        """Initialize DecisionService.

        Args:
            laya_client: Configured LayaClient instance.
            custom_validators: Optional list of additional validation functions.
        """
        self.laya_client = laya_client
        self.custom_validators = custom_validators or []

    def evaluate_and_decide(
        self,
        game_state: GameState,
        session_info: SessionInfo,
    ) -> LayaDecision:
        """Fetch and validate a decision from Laya for the given game state.

        Args:
            game_state: Validated game state.
            session_info: Active session tracking metadata.

        Returns:
            LayaDecision: Fully validated decision with an action verified for this state.

        Raises:
            LayaError: If Laya client fails or times out.
            InvalidDecisionError: If decision structure breaks invariants.
            InvalidActionError: If proposed action is invalid for current state.
        """
        # Step 3: Send state/context to configured Laya service
        decision = self.laya_client.get_decision(game_state, session_info)

        # Step 4: Validate the returned decision
        self.validate_decision(decision)

        # Step 5: Confirm that proposed action is valid for current state
        self.validate_action_for_state(decision.selected_action, game_state)

        logger.info(
            "Decision validated for turn %d: action_type='%s', confidence=%.2f",
            game_state.turn_number,
            decision.selected_action.action_type,
            decision.confidence_score,
        )
        return decision

    def validate_decision(self, decision: LayaDecision) -> None:
        """Validate structure and confidence bounds of a LayaDecision.

        Raises:
            InvalidDecisionError: If decision is malformed.
        """
        if decision is None:
            raise InvalidDecisionError("Laya returned None instead of a decision.")

        if not isinstance(decision, LayaDecision):
            raise InvalidDecisionError(
                f"Expected LayaDecision, got {type(decision).__name__}"
            )

        if not isinstance(decision.selected_action, ProposedAction):
            raise InvalidDecisionError(
                "Laya decision is missing a valid selected_action."
            )

        if not (0.0 <= decision.confidence_score <= 1.0):
            raise InvalidDecisionError(
                f"Confidence score {decision.confidence_score} out of bounds [0.0, 1.0]."
            )

    def validate_action_for_state(
        self,
        action: ProposedAction,
        game_state: GameState,
    ) -> None:
        """Confirm that the proposed action is valid for the current game state.

        Raises:
            InvalidActionError: If action cannot be executed in the current state.
        """
        if action is None:
            raise InvalidActionError("Action cannot be None.")

        if not isinstance(action, ProposedAction):
            raise InvalidActionError(
                f"Expected ProposedAction, got {type(action).__name__}"
            )

        # Invariant 1: Cannot act on an inactive/finished game
        if not game_state.is_active:
            raise InvalidActionError(
                f"Cannot execute action '{action.action_type}' on inactive game "
                f"(turn {game_state.turn_number})."
            )

        # Invariant 2: Action type must be a non-empty string
        if not action.action_type or not action.action_type.strip():
            raise InvalidActionError("Action type cannot be empty.")

        # Invariant 3: Priority must be in range [1, 10]
        if not (1 <= action.priority <= 10):
            raise InvalidActionError(
                f"Action priority {action.priority} is outside allowed range [1, 10]."
            )

        # Invariant 4: Turn time check
        if game_state.time_remaining_ms is not None and game_state.time_remaining_ms == 0:
            raise InvalidActionError(
                f"Cannot submit action '{action.action_type}': remaining turn time is 0ms."
            )

        # Execute any registered custom validators
        for validator in self.custom_validators:
            try:
                is_valid = validator(action, game_state)
            except Exception as exc:
                raise InvalidActionError(
                    f"Custom action validator failed: {exc}"
                ) from exc

            if not is_valid:
                raise InvalidActionError(
                    f"Action '{action.action_type}' rejected by custom domain validator."
                )
