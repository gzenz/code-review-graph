"""R language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class RHandler(BaseLanguageHandler):
    language = "r"
    class_types: list[str] = []  # Classes detected via call pattern-matching
    function_types = ["function_definition"]
    import_types = ["call"]  # library(), require(), source() -- filtered downstream
    call_types = ["call"]
    # R import extraction uses CodeParser helpers (_r_call_func_name, etc.)
    # so it stays in parser.py for now.
