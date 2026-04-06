"""Lua language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class LuaHandler(BaseLanguageHandler):
    language = "lua"
    class_types: list[str] = []  # Lua has no class keyword; table-based OOP
    function_types = ["function_declaration"]
    import_types: list[str] = []  # require() handled via _extract_lua_constructs
    call_types = ["function_call"]
