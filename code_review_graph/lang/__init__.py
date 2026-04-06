"""Per-language parsing handlers."""

from ._base import BaseLanguageHandler
from ._go import GoHandler
from ._javascript import JavaScriptHandler, TsxHandler, TypeScriptHandler
from ._python import PythonHandler

ALL_HANDLERS: list[BaseLanguageHandler] = [
    GoHandler(),
    PythonHandler(),
    JavaScriptHandler(),
    TypeScriptHandler(),
    TsxHandler(),
]

__all__ = [
    "BaseLanguageHandler", "GoHandler", "PythonHandler",
    "JavaScriptHandler", "TypeScriptHandler", "TsxHandler",
    "ALL_HANDLERS",
]
