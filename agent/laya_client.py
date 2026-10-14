"""Client for the Laya cognitive decision engine in GenesisBot V2.

Communicates with the configured Laya decision service (either via HTTP endpoint
or local decision provider) to obtain strategic decisions.

Reliability and Security:
- Strict timeouts on all network calls.
- Full credential redaction in all logging and exception traces.
- Rigorous response validation against the LayaDecision Pydantic schema.
- Explicit failure when configuration or documentation is missing; never falls
  back blindly or silently.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from pydantic import ValidationError
import requests

from core.models import GameState, LayaDecision, SessionInfo

logger = logging.getLogger(__name__)


class LayaError(Exception):
    """Base exception for all Laya client failures."""
    pass


class LayaTimeoutError(LayaError):
    """Raised when the Laya service request times out."""
    pass


class LayaConnectionError(LayaError):
    """Raised when the Laya service cannot be reached."""
    pass


class LayaResponseError(LayaError):
    """Raised when the Laya service returns an HTTP error response."""
    pass


class LayaMalformedResponseError(LayaError):
    """Raised when the Laya service returns malformed or schema-invalid data."""
    pass


class LayaConfigurationError(LayaError):
    """Raised when Laya client configuration or documentation is missing."""
    pass


class LayaClient:
    """Client for querying the Laya decision service.

    Supports:
    - Remote HTTP service endpoint with timeouts, secret redaction, and schema validation.
    - Local decision provider function for deterministic testing and local mock environments.
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_sec: float = 3.0,
        provider: Optional[Callable[[GameState, SessionInfo], LayaDecision]] = None,
    ) -> None:
        """Initialize LayaClient.

        Args:
            endpoint_url: URL of the remote Laya decision service.
            api_key: Optional authorization token (never logged in plain text).
            timeout_sec: Timeout in seconds for decision requests.
            provider: Optional local callable for testing/mock mode.
        """
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.provider = provider
        self._session = requests.Session()

    @staticmethod
    def redact_token(token: Optional[str]) -> str:
        """Return a redacted representation of a secret token for safe logging."""
        if not token:
            return "<EMPTY>"
        if len(token) <= 8:
            return "******"
        return f"{token[:3]}...{token[-3:]}"

    def get_decision(
        self,
        game_state: GameState,
        session_info: SessionInfo,
    ) -> LayaDecision:
        """Request a strategic decision for the current game state.

        Args:
            game_state: Current validated game state.
            session_info: Active session context.

        Returns:
            LayaDecision: Validated decision instance.

        Raises:
            LayaTimeoutError: On network timeout.
            LayaConnectionError: On network transport failure.
            LayaResponseError: On HTTP error status code.
            LayaMalformedResponseError: If response cannot be parsed into LayaDecision.
            LayaConfigurationError: If no provider or endpoint is configured.
        """
        # If a local provider is injected, use it (mock mode or local agent)
        if self.provider is not None:
            try:
                decision = self.provider(game_state, session_info)
            except Exception as exc:
                if isinstance(exc, (LayaTimeoutError, LayaMalformedResponseError)):
                    raise
                raise LayaError(f"Local Laya provider failed: {exc}") from exc

            if not isinstance(decision, LayaDecision):
                raise LayaMalformedResponseError(
                    f"Provider returned {type(decision).__name__}, expected LayaDecision."
                )
            return decision

        # Remote HTTP mode
        if not self.endpoint_url or "placeholder" in self.endpoint_url.lower():
            raise LayaConfigurationError(
                "Laya decision service endpoint is not configured. "
                "Official Laya service documentation is pending. "
                "Configure a valid endpoint URL or provide a decision provider."
            )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "GenesisBot-LayaClient/2.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "session_id": session_info.session_id,
            "bot_name": session_info.bot_name,
            "game_state": game_state.model_dump(mode="json"),
        }

        redacted_auth = self.redact_token(self.api_key)
        logger.debug(
            "Querying Laya service: URL=%s, Auth=%s, Turn=%d",
            self.endpoint_url,
            redacted_auth,
            game_state.turn_number,
        )

        try:
            response = self._session.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self.timeout_sec,
            )
        except requests.Timeout as exc:
            raise LayaTimeoutError(
                f"Laya service timed out after {self.timeout_sec}s."
            ) from exc
        except requests.RequestException as exc:
            raise LayaConnectionError(
                f"Failed to connect to Laya service at {self.endpoint_url}: {exc}"
            ) from exc

        if not response.ok:
            raise LayaResponseError(
                f"Laya service returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LayaMalformedResponseError(
                f"Laya service response is not valid JSON: {response.text[:200]}"
            ) from exc

        if not isinstance(data, dict):
            raise LayaMalformedResponseError(
                f"Expected JSON object from Laya service, got {type(data).__name__}"
            )

        try:
            return LayaDecision(**data)
        except ValidationError as exc:
            raise LayaMalformedResponseError(
                f"Laya service response failed LayaDecision schema validation: {exc}"
            ) from exc
