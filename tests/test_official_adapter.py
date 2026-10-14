"""Unit tests for OfficialGameAdapter."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from core.models import GameState, ProposedAction
from game.official_adapter import (
    OfficialGameAdapter,
    OfficialIntegrationPendingError,
)


class TestOfficialGameAdapter:
    def test_missing_config_fails_clearly(self):
        adapter = OfficialGameAdapter(
            base_url=None,
            api_key=None,
            session_id=None,
        )
        with pytest.raises(OfficialIntegrationPendingError) as excinfo:
            adapter.read_game_state()
        assert "Official competition API endpoint is not configured" in str(excinfo.value)

    def test_placeholder_url_fails_clearly(self):
        adapter = OfficialGameAdapter(
            base_url="https://api.placeholder-competition.org/v1",
            api_key="some_key",
            session_id="valid_sess",
        )
        with pytest.raises(OfficialIntegrationPendingError) as excinfo:
            adapter.read_game_state()
        assert "hackathon organizers have not yet released official endpoints" in str(excinfo.value)

    def test_placeholder_session_fails_clearly(self):
        adapter = OfficialGameAdapter(
            base_url="https://live-official-hackathon.org/api",
            api_key="valid_key",
            session_id="placeholder_session_id",
        )
        with pytest.raises(OfficialIntegrationPendingError) as excinfo:
            adapter.submit_action(ProposedAction(action_type="move"))
        assert "session ID is not configured" in str(excinfo.value)

    def test_redact_token_utility(self):
        assert OfficialGameAdapter.redact_token(None) == "<EMPTY>"
        assert OfficialGameAdapter.redact_token("short") == "******"
        assert OfficialGameAdapter.redact_token("secret_token_12345") == "sec...345"

    @patch("requests.Session.get")
    def test_read_game_state_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "turn_number": 7,
            "is_active": True,
            "score": 120.0,
            "raw_state": {"board": "active"},
        }
        mock_get.return_value = mock_resp

        adapter = OfficialGameAdapter(
            base_url="https://live-official-hackathon.org/api",
            api_key="super_secret_token",
            session_id="sess_live_01",
        )
        state = adapter.read_game_state()

        assert isinstance(state, GameState)
        assert state.turn_number == 7
        assert state.score == 120.0
        mock_get.assert_called_once()
        headers = mock_get.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer super_secret_token"

    @patch("requests.Session.post")
    def test_submit_action_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.content = b'{"action_id": "OFFICIAL-01", "message": "Success"}'
        mock_resp.json.return_value = {"action_id": "OFFICIAL-01", "message": "Success"}
        mock_post.return_value = mock_resp

        adapter = OfficialGameAdapter(
            base_url="https://live-official-hackathon.org/api",
            api_key="super_secret_token",
            session_id="sess_live_01",
        )
        action = ProposedAction(action_type="scout", priority=4)
        result = adapter.submit_action(action)

        assert result.success is True
        assert result.action_id == "OFFICIAL-01"
        assert result.response_code == 200
        assert adapter.check_submission_result(result) is True

    @patch("requests.Session.get")
    def test_read_game_state_timeout(self, mock_get):
        mock_get.side_effect = requests.Timeout("Network timeout")

        adapter = OfficialGameAdapter(
            base_url="https://live-official-hackathon.org/api",
            api_key="valid_key",
            session_id="sess_live_01",
            timeout_sec=2.0,
        )
        with pytest.raises(ConnectionError) as excinfo:
            adapter.read_game_state()
        assert "Timeout" in str(excinfo.value)
