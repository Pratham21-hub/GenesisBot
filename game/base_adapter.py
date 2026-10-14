"""Abstract game adapter interface for GenesisBot V2.

This module defines the abstract port (Anti-Corruption Layer) through which
GenesisBot interacts with any game environment.

Architectural Contract:
- GenesisBot's strategic core interacts solely with this interface.
- Concrete adapters will implement transport specifics (HTTP REST, WebSocket,
  gRPC, or vendor SDK) once competition rules and official APIs are revealed.
- No concrete URLs, endpoint paths, authentication flows, or game-specific
  schemas are invented here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.models import ActionSubmissionResult, GameState, ProposedAction


class BaseGameAdapter(ABC):
    """Abstract base class defining the contract for game environment interaction.

    Any concrete adapter (e.g., REST API adapter, official hackathon SDK wrapper,
    or local simulation adapter) must inherit from this class and implement
    all abstract methods.
    """

    @abstractmethod
    def read_game_state(self) -> GameState:
        """Read and return the current state of the game.

        The implementing adapter is responsible for:
        1. Fetching raw state from the game environment (via network call or SDK).
        2. Ingesting raw fields into `GameState.raw_state` to ensure no data is lost.
        3. Populating core typed fields (`turn_number`, `is_active`, `score`, etc.)
           according to competition documentation.

        Returns:
            GameState: Current validated game state.

        Raises:
            ConnectionError: If unable to reach the game environment.
            ValueError: If the environment returns an unparseable state.
        """
        pass

    @abstractmethod
    def submit_action(self, action: ProposedAction) -> ActionSubmissionResult:
        """Submit a chosen action to the game environment.

        The implementing adapter is responsible for:
        1. Translating the internal `ProposedAction` into the wire format
           required by the official competition API/SDK.
        2. Transmitting the payload to the server.
        3. Measuring roundtrip latency.
        4. Returning an `ActionSubmissionResult` reflecting the server's acceptance.

        Args:
            action: The action proposed by the Laya decision engine.

        Returns:
            ActionSubmissionResult: Standardized outcome of the submission.

        Raises:
            ConnectionError: If communication with the game server fails.
        """
        pass

    @abstractmethod
    def check_submission_result(self, result: ActionSubmissionResult) -> bool:
        """Verify and check the validity of an action submission result.

        Provides a hook for adapters to verify whether an action was successfully
        processed by the server or if compensation/retry logic is required.

        Args:
            result: The ActionSubmissionResult returned from `submit_action`.

        Returns:
            bool: True if the submission was accepted and verified; False otherwise.
        """
        pass

    def connect(self) -> bool:
        """Establish connection or session with the game server.

        Optional lifecycle hook for stateful transports (e.g. WebSockets,
        authenticated sessions). Default implementation returns True.

        Returns:
            bool: True if connection is ready; False otherwise.
        """
        return True

    def close(self) -> None:
        """Clean up network sessions, client handles, or background threads.

        Optional lifecycle hook for graceful shutdown.
        """
        pass

    def is_connected(self) -> bool:
        """Check if the adapter is currently connected and healthy.

        Returns:
            bool: True if healthy; False otherwise.
        """
        return True
