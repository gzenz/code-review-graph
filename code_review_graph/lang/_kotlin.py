"""Kotlin language handler."""

from __future__ import annotations

from ._base import BaseLanguageHandler


class KotlinHandler(BaseLanguageHandler):
    language = "kotlin"
    class_types = ["class_declaration", "object_declaration"]
    function_types = ["function_declaration"]
    import_types = ["import_header"]
    call_types = ["call_expression"]
