# code-review-graph: Strategic Analysis & Future Direction

Last updated: 2026-04-06 (v9 -- Jedi enrichment integrated, polymorphic self.method() next)

This document captures what we've learned across 6 evaluation iterations, what's fundamentally hard, what approaches we've tried (and why some failed), and where the project should go next. It's meant to be a living reference so we don't repeat mistakes and can make informed architecture decisions.

---

## Table of Contents

1. [Where We Are (v6 Scorecard)](#1-where-we-are-v6-scorecard)
2. [What We Built & What Worked](#2-what-we-built--what-worked)
3. [Ideas We Tried That Failed or Had Limits](#3-ideas-we-tried-that-failed-or-had-limits)
4. [The Fundamental Question: Is Tree-Sitter Enough?](#4-the-fundamental-question-is-tree-sitter-enough)
5. [Where Resolution Actually Fails (the 79% breakdown)](#5-where-resolution-actually-fails-the-79-breakdown)
6. [Architecture Options: Stay, Augment, or Replace](#6-architecture-options-stay-augment-or-replace)
7. [Recommended Path: Pluggable Enrichment](#7-recommended-path-pluggable-enrichment)
8. [Code Quality Audit & Refactoring Needs](#8-code-quality-audit--refactoring-needs)
9. [Easy Wins Still Available (within tree-sitter)](#9-easy-wins-still-available-within-tree-sitter)
10. [Process Improvements](#10-process-improvements)
11. [Fork Strategy](#11-fork-strategy)
12. [Decision Log](#12-decision-log)

---

## 1. Where We Are (v6 Scorecard)

### HealthAgent (Python/TypeScript, 253 files)

| Metric | v1 | v3 | v5 | v6 | v7 | v8 | v9 | Trend |
|---|---|---|---|---|---|---|---|---|
| Total edges | 22,737 | 16,594 | 16,650 | 19,362 | 19,392 | 21,296 | 21,308 | +2k from enrichments |
| Resolution rate | 11.7% | 22.2% | 22.2% | 28.0% | 28.1% | 28.6% | 28.6% | Tree-sitter ceiling reached |
| Resolved CALLS | 1,736 | 2,016 | 2,016 | 2,976 | 3,003 | 3,525 | 3,537 | +560 from typed vars + Jedi |
| TESTED_BY | 3,603 | 3,387 | 3,387 | 3,420 | 3,431 | 3,482 | 3,510 | Stable |
| Decorator nodes | present | 0 | 240 | 244 | 244 | 244 | 244 | Fixed in v4 |
| Dead code (tool) | 577 | 648 | 237 | 191 | 191 | ~150 | 139 | -52 from v6 |
| Grep FP rate | 92% | 90% | 27% | ? | ~33% | ~53% | ~53% | Concentrated FPs (smaller set) |
| FP spot check | 1/10 | 2/10 | 9/10 | 10/10 | 10/10 | 10/10 | 10/10 | safe_request genuinely dead |

### Gadgetbridge (Java/Kotlin, 3573 files)

| Metric | Before fixes | v6 | v7 | v8 | v9 | Target |
|---|---|---|---|---|---|---|
| callees_of(syncDataTypeSlice) | 0 | 14 | 13 (bare `sync`) | 14 (13 qualified + mutableListOf) | 14 | PASS |
| callees_of(SleepSyncer.sync) | 1 | 18 | 15 | PASS | PASS | PASS |
| callers_of(SleepSyncer.sync) | 0 | 0 | 0 | PASS (via qualified name) | PASS | PASS |
| callers_of(DataExporter.export) | 0 | 3 | 0 external | 1 Kotlin caller | 1 Kotlin caller | PASS |
| tests_for(RecordedWorkoutSyncer) | 0 | WorkoutSyncerUtilsTest | PASS | PASS | PARTIAL (0 direct, transitive exists) | PASS |
| Communities | 0 | 11 | 11 | 11 | 11 | 10-50 |
| Flows | ~100 | 3,224 | 3,226 | 3,059 | 3,059 | lifecycle entries |
| TESTED_BY edges | 0 | 6,140 | 7,384 | - | 7,409 | - |
| Risk score range | all 0.5 | 0.50-0.70 | 0.50-0.70 | 0.50-0.70 | 0.50-0.70 | differentiated |
| Resolution rate | - | - | - | 32.6% | 32.6% | - |

### Gadgetbridge scorecard: 9/10 PASS, 1 PARTIAL (v9)

v8 was 10/10 but tests_for(RecordedWorkoutSyncer) is now scored more accurately as PARTIAL: the graph has WorkoutSyncerUtils->WorkoutSyncerUtilsTest TESTED_BY edges, but tests_for doesn't traverse CALLS chains transitively. RecordedWorkoutSyncer CALLS WorkoutSyncerUtils which IS tested.

### HealthAgent v9 key gap: safe_request FP spot check

`safe_request` on BaseConnector has 0 callers in the graph. Subclasses call it via `self.safe_request()`, which resolves to `self` (not BaseConnector). All connector `.sync()` methods also appear dead for the same reason. Fix: resolve `self.method()` against class hierarchy using INHERITS edges.

---

## 2. What We Built & What Worked

### Fixes that had high impact (worth keeping and extending)

1. **Test-file exemption from method call filtering** (PR #108)
   - Test files now keep ALL method calls (not just self/cls/this)
   - Restored TESTED_BY edges: 0 -> 6,140 on Gadgetbridge
   - Insight: test code is fundamentally different from production code for call graph purposes

2. **Uppercase receiver heuristic** (PR #107/#108)
   - `ClassName.method()` allowed through the method call filter
   - Captures static/companion object calls without type inference
   - Low noise because uppercase identifiers reliably indicate class names

3. **Per-symbol IMPORTS_FROM edges** (PR #108)
   - `from X import Y as Z` now creates `::Y` edge (using original name, not alias)
   - Already existed for JS/TS; added for Python
   - Directly reduces dead code FP by connecting imported symbols to their definitions

4. **Adaptive community detection** (PR #108)
   - Leiden with resolution scaling (`1/log10(nodes)`)
   - Fallback chain: Leiden -> over-fragmentation check -> adaptive directory grouping
   - Common-prefix stripping + incremental depth search
   - Took 4 iterations to get right but now handles both 245-file and 3573-file repos

5. **Dead code accuracy** (PR #104)
   - @property skip (attribute access, not function calls)
   - INHERITS bare-name lookup (classes with subclasses aren't dead)
   - Override method check: if parent class method has callers, subclass overrides are alive
   - These checks cut dead code count from 237 to 139

### Patterns that scale well

- **Bare-name fallback** (`search_edges_by_target_name()`): When qualified lookup fails, search by bare name. Used in dead code detection, callers_of, tests_for. Simple and effective.
- **Language-specific constant tables** (`_BUILTIN_NAMES`, `_CALL_TYPES`, `_FRAMEWORK_DECORATOR_PATTERNS`): Easy to extend, clear boundaries, testable.
- **Two real-world test projects** with quantitative baselines: catches issues unit tests can't.

---

## 3. Ideas We Tried That Failed or Had Limits

### Community detection: 4 iterations to get right

| Iteration | Approach | Result | Why it failed |
|---|---|---|---|
| 1 | Leiden default resolution=1.0 | 3568 communities (Gadgetbridge) | Over-fragments large graphs; every small cluster becomes its own community |
| 2 | Resolution scaling `1/log10(nodes)` | 3617 communities | Helped but Leiden still over-fragments when graph has many disconnected components from unresolved bare-name edges |
| 3 | File-based fallback (per-file grouping) | 2712 communities | One community per file is too granular for a 3500-file repo |
| 4 | Directory-based with 3 fixed segments | 1 community (Gadgetbridge), 3 (adjusted) | 3 segments from root = `app/src/main` for ALL Android files |
| 5 | Common-prefix stripping + adaptive depth | 11 communities | Works! But took understanding the failure modes of each previous approach |

**Lesson**: Large graphs need fundamentally different clustering strategies than small graphs. Adaptive algorithms that probe different configurations beat fixed heuristics.

### Method call filtering: balancing precision vs recall

| Approach | Precision | Recall | Problem |
|---|---|---|---|
| Allow all method calls | LOW -- `session.execute()`, `data.get()` create thousands of ambiguous edges | HIGH | Graph becomes noisy; dead code detection useless |
| Block all non-self method calls (v1) | HIGH | LOW -- TESTED_BY destroyed, Kotlin calls invisible | Test coverage analysis broken |
| Allow self/cls/this + uppercase + test files (current) | MEDIUM | MEDIUM | Sweet spot for now, but ~25% of real calls still dropped |

**Lesson**: There's no perfect filter without type information. The current heuristic (self/uppercase/test) is the best we can do at the AST level.

### Resolution rate: approaching tree-sitter ceiling

Pushed from 11.7% to 28.6% (v8) through per-symbol imports, module-level import tracking, JVM package-path fallback, uppercase-receiver qualifying, constructor-based type inference, and star import scanning. The tree-sitter ceiling is ~35%; the remaining 71% requires type information. **Jedi is now integrated as a post-build enrichment step** (`jedi_resolver.py`, commit `326bcce`) -- resolved 8 additional method calls in HealthAgent. See Section 7, Phase 1.

### Raw SQL vs tool results divergence

In v6 HealthAgent evaluation, raw SQL reported 620 dead functions while `find_dead_code()` reported 191. The tool applies:
- @property skip
- INHERITS bare-name lookup
- Framework base class exclusion
- Dunder method exclusion
- Bare-name CALLS fallback

**Lesson**: Always use the actual tool for evaluation, never raw SQL. The tool's logic IS the product.

---

## 4. The Fundamental Question: Is Tree-Sitter Enough?

### What tree-sitter gives us

- **Syntax trees for 19 languages** with consistent API
- **Fast**: Full parse of 3573-file Gadgetbridge in ~30s
- **Incremental**: Only re-parse changed files
- **Reliable**: Production-quality grammars maintained by the community
- **Embeddable**: Native Python bindings

### What tree-sitter CANNOT give us

| Capability | Needed for | Available? |
|---|---|---|
| Type of a variable | Resolving `obj.method()` to `ClassName.method()` | NO |
| Module resolution (external packages) | Knowing that `import numpy` maps to `.venv/lib/numpy/` | NO |
| Scope chain / symbol table | Distinguishing local `sync` from imported `sync` | NO |
| Interface/trait resolution | Knowing that `Syncer.sync()` dispatches to `SleepSyncer.sync()` | NO |
| Build system metadata | Path aliases, package.json exports, go.mod | NO (we workaround for tsconfig only) |
| Control flow | Conditional imports, dynamic dispatch | NO |

### The 79% wall

Tree-sitter is a parser, not a compiler. It gives us the syntax tree but NOT the symbol table. The symbol table is what compilers build to answer "what does this name refer to?". Without it, ~79% of CALLS edges stay as bare names.

**This is not a bug. It's the architectural ceiling.**

---

## 5. Where Resolution Actually Fails (the 79% breakdown)

Based on analysis of the resolution pipeline (`parser.py` lines 2082-2294):

| Category | % of failures | Root cause | Example | Fixable with tree-sitter? |
|---|---|---|---|---|
| **Method calls filtered** | 20-25% | Receiver type unknown; `obj.method()` blocked | `session.execute()`, `db.query()` | NO (need type inference) |
| **Module-to-file failed** | 25-30% | External packages, wrong path, no package metadata | `import numpy`, `from django.db import models` | PARTIALLY (package.json/pyproject.toml parsing) |
| **Missing from import_map** | 20-25% | Star imports, re-exports, conditional imports, `import X` (module-level) | `from utils import *`, `import json; json.dumps()` | PARTIALLY (star import scanning, module-level import tracking) |
| **Cross-file bare names** | 15-20% | Same-file resolution only; no cross-file symbol table | `sync` matches 13 different functions | NO (need project-wide symbol table) |
| **Dynamic/runtime** | 5% | `getattr()`, callbacks, string-based dispatch | `getattr(obj, method_name)()` | NO |

### What additional data would close each gap

- **Method calls** -> Need: type checker output (pyright, tsc, gopls)
- **Module resolution** -> Need: build system metadata (go.mod, package.json, pyproject.toml) + package index
- **Import map gaps** -> Need: recursive module scanning + star import resolution
- **Cross-file resolution** -> Need: project-wide symbol table (what the compiler builds)
- **Dynamic dispatch** -> Need: runtime traces (not statically solvable)

---

## 6. Architecture Options: Stay, Augment, or Replace

### Option A: Optimize within tree-sitter limits

- Target: 28-30% resolution (from 22%)
- Add: star import scanning, module-level `import X` tracking, pyproject.toml path aliases, Java per-symbol imports
- Ceiling: ~35% resolution
- Effort: 4-8 weeks
- Risk: Low
- Value: Incremental; still 65% bare names

### Option B: Hybrid -- tree-sitter for structure + per-language enrichment for resolution

- Target: 60-70% resolution on top 3-5 languages
- Architecture: Pluggable enrichers that run AFTER tree-sitter parse
  - Python: **Jedi** (native Python library, resolves types/references, cross-file)
  - TypeScript: **TS Compiler API** (Node.js subprocess, full type checking)
  - Go: **go/callgraph** (Go subprocess, multiple algorithms: static/CHA/RTA/VTA)
  - Rust: **rust-analyzer** (subprocess via LSP, call hierarchy)
  - Java/Kotlin: **kotlin-compiler-embeddable** (JVM subprocess)
- Effort: 12-16 weeks for top 3 languages
- Risk: Medium (new dependencies, subprocess management, caching)
- Value: Transformative for Python/TS/Go repos (the majority of users)

### Option C: Accept limits, focus on other edge types

- Accept that CALLS edges will be 70% bare names
- Double down on CONTAINS, INHERITS, TESTED_BY, IMPORTS_FROM accuracy
- Use communities and flows for coarse-grained understanding
- Effort: 4-6 weeks
- Risk: Low
- Value: Different product -- less about precise call chains, more about architectural understanding

### Option D: SCIP consumption

- If users' CI already emits SCIP indexes (Sourcegraph users), load and merge that data
- Fall back to tree-sitter if no SCIP available
- Effort: 4-6 weeks for SCIP protobuf parsing
- Risk: Low
- Value: Niche -- only helps Sourcegraph-adjacent users

### Comparison

| | Resolution | Languages | Effort | New deps | Best for |
|---|---|---|---|---|---|
| A: Tree-sitter only | 28-35% | 19 | 4-8 wk | None | Quick wins, broad coverage -- **DONE, at 28.6%** |
| B: Hybrid enrichment | 60-70% (top 5) | 19 (5 enriched) | 12-16 wk | Jedi, Node.js, Go | Accuracy-focused -- **Phase 1 (Jedi) DONE** |
| C: Accept + focus | 22% (unchanged) | 19 | 4-6 wk | None | Architecture-focused users |
| D: SCIP | 80%+ (where available) | 5-10 | 4-6 wk | protobuf | Sourcegraph users |

---

## 7. Recommended Path: Pluggable Enrichment

The strategic recommendation is **Option B (Hybrid)** implemented incrementally:

### Phase 0: Exhaust tree-sitter easy wins -- DONE (2-4 weeks)
- ~~Continuous risk scoring~~ DONE
- ~~Java/Kotlin per-symbol imports~~ DONE
- ~~Module-level `import X` tracking for Python~~ DONE
- ~~Framework entry point patterns~~ DONE
- ~~Uppercase-receiver call qualifying~~ DONE
- ~~Constructor-based type inference~~ DONE
- ~~Star import resolution~~ DONE
- ~~Function-reference-as-argument tracking~~ DONE
- ~~JS/TS typed-variable walker~~ DONE
- Achieved 28.6% resolution (HealthAgent), 32.6% (Gadgetbridge), Gadgetbridge 10/10

### Phase 1: Python enrichment via Jedi -- DONE
- Jedi is pure Python, no subprocess needed
- Optional dependency (`pyproject.toml` enrichment extra: `jedi>=0.19.2`)
- Implemented in `jedi_resolver.py` (commit `326bcce`), wired into `full_build()` and `incremental_update()`
- Architecture: post-build, walks Python ASTs for dropped lowercase-receiver method calls, uses `jedi.Script.goto()` to resolve
- Only emits edges for project-internal definitions (filters stdlib/external)
- HealthAgent: resolved 8 calls in 4 files (21,304 edges)
- 4 tests: factory return method, stdlib filtering, dedup, stats
- Impact: modest for HealthAgent (most unresolved targets are SDK symbols), but enables resolution of factory-pattern calls in any Python project

### Phase 2: Java/Kotlin enrichment via scip-java (2-4 weeks)
- Sourcegraph's `scip-java` is a gradle/maven plugin that emits SCIP indexes during build
- For gradle projects (Gadgetbridge, Android apps): add `id("com.sourcegraph.scip-java")` to build.gradle, run `./gradlew scip-java`, consume the `.scip` protobuf file
- No JVM needed at analysis time -- we just read the pre-built index
- SCIP indexes contain: definitions, references, symbol relationships (implements, overrides, calls)
- Architecture: detect `.scip` file in project, parse protobuf, merge resolved edges into graph
- Since our primary Java/Kotlin test project (Gadgetbridge) is gradle-based, this is a natural fit
- Expected impact: Java/Kotlin resolution from ~10% to ~70%
- Dependency: `protobuf` Python library for SCIP consumption (lightweight)

### Phase 3: TypeScript enrichment via TS Compiler API (4-6 weeks)
- Node.js subprocess invoking ts.createProgram()
- `program.getTypeChecker().getSymbolAtLocation(node)` resolves method calls
- JSON IPC between Python and Node.js
- Expected impact: TypeScript resolution from ~30% to ~75%

### Phase 4: Go enrichment (2-4 weeks)
- Go already has `golang.org/x/tools/go/callgraph` in stdlib
- Small Go binary that emits call graph as JSON
- Expected impact: Go resolution from ~15% to ~80%

### Architecture sketch

```
parse_with_tree_sitter(repo)       # Fast, 19 languages, <30s
  |
  v
[nodes, edges] in SQLite            # Structure: files, functions, classes, imports
  |
  v
for lang in detected_languages:     # Check what enrichers are available
  if enricher_available(lang):
    enricher.resolve(nodes, edges)  # Updates bare CALLS targets to qualified names
  |
  v
[enriched graph] in SQLite          # Same schema, better CALLS edges
```

Each enricher is:
- Optional (graceful degradation)
- Cached per file hash
- Only processes edges that are currently bare names
- Outputs: updated `target_qualified` for CALLS edges

### What NOT to do

- Don't embed IntelliJ PSI (too heavy, not designed for headless)
- Don't build SCIP producers for all 19 languages (too much work -- but DO consume scip-java for Java/Kotlin since gradle projects can emit it cheaply)
- Don't use CodeQL (designed for security research, overkill)
- Don't replace tree-sitter (it's excellent at what it does)
- Don't try to build a type checker (compilers exist, use them)

---

## 8. Code Quality Audit & Refactoring Needs

Based on a brutal-honesty review (calibrated "Linus + Ramsay") cross-referenced with current codebase state. Feature velocity has outpaced quality control. These findings justify a fork with deeper refactoring.

### CRITICAL: RCE via trust_remote_code=True

**Status: FIXED** (commit `cdf8f21`, 2026-04-06)

Removed `trust_remote_code=True` and `model_kwargs={"trust_remote_code": True}` from `SentenceTransformer()` in `embeddings.py`. The default model (`all-MiniLM-L6-v2`) doesn't need remote code.

### HIGH: parser.py god class -- SIGNIFICANTLY REDUCED

**Status: DONE (phase 1+2)** -- All 19 languages extracted to `code_review_graph/lang/`. parser.py reduced from 3,130 to 2,895 lines (-235). 35 `if language ==` dispatches reduced to 16. Remaining 16 are blocked on deeper refactoring (JS/TS module resolution, R helper dependencies) -- diminishing returns.

Added typed variable call enrichment for Python/Kotlin/Java (post-parse tree-sitter walk), and shared `_emit_typed_call_edge` helper.

**Key finding (2026-04-06)**: `_get_call_name()` at line ~2815 discards the receiver for `ClassName.method()` calls. Returns `"sync"` instead of `"StepsSyncer::sync"`. This is the root cause of Gadgetbridge tests #1/#2/#4/#9. Fix: return `"ReceiverName.method"` when `is_class_call` is True.

**Secondary finding**: `_extract_calls()` line ~2215 guards with `if call_name and enclosing_func:`, silently dropping module-level calls (where `enclosing_func` is None).

### HIGH: Connection pooling exists but tools don't use it

**Status: FIXED** (commit `cdf8f21`, 2026-04-06)

`tools/_common.py:_get_store()` now caches one `GraphStore` per `db_path` with a `threading.Lock`. MCP tool calls reuse the cached connection instead of opening a fresh one each time.

### HIGH: VS Code extension ships broken commands

**Status: STILL PRESENT**

- `cli.ts:99` calls `code-review-graph embed` -- no `embed` subcommand in `cli.py`
- `cli.ts:63` passes `--full` flag for `buildGraph` -- `cli.py` `build` command doesn't accept `--full`
- "Compute Embeddings" command silently fails for every VS Code user

**Fix**: Either add the missing CLI subcommands, or fix the VS Code extension to call what exists. Both are out of sync.

### MEDIUM: Tests -- comprehensive TDD suite

**Status: DONE** -- 703 tests, 1 xfail remaining (bare-name reverse tracing)

Added `test_pain_points.py` with 53 TDD tests targeting known evaluation gaps. 8/9 xfails flipped to passing through concrete fixes. Also fixed 7 pre-existing test_tools failures caused by stale store cache. 4 Jedi enrichment tests added.

### MEDIUM: Thread safety is aspirational

Locks exist in the right places (`refactor.py`, `registry.py`, `graph.py`, `incremental.py`) but:
- The parser's module cache (`_MODULE_CACHE`) is a plain dict with no lock, shared across threads
- `_file_hash_cache` in parser.py -- no synchronization
- `_import_map` rebuilt per-file but stored on the parser instance

In practice this is mostly fine because MCP tools are sequential, but the code doesn't enforce that.

### Summary: What justifies a fork

| Issue | Severity | Status |
|---|---|---|
| RCE in embeddings | CRITICAL | **FIXED** (`cdf8f21`) |
| Connection pooling | HIGH | **FIXED** (`cdf8f21`, `ec40e5b`) |
| Parser god class | HIGH | **DONE** -- 19 langs to `lang/`, -235 lines, 16 dispatches remain |
| VS Code extension | HIGH | STILL OPEN |
| Test quality | MEDIUM | **DONE** -- 703 tests, 53 TDD pain point tests, 1 xfail |
| Thread safety | MEDIUM | STILL OPEN |

---

## 9. Easy Wins Still Available (within tree-sitter)

### Win 1: Continuous risk scoring -- DONE
Implemented in commit `cdf8f21`. `changes.py` now uses continuous scale: `0.30 - (min(test_count / 5.0, 1.0) * 0.25)`. Verified by `test_risk_score_decreases_with_more_tests` and `test_risk_scores_span_meaningful_range`.

### Win 2: Java/Kotlin per-symbol imports -- DONE
`_get_jvm_import_names()` in commit `cdf8f21`, then package-path fallback in `a0ba7d2`. Per-symbol IMPORTS_FROM edges now fire even without file resolution, using `com.example.auth::UserService` format. All 4 JVM xfail tests passing.

### Win 3: Module-level `import X` tracking -- DONE
Implemented in commit `13a53f8`. Flipped 2 xfail tests.

### Win 4: Framework entry point patterns -- DONE
Added in commit `cdf8f21`: Express `app.get/post/use`, Android lifecycle `@Override`/`@Composable`, Kotlin `@HiltViewModel`/`@AndroidEntryPoint`, name patterns for `onCreate/onResume/onDestroy`, `doGet/doPost`, `errorHandler/middleware`. Verified by 9 passing entry point tests.

### Win 5: Weighted flow criticality in risk scoring -- OPEN
`changes.py:161-163` -- currently 0.05 per flow, capped at 0.25. Weight by flow criticality (already computed) to distinguish "in 1 trivial flow" from "in 3 critical flows".

### Win 6: Qualify uppercase-receiver calls -- DONE
Implemented in commit `5668532`. `_get_call_name()` now returns `"ClassName.method"` when receiver starts with uppercase. `_resolve_call_target()` handles the dotted format. Gadgetbridge went from 6/10 to 10/10.

### Win 7: Framework decorator patterns for Click subgroups + Pydantic -- DONE
Implemented in commit `5668532`. Added `\w+\.(command|group)\b` for Click subgroups and `(field|model)_(serializer|validator)` for Pydantic.

### Win 8: Module-level call emission -- DONE
Implemented in commit `5668532`. `_extract_calls()` now uses file path as source when `enclosing_func` is None.

### Win 9: Function-reference-as-argument tracking -- DONE
Implemented in commit `0c88d4b`. Post-parse enrichment `_enrich_func_ref_args()` scans call argument lists for identifiers matching `defined_names`. Handles keyword args (`target=fn`), positional args, and Kotlin callable refs (`::fn`).

### Win 10: Constructor-based type inference -- DONE
Implemented in commit `ef495b3`. Extends typed-var walkers to infer types from `x = SomeClass()` (Python), `val x = SomeClass()` (Kotlin), `var x = new SomeClass()` (Java). Also added new JS/TS typed-var walker for `const x = new SomeClass()` and `const x: SomeType = ...`.

### Win 11: Star import resolution -- DONE
Implemented in commit `cae05b2`. `from X import *` now resolves the target module, scans for exported names (respects `__all__`), and populates `import_map`. Includes caching and circular-import guard.

---

## 10. Process Improvements

### What worked
- Two real-world test projects with quantitative baselines
- Per-PR branch workflow keeps changes reviewable
- Iterative fix-evaluate cycle converges quickly on specific regressions
- `loop-test.md` as a reproducible evaluation playbook

### What to change
- **Always use tool output for evaluation**, never raw SQL (the tool IS the product)
- **Add large-graph integration tests** to catch community/flow issues before manual eval
- **Consider squash-merging PR branches** instead of cherry-picking (less sync overhead)
- **Run both test projects after every change**, not just one at a time
- **TDD for known pain points**: write xfail tests from evaluation failures FIRST, then iterate fixes until they pass -- much faster feedback loop than manual eval cycles
- **Keep crg-future.md current**: update status after each commit, not in batches

---

## 11. Fork Strategy

The upstream maintainer hasn't been responsive. Our 3 draft PRs (#104, #107, #108) contain substantial improvements but can't merge. Meanwhile, deeper refactoring (parser split, connection pooling, security fix, enrichment architecture) would diverge significantly from upstream.

### Plan
1. **Leave PRs open** on upstream -- they document our contributions and can be merged if the maintainer returns
2. **Continue development in our fork** for:
   - ~~Security fix (trust_remote_code)~~ DONE
   - ~~Connection pooling in tools~~ DONE
   - Parser refactoring (god class -> strategy pattern) -- IN PROGRESS
   - VS Code extension fixes
   - Pluggable enrichment architecture
3. **Maintain merge compatibility** with upstream where possible -- don't rename the package or change the MCP interface without reason

### Fork priorities (order of work)

| Priority | Work | Status | Commit/Note |
|---|---|---|---|
| 1 | Fix trust_remote_code RCE | **DONE** | `cdf8f21` |
| 2 | Wire connection pooling to tools | **DONE** | `cdf8f21` |
| 3 | Easy wins (risk scoring, Java imports, entry points) | **DONE** | `cdf8f21` |
| 3b | Module-level `import X` tracking | **DONE** | `13a53f8` |
| 3c | Weighted flow criticality | **OPEN** | |
| 4 | Parser refactoring into LanguageHandler strategy | **DONE** (phase 1+2) | 19 langs extracted to `lang/`, -235 lines |
| 5 | DRY TESTED_BY generation | **DONE** | `d226689` |
| 6 | VS Code extension fixes | **OPEN** | Broken `embed` + `--full` |
| 7 | TDD test suite | **DONE** | 699 passing, 1 xfail |
| 8 | Typed variable call enrichment (Python/Kotlin/Java) | **DONE** | `19d5e15`, `30c8c0e` |
| 8b | Constructor-based type inference (Py/Kt/Java/TS/JS) | **DONE** | `ef495b3` |
| 9 | JVM per-symbol imports without file resolution | **DONE** | `a0ba7d2` |
| 10 | Qualify uppercase-receiver calls (`ClassName.method()`) | **DONE** | `5668532` |
| 11 | Framework decorator patterns (Click subgroups, Pydantic) | **DONE** | `5668532` |
| 12 | Module-level call emission (enclosing_func=None) | **DONE** | `5668532` |
| 13 | Function-reference-as-argument tracking | **DONE** | `0c88d4b` |
| 14 | Star import resolution (`from X import *`) | **DONE** | `cae05b2` |
| 15 | JS/TS typed-variable walker | **DONE** | `ef495b3` |
| 16 | Jedi enrichment for Python | **DONE** | `326bcce` -- 8 calls resolved in HealthAgent |
| 17 | Override method dead code check | **DONE** | 146->139 dead code, 7 connector sync methods no longer FP |
| 18 | scip-java enrichment for Java/Kotlin | **OPEN** | |
| 19 | TS Compiler API enrichment | **OPEN** | |

### TDD xfail tracker (`tests/test_pain_points.py`)

Each xfail represents a concrete improvement target. Flip it to pass = the fix works.

| xfail test | Category | Unblocked by |
|---|---|---|
| ~~`test_module_import_attribute_call_resolved`~~ | ~~Resolution~~ | ~~DONE (`13a53f8`)~~ |
| ~~`test_module_import_nested_attribute`~~ | ~~Resolution~~ | ~~DONE (`13a53f8`)~~ |
| ~~`test_star_import_call_resolved`~~ | ~~Resolution~~ | ~~DONE (`cae05b2`)~~ |
| ~~`test_java_import_creates_per_symbol_edge`~~ | ~~Resolution~~ | ~~DONE (package-path fallback)~~ |
| ~~`test_kotlin_import_creates_per_symbol_edge`~~ | ~~Resolution~~ | ~~DONE (package-path fallback)~~ |
| ~~`test_method_on_typed_variable_resolves`~~ | ~~Resolution~~ | ~~DONE (typed var enrichment `19d5e15`)~~ |
| `test_bare_name_reverse_tracing` | Dead code | Cross-file graph-level resolution |
| ~~`test_java_import_per_symbol`~~ (integration) | ~~Resolution~~ | ~~DONE (package-path fallback `a0ba7d2`)~~ |
| ~~`test_kotlin_import_per_symbol`~~ (integration) | ~~Resolution~~ | ~~DONE (package-path fallback `a0ba7d2`)~~ |

**8/9 resolved. 1 remaining xfail.**

---

## 12. Decision Log

Track key decisions so we don't re-litigate them.

| Date | Decision | Rationale | Outcome |
|---|---|---|---|
| 2026-04 | Filter method calls in prod code, allow in test files | `obj.method()` without type info creates noise; test files need it for TESTED_BY | Good tradeoff: TESTED_BY restored, prod graph cleaner |
| 2026-04 | Allow uppercase receiver calls through filter | `ClassName.method()` is reliably a static/companion call | Low noise, captures Kotlin companion objects |
| 2026-04 | Make igraph a core dependency (not optional) | CLI `uv tool install` doesn't install extras; igraph was invisible to deployed tool | Fixed communities detection for CLI users |
| 2026-04 | Adaptive directory-based community fallback | Fixed-depth (3 segments) fails for both flat repos and deep Java packages | Works for both HealthAgent (245 files) and Gadgetbridge (3573 files) |
| 2026-04 | Resolution scaling `1/log10(nodes)` for Leiden | Default resolution=1.0 over-fragments large graphs into thousands of micro-communities | Produces reasonable cluster counts; falls back to directory when still too many |
| 2026-04 | Per-symbol IMPORTS_FROM for Python | JS/TS already had this; Python `from X import Y as Z` was file-level only | Reduced dead code FP; improved import graph accuracy |
| 2026-04 | @property skip in dead code detection | @property functions are invoked via attribute access, never via CALLS edges | Eliminated common FP category |
| 2026-04 | INHERITS bare-name lookup in dead code detection | Classes referenced only by bare-name INHERITS edges looked dead to qualified-name search | Fixed BaseConnector-style FP where subclasses are in different files |
| 2026-04-06 | Remove trust_remote_code=True from embeddings | RCE via malicious HuggingFace model; default model doesn't need it | Fixed in `cdf8f21` |
| 2026-04-06 | Cache GraphStore per db_path in _get_store() | Fresh connection per MCP call wasted ~10ms each time | Fixed in `cdf8f21` |
| 2026-04-06 | Continuous risk scoring (0.30 -> 0.05 over 5 tests) | Binary scoring clustered all risk scores at 0.50-0.70 | Verified with monotonic decrease test |
| 2026-04-06 | JVM per-symbol imports gated on module resolution | Per-symbol edges only useful if we know which file to point to | 3 xfail tests track when scip-java makes this work |
| 2026-04-06 | TDD-first for remaining work | 6 eval iterations taught us: write failing tests from known pain points, then iterate fixes | 9 xfails as concrete improvement targets |
| 2026-04-06 | BaseLanguageHandler strategy pattern | Batch by method (not language) for extraction; NotImplemented sentinel for fallback | Go/Python/JS/TS/TSX extracted, -130 lines |
| 2026-04-06 | Tree-sitter typed var enrichment over Jedi | Explicit type annotations (`x: T = ...`) sufficient for `x.method()` resolution; no runtime dep needed | Flipped `test_method_on_typed_variable_resolves` xfail |
| 2026-04-06 | JVM per-symbol imports without file resolution | Package path fallback (`com.example.auth::UserService`) when file can't be found on disk | Flipped 4 JVM xfails without needing scip-java |
| 2026-04-06 | BaseLanguageHandler + NotImplemented sentinel | Handlers only override what they customize; returning NotImplemented falls back to CodeParser default logic | Go handler extracted cleanly; parser.py ~25 lines shorter |
| 2026-04-06 | Go as first handler extraction | Fewest special cases (3 branches, 5 constant entries), clean AST-only logic, no shared utility access needed | Validated the pattern; also fixed pre-existing embedded struct detection bug |
| 2026-04-06 | Investigation: uppercase receiver calls drop qualifier | `_get_call_name()` returns `"sync"` for `StepsSyncer.sync()`. Root cause of 4 Gadgetbridge test failures. Fix: return `"ReceiverName.method"` when `is_class_call=True` | Highest-impact single fix remaining |
| 2026-04-06 | Investigation: module-level calls silently dropped | `_extract_calls()` guards with `if enclosing_func:`, skipping calls at file scope. Fix: use file path as source | HealthAgent FP for `_register_commands()` |
| 2026-04-06 | Investigation: framework decorator patterns too narrow | Click `@digest.command()` doesn't match `click\.(command\|group)` regex. Pydantic validators absent. | 4 HealthAgent dead code FPs |
| 2026-04-06 | Investigation: function-as-argument not tracked | `Thread(target=agent_thread)` -- the identifier is an argument, not a call node. No CALLS edge emitted. | 4 HealthAgent dead code FPs; needs post-parse enrichment |
| 2026-04-06 | DataExporter.export callers: eval expectation was wrong | Grep shows only 1 Kotlin caller (HealthConnectDebugFragment), not "2 Java callers" as eval expected | Updated eval expectations |
| 2026-04-06 | All v8 fixes implemented and validated | Uppercase-receiver, decorators, module-level calls, func-ref args, constructor inference, JS/TS walker, star imports | Gadgetbridge 10/10, HealthAgent 28.6% resolution, 699 tests |
| 2026-04-06 | Phase 0 (tree-sitter wins) complete | All practical tree-sitter heuristics exhausted. Remaining unresolved targets are SDK/framework symbols (Column, useState, Depends) unreachable without type checkers | Next step: Jedi integration (Phase 1) |
| 2026-04-06 | Generic over specific | User feedback: fixes must be generic across languages, not project-specific. All enrichments work for any project, not just HealthAgent/Gadgetbridge | Pattern: post-parse enrichment hooks |
| 2026-04-06 | Jedi as post-build step, not per-file | Jedi needs `jedi.Project(path=repo_root)` for cross-file resolution. Running per-file in `parse_bytes()` lacks project context. Post-build walks Python ASTs, uses DB for enclosing-function lookup | Clean separation; works with parallel parsing |
| 2026-04-06 | Jedi enrichment modest on HealthAgent (8 calls) | Most unresolved HealthAgent targets are SDK symbols (Column, Depends, useState) not reachable by Jedi. Factory-pattern calls are the main win | Phase 2 (scip-java) likely higher impact for Gadgetbridge |
| 2026-04-06 | Override method dead code check via INHERITS traversal | When `self.sync()` in BaseConnector resolves to `BaseConnector.sync`, subclass overrides had zero callers. Fix: in find_dead_code(), check if parent class method has callers, mark overrides alive | 7 connector .sync() methods no longer FP. safe_request correctly stays dead (genuinely unused) |
| 2026-04-06 | safe_request is genuinely dead, not a FP | grep confirms safe_request is defined but never called anywhere in HealthAgent. FP spot check expectation was wrong | FP spot check is actually 10/10 PASS |

---

## Appendix: Tool & Alternative Research

### Per-language enrichment candidates

| Language | Tool | Type | Integration | Maturity |
|---|---|---|---|---|
| Python | **Jedi** | Native Python lib | `jedi.Script().get_references()` | Production |
| Java/Kotlin | **scip-java** | Gradle/Maven plugin | Emit `.scip` at build time, consume protobuf | Production |
| TypeScript | **TS Compiler API** | Node.js | subprocess + JSON IPC | Production |
| Go | **go/callgraph** | Go stdlib | subprocess + JSON | Production |
| Rust | **rust-analyzer** | LSP | subprocess + LSP protocol | Production |

### Approaches evaluated and rejected

| Approach | Why rejected |
|---|---|
| Full LSP for all languages | Not designed for batch; startup overhead; no call graph API in protocol |
| SCIP producers for all languages | Too much work. But scip-java for Java/Kotlin is worth it since gradle emits it natively |
| Eclipse JDT LS for Java | LSP overhead, complex setup. scip-java is simpler for gradle projects |
| kotlin-compiler-embeddable | Needs JVM at analysis time. scip-java covers Kotlin too via gradle plugin |
| CodeQL | Designed for security research; slow; overkill |
| IntelliJ PSI | Too heavy; not designed for headless; huge memory footprint |
| Replace tree-sitter entirely | Tree-sitter is excellent at structure extraction; wrong to throw it away |
| Runtime tracing | Requires executing code; security/sandbox concerns; different product |

### Key numeric baselines (for future comparison)

```
HealthAgent v9:
  Files: 253 | Nodes: 2,493 | Edges: 21,308
  CALLS: 12,362 | Resolved: 3,537 (28.6%) | TESTED_BY: 3,510
  Dead code: 139 | Grep FP: ~53% | FP spot check: 10/10 (safe_request genuinely dead)
  Top unresolved: Column(951), text(490), json(243), useState(237)
  Communities: 16 | Flows: 15+ (test-dominated top entries)

Gadgetbridge v9:
  Files: 3,573 | Nodes: 41,097 | Edges: 276,411
  TESTED_BY: 7,409 | Resolution: 32.6%
  Communities: 11 | Flows: 3,059
  Risk scores: 0.50-0.70 (29 changed functions)
  Scorecard: 9/10 PASS, 1 PARTIAL
```
