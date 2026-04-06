"""Base class for language-specific parsing handlers."""

from __future__ import annotations


class BaseLanguageHandler:
    """Override methods where a language differs from default CodeParser logic.

    Methods returning ``NotImplemented`` signal 'use the default code path'.
    Subclasses only need to override what they actually customise.
    """

    language: str = ""
    class_types: list[str] = []
    function_types: list[str] = []
    import_types: list[str] = []
    call_types: list[str] = []
    builtin_names: frozenset[str] = frozenset()

    def get_name(self, node, kind: str) -> str | None:
        return NotImplemented

    def get_bases(self, node, source: bytes) -> list[str]:
        return NotImplemented

    def extract_import_targets(self, node, source: bytes) -> list[str]:
        return NotImplemented

    def collect_import_names(self, node, file_path: str, import_map: dict[str, str]) -> bool:
        """Populate import_map from an import node. Return True if handled."""
        return False

    def resolve_module(self, module: str, caller_file: str) -> str | None:
        """Resolve a module path to a file path. Return NotImplemented to fall back."""
        return NotImplemented
