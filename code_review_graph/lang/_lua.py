"""Lua language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class LuaHandler(BaseLanguageHandler):
    language = "lua"
    class_types: list[str] = []  # Lua has no class keyword; table-based OOP
    function_types = ["function_declaration"]
    import_types: list[str] = []  # require() handled via _extract_lua_constructs
    call_types = ["function_call"]

    def get_name(self, node, kind: str) -> str | None:
        # function_declaration names may be dot_index_expression or
        # method_index_expression (e.g. function Animal.new() / Animal:speak()).
        # Return only the method name; the table name is used as parent_name
        # in _extract_lua_constructs.
        if node.type == "function_declaration":
            for child in node.children:
                if child.type in ("dot_index_expression", "method_index_expression"):
                    for sub in reversed(child.children):
                        if sub.type == "identifier":
                            return sub.text.decode("utf-8", errors="replace")
                    return None
        return NotImplemented
