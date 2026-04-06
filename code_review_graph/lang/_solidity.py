"""Solidity language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class SolidityHandler(BaseLanguageHandler):
    language = "solidity"
    class_types = [
        "contract_declaration", "interface_declaration", "library_declaration",
        "struct_declaration", "enum_declaration", "error_declaration",
        "user_defined_type_definition",
    ]
    # Events and modifiers use kind="Function" because the graph schema has no
    # dedicated kind for them.  State variables are also modeled as Function
    # nodes (public ones auto-generate getters).
    function_types = [
        "function_definition", "constructor_definition", "modifier_definition",
        "event_definition", "fallback_receive_definition",
    ]
    import_types = ["import_directive"]
    call_types = ["call_expression"]

    def get_name(self, node, kind: str) -> str | None:
        if node.type == "constructor_definition":
            return "constructor"
        if node.type == "fallback_receive_definition":
            for child in node.children:
                if child.type in ("receive", "fallback"):
                    return child.text.decode("utf-8", errors="replace")
        return NotImplemented

    def extract_import_targets(self, node, source: bytes) -> list[str]:
        imports = []
        for child in node.children:
            if child.type == "string":
                val = child.text.decode("utf-8", errors="replace").strip('"')
                if val:
                    imports.append(val)
        return imports

    def get_bases(self, node, source: bytes) -> list[str]:
        bases = []
        for child in node.children:
            if child.type == "inheritance_specifier":
                for sub in child.children:
                    if sub.type == "user_defined_type":
                        for ident in sub.children:
                            if ident.type == "identifier":
                                bases.append(
                                    ident.text.decode("utf-8", errors="replace"),
                                )
        return bases
