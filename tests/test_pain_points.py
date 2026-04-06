"""TDD tests for known pain points identified from evaluation iterations.

Each test targets a specific resolution/analysis gap found in the HealthAgent
and Gadgetbridge evaluations. Tests are organized by pain point category and
marked with ``pytest.mark.xfail`` when they exercise functionality that does
not yet work.  The goal: make these green one at a time as we build enrichers
and fix resolution logic.

Categories:
  1. Call resolution -- module-level imports, star imports, JVM per-symbol
  2. Dead code false positives -- property calls, framework entry points
  3. Risk scoring differentiation -- continuous gradation
  4. Entry point / flow detection -- Android, Servlet, Express
"""

import tempfile
from pathlib import Path

import pytest

from code_review_graph.changes import compute_risk_score
from code_review_graph.flows import detect_entry_points
from code_review_graph.graph import GraphStore
from code_review_graph.parser import CodeParser, EdgeInfo, NodeInfo
from code_review_graph.refactor import find_dead_code

FIXTURES = Path(__file__).parent / "fixtures"


# ===================================================================
# Helpers
# ===================================================================


class _GraphTestBase:
    """Mixin for tests that need a temporary graph store."""

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def _add_func(
        self,
        name: str,
        path: str = "app.py",
        parent: str | None = None,
        is_test: bool = False,
        extra: dict | None = None,
        line_start: int = 1,
        line_end: int = 10,
        language: str = "python",
    ) -> int:
        node = NodeInfo(
            kind="Test" if is_test else "Function",
            name=name,
            file_path=path,
            line_start=line_start,
            line_end=line_end,
            language=language,
            parent_name=parent,
            is_test=is_test,
            extra=extra or {},
        )
        nid = self.store.upsert_node(node, file_hash="abc")
        self.store.commit()
        return nid

    def _add_class(
        self,
        name: str,
        path: str = "app.py",
        parent: str | None = None,
        extra: dict | None = None,
        line_start: int = 1,
        line_end: int = 10,
        language: str = "python",
    ) -> int:
        node = NodeInfo(
            kind="Class",
            name=name,
            file_path=path,
            line_start=line_start,
            line_end=line_end,
            language=language,
            parent_name=parent,
            extra=extra or {},
        )
        nid = self.store.upsert_node(node, file_hash="abc")
        self.store.commit()
        return nid

    def _add_edge(self, kind: str, source: str, target: str,
                  path: str = "app.py", line: int = 5) -> None:
        self.store.upsert_edge(EdgeInfo(
            kind=kind, source=source, target=target,
            file_path=path, line=line,
        ))
        self.store.commit()


# ===================================================================
# 1. CALL RESOLUTION
# ===================================================================


class TestResolutionModuleLevelImport:
    """Pain point: `import json; json.dumps()` stays as bare `dumps`.

    The parser only tracked `from X import Y` in import_map.  Module-level
    imports (`import X`) are now tracked, and module-qualified calls produce
    edges like `json::dumps`.
    """

    def setup_method(self):
        self.parser = CodeParser()

    def test_module_import_attribute_call_resolved(self):
        """import json; json.dumps(data) should produce a CALLS edge to json::dumps."""
        source = (FIXTURES / "resolution_python_module_import.py").read_bytes()
        _, edges = self.parser.parse_bytes(Path("/src/app.py"), source)
        calls = [e for e in edges if e.kind == "CALLS"]
        assert any("dumps" in e.target and "::" in e.target for e in calls), (
            f"Expected resolved call to json::dumps, got: "
            f"{[e.target for e in calls]}"
        )

    def test_module_import_nested_attribute(self):
        """import os.path; os.path.getsize() should resolve."""
        source = (FIXTURES / "resolution_python_module_import.py").read_bytes()
        _, edges = self.parser.parse_bytes(Path("/src/app.py"), source)
        calls = [e for e in edges if e.kind == "CALLS"]
        assert any("getsize" in e.target and "::" in e.target for e in calls), (
            f"Expected resolved call to os.path::getsize, got: "
            f"{[e.target for e in calls]}"
        )


