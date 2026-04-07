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

| Metric                 | v7 (first run) | Current |
|------------------------|----------------|---------|
| Total files            | 1,522          | ?       |
| Total nodes            | 11,091         | ?       |
| Total edges            | 79,877         | ?       |
| CALLS                  | 38,301         | ?       |
| TESTED_BY              | 21,305         | ?       |
| IMPORTS_FROM           | 10,152         | ?       |
| CONTAINS               | 9,568          | ?       |
| INHERITS               | 54             | ?       |
| Resolution rate        | 44.5%          | ?       |
| Resolved CALLS         | 17,031         | ?       |
| Decorator nodes        | 121            | ?       |
| Dead code (total)      | 1,998          | ?       |
| - packages/frontend    | 1,102          | ?       |
| - packages/capabilities| 314            | ?       |
| - packages/backend     | 106            | ?       |
| - packages/voice       | 42 (est)       | ?       |
| - libraries/*          | ~77            | ?       |
| Top dead name: constructor | 416         | ?       |
| FP spot check          | 7/10           | ?       |
| Grep FP rate           | ~100%          | ?       |
| Arch warnings (noise)  | 19/19          | ?       |
| Top flows: test-only   | 14/15          | ?       |

### Known Issues (from v7 first run)
- **constructor (416 FPs)**: JS/TS constructors flagged dead because `new X()` creates CALLS
  to the class, not to `constructor`. Fixed: skip `constructor` with `parent_name`.
- **Angular lifecycle hooks (~92 FPs)**: `ngOnInit`, `ngOnChanges`, `transform`, `canActivate`,
  `writeValue` etc. are framework-invoked. Fixed: added to `_ENTRY_NAME_PATTERNS`.
- **Bare-name collision**: 24 nodes named `handler`, 214 bare CALLS edges — every `handler`
  was saved from dead code by unrelated callers. Fixed: filter by import relationship.
- **Test flows dominate**: `it:should...` test descriptions are top-criticality flows.
  Fixed: `detect_entry_points(include_tests=False)` by default.
- **Architecture warnings all noise**: 19/19 warnings were test↔code TESTED_BY coupling.
  Fixed: skip TESTED_BY in coupling count.
- **Instance method calls not tracked**: `obj.method()` where obj is not `this`/`self`/`cls`
  or ClassName is not tracked by the parser. Causes `cleanup`, `addChunk` FPs. NOT YET FIXED
  (deeper parser issue).

End with a prioritized list of remaining gaps and what specific fix each needs.
