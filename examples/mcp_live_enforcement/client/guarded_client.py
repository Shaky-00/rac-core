from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mcp import ClientSession
from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.demo.local_controller import _demo_initial_basis_from_grant
from rac_core.models import (
    AuthorizationBasis,
    DecisionType,
    DelegationConstraint,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
    SessionContext,
    VerifiedStructuredOutputAnchor,
)
from rac_core.registry import InMemoryResourceRegistry
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore

from .authorization_event_mapper import AuthorizationEventMapper


@dataclass
class RuntimeState:
    session_context: SessionContext
    grant_envelope: GrantEnvelope
    checker: RACPreCommitChecker
    lineage_store: InMemoryCausalLineageStore
    basis_store: InMemoryBasisStore
    step_seq: int
    selected_purpose: str
    anchors: dict[str, dict[str, Any]]
    initial_basis: AuthorizationBasis


class GuardedMCPClient:
    def __init__(self, mapper: AuthorizationEventMapper, resource_registry: InMemoryResourceRegistry) -> None:
        self.mapper = mapper
        self.resource_registry = resource_registry

    def build_runtime_state(self, *, scenario_id: str, grant_id: str, grants: dict[str, dict[str, Any]]) -> RuntimeState:
        grant_raw = grants[grant_id]
        session_id = f"mcp-live:{scenario_id}"
        grant = GrantEnvelope(
            grant_id=grant_raw["grant_id"],
            session_id=session_id,
            subject=GrantSubject(
                user_id=grant_raw["subject"]["user_id"],
                tenant=grant_raw["subject"].get("tenant"),
                roles=set(grant_raw["subject"].get("roles", [])),
            ),
            allowed_actions=set(grant_raw.get("allowed_actions", [])),
            allowed_tools=set(grant_raw.get("allowed_tools", [])),
            resource_scope=ResourceScope(
                type=grant_raw["resource_scope"]["type"],
                allowed_ids=set(grant_raw["resource_scope"].get("allowed_ids", [])),
            ),
            purpose_scope=set(grant_raw.get("purpose_scope", [])),
            delegation=DelegationConstraint(allow_delegation=False),
            conditions=GrantConditions(
                environment=grant_raw.get("conditions", {}).get("environment"),
                tenant=grant_raw.get("conditions", {}).get("tenant"),
                runtime_labels=set(grant_raw.get("conditions", {}).get("runtime_labels", [])),
            ),
        )
        session = SessionContext(
            session_id=session_id,
            user_id=grant.subject.user_id,
            tenant=grant.subject.tenant,
            roles=set(grant.subject.roles),
        )
        lineage = InMemoryCausalLineageStore()
        basis = InMemoryBasisStore()
        semantics = ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())
        checker = RACPreCommitChecker(
            lineage_store=lineage,
            basis_store=basis,
            action_semantics_registry=semantics,
        )
        return RuntimeState(
            session_context=session,
            grant_envelope=grant,
            checker=checker,
            lineage_store=lineage,
            basis_store=basis,
            step_seq=0,
            selected_purpose="internal_analysis",
            anchors={},
            initial_basis=_demo_initial_basis_from_grant(grant),
        )

    async def guarded_call_tool(
        self,
        *,
        scenario_id: str,
        scenario_type: str,
        risk_type: str,
        step_id: str,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        expected_should_block: bool,
        expected_label: str,
        rationale: str,
        server_session: ClientSession,
        runtime_state: RuntimeState,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        first_hop = runtime_state.step_seq == 0
        mapping = self.mapper.map_pending_call(
            step_seq=runtime_state.step_seq,
            step_id=step_id,
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            session_context=runtime_state.session_context,
            grant_envelope=runtime_state.grant_envelope,
            session_anchors=runtime_state.anchors,
            selected_purpose=runtime_state.selected_purpose,
        )
        runtime_state.step_seq += 1

        if not mapping.ok or mapping.event is None:
            return {
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "risk_type": risk_type,
                "step_id": step_id,
                "mcp_server": server_name,
                "mcp_method": "tools/call",
                "tool_name": tool_name,
                "arguments": arguments,
                "rac_decision": "BLOCK",
                "issued_to_server": False,
                "triggered_rules": ["MAPPING_FAIL_CLOSED"],
                "mapping_warnings": mapping.mapping_warnings,
                "expected_label": expected_label,
                "expected_should_block": expected_should_block,
                "matched_expectation": expected_should_block,
                "timestamp": now,
                "rationale": rationale,
            }

        pre = runtime_state.checker.check(
            mapping.event,
            runtime_state.grant_envelope,
            persist=False,
            initial_basis=runtime_state.initial_basis if first_hop else None,
        )
        if pre.decision == DecisionType.BLOCK:
            return {
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "risk_type": risk_type,
                "step_id": step_id,
                "mcp_server": server_name,
                "mcp_method": "tools/call",
                "tool_name": tool_name,
                "arguments": arguments,
                "rac_decision": "BLOCK",
                "issued_to_server": False,
                "triggered_rules": [v.rule for v in pre.violations],
                "mapping_warnings": mapping.mapping_warnings,
                "expected_label": expected_label,
                "expected_should_block": expected_should_block,
                "matched_expectation": expected_should_block,
                "timestamp": now,
                "rationale": rationale,
            }

        raw_result = await server_session.call_tool(tool_name, arguments=arguments)
        payload = _parse_payload(raw_result)

        output_anchor = None
        manifest = mapping.event.metadata.get("manifest_tool", {}) if mapping.event.metadata else {}
        if bool(manifest.get("produces_anchor")):
            anchor_id = str(payload.get("artifact_id") or f"artifact:{scenario_id}:{step_id}")
            content_hash = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            resource_ids = set(payload.get("resources", [])) or set(mapping.event.resource_scope.ids)
            output_anchor = VerifiedStructuredOutputAnchor(
                anchor_id=anchor_id,
                producer_event_id=mapping.event.event_id,
                content_hash=content_hash,
                resource_ids=resource_ids,
                output_type=str(payload.get("output_type") or manifest.get("output_anchor_type") or tool_name),
                verified_by_controller=True,
                session_id=runtime_state.session_context.session_id,
            )

        final = runtime_state.checker.check(
            mapping.event,
            runtime_state.grant_envelope,
            output_anchor=output_anchor,
            persist=True,
            initial_basis=runtime_state.initial_basis if first_hop else None,
        )
        if output_anchor is not None and final.decision == DecisionType.ALLOW:
            runtime_state.anchors[output_anchor.anchor_id] = {
                "resource_ids": sorted(output_anchor.resource_ids),
                "output_type": output_anchor.output_type,
                "producer_event_id": output_anchor.producer_event_id,
            }

        rac_decision = "ALLOW" if final.decision == DecisionType.ALLOW else "BLOCK"
        return {
            "scenario_id": scenario_id,
            "scenario_type": scenario_type,
            "risk_type": risk_type,
            "step_id": step_id,
            "mcp_server": server_name,
            "mcp_method": "tools/call",
            "tool_name": tool_name,
            "arguments": arguments,
            "rac_decision": rac_decision,
            "issued_to_server": True,
            "triggered_rules": [v.rule for v in final.violations],
            "mapping_warnings": mapping.mapping_warnings,
            "expected_label": expected_label,
            "expected_should_block": expected_should_block,
            "matched_expectation": (expected_should_block and rac_decision == "BLOCK") or ((not expected_should_block) and rac_decision == "ALLOW"),
            "timestamp": now,
            "rationale": rationale,
            "result_payload": payload,
        }


def _parse_payload(raw_result: Any) -> dict[str, Any]:
    content = getattr(raw_result, "content", [])
    if not content:
        return {}
    text = getattr(content[0], "text", "")
    if not isinstance(text, str):
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}
    return parsed if isinstance(parsed, dict) else {}