class TestResolutionStarImport:
    """Pain point: `from X import *` doesn't populate import_map."""

    def setup_method(self):
        self.parser = CodeParser()

    @pytest.mark.xfail(reason="star imports don't populate import_map")
    def test_star_import_call_resolved(self):
        """from sample_python import *; create_auth_service() should resolve."""
        _, edges = self.parser.parse_file(
            FIXTURES / "resolution_python_star_import.py"
        )
        calls = [e for e in edges if e.kind == "CALLS"]
        assert any(
            "create_auth_service" in e.target and "::" in e.target for e in calls
        ), (
            f"Expected resolved call to sample_python::create_auth_service, got: "
            f"{[e.target for e in calls]}"
        )


class TestResolutionJvmPerSymbolImport:
    """JVM per-symbol IMPORTS_FROM edges.

    The `_get_jvm_import_names()` method works (unit-tested separately),
    but it only fires when `_resolve_module_to_file()` succeeds.  For JVM
    package imports (com.example.auth.UserService), resolution always fails
    because there's no Java project layout or scip-java index.

    These tests document that gap: per-symbol edges are only created when
    the module CAN be resolved to a file.
    """

    def setup_method(self):
        self.parser = CodeParser()

    @pytest.mark.xfail(
        reason="JVM module-to-file resolution fails without scip-java index"
    )
    def test_java_import_creates_per_symbol_edge(self):
        """import com.example.auth.UserService should create IMPORTS_FROM ::UserService."""
        _, edges = self.parser.parse_file(
            FIXTURES / "resolution_java_import.java"
        )
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        import_targets = {e.target for e in imports}
        has_user_service = any("::UserService" in t for t in import_targets)
        has_user = any("::User" in t for t in import_targets)
        assert has_user_service, (
            f"Expected ::UserService in import targets, got: {import_targets}"
        )
        assert has_user, (
            f"Expected ::User in import targets, got: {import_targets}"
        )

    @pytest.mark.xfail(
        reason="Kotlin module-to-file resolution fails without scip-java index"
    )
    def test_kotlin_import_creates_per_symbol_edge(self):
        """import com.example.auth.UserRepository should create IMPORTS_FROM ::UserRepository."""
        _, edges = self.parser.parse_file(
            FIXTURES / "resolution_kotlin_import.kt"
        )
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        import_targets = {e.target for e in imports}
        has_user_repo = any("::UserRepository" in t for t in import_targets)
        has_user = any("::User" in t for t in import_targets)
        assert has_user_repo, (
            f"Expected ::UserRepository in import targets, got: {import_targets}"
        )
        assert has_user, (
            f"Expected ::User in import targets, got: {import_targets}"
        )

    def test_get_jvm_import_names_unit(self):
        """Unit test: _get_jvm_import_names extracts symbol from dotted path."""

        class FakeNode:
            def __init__(self, text):
                self.text = text.encode("utf-8")

        assert self.parser._get_jvm_import_names(
            FakeNode("import com.example.UserService;"), "java"
        ) == ["UserService"]
        assert self.parser._get_jvm_import_names(
            FakeNode("import static org.junit.Assert.assertEquals"), "java"
        ) == ["assertEquals"]
        assert self.parser._get_jvm_import_names(
            FakeNode("import com.example.*"), "java"
        ) == []
        assert self.parser._get_jvm_import_names(
            FakeNode("import nodomain.freeyourgadget.gadgetbridge.model.ActivityKind"),
            "kotlin",
        ) == ["ActivityKind"]


class TestResolutionCrossFileBareNames:
    """Pain point: multiple files define `sync`, `get`, `run` etc.

    Without cross-file symbol table, bare-name calls can't be traced back.
    """

    def setup_method(self):
        self.parser = CodeParser()

    def test_bare_name_disambiguation_via_import(self):
        """Same-file resolution: a bare call to a locally-defined function
        should resolve to the qualified name even without imports.
        """
        second_file = FIXTURES / "resolution_python_module_import.py"
        _, edges2 = self.parser.parse_bytes(
            second_file,
            b"def create_auth_service(): pass\ndef other(): create_auth_service()\n",
        )
        calls = [e for e in edges2 if e.kind == "CALLS"]
        resolved = [e for e in calls if "::" in e.target and "create_auth_service" in e.target]
        assert len(resolved) >= 1


