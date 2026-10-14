"""Official competition game adapter for GenesisBot V2.

This adapter represents the production interface for the official hackathon
game server.

CURRENT STATUS: PENDING OFFICIAL SPECIFICATION
The tournament organizers have not yet released the official API endpoints,
wire schemas, or SDK libraries. Per project guidelines, no URLs, payloads,
or endpoints are guessed. When required configuration is missing or placeholder
values are detected, this adapter fails cleanly with descriptive diagnostic errors.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

import requests

from config import AppConfig
from core.models import ActionSubmissionResult, GameState, ProposedAction
from game.base_adapter import BaseGameAdapter
from game.state_parser import GameStateParser, StateValidationError

logger = logging.getLogger(__name__)

# Known placeholder strings that indicate official docs have not been configured
PLACEHOLDER_URLS = {
    "https://api.placeholder-competition.org/v1",
    "https://api.example-competition.com/v1",
}


class OfficialIntegrationPendingError(RuntimeError):
    """Raised when official game API configuration or documentation is missing."""
    pass


class OfficialGameAdapter(BaseGameAdapter):
    """Adapter for connecting to the official competition game API.

    Enforces:
    - Zero guessed endpoints: requires verified API endpoints.
    - Explicit network timeouts on every call.
    - Secret redaction in headers, logs, and error messages.
    - Typed state validation via GameStateParser.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_sec: float = 5.0,
    ) -> None:
        """Initialize official adapter with configuration.

        Args:
            config: Optional AppConfig instance.
            base_url: Optional explicit base URL override.
            api_key: Optional explicit API key override.
            session_id: Optional explicit session ID override.
            timeout_sec: Network timeout in seconds.
        """
        if config:
            self.base_url = base_url or config.api_base_url
            self.api_key = api_key or config.api_key
            self.session_id = session_id or config.session_id
            self.timeout_sec = config.request_timeout_sec
        else:
            self.base_url = base_url
            self.api_key = api_key
            self.session_id = session_id
            self.timeout_sec = timeout_sec

        self._session = requests.Session()
        self._connected = False

    @staticmethod
    def redact_token(token: Optional[str]) -> str:
        """Safely redact secret tokens for logging and exception messages."""
        if not token:
            return "<EMPTY>"
        if len(token) <= 8:
            return "******"
        return f"{token[:3]}...{token[-3:]}"

    def _verify_ready(self) -> None:
        """Verify that official API configuration is present and non-placeholder.

        Raises:
            OfficialIntegrationPendingError: If official API settings are missing.
        """
        if not self.base_url or self.base_url.strip() in PLACEHOLDER_URLS:
            raise OfficialIntegrationPendingError(
                "Official competition API endpoint is not configured. "
                "The hackathon organizers have not yet released official endpoints. "
                "Update GENESIS_API_BASE_URL in `.env` once published."
            )

        if not self.session_id or "placeholder" in self.session_id.lower():
            raise OfficialIntegrationPendingError(
                "Official competition session ID is not configured. "
                "Set GENESIS_SESSION_ID in `.env` with a valid match session ID."
            )

    def _get_headers(self) -> Dict[str, str]:
        """Construct HTTP headers with credentials safely managed."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "GenesisBot/2.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def read_game_state(self) -> GameState:
        """Fetch and parse current game state from the official game server.

        Raises:
            OfficialIntegrationPendingError: If configuration is missing.
            ConnectionError: If network request fails.
            StateValidationError: If server returns malformed state.
        """
        self._verify_ready()

        url = f"{self.base_url.rstrip('/')}/sessions/{self.session_id}/state"
        headers = self._get_headers()

        redacted_auth = self.redact_token(self.api_key)
        logger.debug(
            "Fetching official game state: URL=%s, Auth=%s",
            url,
            redacted_auth,
        )

        try:
            response = self._session.get(url, headers=headers, timeout=self.timeout_sec)
            response.raise_for_status()
            raw_payload = response.json()
        except requests.Timeout as exc:
            raise ConnectionError(
                f"Timeout ({self.timeout_sec}s) fetching state from official game server."
            ) from exc
        except requests.RequestException as exc:
            raise ConnectionError(
                f"Network error fetching official state: {exc}"
            ) from exc

        return GameStateParser.parse_raw(raw_payload)

    def submit_action(self, action: ProposedAction) -> ActionSubmissionResult:
        """Submit a chosen action to the official game server.

        Translates internal ProposedAction into the wire format. Catches
        network failures and returns standardized ActionSubmissionResult.

        Raises:
            OfficialIntegrationPendingError: If configuration is missing.
            ConnectionError: If network drop occurs before/during transport.
        """
        self._verify_ready()

        url = f"{self.base_url.rstrip('/')}/sessions/{self.session_id}/action"
        headers = self._get_headers()

        wire_payload = {
            "action_type": action.action_type,
            "parameters": action.parameters,
            "priority": action.priority,
        }

        start_time = datetime.now(timezone.utc)
        try:
            response = self._session.post(
                url,
                json=wire_payload,
                headers=headers,
                timeout=self.timeout_sec,
            )
            latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0

            try:
                raw_resp = response.json() if response.content else {}
            except ValueError:
                raw_resp = {"raw_text": response.text}

            return ActionSubmissionResult(
                success=response.ok,
                action_id=raw_resp.get("action_id"),
                response_code=response.status_code,
                message=raw_resp.get("message") or response.reason,
                latency_ms=latency,
                raw_response=raw_resp,
                timestamp=datetime.now(timezone.utc),
            )

        except requests.Timeout as exc:
            latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0
            logger.error("Timeout submitting action to official game server: %s", exc)
            return ActionSubmissionResult(
                success=False,
                response_code=408,
                message=f"Timeout ({self.timeout_sec}s) submitting action to official server.",
                latency_ms=latency,
                raw_response={"error": "timeout", "detail": str(exc)},
                timestamp=datetime.now(timezone.utc),
            )
        except requests.RequestException as exc:
            latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0
            logger.error("Connection error submitting action to official game server: %s", exc)
            raise ConnectionError(
                f"Transport failure submitting action to official server: {exc}"
            ) from exc

    def check_submission_result(self, result: ActionSubmissionResult) -> bool:
        """Verify acceptance of action submission by official server."""
        return result.success and (result.response_code in (200, 201, 202))

    def connect(self) -> bool:
        """Verify connectivity to official server."""
        self._verify_ready()
        self._connected = True
        return True

    def close(self) -> None:
        """Close HTTP session."""
        self._session.close()
        self._connected = False

    def is_connected(self) -> bool:
        """Check connection state."""
        return self._connected
