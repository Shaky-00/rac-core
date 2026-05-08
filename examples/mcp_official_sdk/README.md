# Official MCP Python SDK + RAC v0.6 (real `call_tool` boundary)

This example shows how **RAC** is wired to the **official MCP Python SDK** over **stdio**: every pending tool call is turned into a **v0.6** authorization event, checked with **`RACPreCommitChecker`**, and only if the decision is **ALLOW** does the client execute **`ClientSession.call_tool`**. The MCP server is a small, deterministic stub; the important property is a **real MCP SDK transport and call boundary**, not the business logic inside tools.

---

## 1. Demo goal

This demo is meant to show that **RAC can be placed in front of a real MCP SDK `call_tool` boundary** and **stop unauthorized tool invocation before the server handler runs**. When RAC returns **BLOCK**, the guarded client **does not** call the MCP server for that step; optional server-side logging can confirm that no `call_tool` entry was recorded for the blocked tool.

This is **not** an end-to-end agent or LLM benchmark. It is a **minimal feasibility / enforcement-boundary** demo for pre-commit style checks at the tool-invocation layer.

---

## 2. Components

| Component | Role |
|-----------|------|
| **`mcp_demo_server.py`** | Minimal MCP **server** (stdio) exposing `read_file`, `search_documents`, `summarize_text`, `create_email_draft`. Returns deterministic JSON payloads. Optionally logs each **actual** server-side tool invocation when **`MCP_OFFICIAL_SDK_SERVER_CALL_LOG`** is set (see §6). |
| **`guarded_mcp_client.py`** | **`GuardedMCPClient`**: builds events via the adapter, runs **`checker.check`** **before** `await session.call_tool(...)`. Records **JSONL** audit rows (see §7). Sets **`server_call_issued`** only after a successful pre-check and uses it consistently with MCP issuance (false on BLOCK). |
| **`rac_mcp_adapter.py`** | **`RACMCPAdapter`**: **`ToolManifest`** registry with **`authorization_profile`** (v0.6), **`EventAdapter`**, **`InMemoryCausalLineageStore`**, and **`ActionSemanticsRegistry`** aligned with RAC defaults. |
| **`run_mcp_sdk_case_study.py`** | Runs multiple scripted scenarios against one stdio server session, clears **`traces/mcp_official_sdk_v06_trace.jsonl`** at start of a full run, and writes **`artifacts/tables/`** CSV/MD/TeX/JSON summaries (historical case-study matrix). |
| **`traces/mcp_official_sdk_v06_trace.jsonl`** | Append-only **client-side audit trace**: one JSON object per guarded step (see §7). Reset when you run `run_mcp_sdk_case_study.py` (that script deletes the file before running). |
| **`MCP_OFFICIAL_SDK_SERVER_CALL_LOG`** | Environment variable: path to a **server-side** JSONL file. Each line is recorded **inside** `mcp_demo_server.call_tool` **only when** Python actually enters the handler—so a blocked step produces **no** line for that tool (see §6). |

---

## 3. RAC v0.6 integration points

- **`ToolManifest.authorization_profile`** (`rac_mcp_adapter.py`): each tool declares **`required_actions`** (leaf labels, e.g. `acquire.read_object`, `transform.summarize`, `disclose.send_message`), **`resource_mappings`**, **`effects`**, **`output_anchor_fields`**, **`commit_type`**. Legacy **`operation` / `resource_arg`** remain for compatibility but **event leaf coverage** uses **`required_actions`**.
- **`EventAdapter`** → **`TypedAuthorizationEvent.required_actions`**: populated from the manifest profile when present (validated against **`ActionSemanticsRegistry`**).
- **`GrantProfileExpander`** → **initial `AuthorizationBasis`**: **`demo_initial_basis_from_grant(grant, grant_template_ids=[...])`** (defaults include **`internal_analysis`** and **`search_and_retrieval`**) builds **`allowed_action_labels`** from compiled grant templates—**without** granting external disclosure leaves needed for `create_email_draft` in the benign template mix used here.
- **`RACPreCommitChecker.check(..., initial_basis=...)`**: **`initial_basis`** is passed **only** when lineage reports **`NO_PREDECESSOR`** (first hop in a chain), matching controlled-trace / **`TraceRunner`** semantics.
- **`ActionCoverageChecker`** (inside pre-commit): compares **`event.required_actions`** (and related v0.6 metadata) against the evolving basis; **`disclose.send_message`** on the email step triggers **`ACTION_ESCALATION`** when not covered by the session basis.
- **BLOCK before MCP**: if pre-check is **BLOCK**, the client returns immediately—**no** `await session.call_tool(...)`.

---

## 4. How to run

From the **repository root**:

```bash
python3 examples/mcp_official_sdk/run_mcp_sdk_case_study.py
```

Typical stdout (aggregate over all bundled scenarios):

```json
{"ALLOW": 10, "BLOCK": 3}
```

