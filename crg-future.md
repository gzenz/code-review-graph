# code-review-graph: Strategic Analysis & Future Direction

Last updated: 2026-04-08 (v17 -- workspace resolution, Angular template improvements, dead code FP reduction, VS Code extension fixes)

---

## Table of Contents

1. [Current Status](#1-current-status)
2. [Open Work](#2-open-work)
3. [Architecture & Limits](#3-architecture--limits)
4. [Process](#4-process)
5. [History](#5-history)

---

## 1. Current Status

### HealthAgent (Python/TypeScript, 261 files)

| Metric | v1 | v6 | v10 | v14 | Trend |
|---|---|---|---|---|---|
| Total edges | 22,737 | 19,362 | 21,926 | **24,991** | Steady growth |
| Resolution rate | 11.7% | 28.0% | **45.6%** | **40.0%** | Plateau ~40% |
| Resolved CALLS | 1,736 | 2,976 | 5,831 | **6,281** | +164 |
| TESTED_BY | 3,603 | 3,420 | 3,570 | **3,667** | Stable |
| Decorator nodes | present | 244 | 244 | 245 | Stable |
| Dead code (tool) | 577 | 191 | ~140 | **101** | -47% since v6 |
| Grep FP rate | 92% | ? | ~47% | **40%** | Improving |
| FP spot check | 1/10 | 10/10 | 10/10 | **10/10** | All correct |

### Gadgetbridge (Java/Kotlin, 3574 files)

| Metric | v6 | v10 | v12 | v14 | Target |
|---|---|---|---|---|---|
| callees_of(syncDataTypeSlice) | 14 | 15 | 14+mutableListOf | PASS | PASS |
| callees_of(SleepSyncer.sync) | 18 | PASS | PASS | PASS | PASS |
| callers_of(SleepSyncer.sync) | 0 | PASS | PASS | PASS | PASS |
| callers_of(DataExporter.export) | 3 | PASS | PASS | PASS | PASS |
| tests_for(RecordedWorkoutSyncer) | WorkoutSyncerUtilsTest | PARTIAL | **PASS (41 tests)** | PASS | PASS |
| Communities | 11 | 11 | 11 | 11 | 10-50 |
| Flows | 3,224 | 4,060 | top10: 0.95-0.96 | 0.95-0.96 | lifecycle entries |
| Risk score range | 0.50-0.70 | 0.0-1.0 | 0.25-0.85 | 0.25-0.85 | differentiated |
| Resolution rate | - | **36.3%** | 35.9% | 35.9% | - |

**Gadgetbridge scorecard: 11/11 PASS** (v14)

### Test suite

829 tests passing, 4 skipped, 0 xfail. Includes:
- 53 TDD pain-point tests (`test_pain_points.py`)
- 26 hardened tests (`test_hardened.py`) -- exact risk/flow scores, error paths, cache eviction

### Cova (TypeScript/Python monorepo, 1,668 files)

| Metric | v13 (2026-04-07) | v14 (2026-04-08) | Change |
|---|---|---|---|
| Total edges | 82,885 | **86,156** | +3,271 |
| IMPORTS_FROM | 10,294 | **12,968** | +2,674 (workspace resolution) |
| Resolution rate | 38.4% | **39.1%** | +0.7% |
| Dead code | ~480 | **236** | -51% |
| Grep FP rate | ~73% | **~50%** | -23pp |

### Recent commits (this session)

| Commit | What |
|---|---|
| `dc9ed65` | Workspace package alias resolution, dead code FP reduction (CDK, decorators, plausible caller) |
| `4891fa7` | Dead code FP reduction — decorators, CDK methods, abstract overrides, .d.ts, test-utils |
| (pending) | Angular template improvements, VS Code extension fixes, `embed` CLI subcommand |

---

## 2. Open Work

### ~~HIGH: VS Code extension ships broken commands~~ DONE (v17)

- ~~`cli.ts:99` calls `code-review-graph embed` -- no `embed` subcommand in `cli.py`~~ Added `embed` CLI subcommand
- ~~`cli.ts:63` passes `--full` flag for `buildGraph` -- `cli.py` `build` command doesn't accept `--full`~~ Removed invalid `--full` flag
- ~~"Compute Embeddings" command silently fails for every VS Code user~~ Fixed

### MEDIUM: Thread safety is aspirational

- `_MODULE_CACHE` in parser.py -- plain dict, no lock, shared across threads
- `_file_hash_cache` in parser.py -- no synchronization
- `_import_map` rebuilt per-file but stored on the parser instance
- Fine in practice (MCP tools are sequential) but not enforced

### ~~MEDIUM: Build performance~~ DONE (v16)

Gadgetbridge full build: **~72s -> ~23s** (3x faster overall).

Phase timing (Gadgetbridge, 3,575 files, 41k nodes, 280k edges):

| Phase | v15 | v16 | Speedup |
|---|---|---|---|
| Parsing (parallel) | 15.3s | 11.5s | 1.3x (batch storage) |
| Jedi enrichment | 0.3s | 0.4s | -- |
| Bare-name resolution | 0.8s | 1.2s | -- |
| Signatures | 0.3s | 0.3s | -- |
| FTS rebuild | 0.9s | 0.5s | 2x |
| Flows | 5.5s | 5.5s | -- |
| **Communities** | **48.6s** | **2.3s** | **21x** |
| Summaries | 0.8s | 1.4s | -- |

Changes made:
- Thread safety: `threading.Lock` on CodeParser caches (watch mode safe)
- Batch file storage: 50 files/transaction via `store_file_batch()`
- Batch risk_index: 2 GROUP BY queries replace ~70k per-node COUNT queries
- Community detection: bulk `get_all_nodes()` (1 query vs 3,574), adjacency-indexed cohesion
- Phase timing at INFO level in build and postprocess

Remaining opportunity: `trace_flows()` at 5.5s is now the largest postprocess phase.

### MEDIUM: Remaining dead code FP sources (~50% grep FP rate)

**HealthAgent** (~40% FP rate):

| FP category | Count | Root cause | Potential fix |
|---|---|---|---|
| String-based lazy imports | 4 | `"module.path:ClassName"` in dicts | Pattern-match string module references |
| Function-ref-as-argument (tenacity) | 2 | `retry_if_exception(_is_retryable)` not matched | Check if current func-ref walker covers this pattern |
| Instance method resolution | 1 | `settings.validate_startup()` -- lowercase instance vs `Settings` class | Rewrite during bare-name resolution |
| UI component library re-exports | ~74 | shadcn/ui components exported but never imported | `--exclude-exports` flag or UI library heuristic |

**Cova** (~50% FP rate, 236 dead total):

| FP category | Count | Root cause | Potential fix |
|---|---|---|---|
| Angular template expressions | ~13 | Complex bindings regex can't parse | Angular compiler API (weeks of work) |
| Cross-file TS imports | ~20 | IMPORTS_FROM edges missing for intra-package imports | Better TS module resolution |
| Short/common names | ~10 | `response`, `accessToken`, `reference` -- inherently ambiguous | Name length/frequency filter |
| Cross-file Python imports | ~5 | Functions in `shared/` dirs imported via `__init__.py` re-exports | Improved (still gaps) |
| Non-abstract method overrides | ~5 | Base class methods overridden in subclasses | INHERITS-based override detection |

### Summary table

| Issue | Severity | Status |
|---|---|---|
| ~~VS Code extension~~ | ~~HIGH~~ | **DONE** (v17) -- `embed` CLI added, `--full` flag removed |
| ~~Thread safety~~ | ~~MEDIUM~~ | **DONE** (v16) |
| ~~Build performance~~ | ~~MEDIUM~~ | **DONE** (v16) -- 48.6s -> 2.3s communities, 3x overall |
| Dead code FP rate (~50%) | MEDIUM | IMPROVED -- 252 -> 236 dead on cova, structural limits remain |
| scip-java for Java/Kotlin | LOW | DEPRIORITIZED -- ROI unclear vs 2-4 week effort |

---

## 3. Architecture & Limits

### What tree-sitter gives us

- Syntax trees for 19 languages with consistent API
- Fast: full parse of 3,573-file Gadgetbridge in ~30s
- Incremental: only re-parse changed files
- Reliable production-quality grammars

### The ~60% wall

Tree-sitter is a parser, not a compiler. Without a symbol table, ~60% of CALLS edges stay as bare names. This is the architectural ceiling.

| Missing capability | Needed for | Fixable? |
|---|---|---|
| Variable types | `obj.method()` -> `ClassName.method()` | NO (need type inference) |
| External module resolution | `import numpy` -> file path | PARTIALLY (package metadata) |
| Scope chain / symbol table | Distinguishing local vs imported `sync` | NO |
| Interface/trait resolution | `Syncer.sync()` -> `SleepSyncer.sync()` | NO |

Top unresolved targets are SDK/framework symbols: `Column` (959), `execute` (565), `text` (547), `useState` (240). These will never resolve to user code -- they're external.

### Enrichment strategy (Option B: Hybrid)

Tree-sitter for structure + per-language enrichers for resolution:

| Phase | Language | Tool | Status |
|---|---|---|---|
| 0 | All | Tree-sitter heuristics (28 -> 40% resolution) | **DONE** |
| 0b | All | Post-build bare-name resolution (+2,294 HA, +5,625 GB) | **DONE** |
| 1 | Python | Jedi (post-build, 8 additional calls on HA) | **DONE** |
| 2 | Java/Kotlin | scip-java (gradle plugin) | **DEPRIORITIZED** |
| 3a | JS/TS | Namespace imports, CommonJS, re-exports | **DONE** |
| 3b | JS/TS | TS Compiler API | **NOT WORTH DOING** (100% external API) |
| 4 | Go | go/callgraph | Future |

### What NOT to do

- IntelliJ PSI (too heavy), CodeQL (overkill), replace tree-sitter (excellent at what it does)
- Build SCIP producers for all 19 languages (too much work)
- TS Compiler API (unresolved targets are all external -- zero impact)

---

## 4. Process

### Evaluation workflow

- Two real-world test projects: HealthAgent (261 files, Python/TS) and Gadgetbridge (3,574 files, Java/Kotlin)
- Quantitative scorecard with PASS/PARTIAL/FAIL on specific queries
- `loop-test.md` is the reproducible evaluation playbook
- TDD-first: write xfail tests from eval pain points, then iterate fixes

### Rules

- Always use tool output for evaluation, never raw SQL (the tool IS the product)
- Run BOTH test projects after every change
- Fixes must be generic across languages, not project-specific
- Keep crg-future.md current after each commit

### Per-PR branch workflow

| PR | Branch | Scope |
|----|--------|-------|
| #100 | `fix/claude-code-hooks-and-cli-flags` | CLI flags, hooks template, skills.py |
| #102 | `fix/search-quality-and-deduplication` | search.py, query deduplication |
| #103 | `feat/pretooluse-search-enrichment` | PreToolUse hook, enrich command |
| #104 | `fix/reduce-dead-code-false-positives` | refactor.py dead code detection |
| #107 | `fix/kotlin-calls` | Kotlin/Java parser, test_multilang.py |
| #108 | `fix/filter-method-call-noise` | Method call filter, JSX, builtins, communities |

---

## 5. History

<details>
<summary>Completed work (click to expand)</summary>

### Fixes that had high impact

1. **Test-file exemption from method call filtering** (PR #108) -- TESTED_BY: 0 -> 6,140 on Gadgetbridge
2. **Uppercase receiver heuristic** (PR #107/#108) -- `ClassName.method()` through filter
3. **Per-symbol IMPORTS_FROM edges** (PR #108) -- `from X import Y as Z` creates `::Y` edge
4. **Adaptive community detection** (PR #108) -- Leiden + common-prefix stripping + adaptive depth
5. **Dead code accuracy** (PR #104) -- @property skip, INHERITS lookup, override method check

### Community detection: 5 iterations

| Iter | Approach | Result |
|---|---|---|
| 1 | Leiden default resolution=1.0 | 3,568 communities (over-fragmented) |
| 2 | Resolution scaling `1/log10(nodes)` | 3,617 (still too many) |
| 3 | File-based fallback | 2,712 (too granular) |
| 4 | Directory-based, 3 fixed segments | 1 community (Android `app/src/main` for all) |
| 5 | Common-prefix stripping + adaptive depth | 11 communities (correct) |

### Method call filtering tradeoffs

| Approach | Precision | Recall | Problem |
|---|---|---|---|
| Allow all | LOW | HIGH | Graph noise, dead code useless |
| Block all non-self (v1) | HIGH | LOW | TESTED_BY destroyed |
| self/cls/this + uppercase + test files | MEDIUM | MEDIUM | Current sweet spot |

### Code quality audit (all addressed)

| Issue | Severity | Status |
|---|---|---|
| RCE in embeddings (trust_remote_code) | CRITICAL | **FIXED** (`cdf8f21`) |
| Connection pooling | HIGH | **FIXED** (`cdf8f21`, `ec40e5b`) |
| Parser god class (4,160 -> 3,149 lines) | HIGH | **DONE** (handler migration `135e49b`) |
| Test quality (820 tests, 0 xfail) | MEDIUM | **DONE** |
| Silent failures (logging added) | MEDIUM | **DONE** (`242d521`) |
| Call resolution fallback | MEDIUM | **DONE** (`242d521`) |
| Cache eviction (evict-oldest-half) | LOW | **DONE** (`242d521`) |

### Fork priorities (27 items, 26 DONE)

| # | Work | Status |
|---|---|---|
| 1 | Fix trust_remote_code RCE | **DONE** (`cdf8f21`) |
| 2 | Wire connection pooling to tools | **DONE** (`cdf8f21`) |
| 3 | Easy wins (risk scoring, Java imports, entry points) | **DONE** |
| 3b | Module-level `import X` tracking | **DONE** (`13a53f8`) |
| 3c | Weighted flow criticality | **DONE** (`48c38dd`) |
| 4 | Parser refactoring into LanguageHandler strategy | **DONE** (`135e49b`) |
| 5 | DRY TESTED_BY generation | **DONE** (`d226689`) |
| 6 | VS Code extension fixes | **DONE** (v17) |
| 7 | TDD test suite | **DONE** (829 tests) |
| 8 | Typed variable call enrichment | **DONE** (`19d5e15`, `30c8c0e`) |
| 8b | Constructor-based type inference | **DONE** (`ef495b3`) |
| 9 | JVM per-symbol imports | **DONE** (`a0ba7d2`) |
| 10 | Qualify uppercase-receiver calls | **DONE** (`5668532`) |
| 11 | Framework decorator patterns | **DONE** (`5668532`) |
| 12 | Module-level call emission | **DONE** (`5668532`) |
| 13 | Function-reference-as-argument tracking | **DONE** (`0c88d4b`) |
| 14 | Star import resolution | **DONE** (`cae05b2`) |
| 15 | JS/TS typed-variable walker | **DONE** (`ef495b3`) |
| 16 | Jedi enrichment for Python | **DONE** (`326bcce`) |
| 17 | Override method dead code check | **DONE** (`d25f8a0`) |
| 18 | Post-build bare-name resolution | **DONE** (`9038765`) |
| 19 | JS/TS namespace imports, require(), re-exports | **DONE** (`0aa4d38`) |
| 20 | Transitive TESTED_BY | **DONE** (`04327b6`) |
| 21 | JSX attribute function references | **DONE** |
| 22 | Class-level transitive TESTED_BY | **DONE** |
| 23 | Decorator pattern gaps | **DONE** (`06aeb42`) |
| 24 | Nested function-ref-as-argument tracking | **DONE** (`0f26ef5`) |
| 25 | Python HTTP handler entry points | **DONE** (`0f26ef5`) |
| 26 | scip-java | **DEPRIORITIZED** |
| 27 | TS Compiler API | **NOT WORTH DOING** |

### TDD xfail tracker -- all 9 resolved

All 9 xfails from `test_pain_points.py` flipped to passing. 15 additional tests added.

### Easy wins (tree-sitter) -- all 11 DONE

1. Continuous risk scoring (`cdf8f21`)
2. Java/Kotlin per-symbol imports (`a0ba7d2`)
3. Module-level `import X` tracking (`13a53f8`)
4. Framework entry point patterns (`cdf8f21`)
5. Weighted flow criticality (`48c38dd`)
6. Qualify uppercase-receiver calls (`5668532`)
7. Framework decorator patterns (`5668532`)
8. Module-level call emission (`5668532`)
9. Function-reference-as-argument tracking (`0c88d4b`)
10. Constructor-based type inference (`ef495b3`)
11. Star import resolution (`cae05b2`)

</details>

<details>
<summary>Decision log (click to expand)</summary>

| Date | Decision | Rationale | Outcome |
|---|---|---|---|
| 2026-04 | Filter method calls in prod, allow in test files | test files need TESTED_BY | TESTED_BY restored, prod cleaner |
| 2026-04 | Allow uppercase receiver calls through filter | `ClassName.method()` reliably static | Low noise, captures Kotlin companions |
| 2026-04 | Make igraph a core dependency | CLI `uv tool install` doesn't install extras | Fixed communities for CLI users |
| 2026-04 | Adaptive directory-based community fallback | Fixed-depth fails for both flat and deep repos | Works for 245 and 3573 file repos |
| 2026-04 | Per-symbol IMPORTS_FROM for Python | JS/TS already had it | Reduced dead code FP |
| 2026-04 | @property skip in dead code | Attribute access, never CALLS edges | Eliminated common FP |
| 2026-04 | INHERITS bare-name lookup | Subclasses in different files looked dead | Fixed BaseConnector FPs |
| 2026-04-06 | Remove trust_remote_code from embeddings | RCE risk, default model doesn't need it | Fixed |
| 2026-04-06 | Cache GraphStore per db_path | Fresh connection per MCP call wasted ~10ms | Fixed |
| 2026-04-06 | TDD-first for remaining work | 6 eval iterations proved xfail-driven is faster | 9 xfails as targets |
| 2026-04-06 | BaseLanguageHandler + NotImplemented sentinel | Handlers override only what they customize | Clean extraction pattern |
| 2026-04-06 | Tree-sitter typed var enrichment over Jedi | `x: T = ...` sufficient for `x.method()` | No runtime dep needed |
| 2026-04-06 | JVM per-symbol imports without file resolution | Package path fallback works | 4 xfails without scip-java |
| 2026-04-06 | Generic over specific | Fixes must work for any project | All enrichments are generic |
| 2026-04-06 | Jedi as post-build step, not per-file | Needs `jedi.Project(path=repo_root)` for cross-file | Clean separation |
| 2026-04-06 | safe_request is genuinely dead | grep confirms never called | FP spot check is 10/10 |
| 2026-04-07 | Post-build bare-name CALLS resolution | Can't resolve cross-file at parse time | +2,294 HA, +5,625 GB |
| 2026-04-07 | Transitive TESTED_BY | Direct TESTED_BY misses indirect coverage | Fixed RecordedWorkoutSyncer |
| 2026-04-07 | TS/JS Tier 2 NOT WORTH DOING | 100% external API unresolved | Saved 4-6 weeks |
| 2026-04-07 | Class-level transitive TESTED_BY | CALLS edges have method-level sources | Expand class via CONTAINS |
| 2026-04-07 | Grep FP root cause is decorators, not JSX | FastAPI/Pydantic/CLI endpoint functions | Decorator exclusion priority |
| 2026-04-07 | Decorator pattern gaps filled | Missing bare @tool, Pydantic AI, Flask bp | request_id_middleware excluded |
| 2026-04-07 | Nested func names added to defined_names | Thread(target=fn) invisible for nested defs | Dead code 122->101 |
| 2026-04-07 | upsert_batch is NOT a dead code FP | SQL query missed class-prefixed name | 10/10 confirmed |

</details>

<details>
<summary>Rejected approaches (click to expand)</summary>

| Approach | Why rejected |
|---|---|
| Full LSP for all languages | Not batch-oriented; startup overhead; no call graph API |
| SCIP producers for all languages | Too much work (but scip-java is feasible for gradle) |
| Eclipse JDT LS for Java | LSP overhead, complex setup |
| kotlin-compiler-embeddable | Needs JVM at analysis time |
| CodeQL | Designed for security research; overkill |
| IntelliJ PSI | Too heavy; not headless-friendly |
| Replace tree-sitter entirely | Excellent at structure extraction |
| Runtime tracing | Security concerns; different product |
| TS Compiler API | Unresolved targets are 100% external API -- zero impact |

</details>

<details>
<summary>Numeric baselines (click to expand)</summary>

```
HealthAgent v9 (2026-04-06):
  Files: 253 | Nodes: 2,493 | Edges: 21,308
  CALLS: 12,362 | Resolved: 3,537 (28.6%) | TESTED_BY: 3,510
  Dead code: 139 | Grep FP: ~53% | FP spot check: 10/10
  Top unresolved: Column(951), text(490), json(243), useState(237)

Gadgetbridge v9 (2026-04-06):
  Files: 3,573 | Nodes: 41,097 | Edges: 276,411
  TESTED_BY: 7,409 | Resolution: 32.6%
  Communities: 11 | Flows: 3,059
  Risk scores: 0.50-0.70 | Scorecard: 9/10 PASS, 1 PARTIAL
```

</details>

### Per-language enrichment candidates

| Language | Tool | Type | Status |
|---|---|---|---|
| Python | **Jedi** | Native Python lib | **DONE** |
| Java/Kotlin | **scip-java** | Gradle/Maven plugin | Deprioritized |
| TypeScript | **TS Compiler API** | Node.js subprocess | Not worth doing |
| Go | **go/callgraph** | Go stdlib | Future |
| Rust | **rust-analyzer** | LSP subprocess | Future |
