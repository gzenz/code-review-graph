# TASK
Test code-review-graph against real projects. Run the evaluation prompts, analyse results, plan improvements, and iterate.

# WORKFLOW
All work happens on `local/all-features`. The loop is:
```bash
# 1. Make changes, run tests
uv run pytest tests/ -x --tb=short -q

# 2. Reinstall the tool from local source
#    IMPORTANT: cache clean is mandatory — without it, uv reuses the old cached wheel.
pkill -f "code-review-graph serve" || true
uv cache clean code-review-graph
uv tool uninstall code-review-graph
uv tool install --reinstall --from . code-review-graph

# 3. Verify new code is installed (check a recently-added constant/function)
uv run python -c "import code_review_graph.parser as p; print(len(p._INSTANCE_METHOD_BLOCKLIST))"

# 4. Delete the old DB before rebuilding (ensures fresh parse with new code)
rm -f /path/to/project/.code-review-graph/graph.db

# 5. Run evaluation against test projects (see below)
# 6. Analyse results, identify gaps, fix, repeat
```

Rules:
- Do NOT push unless the user explicitly asks.
- Iterate locally first. Push only when evaluation results are satisfactory.

# PROJECT 1 -- cova
## PATH
/home/gideon/PycharmProjects/cova

## About
Large TypeScript + Python monorepo (1,522 files). Monorepo structure uses `packages/` and `libraries/`
directories (NOT backend/frontend flat layout). Angular frontend, AWS Lambda backends, CDK infra.

## PROMPT
Rebuild the code-review-graph and analyze its quality. Run these steps in order:

1. Rebuild: `cd /home/gideon/PycharmProjects/cova && code-review-graph build`
2. Core metrics (query .code-review-graph/graph.db via `uv run python` or `sqlite3`):
   - Edge breakdown by kind (CALLS, TESTED_BY, CONTAINS, IMPORTS_FROM, INHERITS)
   - Call resolution rate: CALLS edges where target_qualified contains `::` or starts with `/`
     (resolved) vs bare names (unresolved). Report resolved/total as percentage.
   - Top 20 unresolved bare-name targets (grouped by target_qualified, sorted by count)
   - Decorator metadata: count nodes where extra LIKE '%decorator%'
3. Dead code audit (via Python API: `find_dead_code(store)`):
   - Total count and breakdown by directory (relative path, first 2 segments)
   - Key category counts: packages/frontend, packages/capabilities, packages/backend,
     packages/voice, libraries/*, packages/e2e-tests
   - Top 20 most common dead code names (to spot structural FPs like `constructor`)
4. False positive spot check: For each known-used symbol, check if it exists as a node,
   check resolved CALLS + bare CALLS + TESTED_BY edges, and check if `find_dead_code`
   flags it. Report alive/dead status.
   Symbols: `generateJSONLog`, `environment`, `errorLoggerMiddleware`, `createMockDriveItem`,
   `createMockMcpRequest`, `BasePage.click`, `SimpleEventEmitter.on`, `processWebSocketEvent`,
   `initializeForSession`, `getInvalidClassifications`
5. Ground truth grep audit: Pick 15 random dead functions (exclude `constructor`, single-char
   names, and names < 7 chars). For each, `grep -rw --include='*.ts' --include='*.py'
   --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist -l <name>` in the cova
   root. If grep finds >1 file, it's a false positive. Report FP rate.
6. Architecture & flows: Run `get_architecture_overview` and `get_flows` (limit 15, sort by
   criticality). Check whether warnings are real architectural issues vs noise. Check whether
   top flows are production entry points vs test descriptions.

Produce a summary table comparing metrics against baselines:

| Metric                 | v7 (first run) | v13 (2026-04-07) |
|------------------------|----------------|------------------|
| Total files            | 1,522          | 1,668            |
| Total nodes            | 11,091         | 10,449           |
| Total edges            | 79,877         | 82,885           |
| CALLS                  | 38,301         | 41,689           |
| TESTED_BY              | 21,305         | 21,305           |
| IMPORTS_FROM           | 10,152         | 10,294           |
| CONTAINS               | 9,568          | 8,785            |
| INHERITS               | 54             | 54               |
| Resolution rate        | 44.5%          | 38.4%            |
| Resolved CALLS         | 17,031         | 16,029           |
| Decorator nodes        | 121            | 355              |
| Dead code (total)      | 1,998          | ~480             |
| - packages/frontend    | 1,102          | 181              |
| - packages/capabilities| 314            | 23               |
| - packages/backend     | 106            | 107              |
| - packages/voice       | 42 (est)       | 9                |
| - libraries/*          | ~77            | 55               |
| Top dead name: constructor | 416         | 0                |
| FP spot check          | 7/10           | 0/8 dead         |
| Grep FP rate           | ~100%          | ~73%             |
| Arch warnings (noise)  | 19/19          | 2/2 real         |
| Top flows: test-only   | 14/15          | 0/15             |

Note: resolution rate denominator grew because instance method tracking added ~3,400 new
(mostly unresolved) CALLS edges. Absolute resolved count increased from 17,031 to 16,029
is due to bundle exclusion removing marp-cli nodes. Dead code ~480 is after e2e-test exclusion.

### Fixes applied (v7 → v13)
- **constructor skip**: `new X()` → CALLS to class, skip `constructor` with `parent_name`
- **Angular lifecycle hooks**: added to `_ENTRY_NAME_PATTERNS`
- **Bare-name collision**: filter by import relationship + unique-name optimization
- **Test flows**: `detect_entry_points(include_tests=False)` + test file path regex
- **Arch warnings**: skip TESTED_BY in coupling + test community name filtering
- **Instance method calls**: blocklist-based tracking (~120 common methods filtered)
- **Angular template parsing**: regex extraction of (event), {{interp}}, [binding], @if/@for
- **Constructor DI types**: `constructor(private svc: Type)` → `this.svc.method()` resolves
- **Transitive imports**: 2-hop barrel file resolution for plausible caller check
- **Function references**: `return funcName` and `const x = funcName` tracked
- **Mock/stub exclusion**: regex pattern for mock variables in test files
- **Framework decorator exclusion**: Angular @Component/@Injectable classes not dead
- **Handler entry points**: `handler`, `handle`, `lambda_handler` patterns
- **Bundled JS exclusion**: skip JS files >500KB + cdk.out/** ignore pattern
- **E2e-test exclusion**: `/e2e[-_]?tests?/` directory pattern treated as test files
- **Jedi**: moved to core dependency (helps Python-heavy projects, not cova specifically)

### Remaining structural limits
- **CDK/SAM wiring**: Lambda handlers referenced in IaC config, not code calls
- **Angular template expressions**: complex bindings beyond regex capability
- **Short common names**: ambiguous without type info (response, request, start)

End with a prioritized list of remaining gaps and what specific fix each needs.
