from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rac_core.models import (
    DecisionType,
    DelegationConstraint,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
    SessionContext,
)
from rac_core.validation import to_csv, to_latex_tabular, to_markdown_table

from examples.mcp_official_sdk.guarded_mcp_client import GuardedCallResult, GuardedMCPClient


class MCPCaseStudyRow(BaseModel):
    Scenario: str
    MCP_workflow: str
    Expected: str
    RAC_decision: str
    Server_call_issued: str
    Evidence: str


class MCPCaseStudySummaryRow(BaseModel):
    Scenario: str
    MCP_workflow: str
    Outcome: str
    Blocked_step: str
    Server_call_issued: str
    Evidence: str


def _make_grant(session_id: str, include_external: bool = False) -> GrantEnvelope:
    actions = {"read", "summarize"}
    tools = {"read_file", "search_documents", "summarize_text", "create_email_draft"}
    resources = {"file_A", "file_B", "file_C"}
    if include_external:
        resources.add("external@example.com")
    return GrantEnvelope(
        grant_id=f"grant:{session_id}",
        session_id=session_id,
        subject=GrantSubject(user_id="analyst_1", tenant="acme", roles={"analyst"}),
        allowed_actions=actions,
        allowed_tools=tools,
        resource_scope=ResourceScope(type="file", allowed_ids=resources),
        purpose_scope={"internal_analysis", "external_sharing"},
        delegation=DelegationConstraint(allow_delegation=False),
        conditions=GrantConditions(environment="trusted_workspace", tenant="acme"),
    )


def _make_session(session_id: str) -> SessionContext:
    return SessionContext(
        session_id=session_id,
        user_id="analyst_1",
        effective_subject="analyst_1",
        tenant="acme",
        roles={"analyst"},
    )


def _to_row(result: GuardedCallResult, workflow: str) -> MCPCaseStudyRow:
    return MCPCaseStudyRow(
        Scenario=result.scenario,
        MCP_workflow=workflow,
        Expected=result.expected,
        RAC_decision=result.rac_decision,
        Server_call_issued="Yes" if result.server_call_issued else "No",
        Evidence=result.evidence_or_rule,
    )


def _build_summary_rows(all_results: list[GuardedCallResult]) -> list[MCPCaseStudySummaryRow]:
    workflow_by_case = {
        "mcp_benign_read_summarize": "read_file(file_A) -> summarize_text(anchor_A)",
        "mcp_search_read_summarize": "search_documents('Q2') -> read_file(file_A) -> summarize_text(anchor_A)",
        "mcp_action_escalation": "read_file(file_A) -> summarize_text(anchor_A) -> create_email_draft(summary_anchor, external)",
        "mcp_resource_expansion": "read_file(file_A) -> read_file(file_B)",
        "mcp_forged_anchor_or_predecessor": "summarize_text(fake_anchor)",
        "mcp_purpose_drift": "read_file(file_A) -> summarize_text(anchor_A, purpose=external_sharing)",
    }
    by_case: dict[str, list[GuardedCallResult]] = {}
    for result in all_results:
        by_case.setdefault(result.case_id, []).append(result)

    ordered_cases = [
        "mcp_benign_read_summarize",
        "mcp_search_read_summarize",
        "mcp_action_escalation",
        "mcp_resource_expansion",
        "mcp_forged_anchor_or_predecessor",
        "mcp_purpose_drift",
    ]
    rows: list[MCPCaseStudySummaryRow] = []
    for case_id in ordered_cases:
        case_steps = by_case.get(case_id, [])
        blocked = next((x for x in case_steps if x.rac_decision == "BLOCK"), None)
        if blocked is None:
            rows.append(
                MCPCaseStudySummaryRow(
                    Scenario=case_id,
                    MCP_workflow=workflow_by_case[case_id],
                    Outcome="ALLOW",
                    Blocked_step="--",
                    Server_call_issued="Yes",
                    Evidence="ALLOW" if case_id == "mcp_benign_read_summarize" else "anchor-derived continuation",
                )
            )
            continue
        rows.append(
            MCPCaseStudySummaryRow(
                Scenario=case_id,
                MCP_workflow=workflow_by_case[case_id],
                Outcome="BLOCK",
                Blocked_step=blocked.tool_name,
                Server_call_issued="Yes" if blocked.server_call_issued else "No",
                Evidence=blocked.evidence_or_rule,
            )
        )
    return rows


