from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from rac_core.adapter import EventConstructionError
from rac_core.checker import RACPreCommitChecker
from rac_core.models import DecisionType, GrantEnvelope, SessionContext
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.verification import OutputAnchorVerifier, ToolOutputAnchorClaim

from .rac_mcp_adapter import MCPIntent, RACMCPAdapter


@dataclass
class GuardedCallResult:
    case_id: str
    scenario: str
    tool_name: str
    expected: str
    rac_decision: str
    server_call_issued: bool
    evidence_or_rule: str
    result_summary: str
    matched: bool


class GuardedMCPClient:
    def __init__(
        self,
        *,
        session: ClientSession,
        session_context: SessionContext,
        grant_envelope: GrantEnvelope,
    ) -> None:
        self.session = session
        self.session_context = session_context
        self.grant_envelope = grant_envelope
        self.lineage_store = InMemoryCausalLineageStore()
        self.basis_store = InMemoryBasisStore()
        self.rac_adapter = RACMCPAdapter(
            session_context=session_context,
            grant_envelope=grant_envelope,
            lineage_store=self.lineage_store,
        )
        self.checker = RACPreCommitChecker(
            lineage_store=self.lineage_store,
            basis_store=self.basis_store,
        )
        self.anchor_verifier = OutputAnchorVerifier(self.rac_adapter.resource_registry)
        self._step_seq = 0
        self.last_anchor_id: str | None = None
        self.last_summary_text: str | None = None
        self.last_search_results: list[str] = []

    async def guarded_tool_call(
        self,
        *,
        case_id: str,
        scenario: str,
        expected: str,
        tool_name: str,
        arguments: dict[str, Any],
        selected_purpose: str | None = None,
        input_anchor: str | None = None,
    ) -> GuardedCallResult:
        step_id = f"{case_id}:step_{self._step_seq}"
        intent = MCPIntent(
            step_id=step_id,
            step_seq=self._step_seq,
            tool_name=tool_name,
            arguments=arguments,
            selected_purpose=selected_purpose,
            input_anchor=input_anchor,
        )
        self._step_seq += 1
        server_call_issued = False

        try:
            pending = self.rac_adapter.build_pending_call(intent)
            trace = self.rac_adapter.build_runtime_trace(intent)
            event = self.rac_adapter.event_adapter.construct_event(
                self.session_context,
                self.grant_envelope,
                pending,
                trace,
            )
        except (EventConstructionError, ValueError) as exc:
            decision = "BLOCK"
            rule = "EVENT_CONSTRUCTION_ERROR"
            return self._result(
                case_id, scenario, tool_name, expected, decision, server_call_issued, rule, str(exc)
            )

        pre_decision = self.checker.check(event, self.grant_envelope, persist=False)
        if pre_decision.decision == DecisionType.BLOCK:
            rule = pre_decision.violations[0].rule if pre_decision.violations else "BLOCKED"
            reason = pre_decision.violations[0].reason if pre_decision.violations else "blocked"
            return self._result(
                case_id, scenario, tool_name, expected, "BLOCK", False, rule, reason
            )

        server_call_issued = True
        raw_result = await self.session.call_tool(tool_name, arguments=arguments)
        parsed = _parse_tool_payload(raw_result)
        observed_resource_ids = _observed_resource_ids(tool_name, arguments, parsed)
        actual_output: dict[str, Any] = {"tool": tool_name, "payload": parsed}
        claim = ToolOutputAnchorClaim(
            anchor_id=f"out:{event.event_id}",
            producer_event_id=event.event_id,
            content_hash=self.anchor_verifier.compute_content_hash(actual_output),
            resource_ids=observed_resource_ids,
            output_type=tool_name,
        )
        verify = self.anchor_verifier.verify_output_anchor(
            claim, actual_output, event, observed_resource_ids
        )
        if not verify.valid or verify.verified_anchor is None:
            return self._result(
                case_id,
                scenario,
                tool_name,
                expected,
                "BLOCK",
                server_call_issued,
                verify.rule or "OUTPUT_ANCHOR_INVALID",
                verify.reason or "output anchor verification failed",
            )

        final_decision = self.checker.check(
            event,
            self.grant_envelope,
            output_anchor=verify.verified_anchor,
            persist=True,
        )
        decision = final_decision.decision.value
        if parsed.get("summary"):
            self.last_summary_text = str(parsed.get("summary"))
        if parsed.get("results") and isinstance(parsed.get("results"), list):
            self.last_search_results = [str(x) for x in parsed["results"]]
        self.last_anchor_id = verify.verified_anchor.anchor_id
        rule = final_decision.violations[0].rule if final_decision.violations else "ALLOW"
        summary = f"tool_call_ok={server_call_issued}"
        return self._result(
            case_id, scenario, tool_name, expected, decision, server_call_issued, rule, summary
        )

    def _result(
        self,
        case_id: str,
        scenario: str,
        tool_name: str,
        expected: str,
        decision: str,
        server_call_issued: bool,
        evidence_or_rule: str,
        result_summary: str,
    ) -> GuardedCallResult:
        return GuardedCallResult(
            case_id=case_id,
            scenario=scenario,
            tool_name=tool_name,
            expected=expected,
            rac_decision=decision,
            server_call_issued=server_call_issued,
            evidence_or_rule=evidence_or_rule,
            result_summary=result_summary,
            matched=(expected == decision),
        )


def _parse_tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(result, "content", [])
    if content:
        first = content[0]
        text = getattr(first, "text", "")
        if isinstance(text, str):
            try:
                loaded = ast.literal_eval(text)
                if isinstance(loaded, dict):
                    return loaded
            except (ValueError, SyntaxError):
                return {"text": text}
    return {}


def _observed_resource_ids(
    tool_name: str, arguments: dict[str, Any], payload: dict[str, Any]
) -> set[str]:
    if tool_name == "read_file":
        return {str(arguments["file_id"])}
    if tool_name == "search_documents":
        raw = payload.get("results", [])
        if isinstance(raw, list):
            return {str(x) for x in raw}
        return set()
    if tool_name == "summarize_text":
        return {str(x) for x in payload.get("source_resource_ids", [])}
    if tool_name == "create_email_draft":
        return {str(arguments["recipient"])}
    return set()