Tables under **`artifacts/tables/`** are regenerated (e.g. `mcp_sdk_case_study.csv`, `.json`, `.md`).

### Dependency

The **`mcp`** package is listed in the project dependencies. If it is missing:

```bash
pip install 'mcp>=1.0,<2.0'
```

---

## 5. Tests

```bash
python3 -m pytest tests/test_mcp_official_sdk_v06_guarded.py -q
python3 -m pytest tests/ -q --tb=short
```

If **`mcp`** is not installed, the guarded tests are **skipped** at import time (see the skip message in the test module).

---

## 6. Verifying that BLOCK did not hit the MCP server

Two independent signals:

1. **Client guard (`server_call_issued`)**  
   On **BLOCK**, **`GuardedCallResult.server_call_issued`** is **`false`** and the client never awaits **`call_tool`** for that step.

2. **Server-side log (optional, recommended for audits)**  
   Start the server subprocess with:

   ```bash
   export MCP_OFFICIAL_SDK_SERVER_CALL_LOG=/tmp/mcp_official_server_calls.jsonl
   ```

   Each **actual** invocation appends one JSON line: `{"tool": "<name>", "arguments": {...}}`.  
   For the **attack** workflow (**read_file → summarize_text → create_email_draft**), you should see **read_file** and **summarize_text** only; **no** line with **`create_email_draft`** after RAC blocks the third step.

The pytest **`test_attack_email_blocked_no_server_call`** sets this env var to a temp file and asserts exactly **two** server lines and none for **`create_email_draft`**.

---

## 7. Trace JSONL vs server call log (field meaning)

### Client audit: `traces/mcp_official_sdk_v06_trace.jsonl`

Each line is one JSON object. Typical keys:

| Field | Meaning |
|-------|---------|
| **`step_id`** | Scoped step id (e.g. `case_id:step_N`). |
| **`tool_name`** | MCP tool requested for this step. |
| **`pending_arguments`** | Arguments dict passed toward MCP `call_tool` / mapping (pending proposal). |
| **`required_actions`** | Leaf labels from **`authorization_profile`** on the **`ToolManifest`** (`event.required_actions`). |
| **`rac_decision`** | **`ALLOW`** or **`BLOCK`** (from the **`Decision`** recorded for that trace row—pre-check on block paths, final check on allow paths). |
| **`violations`** | List of **`Violation.rule`** strings (e.g. **`ACTION_ESCALATION`**). |
| **`server_call_issued`** | **`true`** only if the client actually proceeded to **`call_tool`** for this step after pre-check. |
| **`output_anchor_id`** | Verified output anchor id when applicable; **`null`/`None`** on BLOCK before call. |
| **`predecessor`** | Snapshot from **`event.metadata["predecessor_resolution"]`** (lineage resolution result). |
| **`input_anchors`** | Serialized **`InputAnchorRef`** list for the step. |
| **`reason`** | Short human-readable reason or primary rule label context. |

Mapping failures may write a shorter row (e.g. **`EVENT_CONSTRUCTION_ERROR`**).

### Server log: `MCP_OFFICIAL_SDK_SERVER_CALL_LOG`

| Field | Meaning |
|-------|---------|
| **`tool`** | Tool name passed to the server handler. |
| **`arguments`** | Arguments dict as seen by the server. |

Only steps that **entered** the server **`call_tool`** handler appear here—blocked steps do not.

---

## 8. Expected outcomes (reference workflows)

### Benign

- **`read_file(file_A)`** → **ALLOW**, **`server_call_issued=true`**
- **`summarize_text(anchor)`** → **ALLOW**, **`server_call_issued=true`**

### Attack (action escalation)

- First two steps as above.
- **`create_email_draft(..., external recipient)`** → **BLOCK**, **`server_call_issued=false`**
- Violation rule typically **`ACTION_ESCALATION`** (required leaf **`disclose.send_message`** not covered by **`initial_basis.allowed_action_labels`** / session basis).
- Server call log: contains **`read_file`** and **`summarize_text`** only—not **`create_email_draft`**.

---

## 9. Limitations

- **Minimal MCP SDK feasibility demo**: one stdio server process, stub tools, deterministic outputs.
- **No live LLM planner** and no production agent loop.
- **Does not** cover every MCP deployment shape (HTTP, multi-tenant servers, etc.).
- **Goal**: validate **pre-commit enforcement at the MCP `call_tool` boundary**, not to score full agent workflows.
- **Future work**: plug an LLM or planner that emits pending calls into the same **`GuardedMCPClient`** API without changing RAC core checker semantics.

---

## 10. Artifacts (case study matrix)

Running **`run_mcp_sdk_case_study.py`** also refreshes:

- `artifacts/tables/mcp_sdk_case_study.{csv,json,md,tex}`
- `artifacts/tables/mcp_sdk_case_study_summary.{csv,json,md,tex}`

These summarize **all** scripted scenarios in that script (not only the two reference workflows above).
