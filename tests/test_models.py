"""Unit tests for GenesisBot V2 core domain models."""

from datetime import datetime
import pytest
from pydantic import ValidationError

from core.models import (
    ActionSubmissionResult,
    GameState,
    LayaDecision,
    ProposedAction,
    SessionInfo,
)


class TestSessionInfo:
    def test_default_values(self):
        session = SessionInfo()
        assert session.session_id is not None
        assert len(session.session_id) > 0
        assert session.bot_name == "GenesisBot"
        assert session.status == "initialized"
        assert isinstance(session.created_at, datetime)
        assert session.metadata == {}

    def test_custom_values_and_serialization(self):
        session = SessionInfo(
            session_id="custom-123",
            bot_name="CustomLaya",
            status="active",
            metadata={"arena": "map_01", "round": 1},
        )
        assert session.session_id == "custom-123"
        assert session.bot_name == "CustomLaya"
        assert session.status == "active"
        assert session.metadata["arena"] == "map_01"

        data = session.model_dump(mode="json")
        assert data["session_id"] == "custom-123"
        assert data["status"] == "active"


class TestGameState:
    def test_default_values(self):
        state = GameState()
        assert state.turn_number == 0
        assert state.is_active is True
        assert state.score is None
        assert state.time_remaining_ms is None
        assert state.raw_state == {}
        assert isinstance(state.timestamp, datetime)

    def test_preserving_raw_state_payload(self):
        raw_server_payload = {
            "official_turn": 42,
            "units": [{"id": "u1", "x": 10, "y": 20}],
            "fog_of_war": True,
        }
        state = GameState(
            turn_number=42,
            is_active=True,
            score=150.5,
            time_remaining_ms=450,
            raw_state=raw_server_payload,
        )
        assert state.turn_number == 42
        assert state.score == 150.5
        assert state.time_remaining_ms == 450
        assert state.raw_state["official_turn"] == 42
        assert state.raw_state["units"][0]["id"] == "u1"

    def test_negative_turn_number_validation(self):
        with pytest.raises(ValidationError):
            GameState(turn_number=-1)

    def test_negative_time_remaining_validation(self):
        with pytest.raises(ValidationError):
            GameState(time_remaining_ms=-10)


class TestProposedAction:
    def test_valid_action(self):
        action = ProposedAction(
            action_type="move",
            parameters={"target_x": 5, "target_y": 10},
            priority=5,
            reasoning="Advancing towards objective",
        )
        assert action.action_type == "move"
        assert action.parameters == {"target_x": 5, "target_y": 10}
        assert action.priority == 5
        assert action.reasoning == "Advancing towards objective"

    def test_missing_action_type_raises(self):
        with pytest.raises(ValidationError):
            ProposedAction()  # type: ignore

    def test_priority_range_validation(self):
        with pytest.raises(ValidationError):
            ProposedAction(action_type="wait", priority=0)

        with pytest.raises(ValidationError):
            ProposedAction(action_type="wait", priority=11)


class TestLayaDecision:
    def test_decision_with_single_action(self):
        action = ProposedAction(action_type="attack", parameters={"target_id": "enemy_1"})
        decision = LayaDecision(
            selected_action=action,
            confidence_score=0.95,
            rationale="High probability strike against visible threat",
        )
        assert decision.decision_id is not None
        assert decision.selected_action.action_type == "attack"
        assert decision.confidence_score == 0.95
        assert "visible threat" in decision.rationale
        assert decision.alternatives_considered == []

    def test_decision_with_alternatives(self):
        action_winner = ProposedAction(action_type="defend", priority=8)
        action_alt = ProposedAction(action_type="flee", priority=3)
        decision = LayaDecision(
            selected_action=action_winner,
            confidence_score=0.8,
            alternatives_considered=[action_alt],
        )
        assert len(decision.alternatives_considered) == 1
        assert decision.alternatives_considered[0].action_type == "flee"

    def test_confidence_score_out_of_bounds(self):
        action = ProposedAction(action_type="idle")
        with pytest.raises(ValidationError):
            LayaDecision(selected_action=action, confidence_score=1.5)

        with pytest.raises(ValidationError):
            LayaDecision(selected_action=action, confidence_score=-0.1)


class TestActionSubmissionResult:
    def test_successful_result(self):
        result = ActionSubmissionResult(
            success=True,
            action_id="act-001",
            response_code=200,
            message="Action executed successfully",
            latency_ms=18.4,
            raw_response={"server_time": 1700000000},
        )
        assert result.success is True
        assert result.action_id == "act-001"
        assert result.response_code == 200
        assert result.latency_ms == 18.4
        assert result.raw_response["server_time"] == 1700000000

    def test_failure_result(self):
        result = ActionSubmissionResult(
            success=False,
            response_code=400,
            message="Invalid parameters for move action",
        )
        assert result.success is False
        assert result.response_code == 400
        assert "Invalid parameters" in result.message

    def test_negative_latency_validation(self):
        with pytest.raises(ValidationError):
            ActionSubmissionResult(success=True, latency_ms=-5.0)
