from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession
from rac_core.adapter import EventConstructionError
from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.demo.local_controller import demo_initial_basis_from_grant
from rac_core.models import AuthorizationBasis, Decision, DecisionType, GrantEnvelope, SessionContext, TypedAuthorizationEvent
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.verification import OutputAnchorVerifier, ToolOutputAnchorClaim

from .rac_mcp_adapter import MCPIntent, RACMCPAdapter


OFFICIAL_SDK_DIR = Path(__file__).resolve().parent
DEFAULT_TRACE_JSONL = OFFICIAL_SDK_DIR / "traces" / "mcp_official_sdk_v06_trace.jsonl"


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


def _append_trace_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


class GuardedMCPClient:
    def __init__(
        self,
        *,
        session: ClientSession,
        session_context: SessionContext,
        grant_envelope: GrantEnvelope,
        grant_template_ids: tuple[str, ...] = ("internal_analysis", "search_and_retrieval"),
        trace_jsonl_path: Path | None = None,
        action_semantics_registry: ActionSemanticsRegistry | None = None,
    ) -> None:
        self.session = session
        self.session_context = session_context
        self.grant_envelope = grant_envelope
        self.trace_jsonl_path = trace_jsonl_path if trace_jsonl_path is not None else DEFAULT_TRACE_JSONL
        sem = action_semantics_registry or ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())
        self.lineage_store = InMemoryCausalLineageStore()
        self.basis_store = InMemoryBasisStore()
        self.rac_adapter = RACMCPAdapter(
            session_context=session_context,
            grant_envelope=grant_envelope,
            lineage_store=self.lineage_store,
            action_semantics_registry=sem,
        )
        self.checker = RACPreCommitChecker(
            lineage_store=self.lineage_store,
            basis_store=self.basis_store,
            action_semantics_registry=sem,
        )
        self.anchor_verifier = OutputAnchorVerifier(self.rac_adapter.resource_registry)
        self._initial_basis_obj: AuthorizationBasis | None = demo_initial_basis_from_grant(
            grant_envelope,
            grant_template_ids=list(grant_template_ids),
        )
        self._step_seq = 0
        self.last_anchor_id: str | None = None
        self.last_summary_text: str | None = None
        self.last_search_results: list[str] = []

    def _resolve_initial_basis(self, event: TypedAuthorizationEvent) -> AuthorizationBasis | None:
        if self._initial_basis_obj is None:
            return None
        pred = self.lineage_store.resolve_predecessor(
            event.input_anchors,
            event.advisory_predecessor_hints,
            event.session_id,
        )
        if pred.status == "NO_PREDECESSOR":
            return self._initial_basis_obj
        return None

    def _trace_record(
        self,
        *,
        step_id: str,
        tool_name: str,
        pending_arguments: dict[str, Any],
        event: TypedAuthorizationEvent,
        pre_decision: Decision,
        server_call_issued: bool,
        output_anchor_id: str | None,
        reason: str,
    ) -> None:
        pred = event.metadata.get("predecessor_resolution") if event.metadata else None
        row = {
            "step_id": step_id,
            "tool_name": tool_name,
            "pending_arguments": pending_arguments,
            "required_actions": list(event.required_actions),
            "rac_decision": pre_decision.decision.value,
            "violations": [v.rule for v in pre_decision.violations],
            "server_call_issued": server_call_issued,
            "output_anchor_id": output_anchor_id,
            "predecessor": pred,
            "input_anchors": [a.model_dump() for a in event.input_anchors],
            "reason": reason,
        }
        _append_trace_row(self.trace_jsonl_path, row)

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
            _append_trace_row(
                self.trace_jsonl_path,
                {
                    "step_id": step_id,
                    "tool_name": tool_name,
                    "pending_arguments": dict(arguments),
                    "required_actions": [],
                    "rac_decision": "BLOCK",
                    "violations": ["EVENT_CONSTRUCTION_ERROR"],
                    "server_call_issued": False,
                    "output_anchor_id": None,
                    "predecessor": None,
                    "input_anchors": [],
                    "reason": str(exc),
                },
            )
            return self._result(
                case_id, scenario, tool_name, expected, "BLOCK", server_call_issued, "EVENT_CONSTRUCTION_ERROR", str(exc)
            )

        init_basis = self._resolve_initial_basis(event)
        pre_decision = self.checker.check(
            event,
            self.grant_envelope,
            persist=False,
            initial_basis=init_basis,
        )

        if pre_decision.decision == DecisionType.BLOCK:
            rule = pre_decision.violations[0].rule if pre_decision.violations else "BLOCKED"
            reason = pre_decision.violations[0].reason if pre_decision.violations else "blocked"
            self._trace_record(
                step_id=step_id,
                tool_name=tool_name,
                pending_arguments=dict(arguments),
                event=event,
                pre_decision=pre_decision,
                server_call_issued=False,
                output_anchor_id=None,
                reason=reason,
            )
            return self._result(case_id, scenario, tool_name, expected, "BLOCK", False, rule, reason)

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
            reason = verify.reason or "output anchor verification failed"
            self._trace_record(
                step_id=step_id,
                tool_name=tool_name,
                pending_arguments=dict(arguments),
                event=event,
                pre_decision=pre_decision,
                server_call_issued=server_call_issued,
                output_anchor_id=None,
                reason=reason,
            )
            return self._result(
                case_id,
                scenario,
                tool_name,
                expected,
                "BLOCK",
                server_call_issued,
                verify.rule or "OUTPUT_ANCHOR_INVALID",
                reason,
            )

        final_decision = self.checker.check(
            event,
            self.grant_envelope,
            output_anchor=verify.verified_anchor,
            persist=True,
            initial_basis=init_basis,
        )
        decision = final_decision.decision.value
        if parsed.get("summary"):
            self.last_summary_text = str(parsed.get("summary"))
        if parsed.get("results") and isinstance(parsed.get("results"), list):
            self.last_search_results = [str(x) for x in parsed["results"]]
        self.last_anchor_id = verify.verified_anchor.anchor_id
        rule = final_decision.violations[0].rule if final_decision.violations else "ALLOW"
        summary = f"tool_call_ok={server_call_issued}"
        out_id = verify.verified_anchor.anchor_id
        self._trace_record(
            step_id=step_id,
            tool_name=tool_name,
            pending_arguments=dict(arguments),
            event=event,
            pre_decision=final_decision,
            server_call_issued=server_call_issued,
            output_anchor_id=out_id,
            reason=rule,
        )
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
