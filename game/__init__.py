"""Game adapter package for GenesisBot V2.

Contains the abstract adapter interface that decouples internal bot logic
from official competition transport protocols and SDKs.
"""

from game.base_adapter import BaseGameAdapter

__all__ = ["BaseGameAdapter"]
