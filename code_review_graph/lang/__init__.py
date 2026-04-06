"""Per-language parsing handlers."""

from ._base import BaseLanguageHandler
from ._go import GoHandler

ALL_HANDLERS: list[BaseLanguageHandler] = [
    GoHandler(),
]

__all__ = ["BaseLanguageHandler", "GoHandler", "ALL_HANDLERS"]
