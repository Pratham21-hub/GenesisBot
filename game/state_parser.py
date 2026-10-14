"""State parser and validator for GenesisBot V2.

Provides rigorous validation and sanitization for GameState instances and
raw payloads ingested from game adapters.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from pydantic import ValidationError

from core.models import GameState


class StateValidationError(Exception):
    """Raised when game state data is missing, malformed, or breaks invariants."""
    pass


class GameStateParser:
    """Parses and validates game state representations before bot consumption.

    Enforces domain invariants:
    - State cannot be None.
    - Turn number must be non-negative and monotonically non-decreasing
      (unless an explicit reset is detected).
    - Time remaining and scores must be valid numbers when provided.
    - Raw upstream payloads are preserved in `raw_state`.
    """

    @staticmethod
    def parse_raw(raw_data: Dict[str, Any]) -> GameState:
        """Parse a raw dictionary payload into a validated GameState.

        Args:
            raw_data: Dictionary representing raw state from game adapter.

        Returns:
            GameState: Validated domain model.

        Raises:
            StateValidationError: If the payload cannot be parsed into GameState.
        """
        if not isinstance(raw_data, dict):
            raise StateValidationError(
                f"Expected dictionary payload for game state, got {type(raw_data).__name__}"
            )

        try:
            return GameState(**raw_data)
        except ValidationError as exc:
            raise StateValidationError(f"Invalid game state payload: {exc}") from exc

    @staticmethod
    def validate_state(
        current_state: GameState,
        previous_state: Optional[GameState] = None,
    ) -> GameState:
        """Validate domain invariants on a GameState instance.

        Args:
            current_state: The state to validate.
            previous_state: Optional previous turn's state for transition checks.

        Returns:
            GameState: The validated current_state.

        Raises:
            StateValidationError: If any validation rule is violated.
        """
        if current_state is None:
            raise StateValidationError("Game state cannot be None.")

        if not isinstance(current_state, GameState):
            raise StateValidationError(
                f"Expected GameState instance, got {type(current_state).__name__}"
            )

        if current_state.turn_number < 0:
            raise StateValidationError(
                f"Turn number cannot be negative: {current_state.turn_number}"
            )

        if current_state.time_remaining_ms is not None:
            if current_state.time_remaining_ms < 0:
                raise StateValidationError(
                    f"Time remaining cannot be negative: {current_state.time_remaining_ms}"
                )

        if current_state.score is not None:
            if math.isnan(current_state.score) or math.isinf(current_state.score):
                raise StateValidationError(
                    f"Score must be a finite number: {current_state.score}"
                )

        # Transition validation against previous state
        if previous_state is not None:
            if current_state.turn_number < previous_state.turn_number:
                raise StateValidationError(
                    f"Turn number decreased from {previous_state.turn_number} "
                    f"to {current_state.turn_number} without game reset."
                )

        return current_state

    @staticmethod
    def sanitize_for_logging(state: GameState) -> Dict[str, Any]:
        """Return a sanitized dictionary representation of the state for logs.

        Redacts sensitive tokens or authorization keys if they accidentally appear
        in raw_state.
        """
        data = state.model_dump(mode="json")
        raw = data.get("raw_state", {})
        if isinstance(raw, dict):
            sanitized_raw = {}
            for k, v in raw.items():
                if any(sec in k.lower() for sec in ("token", "key", "secret", "auth", "password")):
                    sanitized_raw[k] = "******"
                else:
                    sanitized_raw[k] = v
            data["raw_state"] = sanitized_raw
        return data
