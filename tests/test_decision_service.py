"""Unit tests for DecisionService and state-action validation."""

import pytest

from agent.decision_service import (
    DecisionService,
    InvalidActionError,
    InvalidDecisionError,
)
from agent.laya_client import LayaClient
from core.models import GameState, LayaDecision, ProposedAction, SessionInfo


class TestDecisionService:
    def test_evaluate_and_decide_success(self):
        action = ProposedAction(action_type="gather_resources", priority=4)
        decision = LayaDecision(
            selected_action=action,
            confidence_score=0.92,
            rationale="Resource advantage",
        )
        client = LayaClient(provider=lambda st, si: decision)
        service = DecisionService(laya_client=client)

        state = GameState(turn_number=1, is_active=True, time_remaining_ms=800)
        sess = SessionInfo()
        result = service.evaluate_and_decide(state, sess)

        assert result.selected_action.action_type == "gather_resources"
        assert result.confidence_score == 0.92

    def test_inactive_game_raises_invalid_action(self):
        action = ProposedAction(action_type="move")
        decision = LayaDecision(selected_action=action)
        client = LayaClient(provider=lambda st, si: decision)
        service = DecisionService(laya_client=client)

        state = GameState(turn_number=10, is_active=False)
        with pytest.raises(InvalidActionError) as excinfo:
            service.evaluate_and_decide(state, SessionInfo())
        assert "inactive game" in str(excinfo.value)

    def test_empty_action_type_raises_invalid_action(self):
        action = ProposedAction(action_type="   ")
        decision = LayaDecision(selected_action=action)
        client = LayaClient(provider=lambda st, si: decision)
        service = DecisionService(laya_client=client)

        with pytest.raises(InvalidActionError) as excinfo:
            service.evaluate_and_decide(GameState(is_active=True), SessionInfo())
        assert "Action type cannot be empty" in str(excinfo.value)

    def test_zero_time_remaining_raises_invalid_action(self):
        action = ProposedAction(action_type="move")
        decision = LayaDecision(selected_action=action)
        client = LayaClient(provider=lambda st, si: decision)
        service = DecisionService(laya_client=client)

        state = GameState(turn_number=1, is_active=True, time_remaining_ms=0)
        with pytest.raises(InvalidActionError) as excinfo:
            service.evaluate_and_decide(state, SessionInfo())
        assert "turn time is 0ms" in str(excinfo.value)

    def test_custom_validator_rejection(self):
        def reject_attack_validator(act: ProposedAction, st: GameState) -> bool:
            return act.action_type != "attack"

        action = ProposedAction(action_type="attack")
        decision = LayaDecision(selected_action=action)
        client = LayaClient(provider=lambda st, si: decision)
        service = DecisionService(
            laya_client=client,
            custom_validators=[reject_attack_validator],
        )

        with pytest.raises(InvalidActionError) as excinfo:
            service.evaluate_and_decide(GameState(is_active=True), SessionInfo())
        assert "rejected by custom domain validator" in str(excinfo.value)

    def test_none_decision_raises_invalid_decision(self):
        client = LayaClient(provider=lambda st, si: None)  # type: ignore
        service = DecisionService(laya_client=client)

        with pytest.raises(Exception):
            service.evaluate_and_decide(GameState(is_active=True), SessionInfo())