async def run_case_study() -> dict[str, object]:
    server_path = ROOT / "examples" / "mcp_official_sdk" / "mcp_demo_server.py"
    trace_jsonl = ROOT / "examples" / "mcp_official_sdk" / "traces" / "mcp_official_sdk_v06_trace.jsonl"
    trace_jsonl.parent.mkdir(parents=True, exist_ok=True)
    trace_jsonl.unlink(missing_ok=True)

    params = StdioServerParameters(command=sys.executable, args=[str(server_path)])
    all_results: list[GuardedCallResult] = []
    rows: list[MCPCaseStudyRow] = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) benign read -> summarize
            c1 = GuardedMCPClient(
                session=session,
                session_context=_make_session("mcp_case_1"),
                grant_envelope=_make_grant("mcp_case_1"),
                trace_jsonl_path=trace_jsonl,
            )
            r = await c1.guarded_tool_call(
                case_id="mcp_benign_read_summarize",
                scenario="mcp_benign_read_summarize/read",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"file_id": "file_A"},
                selected_purpose="internal_analysis",
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file(file_A)"))
            r = await c1.guarded_tool_call(
                case_id="mcp_benign_read_summarize",
                scenario="mcp_benign_read_summarize/summarize",
                expected="ALLOW",
                tool_name="summarize_text",
                arguments={"input_anchor": c1.last_anchor_id},
                selected_purpose="internal_analysis",
                input_anchor=c1.last_anchor_id,
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file(file_A) -> summarize_text(anchor_A)"))

            # 2) search -> read -> summarize
            c2 = GuardedMCPClient(
                session=session,
                session_context=_make_session("mcp_case_2"),
                grant_envelope=_make_grant("mcp_case_2"),
                trace_jsonl_path=trace_jsonl,
            )
            r = await c2.guarded_tool_call(
                case_id="mcp_search_read_summarize",
                scenario="mcp_search_read_summarize/search",
                expected="ALLOW",
                tool_name="search_documents",
                arguments={"query": "Q2"},
                selected_purpose="internal_analysis",
            )
            all_results.append(r)
            rows.append(_to_row(r, "search_documents('Q2')"))
            picked = c2.last_search_results[0] if c2.last_search_results else "file_A"
            r = await c2.guarded_tool_call(
                case_id="mcp_search_read_summarize",
                scenario="mcp_search_read_summarize/read",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"file_id": picked},
                selected_purpose="internal_analysis",
            )
            all_results.append(r)
            rows.append(_to_row(r, f"search_documents('Q2') -> read_file({picked})"))
            r = await c2.guarded_tool_call(
                case_id="mcp_search_read_summarize",
                scenario="mcp_search_read_summarize/summarize",
                expected="ALLOW",
                tool_name="summarize_text",
                arguments={"input_anchor": c2.last_anchor_id},
                selected_purpose="internal_analysis",
                input_anchor=c2.last_anchor_id,
            )
            all_results.append(r)
            rows.append(_to_row(r, "search -> read -> summarize_text(anchor_from_read)"))

            # 3) action escalation
            c3 = GuardedMCPClient(
                session=session,
                session_context=_make_session("mcp_case_3"),
                grant_envelope=_make_grant("mcp_case_3", include_external=True),
                trace_jsonl_path=trace_jsonl,
            )
            r = await c3.guarded_tool_call(
                case_id="mcp_action_escalation",
                scenario="mcp_action_escalation/read",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"file_id": "file_A"},
                selected_purpose="internal_analysis",
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file(file_A)"))
            r = await c3.guarded_tool_call(
                case_id="mcp_action_escalation",
                scenario="mcp_action_escalation/summarize",
                expected="ALLOW",
                tool_name="summarize_text",
                arguments={"input_anchor": c3.last_anchor_id},
                selected_purpose="internal_analysis",
                input_anchor=c3.last_anchor_id,
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file(file_A) -> summarize_text(anchor_A)"))
            r = await c3.guarded_tool_call(
                case_id="mcp_action_escalation",
                scenario="mcp_action_escalation/email",
                expected="BLOCK",
                tool_name="create_email_draft",
                arguments={"summary": c3.last_summary_text or "s", "recipient": "external@example.com"},
                selected_purpose="internal_analysis",
                input_anchor=c3.last_anchor_id,
            )
            all_results.append(r)
            rows.append(
                _to_row(
                    r,
                    "read_file(file_A) -> summarize_text(anchor_A) -> create_email_draft(summary_anchor, external)",
                )
            )

            # 4) resource expansion
            c4 = GuardedMCPClient(
                session=session,
                session_context=_make_session("mcp_case_4"),
                grant_envelope=_make_grant("mcp_case_4"),
                trace_jsonl_path=trace_jsonl,
            )
            r = await c4.guarded_tool_call(
                case_id="mcp_resource_expansion",
                scenario="mcp_resource_expansion/read_A",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"file_id": "file_A"},
                selected_purpose="internal_analysis",
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file(file_A)"))
            r = await c4.guarded_tool_call(
                case_id="mcp_resource_expansion",
                scenario="mcp_resource_expansion/read_B",
                expected="BLOCK",
                tool_name="read_file",
                arguments={"file_id": "file_B"},
                selected_purpose="internal_analysis",
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file(file_A) -> read_file(file_B)"))

            # 5) forged anchor
            c5 = GuardedMCPClient(
                session=session,
                session_context=_make_session("mcp_case_5"),
                grant_envelope=_make_grant("mcp_case_5"),
                trace_jsonl_path=trace_jsonl,
            )
            r = await c5.guarded_tool_call(
                case_id="mcp_forged_anchor_or_predecessor",
                scenario="mcp_forged_anchor_or_predecessor/forged",
                expected="BLOCK",
                tool_name="summarize_text",
                arguments={"input_anchor": "out:fake_anchor"},
                selected_purpose="internal_analysis",
                input_anchor="out:fake_anchor",
            )
            all_results.append(r)
            rows.append(_to_row(r, "summarize_text(fake_anchor)"))

            # 6) purpose drift
            c6 = GuardedMCPClient(
                session=session,
                session_context=_make_session("mcp_case_6"),
                grant_envelope=_make_grant("mcp_case_6"),
                trace_jsonl_path=trace_jsonl,
            )
            r = await c6.guarded_tool_call(
                case_id="mcp_purpose_drift",
                scenario="mcp_purpose_drift/read",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"file_id": "file_A"},
                selected_purpose="internal_analysis",
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file(file_A)"))
            r = await c6.guarded_tool_call(
                case_id="mcp_purpose_drift",
                scenario="mcp_purpose_drift/drift",
                expected="BLOCK",
                tool_name="summarize_text",
                arguments={"input_anchor": c6.last_anchor_id},
                selected_purpose="external_sharing",
                input_anchor=c6.last_anchor_id,
            )
            all_results.append(r)
            rows.append(_to_row(r, "read_file -> summarize_text(anchor, purpose=external_sharing)"))

    table_dir = ROOT / "artifacts" / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    (table_dir / "mcp_sdk_case_study.csv").write_text(to_csv(rows), encoding="utf-8")
    (table_dir / "mcp_sdk_case_study.md").write_text(to_markdown_table(rows), encoding="utf-8")
    (table_dir / "mcp_sdk_case_study.tex").write_text(
        to_latex_tabular(rows, caption="MCP SDK RAC pre-call case study"),
        encoding="utf-8",
    )
    payload = [r.__dict__ for r in all_results]
    (table_dir / "mcp_sdk_case_study.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary_rows = _build_summary_rows(all_results)
    (table_dir / "mcp_sdk_case_study_summary.csv").write_text(
        to_csv(summary_rows), encoding="utf-8"
    )
    (table_dir / "mcp_sdk_case_study_summary.md").write_text(
        to_markdown_table(summary_rows), encoding="utf-8"
    )
    (table_dir / "mcp_sdk_case_study_summary.tex").write_text(
        to_latex_tabular(summary_rows, caption="MCP SDK RAC pre-call case study summary"),
        encoding="utf-8",
    )
    (table_dir / "mcp_sdk_case_study_summary.json").write_text(
        json.dumps([r.model_dump() for r in summary_rows], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "results": payload,
        "summary": [r.model_dump() for r in summary_rows],
        "decision_counts": {
            "ALLOW": sum(1 for r in all_results if r.rac_decision == DecisionType.ALLOW.value),
            "BLOCK": sum(1 for r in all_results if r.rac_decision == DecisionType.BLOCK.value),
        },
    }


def main() -> None:
    outcome = asyncio.run(run_case_study())
    print(json.dumps(outcome["decision_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
