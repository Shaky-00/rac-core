from __future__ import annotations

from datetime import datetime

from rac_core.adapter import EventAdapter, EventConstructionError
from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    Decision,
    DecisionType,
    GrantEnvelope,
    InputAnchorRef,
    PendingToolCall,
    ResourceMetadata,
    RuntimeTraceContext,
    SessionContext,
    Violation,
)
from rac_core.models.event import TypedEventResourceScope
from rac_core.registry import (
    InMemoryResourceRegistry,
    build_default_manifest_registry,
)
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.verification import OutputAnchorVerifier

from .models import DemoRunResult, DemoStepResult
from .scripted_planner import ScriptedPlanner


class DemoEventAdapter(EventAdapter):
    """EventAdapter with deterministic demo-only resource_scope injection."""

    def _build_resource_scope(
        self,
        pending_tool_call: PendingToolCall,
        runtime_trace_context: RuntimeTraceContext,
        manifest_resource_arg: str,
        manifest_resource_type: str,
    ) -> TypedEventResourceScope:
        malicious = pending_tool_call.arguments.get("malicious_resource_override")
        if manifest_resource_arg == "input_anchor" and malicious not in (None, "", []):
            if not runtime_trace_context.input_anchors:
                raise EventConstructionError(
                    "input_anchor resource_arg requires runtime input_anchors."
                )
            resource_ids = self._coerce_resource_ids(
                malicious, "malicious_resource_override"
            )
            self.resource_registry.validate_resource_ids(resource_ids, expected_type="file")
            return TypedEventResourceScope(type="file", ids=resource_ids)
        return super()._build_resource_scope(
            pending_tool_call=pending_tool_call,
            runtime_trace_context=runtime_trace_context,
            manifest_resource_arg=manifest_resource_arg,
            manifest_resource_type=manifest_resource_type,
        )


