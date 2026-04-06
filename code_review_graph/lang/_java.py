"""Java language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class JavaHandler(BaseLanguageHandler):
    language = "java"
    class_types = ["class_declaration", "interface_declaration", "enum_declaration"]
    function_types = ["method_declaration", "constructor_declaration"]
    import_types = ["import_declaration"]
    call_types = ["method_invocation", "object_creation_expression"]

    def extract_import_targets(self, node, source: bytes) -> list[str]:
        text = node.text.decode("utf-8", errors="replace").strip()
        parts = text.split()
        if len(parts) >= 2:
            return [parts[-1].rstrip(";")]
        return []
