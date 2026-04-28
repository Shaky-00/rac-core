from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    DecisionType,
    InputAnchorRef,
    VerifiedStructuredOutputAnchor,
)
from rac_core.store.basis_store import InMemoryBasisStore
from rac_core.store.lineage_store import InMemoryCausalLineageStore
from rac_core.validation.taxonomy_traces import _evt, _make_grant
from rac_core.validation.trace import ControlledTrace, TraceRunner, TraceStep


def _tool_action(tool_name: str) -> str:
    if tool_name == "read_file":
        return "read"
    if tool_name == "summarize_file":
        return "summarize"
    if tool_name == "create_email_draft":
        return "external_disclosure"
    return "read"


def _resource_ids_for_step(tool_name: str, args: dict[str, object]) -> set[str]:
    if tool_name == "read_file":
        file_id = str(args.get("file_id", "file_A"))
        return {file_id}
    if tool_name == "create_email_draft":
        recipient = str(args.get("recipient", "external@example.com"))
        return {recipient}
    if tool_name == "summarize_file":
        if "malicious_resource_override" in args:
            raw = args["malicious_resource_override"]
            if isinstance(raw, list):
                return {str(x) for x in raw}
            return {str(raw)}
        return {"file_A"}
    return {"file_A"}


def _purpose_for_step(args: dict[str, object]) -> str:
    sp = args.get("selected_purpose")
    if isinstance(sp, str) and sp:
        return sp
    return "internal_summarization"


def main() -> int:
    plan_dir = ROOT / "examples" / "llm_plans" / "stress_test_v2"
    if not plan_dir.is_dir():
        print(f"ERROR: missing plan dir: {plan_dir}")
        return 1

    for plan_path in sorted(plan_dir.glob("*.json")):
        if plan_path.name == "oracle.json":
            continue
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        grant = _make_grant(
            purpose_scope={"internal_summarization", "external_sharing"},
            allowed_ids={"file_A", "external@example.com", "internal@example.com"},
        )
        checker = RACPreCommitChecker(
            lineage_store=InMemoryCausalLineageStore(),
            basis_store=InMemoryBasisStore(),
        )
        runner = TraceRunner(checker)

        steps: list[TraceStep] = []
        prior_anchor: VerifiedStructuredOutputAnchor | None = None
        for idx, raw_step in enumerate(plan_data.get("steps", [])):
            tool_name = str(raw_step.get("tool_name", ""))
            args = raw_step.get("arguments", {})
            if not isinstance(args, dict):
                args = {}
            resource_ids = _resource_ids_for_step(tool_name, args)
            purpose = _purpose_for_step(args)
            event_id = f"evt_{plan_path.stem}_{idx}"
            step_id = f"s{idx}"
            input_anchors = []
            if prior_anchor is not None:
                input_anchors = [
                    InputAnchorRef(
                        anchor_id=prior_anchor.anchor_id,
                        producer_event_id=prior_anchor.producer_event_id,
                        content_hash=prior_anchor.content_hash,
                    )
                ]
            event = _evt(
                event_id=event_id,
                session_id=grant.session_id,
                step_id=step_id,
                step_seq=idx,
                tool_name=tool_name,
                action=_tool_action(tool_name),
                resource_type="file",
                resource_ids=resource_ids,
                purpose=purpose,
                input_anchors=input_anchors,
            )
            output_anchor = VerifiedStructuredOutputAnchor(
                anchor_id=f"out_{plan_path.stem}_{idx}",
                producer_event_id=event_id,
                content_hash=f"hash:{plan_path.stem}:{idx}",
                resource_ids=set(resource_ids),
                verified_by_controller=True,
                session_id=grant.session_id,
            )
            prior_anchor = output_anchor
            steps.append(
                TraceStep(
                    name=step_id,
                    event=event,
                    grant=grant,
                    output_anchor=output_anchor,
                    expected_decision=DecisionType.ALLOW,
                    expected_rule=None,
                )
            )

        trace = ControlledTrace(name=plan_path.stem, steps=steps)
        result = runner.run(trace)
        final = result.step_results[-1] if result.step_results else None
        decision = final.decision.decision.value if final is not None else "NO_STEPS"
        rules = final.observed_rules if final is not None else []
        print(f"{plan_path.stem:40s} decision={decision:5s} rules={rules}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

