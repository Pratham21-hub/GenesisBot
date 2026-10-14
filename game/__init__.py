"""Game adapter package for GenesisBot V2.

Contains the abstract adapter interface, deterministic mock adapter,
official game adapter, and state parsing utilities.
"""

from game.base_adapter import BaseGameAdapter
from game.mock_adapter import MockGameAdapter
from game.official_adapter import (
    OfficialGameAdapter,
    OfficialIntegrationPendingError,
)
from game.state_parser import GameStateParser, StateValidationError

__all__ = [
    "BaseGameAdapter",
    "GameStateParser",
    "MockGameAdapter",
    "OfficialGameAdapter",
    "OfficialIntegrationPendingError",
    "StateValidationError",
]
