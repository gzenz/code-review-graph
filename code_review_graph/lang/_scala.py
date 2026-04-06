"""Scala language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class ScalaHandler(BaseLanguageHandler):
    language = "scala"
    class_types = [
        "class_definition", "trait_definition",
        "object_definition", "enum_definition",
    ]
    function_types = ["function_definition", "function_declaration"]
    import_types = ["import_declaration"]
    call_types = ["call_expression", "instance_expression", "generic_function"]

    def extract_import_targets(self, node, source: bytes) -> list[str]:
        parts: list[str] = []
        selectors: list[str] = []
        is_wildcard = False
        for child in node.children:
            if child.type == "identifier":
                parts.append(child.text.decode("utf-8", errors="replace"))
            elif child.type == "namespace_selectors":
                for sub in child.children:
                    if sub.type == "identifier":
                        selectors.append(sub.text.decode("utf-8", errors="replace"))
            elif child.type == "namespace_wildcard":
                is_wildcard = True
        base = ".".join(parts)
        if selectors:
            return [f"{base}.{name}" for name in selectors]
        if is_wildcard:
            return [f"{base}.*"]
        if base:
            return [base]
        return []
