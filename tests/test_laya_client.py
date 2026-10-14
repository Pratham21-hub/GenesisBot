"""Unit tests for LayaClient."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from agent.laya_client import (
    LayaClient,
    LayaConfigurationError,
    LayaConnectionError,
    LayaMalformedResponseError,
    LayaResponseError,
    LayaTimeoutError,
)
from core.models import GameState, LayaDecision, ProposedAction, SessionInfo


class TestLayaClient:
    def test_missing_config_fails_clearly(self):
        client = LayaClient(endpoint_url=None, provider=None)
        state = GameState(turn_number=1)
        sess = SessionInfo()

        with pytest.raises(LayaConfigurationError) as excinfo:
            client.get_decision(state, sess)
        assert "endpoint is not configured" in str(excinfo.value)

    def test_local_provider_success(self):
        def sample_provider(st: GameState, si: SessionInfo) -> LayaDecision:
            return LayaDecision(
                selected_action=ProposedAction(action_type="jump", priority=5),
                confidence_score=0.9,
                rationale="Provider chose jump",
            )

        client = LayaClient(provider=sample_provider)
        decision = client.get_decision(GameState(), SessionInfo())

        assert isinstance(decision, LayaDecision)
        assert decision.selected_action.action_type == "jump"
        assert decision.confidence_score == 0.9

    def test_local_provider_malformed_return_raises(self):
        def bad_provider(st: GameState, si: SessionInfo):
            return "not a LayaDecision"

        client = LayaClient(provider=bad_provider)  # type: ignore
        with pytest.raises(LayaMalformedResponseError) as excinfo:
            client.get_decision(GameState(), SessionInfo())
        assert "expected LayaDecision" in str(excinfo.value)

    @patch("requests.Session.post")
    def test_remote_http_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "decision_id": "dec-100",
            "selected_action": {
                "action_type": "move",
                "parameters": {"direction": "north"},
                "priority": 7,
            },
            "confidence_score": 0.88,
            "rationale": "Clear path north",
        }
        mock_post.return_value = mock_resp

        client = LayaClient(
            endpoint_url="https://laya.ai.internal/decide",
            api_key="secret_laya_key",
        )
        decision = client.get_decision(GameState(turn_number=2), SessionInfo())

        assert isinstance(decision, LayaDecision)
        assert decision.selected_action.action_type == "move"
        assert decision.confidence_score == 0.88
        mock_post.assert_called_once()
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer secret_laya_key"

    @patch("requests.Session.post")
    def test_remote_http_timeout(self, mock_post):
        mock_post.side_effect = requests.Timeout("Gateway timeout")

        client = LayaClient(
            endpoint_url="https://laya.ai.internal/decide",
            timeout_sec=1.5,
        )
        with pytest.raises(LayaTimeoutError) as excinfo:
            client.get_decision(GameState(), SessionInfo())
        assert "timed out after 1.5s" in str(excinfo.value)

    @patch("requests.Session.post")
    def test_remote_http_connection_error(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("Connection refused")

        client = LayaClient(endpoint_url="https://laya.ai.internal/decide")
        with pytest.raises(LayaConnectionError) as excinfo:
            client.get_decision(GameState(), SessionInfo())
        assert "Failed to connect to Laya service" in str(excinfo.value)

    @patch("requests.Session.post")
    def test_remote_http_500_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        client = LayaClient(endpoint_url="https://laya.ai.internal/decide")
        with pytest.raises(LayaResponseError) as excinfo:
            client.get_decision(GameState(), SessionInfo())
        assert "HTTP 500" in str(excinfo.value)

    @patch("requests.Session.post")
    def test_remote_http_malformed_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_resp.text = "<html>502 Bad Gateway</html>"
        mock_post.return_value = mock_resp

        client = LayaClient(endpoint_url="https://laya.ai.internal/decide")
        with pytest.raises(LayaMalformedResponseError) as excinfo:
            client.get_decision(GameState(), SessionInfo())
        assert "not valid JSON" in str(excinfo.value)

    @patch("requests.Session.post")
    def test_remote_http_schema_invalid_payload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = True
        # Missing required selected_action
        mock_resp.json.return_value = {"confidence_score": 0.5}
        mock_post.return_value = mock_resp

        client = LayaClient(endpoint_url="https://laya.ai.internal/decide")
        with pytest.raises(LayaMalformedResponseError) as excinfo:
            client.get_decision(GameState(), SessionInfo())
        assert "schema validation" in str(excinfo.value)