class TestResolutionMethodCallOnImportedClass:
    """Pain point: `service.authenticate(token)` where service is of type
    AuthService (imported) can't resolve to AuthService.authenticate.

    This requires type inference that tree-sitter can't provide.
    """

    def setup_method(self):
        self.parser = CodeParser()

    @pytest.mark.xfail(
        reason="type inference needed to resolve variable.method() calls"
    )
    def test_method_on_typed_variable_resolves(self):
        """service.authenticate() where service: AuthService should resolve."""
        _, edges = self.parser.parse_bytes(
            Path("/src/app.py"),
            (
                b"from auth import AuthService\n"
                b"def main():\n"
                b"    service: AuthService = AuthService('x', 'y')\n"
                b"    service.authenticate('token')\n"
            ),
        )
        calls = [e for e in edges if e.kind == "CALLS"]
        # Should resolve authenticate to AuthService.authenticate
        assert any(
            "authenticate" in e.target and "::" in e.target for e in calls
        ), f"Expected resolved authenticate call, got: {[e.target for e in calls]}"


# ===================================================================
# 2. DEAD CODE FALSE POSITIVES
# ===================================================================


class TestDeadCodeFalsePositives(_GraphTestBase):
    """Tests for known false positives in dead code detection.

    Each test seeds a graph scenario where a function is actually used
    but find_dead_code() incorrectly flags it.
    """

    def test_property_getter_not_dead(self):
        """@property methods are accessed as attributes, not called.
        They should not be flagged as dead code.
        """
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/models.py", file_path="/repo/models.py",
            line_start=1, line_end=50, language="python",
        ))
        self._add_func(
            "full_name", path="/repo/models.py", parent="User",
            extra={"decorators": ["property"]},
        )
        self._add_class("User", path="/repo/models.py")
        self.store.commit()
        dead = find_dead_code(self.store)
        dead_names = {d["name"] for d in dead}
        assert "full_name" not in dead_names, (
            "@property getter flagged as dead code"
        )

    def test_interface_implementation_not_dead(self):
        """Methods implementing an interface should not be dead.
        Even if no direct CALLS edges point to them, they're called
        polymorphically via the interface.
        """
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/syncer.kt", file_path="/repo/syncer.kt",
            line_start=1, line_end=50, language="kotlin",
        ))
        self._add_class("Syncer", path="/repo/syncer.kt", language="kotlin")
        self._add_func(
            "sync", path="/repo/syncer.kt", parent="Syncer",
            language="kotlin",
        )
        self._add_class("SleepSyncer", path="/repo/syncer.kt", language="kotlin")
        self._add_func(
            "sync", path="/repo/syncer.kt", parent="SleepSyncer",
            language="kotlin", line_start=20, line_end=30,
        )
        # SleepSyncer inherits Syncer
        self._add_edge(
            "INHERITS", "/repo/syncer.kt::SleepSyncer", "Syncer",
            path="/repo/syncer.kt",
        )
        # Some caller calls Syncer.sync (the interface method)
        self._add_func("doSync", path="/repo/manager.kt", language="kotlin")
        self._add_edge(
            "CALLS", "/repo/manager.kt::doSync", "sync",
            path="/repo/manager.kt",
        )
        dead = find_dead_code(self.store)
        dead_names = {d["name"] for d in dead}
        # SleepSyncer.sync implements Syncer.sync -- should NOT be dead
        assert "sync" not in dead_names, (
            "Interface implementation flagged as dead code"
        )

    @pytest.mark.xfail(
        reason="callers_of can't reverse-trace bare name 'sync' to SleepSyncer.sync"
    )
    def test_bare_name_reverse_tracing(self):
        """When caller calls bare `sync`, and SleepSyncer.sync exists,
        callers_of(SleepSyncer.sync) should find the caller.
        """
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/syncer.kt", file_path="/repo/syncer.kt",
            line_start=1, line_end=50, language="kotlin",
        ))
        self._add_func(
            "sync", path="/repo/syncer.kt", parent="SleepSyncer",
            language="kotlin",
        )
        self._add_func("doSync", path="/repo/manager.kt", language="kotlin")
        # Bare-name call: doSync() -> sync
        self._add_edge(
            "CALLS", "/repo/manager.kt::doSync", "sync",
            path="/repo/manager.kt",
        )

        # Query callers of the qualified name
        edges = self.store.get_edges_by_target(
            "/repo/syncer.kt::SleepSyncer.sync"
        )
        callers = [e for e in edges if e.kind == "CALLS"]
        assert len(callers) >= 1, (
            "Bare-name CALLS edge to 'sync' should be findable when querying "
            "callers of SleepSyncer.sync"
        )

    def test_exported_function_not_dead(self):
        """Functions that are imported by other files should not be dead.
        Even without direct CALLS, IMPORTS_FROM edges should count.
        """
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/utils.py", file_path="/repo/utils.py",
            line_start=1, line_end=50, language="python",
        ))
        self._add_func("helper", path="/repo/utils.py")
        # Another file imports it
        self._add_edge(
            "IMPORTS_FROM", "/repo/main.py", "/repo/utils.py::helper",
            path="/repo/main.py",
        )
        dead = find_dead_code(self.store)
        dead_names = {d["name"] for d in dead}
        assert "helper" not in dead_names, (
            "Imported function flagged as dead code"
        )