class LocalRACController:
    """Minimal deterministic controller: adapter → tools → anchor verify → pre-commit."""

    def __init__(
        self,
        grant_envelope: GrantEnvelope,
        session_context: SessionContext,
        tool_runtime: "LocalToolRuntime",
        planner: ScriptedPlanner | None = None,
    ) -> None:
        self.grant_envelope = grant_envelope
        self.session_context = session_context
        self.tool_runtime = tool_runtime
        self.planner = planner or ScriptedPlanner()

        self.lineage_store = InMemoryCausalLineageStore()
        self.basis_store = InMemoryBasisStore()
        self.resource_registry = _build_demo_resource_registry()
        self.manifest_registry = build_default_manifest_registry()
        self.event_adapter = DemoEventAdapter(
            manifest_registry=self.manifest_registry,
            resource_registry=self.resource_registry,
            lineage_store=self.lineage_store,
        )
        self.output_verifier = OutputAnchorVerifier(self.resource_registry)
        self.checker = RACPreCommitChecker(
            lineage_store=self.lineage_store,
            basis_store=self.basis_store,
        )

    def run_scenario(self, scenario_name: str) -> DemoRunResult:
        calls = self.planner.plan(scenario_name)
        steps: list[DemoStepResult] = []
        last_verified_anchor = None
        last_actual_output: object | None = None
        run_metadata: dict[str, object] = {"scenario_name": scenario_name}

        for idx, call in enumerate(calls):
            step_name = f"step_{idx}"
            event_id = f"evt:{self.session_context.session_id}:{step_name}"
            try:
                trace = self._build_runtime_trace(
                    idx=idx,
                    step_name=step_name,
                    call=call,
                    last_verified_anchor=last_verified_anchor,
                )
                event = self.event_adapter.construct_event(
                    self.session_context,
                    self.grant_envelope,
                    call,
                    trace,
                )
            except (EventConstructionError, ValueError) as exc:
                decision = _block_decision(
                    "EVENT_CONSTRUCTION_ERROR", str(exc) or "event construction failed"
                )
                steps.append(
                    DemoStepResult(
                        step_name=step_name,
                        pending_tool_call=call,
                        event_id=event_id,
                        decision=decision,
                        blocked_reason=str(exc),
                        metadata={"rac_components": ["event_adapter"]},
                    )
                )
                return DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                )

            try:
                tool_result = self._execute_tool(
                    call=call,
                    event_id=event.event_id,
                    last_verified_anchor=last_verified_anchor,
                    last_actual_output=last_actual_output,
                )
            except ValueError as exc:
                decision = _block_decision(
                    "TOOL_RUNTIME_ERROR", str(exc) or "tool runtime error"
                )
                steps.append(
                    DemoStepResult(
                        step_name=step_name,
                        pending_tool_call=call,
                        event_id=event_id,
                        decision=decision,
                        blocked_reason=str(exc),
                        metadata={"rac_components": ["event_adapter", "local_tool_runtime"]},
                    )
                )
                return DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                )

            if tool_result.anchor_claim is None:
                decision = _block_decision(
                    "OUTPUT_ANCHOR_INVALID", "Tool did not return an output anchor claim."
                )
                steps.append(
                    DemoStepResult(
                        step_name=step_name,
                        pending_tool_call=call,
                        event_id=event.event_id,
                        decision=decision,
                        blocked_reason="missing anchor claim",
                        metadata={"rac_components": ["event_adapter", "local_tool_runtime"]},
                    )
                )
                return DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                )

            verify = self.output_verifier.verify_output_anchor(
                tool_result.anchor_claim,
                tool_result.actual_output,
                event,
                tool_result.observed_resource_ids,
            )
            if not verify.valid or verify.verified_anchor is None:
                rule = verify.rule or "OUTPUT_ANCHOR_INVALID"
                reason = verify.reason or "output anchor verification failed"
                decision = _block_decision(rule, reason)
                steps.append(
                    DemoStepResult(
                        step_name=step_name,
                        pending_tool_call=call,
                        event_id=event.event_id,
                        decision=decision,
                        blocked_reason=reason,
                        metadata={
                            "rac_components": [
                                "event_adapter",
                                "local_tool_runtime",
                                "output_anchor_verifier",
                            ],
                            "output_anchor_verification": verify.model_dump(mode="python"),
                        },
                    )
                )
                return DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                )

            decision = self.checker.check(
                event,
                self.grant_envelope,
                output_anchor=verify.verified_anchor,
                persist=True,
            )

            step_metadata: dict[str, object] = {
                "rac_components": [
                    "event_adapter",
                    "local_tool_runtime",
                    "output_anchor_verifier",
                    "rac_precommit_checker",
                ],
                "output_anchor_verified_by_controller": verify.verified_anchor.verified_by_controller,
                "tool_metadata": dict(tool_result.metadata),
            }
            self._attach_demo_attack_metadata(call, step_metadata)

            if decision.decision == DecisionType.BLOCK:
                if call.tool_name == "create_email_draft":
                    step_metadata["blocked_before_external_commit"] = True
                    step_metadata["draft_staged_only"] = True
                steps.append(
                    DemoStepResult(
                        step_name=step_name,
                        pending_tool_call=call,
                        event_id=event.event_id,
                        decision=decision,
                        blocked_reason=decision.violations[0].reason
                        if decision.violations
                        else None,
                        metadata=step_metadata,
                    )
                )
                return DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                )

            last_verified_anchor = verify.verified_anchor
            last_actual_output = tool_result.actual_output
            steps.append(
                DemoStepResult(
                    step_name=step_name,
                    pending_tool_call=call,
                    event_id=event.event_id,
                    decision=decision,
                    verified_anchor=verify.verified_anchor,
                    metadata=step_metadata,
                )
            )

        return DemoRunResult(
            scenario_name=scenario_name,
            steps=steps,
            final_decision=DecisionType.ALLOW,
            blocked_at_step=None,
            metadata=run_metadata,
        )

    def _build_runtime_trace(
        self,
        *,
        idx: int,
        step_name: str,
        call: PendingToolCall,
        last_verified_anchor,
    ) -> RuntimeTraceContext:
        input_anchors: list[InputAnchorRef] = []
        if call.tool_name == "summarize_file":
            raw = call.arguments.get("input_anchor")
            if raw == "out:fake":
                input_anchors = [InputAnchorRef(anchor_id="out:fake")]
            elif raw == "previous" or raw is None:
                if last_verified_anchor is None:
                    raise EventConstructionError(
                        "summarize_file requires a verified predecessor anchor."
                    ) from None
                input_anchors = [
                    InputAnchorRef(
                        anchor_id=last_verified_anchor.anchor_id,
                        producer_event_id=last_verified_anchor.producer_event_id,
                        content_hash=last_verified_anchor.content_hash,
                    )
                ]

        selected: str | None = None
        sp = call.arguments.get("selected_purpose")
        if isinstance(sp, str) and sp:
            selected = sp

        return RuntimeTraceContext(
            session_id=self.session_context.session_id,
            step_id=step_name,
            step_seq=idx,
            input_anchors=input_anchors,
            selected_purpose=selected,
            observed_time=datetime(2026, 4, 26, 12, 0, 0),
            environment=self.grant_envelope.conditions.environment or "trusted_workspace",
            tenant=self.grant_envelope.conditions.tenant
            or self.session_context.tenant
            or "tenant_X",
            runtime_labels=set(self.grant_envelope.conditions.runtime_labels)
            or {"internal"},
        )

    def _attach_demo_attack_metadata(
        self, call: PendingToolCall, step_metadata: dict[str, object]
    ) -> None:
        if call.tool_name != "summarize_file":
            return
        raw = call.arguments.get("malicious_resource_override")
        if raw in (None, "", []):
            return
        ids = self._coerce_demo_resource_ids(raw, "malicious_resource_override")
        step_metadata["malicious_resource_override"] = sorted(ids)
        step_metadata["attack_injection_level"] = "event_and_tool_observed_resource"

    def _coerce_demo_resource_ids(self, value: object, field_name: str) -> set[str]:
        """Structured demo-only coercion (scripted planner); not for free-form trust."""
        if isinstance(value, str):
            if not value:
                raise ValueError(f"Argument `{field_name}` must not be empty.")
            return {value}
        if isinstance(value, list):
            if not value:
                raise ValueError(f"Argument `{field_name}` list must not be empty.")
            if not all(isinstance(item, str) and item for item in value):
                raise ValueError(f"Argument `{field_name}` must be str or list[str].")
            return set(value)
        raise ValueError(f"Argument `{field_name}` must be str or list[str].")

    def _execute_tool(
        self,
        *,
        call: PendingToolCall,
        event_id: str,
        last_verified_anchor,
        last_actual_output: object | None,
    ):
        if call.tool_name == "read_file":
            return self.tool_runtime.read_file(str(call.arguments["file_id"]), event_id)
        if call.tool_name == "summarize_file":
            if last_verified_anchor is None or last_actual_output is None:
                raise ValueError("summarize_file requires a prior verified step output.")
            source_resource_ids = set(last_verified_anchor.resource_ids)
            source_content = last_actual_output
            malicious = call.arguments.get("malicious_resource_override")
            if malicious not in (None, "", []):
                source_resource_ids = self._coerce_demo_resource_ids(
                    malicious, "malicious_resource_override"
                )
                self.resource_registry.validate_resource_ids(
                    source_resource_ids, expected_type="file"
                )
            return self.tool_runtime.summarize_file(
                source_content=source_content,
                source_resource_ids=source_resource_ids,
                event_id=event_id,
            )
        if call.tool_name == "create_email_draft":
            recipient = str(call.arguments["recipient"])
            body = last_actual_output
            return self.tool_runtime.create_email_draft(recipient, body, event_id)
        raise ValueError(f"Unsupported tool_name={call.tool_name}")


def _block_decision(rule: str, reason: str) -> Decision:
    return Decision(
        decision=DecisionType.BLOCK,
        violations=[Violation(rule=rule, reason=reason)],
    )


def _build_demo_resource_registry() -> InMemoryResourceRegistry:
    reg = InMemoryResourceRegistry()
    for rid in ("file_A", "file_B"):
        reg.register(ResourceMetadata(resource_id=rid, resource_type="file"))
    for rid in ("external@example.com", "internal@example.com"):
        reg.register(ResourceMetadata(resource_id=rid, resource_type="external_channel"))
    return reg
