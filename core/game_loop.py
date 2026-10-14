"""Game loop orchestrator for GenesisBot V2.

Executes the turn-by-turn game-playing pipeline:
1. Read current game state through the adapter.
2. Validate the state before using it.
3. Send state/context to configured Laya service.
4. Validate the returned decision.
5. Confirm that proposed action is valid for the current state.
6. Submit action through the game adapter.
7. Read or verify resulting game state when supported.
8. Record the outcome and relevant metadata.

Safety and Reliability Guarantees:
- Never submits an action if Laya fails, times out, or produces invalid output.
- Never silently invents a fallback move.
- Avoids blind retries on ambiguous submission outcomes to prevent duplicate moves.
- Records all transitions in structured JSONL audit logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional

from agent.decision_service import (
    DecisionService,
    InvalidActionError,
    InvalidDecisionError,
)
from agent.laya_client import LayaError
from core.logger import log_jsonl_event
from core.models import (
    ActionSubmissionResult,
    GameState,
    LayaDecision,
    ProposedAction,
    SessionInfo,
)
from game.base_adapter import BaseGameAdapter
from game.state_parser import GameStateParser, StateValidationError

logger = logging.getLogger(__name__)


class TurnStatus(str, Enum):
    """Categorized outcome of a turn execution."""
    SUCCESS = "SUCCESS"
    GAME_OVER = "GAME_OVER"
    FAILED_STATE_READ = "FAILED_STATE_READ"
    FAILED_STATE_VALIDATION = "FAILED_STATE_VALIDATION"
    FAILED_LAYA = "FAILED_LAYA"
    FAILED_ACTION_VALIDATION = "FAILED_ACTION_VALIDATION"
    FAILED_SUBMISSION = "FAILED_SUBMISSION"
    AMBIGUOUS_SUBMISSION = "AMBIGUOUS_SUBMISSION"


class TurnExecutionRecord:
    """Audit record capturing the full lifecycle of a single turn execution."""

    def __init__(
        self,
        turn_number: int,
        status: TurnStatus,
        initial_state: Optional[GameState] = None,
        laya_decision: Optional[LayaDecision] = None,
        action_submitted: Optional[ProposedAction] = None,
        submission_result: Optional[ActionSubmissionResult] = None,
        resulting_state: Optional[GameState] = None,
        error_message: Optional[str] = None,
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.turn_number = turn_number
        self.status = status
        self.initial_state = initial_state
        self.laya_decision = laya_decision
        self.action_submitted = action_submitted
        self.submission_result = submission_result
        self.resulting_state = resulting_state
        self.error_message = error_message
        self.duration_ms = duration_ms
        self.timestamp = datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for JSONL logging or telemetry."""
        return {
            "turn_number": self.turn_number,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
            "has_initial_state": self.initial_state is not None,
            "has_decision": self.laya_decision is not None,
            "action_submitted": (
                self.action_submitted.action_type if self.action_submitted else None
            ),
            "submission_success": (
                self.submission_result.success if self.submission_result else None
            ),
            "resulting_turn": (
                self.resulting_state.turn_number if self.resulting_state else None
            ),
            "metadata": self.metadata,
        }