# ===================================================================
# 3. RISK SCORING
# ===================================================================


class TestRiskScoringContinuous(_GraphTestBase):
    """Pain point: risk scores cluster at 0.50-0.70 with only 4 unique values.

    The continuous test coverage scale (0.30 untested -> 0.05 well-tested)
    should produce differentiated scores.
    """

    def test_risk_score_decreases_with_more_tests(self):
        """More TESTED_BY edges should monotonically decrease the test coverage
        component of the risk score.
        """
        self._add_func("func_0_tests", path="a.py", line_start=1, line_end=10)
        self._add_func("func_1_test", path="b.py", line_start=1, line_end=10)
        self._add_func("func_3_tests", path="c.py", line_start=1, line_end=10)
        self._add_func("func_5_tests", path="d.py", line_start=1, line_end=10)

        # Add tests for func_1
        self._add_func("test_1", path="test_b.py", is_test=True)
        self._add_edge("TESTED_BY", "test_b.py::test_1", "b.py::func_1_test", "test_b.py")

        # Add 3 tests for func_3
        for i in range(3):
            self._add_func(f"test_3_{i}", path="test_c.py", is_test=True,
                           line_start=i * 10 + 1, line_end=i * 10 + 10)
            self._add_edge(
                "TESTED_BY", f"test_c.py::test_3_{i}", "c.py::func_3_tests", "test_c.py",
            )

        # Add 5 tests for func_5
        for i in range(5):
            self._add_func(f"test_5_{i}", path="test_d.py", is_test=True,
                           line_start=i * 10 + 1, line_end=i * 10 + 10)
            self._add_edge(
                "TESTED_BY", f"test_d.py::test_5_{i}", "d.py::func_5_tests", "test_d.py",
            )

        scores = {}
        for name, path in [
            ("func_0_tests", "a.py"),
            ("func_1_test", "b.py"),
            ("func_3_tests", "c.py"),
            ("func_5_tests", "d.py"),
        ]:
            node = self.store.get_node(f"{path}::{name}")
            assert node is not None, f"Node {path}::{name} not found"
            scores[name] = compute_risk_score(self.store, node)

        # Monotonically decreasing
        assert scores["func_0_tests"] > scores["func_1_test"], (
            f"0 tests ({scores['func_0_tests']}) should score higher than "
            f"1 test ({scores['func_1_test']})"
        )
        assert scores["func_1_test"] > scores["func_3_tests"], (
            f"1 test ({scores['func_1_test']}) should score higher than "
            f"3 tests ({scores['func_3_tests']})"
        )
        assert scores["func_3_tests"] > scores["func_5_tests"], (
            f"3 tests ({scores['func_3_tests']}) should score higher than "
            f"5 tests ({scores['func_5_tests']})"
        )

    def test_risk_scores_span_meaningful_range(self):
        """When combining multiple scoring factors, risk scores should span
        a meaningful range -- not cluster within 0.20.
        """
        # Low risk: well-tested, no security keywords, few callers
        self._add_func("safe_helper", path="utils.py", line_start=1, line_end=10)
        for i in range(5):
            self._add_func(f"test_safe_{i}", path="test_utils.py", is_test=True,
                           line_start=i * 10 + 1, line_end=i * 10 + 10)
            self._add_edge(
                "TESTED_BY", f"test_utils.py::test_safe_{i}",
                "utils.py::safe_helper", "test_utils.py",
            )

        # High risk: untested, security keyword, many callers, cross-community
        self._add_func(
            "authenticate_user", path="auth.py",
            line_start=1, line_end=10,
        )
        for i in range(10):
            caller_path = f"caller_{i}.py"
            self._add_func(f"caller_{i}", path=caller_path,
                           line_start=1, line_end=10)
            self._add_edge(
                "CALLS", f"{caller_path}::caller_{i}",
                "auth.py::authenticate_user", caller_path,
            )

        low_node = self.store.get_node("utils.py::safe_helper")
        high_node = self.store.get_node("auth.py::authenticate_user")
        assert low_node is not None
        assert high_node is not None

        low_score = compute_risk_score(self.store, low_node)
        high_score = compute_risk_score(self.store, high_node)

        # High risk should be at least 0.30 higher than low risk
        gap = high_score - low_score
        assert gap >= 0.30, (
            f"Risk score gap too small: high={high_score:.4f} low={low_score:.4f} "
            f"gap={gap:.4f} (want >= 0.30)"
        )


