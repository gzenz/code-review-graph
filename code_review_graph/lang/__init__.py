"""Per-language parsing handlers."""

from ._base import BaseLanguageHandler
from ._go import GoHandler
from ._python import PythonHandler

ALL_HANDLERS: list[BaseLanguageHandler] = [
    GoHandler(),
    PythonHandler(),
]

__all__ = ["BaseLanguageHandler", "GoHandler", "PythonHandler", "ALL_HANDLERS"]
