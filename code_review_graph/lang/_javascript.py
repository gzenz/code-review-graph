"""JavaScript / TypeScript / TSX language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class _JsTsBase(BaseLanguageHandler):
    """Shared handler logic for JS, TS, and TSX."""

    class_types = ["class_declaration", "class"]
    function_types = ["function_declaration", "method_definition", "arrow_function"]
    import_types = ["import_statement"]
    # No builtin_names -- JS/TS builtins are not filtered

    def get_bases(self, node, source: bytes) -> list[str]:
        bases = []
        for child in node.children:
            if child.type in ("extends_clause", "implements_clause"):
                for sub in child.children:
                    if sub.type in ("identifier", "type_identifier", "nested_identifier"):
                        bases.append(sub.text.decode("utf-8", errors="replace"))
        return bases

    def extract_import_targets(self, node, source: bytes) -> list[str]:
        imports = []
        for child in node.children:
            if child.type == "string":
                val = child.text.decode("utf-8", errors="replace").strip("'\"")
                imports.append(val)
        return imports


class JavaScriptHandler(_JsTsBase):
    language = "javascript"
    call_types = [
        "call_expression", "new_expression",
        "jsx_self_closing_element", "jsx_opening_element",
    ]


class TypeScriptHandler(_JsTsBase):
    language = "typescript"
    call_types = ["call_expression", "new_expression"]


class TsxHandler(_JsTsBase):
    language = "tsx"
    call_types = [
        "call_expression", "new_expression",
        "jsx_self_closing_element", "jsx_opening_element",
    ]