# ===================================================================
# 4. ENTRY POINT / FLOW DETECTION
# ===================================================================


class TestEntryPointDetection(_GraphTestBase):
    """Tests for framework-specific entry point detection."""

    def test_android_oncreate_is_entry_point(self):
        """Android Activity.onCreate() should be detected as entry point."""
        self._add_func(
            "onCreate", path="/app/MainActivity.kt",
            parent="MainActivity", language="kotlin",
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "onCreate" in ep_names

    def test_android_onresume_is_entry_point(self):
        """Android onResume() should be detected as entry point."""
        self._add_func(
            "onResume", path="/app/MainActivity.kt",
            parent="MainActivity", language="kotlin",
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "onResume" in ep_names

    def test_android_ondestroy_is_entry_point(self):
        """Android onDestroy() should be detected as entry point."""
        self._add_func(
            "onDestroy", path="/app/MainActivity.kt",
            parent="MainActivity", language="kotlin",
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "onDestroy" in ep_names

    def test_servlet_doget_is_entry_point(self):
        """Java Servlet doGet() should be detected as entry point."""
        self._add_func(
            "doGet", path="/web/UserServlet.java",
            parent="UserServlet", language="java",
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "doGet" in ep_names

    def test_servlet_dopost_is_entry_point(self):
        """Java Servlet doPost() should be detected as entry point."""
        self._add_func(
            "doPost", path="/web/UserServlet.java",
            parent="UserServlet", language="java",
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "doPost" in ep_names

    def test_express_error_handler_is_entry_point(self):
        """Express errorHandler function should be detected as entry point."""
        self._add_func(
            "errorHandler", path="/src/app.ts",
            language="typescript",
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "errorHandler" in ep_names

    def test_composable_decorator_is_entry_point(self):
        """@Composable annotated functions should be entry points."""
        self._add_func(
            "HomeScreen", path="/ui/Home.kt",
            parent=None, language="kotlin",
            extra={"decorators": ["Composable"]},
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "HomeScreen" in ep_names

    def test_spring_get_mapping_is_entry_point(self):
        """@GetMapping annotated functions should be entry points."""
        self._add_func(
            "getUsers", path="/web/UserController.java",
            parent="UserController", language="java",
            extra={"decorators": ["GetMapping('/users')"]},
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "getUsers" in ep_names

    def test_hilt_viewmodel_is_entry_point(self):
        """@HiltViewModel annotated classes should be entry points."""
        self._add_func(
            "UserViewModel", path="/viewmodel/UserViewModel.kt",
            parent=None, language="kotlin",
            extra={"decorators": ["HiltViewModel"]},
        )
        eps = detect_entry_points(self.store)
        ep_names = {ep.name for ep in eps}
        assert "UserViewModel" in ep_names


# ===================================================================
# 5. PARSER-LEVEL INTEGRATION (parse real fixtures)
# ===================================================================


class TestParserFixtureIntegration:
    """Parse the new fixture files and verify expected edges/nodes."""

    def setup_method(self):
        self.parser = CodeParser()

    def test_android_lifecycle_nodes_extracted(self):
        """android_lifecycle.kt should produce nodes for lifecycle methods."""
        nodes, _ = self.parser.parse_file(FIXTURES / "android_lifecycle.kt")
        func_names = {n.name for n in nodes if n.kind == "Function"}
        assert "onCreate" in func_names
        assert "onResume" in func_names
        assert "onDestroy" in func_names
        assert "initializeUI" in func_names

    def test_android_lifecycle_calls_extracted(self):
        """onCreate should call initializeUI, onResume should call refreshData."""
        _, edges = self.parser.parse_file(FIXTURES / "android_lifecycle.kt")
        calls = [e for e in edges if e.kind == "CALLS"]
        targets = {e.target for e in calls}
        # These are same-file calls, should be resolved
        assert any("initializeUI" in t for t in targets), (
            f"Expected call to initializeUI, got: {targets}"
        )
        assert any("refreshData" in t for t in targets), (
            f"Expected call to refreshData, got: {targets}"
        )

    def test_servlet_nodes_extracted(self):
        """servlet_handler.java should produce nodes for doGet, doPost."""
        nodes, _ = self.parser.parse_file(FIXTURES / "servlet_handler.java")
        func_names = {n.name for n in nodes if n.kind == "Function"}
        assert "doGet" in func_names
        assert "doPost" in func_names
        assert "handleGetUser" in func_names

    def test_servlet_calls_extracted(self):
        """doGet should call handleGetUser, doPost should call handleCreateUser."""
        _, edges = self.parser.parse_file(FIXTURES / "servlet_handler.java")
        calls = [e for e in edges if e.kind == "CALLS"]
        targets = {e.target for e in calls}
        assert any("handleGetUser" in t for t in targets), (
            f"Expected call to handleGetUser, got: {targets}"
        )
        assert any("handleCreateUser" in t for t in targets), (
            f"Expected call to handleCreateUser, got: {targets}"
        )

    def test_express_routes_nodes_extracted(self):
        """express_routes.ts should produce nodes for handler functions."""
        nodes, _ = self.parser.parse_file(FIXTURES / "express_routes.ts")
        func_names = {n.name for n in nodes if n.kind == "Function"}
        assert "getUsers" in func_names
        assert "createUser" in func_names
        assert "errorHandler" in func_names

    @pytest.mark.xfail(
        reason="JVM module-to-file resolution fails without scip-java index"
    )
    def test_java_import_per_symbol(self):
        """resolution_java_import.java should have IMPORTS_FROM with ::ClassName."""
        _, edges = self.parser.parse_file(
            FIXTURES / "resolution_java_import.java"
        )
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        import_targets = {e.target for e in imports}
        assert any("::UserService" in t for t in import_targets), (
            f"Expected ::UserService import, got: {import_targets}"
        )

    @pytest.mark.xfail(
        reason="Kotlin module-to-file resolution fails without scip-java index"
    )
    def test_kotlin_import_per_symbol(self):
        """resolution_kotlin_import.kt should have IMPORTS_FROM with ::ClassName."""
        _, edges = self.parser.parse_file(
            FIXTURES / "resolution_kotlin_import.kt"
        )
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        import_targets = {e.target for e in imports}
        assert any("::UserRepository" in t for t in import_targets), (
            f"Expected ::UserRepository import, got: {import_targets}"
        )
