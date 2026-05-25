# RQ3 — MCP filesystem case study (Table IV)

**Expected files:** `expected/direct_demo_summary.json`, `expected/planner_corpus_summary.json`

- **Type:** Reference summaries for the **direct filesystem demo** and **planner corpus** case study reported in Table IV.
- **Default check (rac-core only):** `bash scripts/run_mcp_case_study.sh` — **expected-summary verification**; does **not** start a live MCP filesystem server.
- **Optional live replay:** `bash scripts/run_mcp_case_study.sh --live` or `examples/mcp_real_filesystem_v06/run_real_filesystem_case.py` — requires Node/npx and `@modelcontextprotocol/server-filesystem`; environment-dependent.

**In-repo fixtures:** `examples/mcp_real_filesystem_v06/plans/` (14 deterministic planner JSON workflows).

**Outputs:** `results/mcp_case_study_verification.json` (gitignored) from the default verification script.