class GameLoop:
    """Core game loop orchestrator managing adapter interactions and Laya decisions."""

    def __init__(
        self,
        adapter: BaseGameAdapter,
        decision_service: DecisionService,
        state_parser: Optional[GameStateParser] = None,
        session_info: Optional[SessionInfo] = None,
        audit_logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize GameLoop.

        Args:
            adapter: Concrete game adapter port.
            decision_service: DecisionService for retrieving and validating actions.
            state_parser: StateParser for invariant validation.
            session_info: SessionInfo for tracking session metadata.
            audit_logger: Logger for JSONL structured event logging.
        """
        self.adapter = adapter
        self.decision_service = decision_service
        self.state_parser = state_parser or GameStateParser()
        self.session_info = session_info or SessionInfo()
        self.audit_logger = audit_logger or logging.getLogger("genesis_bot.gameloop")

        self.history: List[TurnExecutionRecord] = []
        self._last_state: Optional[GameState] = None

    def execute_turn(self) -> TurnExecutionRecord:
        """Execute a single turn following the strict 8-step pipeline.

        Returns:
            TurnExecutionRecord: Complete audit record of turn execution.
        """
        start_time = time.perf_counter()
        current_turn = self._last_state.turn_number + 1 if self._last_state else 1

        # ----------------------------------------------------------------------
        # Step 1: Read current game state through adapter
        # ----------------------------------------------------------------------
        try:
            raw_state = self.adapter.read_game_state()
        except Exception as exc:
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Failed to read game state from adapter: {exc}"
            logger.error(err_msg)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.FAILED_STATE_READ,
                error_message=err_msg,
                duration_ms=duration,
            )
            self._log_and_record(record)
            return record

        current_turn = raw_state.turn_number

        # Check for game completion
        if not raw_state.is_active:
            duration = (time.perf_counter() - start_time) * 1000.0
            logger.info("Game state indicates match is inactive/over (turn %d).", current_turn)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.GAME_OVER,
                initial_state=raw_state,
                duration_ms=duration,
            )
            self._last_state = raw_state
            self._log_and_record(record)
            return record

        # ----------------------------------------------------------------------
        # Step 2: Validate state before using it
        # ----------------------------------------------------------------------
        try:
            validated_state = self.state_parser.validate_state(
                raw_state,
                previous_state=self._last_state,
            )
        except StateValidationError as exc:
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"State validation failed on turn {current_turn}: {exc}"
            logger.error(err_msg)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.FAILED_STATE_VALIDATION,
                initial_state=raw_state,
                error_message=err_msg,
                duration_ms=duration,
            )
            self._log_and_record(record)
            return record

        # ----------------------------------------------------------------------
        # Steps 3, 4, 5: Query Laya, validate decision, confirm action validity
        # ----------------------------------------------------------------------
        try:
            decision = self.decision_service.evaluate_and_decide(
                validated_state,
                self.session_info,
            )
        except LayaError as exc:
            # Step 3/4 Failure: Laya request failed, timed out, or malformed
            # CRITICAL: Never submit action if Laya fails! Do not invent fallback!
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Laya decision failed on turn {current_turn}: {exc}"
            logger.error(err_msg)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.FAILED_LAYA,
                initial_state=validated_state,
                error_message=err_msg,
                duration_ms=duration,
            )
            self._log_and_record(record)
            return record
        except (InvalidDecisionError, InvalidActionError) as exc:
            # Step 4/5 Failure: Decision malformed or action invalid for current state
            # CRITICAL: Refuse to submit invalid action!
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Action validation failed on turn {current_turn}: {exc}"
            logger.error(err_msg)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.FAILED_ACTION_VALIDATION,
                initial_state=validated_state,
                error_message=err_msg,
                duration_ms=duration,
            )
            self._log_and_record(record)
            return record

        action_to_submit = decision.selected_action

        # ----------------------------------------------------------------------
        # Step 6: Submit action through game adapter
        # ----------------------------------------------------------------------
        try:
            submission_result = self.adapter.submit_action(action_to_submit)
        except (ConnectionError, TimeoutError) as exc:
            # Ambiguous outcome: network dropped or timed out during transport
            # CRITICAL: Avoid blind retries to prevent duplicate moves!
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = (
                f"Transport failure during action submission on turn {current_turn}: {exc}. "
                "Outcome is UNCERTAIN. Refraining from blind retry."
            )
            logger.critical(err_msg)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.AMBIGUOUS_SUBMISSION,
                initial_state=validated_state,
                laya_decision=decision,
                action_submitted=action_to_submit,
                error_message=err_msg,
                duration_ms=duration,
            )
            self._log_and_record(record)
            return record
        except Exception as exc:
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Unexpected failure submitting action on turn {current_turn}: {exc}"
            logger.error(err_msg)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.FAILED_SUBMISSION,
                initial_state=validated_state,
                laya_decision=decision,
                action_submitted=action_to_submit,
                error_message=err_msg,
                duration_ms=duration,
            )
            self._log_and_record(record)
            return record

        # Check server rejection
        if not submission_result.success:
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = (
                f"Action rejected by server (code {submission_result.response_code}): "
                f"{submission_result.message}"
            )
            logger.warning(err_msg)
            record = TurnExecutionRecord(
                turn_number=current_turn,
                status=TurnStatus.FAILED_SUBMISSION,
                initial_state=validated_state,
                laya_decision=decision,
                action_submitted=action_to_submit,
                submission_result=submission_result,
                error_message=err_msg,
                duration_ms=duration,
            )
            self._log_and_record(record)
            return record

        # ----------------------------------------------------------------------
        # Step 7: Read or verify resulting game state when supported
        # ----------------------------------------------------------------------
        resulting_state: Optional[GameState] = None
        try:
            resulting_state = self.adapter.read_game_state()
            self.state_parser.validate_state(resulting_state, previous_state=validated_state)
            self._last_state = resulting_state
        except Exception as exc:
            logger.warning(
                "Could not immediately read or verify resulting state on turn %d: %s",
                current_turn,
                exc,
            )
            self._last_state = validated_state

        # ----------------------------------------------------------------------
        # Step 8: Record outcome and relevant metadata
        # ----------------------------------------------------------------------
        duration = (time.perf_counter() - start_time) * 1000.0
        record = TurnExecutionRecord(
            turn_number=current_turn,
            status=TurnStatus.SUCCESS,
            initial_state=validated_state,
            laya_decision=decision,
            action_submitted=action_to_submit,
            submission_result=submission_result,
            resulting_state=resulting_state,
            duration_ms=duration,
            metadata={
                "action_type": action_to_submit.action_type,
                "confidence": decision.confidence_score,
                "submission_latency_ms": submission_result.latency_ms,
            },
        )
        self._log_and_record(record)
        return record

    def run(self, max_turns: int = 100) -> List[TurnExecutionRecord]:
        """Execute consecutive turns until match terminates or unrecoverable error occurs.

        Args:
            max_turns: Maximum turn limit to safeguard against infinite loops.

        Returns:
            List[TurnExecutionRecord]: Full sequence of turn records.
        """
        logger.info("Starting GenesisBot game loop (max_turns=%d)...", max_turns)
        for _ in range(max_turns):
            record = self.execute_turn()
            if record.status in (
                TurnStatus.GAME_OVER,
                TurnStatus.FAILED_STATE_READ,
                TurnStatus.FAILED_STATE_VALIDATION,
                TurnStatus.FAILED_LAYA,
                TurnStatus.FAILED_ACTION_VALIDATION,
                TurnStatus.AMBIGUOUS_SUBMISSION,
            ):
                logger.info(
                    "Game loop halting on turn %d due to status: %s",
                    record.turn_number,
                    record.status.value,
                )
                break
        return self.history

    def _log_and_record(self, record: TurnExecutionRecord) -> None:
        """Append record to history and emit JSONL structured log event."""
        self.history.append(record)
        log_jsonl_event(
            self.audit_logger,
            logging.INFO if record.status == TurnStatus.SUCCESS else logging.WARNING,
            f"Turn {record.turn_number} executed with status {record.status.value}",
            turn_record=record.to_dict(),
        )
