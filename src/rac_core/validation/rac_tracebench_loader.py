"""Load RAC-TraceBench v0.6 JSON fixtures into :class:`~rac_core.validation.trace.ControlledTrace` objects."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import yaml

from rac_core.models import (
    DecisionType,
    DelegationConstraint,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    InputAnchorRef,
    ResourceScope,
    TypedAuthorizationEvent,
    TypedEventConditions,
    TypedEventDelegation,
    TypedEventResourceScope,
    TypedEventSubject,
    VerifiedStructuredOutputAnchor,
)
from rac_core.validation.trace import ControlledTrace, TraceStep, initial_basis_from_grant_templates

_T0 = datetime(2026, 4, 26, 12, 0, 0)

_MANIFEST_ACTION_DEFAULTS_CACHE: dict[str, dict[str, list[str]]] = {}


def _tracebench_manifest_action_defaults(root: Path) -> dict[str, list[str]]:
    """Load ``manifests/sample_tool_manifests_v06.yaml`` default_required_actions per tool name."""
    key = str(root.resolve())
    if key in _MANIFEST_ACTION_DEFAULTS_CACHE:
        return _MANIFEST_ACTION_DEFAULTS_CACHE[key]
    path = root / "manifests" / "sample_tool_manifests_v06.yaml"
    out: dict[str, list[str]] = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tools = (data or {}).get("tools") or {}
        for tname, body in tools.items():
            if not isinstance(body, dict):
                continue
            prof = body.get("authorization_profile") or {}
            actions = prof.get("default_required_actions") or prof.get("required_actions")
            if isinstance(actions, list) and actions:
                out[str(tname)] = [str(x) for x in actions]
    _MANIFEST_ACTION_DEFAULTS_CACHE[key] = out
    return out


def rac_tracebench_root_candidates() -> list[Path]:
    from rac_core.evaluation.data_paths import tracebench_root_candidates as _candidates

    return _candidates()


def resolve_rac_tracebench_root() -> Path | None:
    for p in rac_tracebench_root_candidates():
        if (p / "controlled_traces" / "core").is_dir():
            return p
        if (p / "controlled_traces" / "paired").is_dir():
            return p
    return None


def is_v1_tracebench_root(root: Path) -> bool:
    from rac_core.validation.rac_tracebench_v1_adapter import is_v1_bundle_root

    return is_v1_bundle_root(root)


def load_trace_case(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"trace case must be a JSON object: {p}")
    data["_source_path"] = str(p.resolve())
    return data


def load_trace_cases(directory: str | Path) -> list[dict[str, Any]]:
    d = Path(directory)
    cases: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        cases.append(load_trace_case(p))
    return cases


def load_oracle_labels(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "labels" not in data:
        raise ValueError(f"oracle labels must be an object with 'labels': {p}")
    return data


def adapt_tracebench_grant_yaml_root(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize TraceBench ``grants/*.yaml`` into the ``templates:`` shape :class:`GrantProfileExpander` expects."""
    if "templates" in raw and isinstance(raw["templates"], dict):
        return raw
    templates: dict[str, Any] = {}
    for tid, body in raw.items():
        if not isinstance(tid, str) or not tid or tid.startswith("#"):
            continue
        if not isinstance(body, dict):
            continue
        actions = list(body.get("allowed_action_labels") or body.get("actions") or [])
        pc = body.get("purpose_constraints")
        purpose_flat: list[str] = []
        if isinstance(pc, dict):
            apl = pc.get("allowed_purpose_labels") or []
            if isinstance(apl, list):
                purpose_flat = [str(x) for x in apl]
        elif isinstance(pc, list):
            purpose_flat = [str(x) for x in pc]
        conditions = dict(body.get("condition_constraints") or body.get("conditions") or {})
        delegation = dict(body.get("delegation") or {})
        desc = body.get("description")
        if desc is None:
            notes = body.get("notes")
            if isinstance(notes, str):
                desc = notes.strip()[:800] or None
        templates[tid] = {
            "actions": actions,
            "purpose_constraints": purpose_flat,
            "conditions": conditions,
            "delegation": delegation,
            "description": desc,
        }
    return {"templates": templates}


def build_tracebench_grant_templates_root(tracebench_root: str | Path) -> dict[str, Any]:
    """Load ``grants/sample_grant_templates_v06.yaml`` from a TraceBench root and adapt it for the expander."""
    root = Path(tracebench_root).expanduser().resolve()
    path = root / "grants" / "sample_grant_templates_v06.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"TraceBench grant templates not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"grant templates YAML root must be a mapping: {path}")
    return adapt_tracebench_grant_yaml_root(data)


def load_rac_tracebench(
    root_path: str | Path,
    *,
    suite: str = "all",
    include_mixed: bool = True,
    include_rq2_overlay: bool = False,
) -> dict[str, Any]:
    root = Path(root_path).expanduser().resolve()
    if is_v1_tracebench_root(root):
        from rac_core.validation.rac_tracebench_v1_adapter import (
            load_v1_cases_from_dirs,
            load_v1_oracle_doc,
        )

        return {
            "root": root,
            "benchmark_version": "1.0.0",
            "suite": suite,
            "include_mixed": include_mixed,
            "include_rq2_overlay": include_rq2_overlay,
            "traces": load_v1_cases_from_dirs(
                root,
                suite=suite,
                include_mixed=include_mixed,
                include_rq2_overlay=include_rq2_overlay,
            ),
            "oracle_labels": load_v1_oracle_doc(
                root, suite=suite, include_rq2_overlay=include_rq2_overlay
            ),
        }
    traces_dir = root / "controlled_traces" / "paired"
    oracle_path = root / "oracle_labels" / "paired_oracle_labels.json"
    return {
        "root": root,
        "benchmark_version": "0.6",
        "suite": suite,
        "include_mixed": include_mixed,
        "traces": load_trace_cases(traces_dir),
        "oracle_labels": load_oracle_labels(oracle_path),
    }


def _decision(s: str) -> DecisionType:
    return DecisionType.ALLOW if s.upper() == "ALLOW" else DecisionType.BLOCK


def _tool_action(tool_name: str) -> str:
    if tool_name == "read_file":
        return "read"
    if tool_name in ("summarize_file", "merge_summaries", "aggregate_cross_section"):
        return "summarize"
    if tool_name in ("create_email_draft", "post_status_webhook", "publish_release_discussion"):
        return "external_disclosure"
    if tool_name == "spawn_sub_agent":
        return "delegate"
    return tool_name


def _event_environment(step_conditions: dict[str, Any]) -> str:
    wk = step_conditions.get("workspace_kind")
    if isinstance(wk, str) and wk:
        return wk
    if step_conditions.get("trusted_workspace") is False:
        return "external_workspace"
    return "trusted_workspace"


def _runtime_labels(initial_conditions: dict[str, Any]) -> set[str]:
    labels: set[str] = {"internal"}
    if initial_conditions.get("external_disclosure") is True:
        labels.add("external_disclosure")
    return labels


def _runtime_labels_merged(
    initial_conditions: dict[str, Any], step_conditions: dict[str, Any]
) -> set[str]:
    """Grant/session labels plus step-level disclosure flags (e.g. TRC-V06-026 final hop)."""
    labels = _runtime_labels(initial_conditions)
    if step_conditions.get("external_disclosure") is True:
        labels.add("external_disclosure")
    return labels


def _grant_envelope(
    case: dict[str, Any],
    *,
    session_id: str,
    user_id: str,
) -> GrantEnvelope:
    init_rs = case.get("initial_resource_scope") or {}
    init_purpose = case.get("initial_purpose_scope") or {}
    init_cond = case.get("initial_conditions") or {}
    resource_ids = set(init_rs.get("resource_ids") or [])
    purpose_labels = set(init_purpose.get("allowed_purpose_labels") or [])
    primary = init_purpose.get("primary_purpose")
    if isinstance(primary, str) and primary:
        purpose_labels.add(primary)
    env = "trusted_workspace" if init_cond.get("trusted_workspace", True) else "external_workspace"
    return GrantEnvelope(
        grant_id=f"grant:{case.get('trace_id', 'trace')}",
        session_id=session_id,
        subject=GrantSubject(user_id=user_id, effective_subject=user_id),
        allowed_actions={"read", "summarize", "external_disclosure", "delegate"},
        allowed_tools={
            "read_file",
            "summarize_file",
            "create_email_draft",
            "spawn_sub_agent",
            "merge_summaries",
            "aggregate_cross_section",
            "post_status_webhook",
            "publish_release_discussion",
        },
        resource_scope=ResourceScope(type="file", allowed_ids=resource_ids),
        purpose_scope=purpose_labels,
        delegation=DelegationConstraint(
            allow_delegation=bool(init_cond.get("allow_delegation", False)),
            allowed_delegatees=set(),
        ),
        conditions=GrantConditions(
            environment=env,
            tenant="tenant_tracebench",
            runtime_labels=_runtime_labels(init_cond),
        ),
    )


def _output_anchor_for_step(
    step: dict[str, Any],
    *,
    event_id: str,
    session_id: str,
    trace_metadata: dict[str, Any],
) -> VerifiedStructuredOutputAnchor | None:
    raw = step.get("output_anchor")
    if raw is None or raw is False:
        return None
    if not isinstance(raw, dict):
        return None
    anchor_id = raw.get("anchor_id")
    if not isinstance(anchor_id, str) or not anchor_id:
        return None
    content_sha = raw.get("content_sha256")
    content_hash = content_sha if isinstance(content_sha, str) and content_sha else f"sha256:{anchor_id}"
    resource_ids = set(raw.get("resource_ids") or [])
    meta: dict[str, object] = {}
    reserved_core = {"anchor_id", "content_sha256", "resource_ids"}
    for k in ("content_kind", "summary_text_excerpt", "recipient", "sensitivity"):
        v = raw.get(k)
        if v is not None:
            meta[k] = v
    if "observed_access" in raw:
        meta["observed_access"] = raw["observed_access"]
    for k, v in raw.items():
        if k in reserved_core or k in meta:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            meta[k] = v
    meta["rac_tracebench_step_id"] = step.get("step_id", "")
    meta["rac_tracebench_trace_metadata"] = trace_metadata
    return VerifiedStructuredOutputAnchor(
        anchor_id=anchor_id,
        producer_event_id=event_id,
        content_hash=content_hash,
        resource_ids=resource_ids,
        output_type=raw.get("content_kind") if isinstance(raw.get("content_kind"), str) else None,
        verified_by_controller=True,
        session_id=session_id,
        metadata=meta,
    )


def _event_resource_scope(rs: dict[str, Any]) -> TypedEventResourceScope:
    ids = set(rs.get("resource_ids") or [])
    return TypedEventResourceScope(type="file", ids=ids)


def _strip_placeholder_producer_id(pid: Any) -> str | None:
    if not isinstance(pid, str) or not pid:
        return None
    if pid.startswith("evt_") or pid.startswith("TRC-"):
        return pid
    if len(pid) <= 8 and pid.replace("_", "").isalnum() and pid.upper() in {"E1", "E2", "E3"}:
        return None
    return pid


def _step_expected_rule_from_tracebench(step: dict[str, Any]) -> str | None:
    """Map TraceBench ``expected_step_violation_types`` to checker rule names for TraceRunner / ablation."""
    raw = step.get("expected_step_violation_types") or []
    if not isinstance(raw, list) or not raw:
        return None
    types_set = {str(t) for t in raw}
    # Order matters when multiple tags appear (should not happen on fixture steps).
    for key, rule in (
        ("MULTI_PREDECESSOR_UNSUPPORTED", "MULTI_PREDECESSOR_UNSUPPORTED"),
        ("LINEAGE_INVALID", "LINEAGE_INVALID"),
        ("LINEAGE_FORGERY", "LINEAGE_INVALID"),
        ("DELEGATION_AMPLIFICATION", "DELEGATION_AMPLIFICATION"),
        ("OUTPUT_ANCHOR_MISMATCH", "OUTPUT_ANCHOR_MISMATCH"),
        ("ACTION_ESCALATION", "ACTION_ESCALATION"),
        ("RESOURCE_EXPANSION", "RESOURCE_EXPANSION"),
        ("RESOURCE_ORIGIN_UNVERIFIABLE", "RESOURCE_ORIGIN_UNVERIFIABLE"),
        ("PURPOSE_DRIFT", "PURPOSE_DRIFT"),
        ("CONDITION_WEAKENING", "CONDITION_WEAKENING"),
    ):
        if key in types_set:
            return rule
    return None


def _producer_event_id_for_input_anchor(
    *,
    anchor_ref: str,
    predecessor: str | None,
    producer_by_anchor: dict[str, str],
) -> str | None:
    real = producer_by_anchor.get(anchor_ref)
    if predecessor and predecessor.startswith("evt_") and real and predecessor != real:
        return predecessor
    return None


def convert_trace_case_to_controlled_trace(
    case: dict[str, Any],
    *,
    session_id: str | None = None,
    user_id: str = "user_1",
) -> ControlledTrace:
    trace_id = str(case["trace_id"])
    sid = session_id or f"sess:{trace_id}"
    grant = _grant_envelope(case, session_id=sid, user_id=user_id)
    steps_raw = case.get("steps") or []
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError(f"trace {trace_id} has no steps")

    producer_by_anchor: dict[str, str] = {}
    trace_meta = {
        "trace_id": trace_id,
        "trace_name": case.get("trace_name"),
        "pair_id": case.get("pair_id"),
        "pair_role": case.get("pair_role"),
        "initial_resource_scope": case.get("initial_resource_scope"),
        "initial_purpose_scope": case.get("initial_purpose_scope"),
        "initial_conditions": case.get("initial_conditions"),
    }

    tb_root = resolve_rac_tracebench_root()
    manifest_defaults: dict[str, list[str]] = (
        _tracebench_manifest_action_defaults(tb_root) if tb_root is not None else {}
    )

    trace_steps: list[TraceStep] = []
    for seq, st in enumerate(steps_raw):
        if not isinstance(st, dict):
            raise ValueError(f"invalid step record at index {seq}")
        step_id = str(st["step_id"])
        event_id = f"{trace_id}:{step_id}"
        tool_name = str(st["tool_name"])
        step_conditions = st.get("conditions") or {}
        if not isinstance(step_conditions, dict):
            step_conditions = {}
        rs = st.get("resource_scope") or {}
        if not isinstance(rs, dict):
            rs = {}
        purpose_raw = st.get("purpose", "internal_analysis")
        purpose = purpose_raw if isinstance(purpose_raw, str) else str(purpose_raw)

        pred = st.get("predecessor")
        pred_s = str(pred) if pred is not None and not isinstance(pred, bool) else None

        input_json = st.get("input_anchors") or []
        if not isinstance(input_json, list):
            input_json = []

        advisory: list[str] = []
        if pred_s and not pred_s.startswith("evt_"):
            advisory.append(pred_s)

        in_anchors: list[InputAnchorRef] = []
        for spec in input_json:
            if not isinstance(spec, dict):
                continue
            ref = spec.get("anchor_ref") or spec.get("anchor_id")
            if not isinstance(ref, str) or not ref:
                continue
            pin = _strip_placeholder_producer_id(spec.get("producer_event_id"))
            forged = _producer_event_id_for_input_anchor(
                anchor_ref=ref,
                predecessor=pred_s,
                producer_by_anchor=producer_by_anchor,
            )
            if forged is not None:
                pin = forged
            ch = spec.get("content_hash")
            ch_s = ch if isinstance(ch, str) else None
            in_anchors.append(InputAnchorRef(anchor_id=ref, producer_event_id=pin, content_hash=ch_s))

        delegated = tool_name == "spawn_sub_agent"
        delegatee = None
        del_obj = st.get("delegation")
        if isinstance(del_obj, dict):
            if del_obj.get("delegated") is True:
                delegated = True
            de = del_obj.get("delegatee")
            if isinstance(de, str) and de:
                delegatee = de
        if isinstance(rs.get("delegatee"), str) and rs["delegatee"]:
            delegatee = rs["delegatee"]

        req = st.get("required_actions") or []
        req_list = [str(x) for x in req] if isinstance(req, list) else []
        if not req_list:
            req_list = list(manifest_defaults.get(tool_name, []))

        mut_b = st.get("mutation_from_benign")
        lineage_binding_fixture = (
            isinstance(mut_b, dict)
            and str(mut_b.get("dimension_changed", "")) == "lineage_producer_binding"
        )

        ev_meta: dict[str, object] = {
            "rac_tracebench": {
                "rationale": st.get("rationale"),
                "mutation_from_benign": st.get("mutation_from_benign"),
                "input_anchor_extras": [
                    {k: v for k, v in a.items() if k not in ("anchor_ref", "anchor_id", "producer_event_id", "content_hash")}
                    for a in input_json
                    if isinstance(a, dict)
                ],
            }
        }
        if lineage_binding_fixture:
            tb_dict = ev_meta["rac_tracebench"]
            if isinstance(tb_dict, dict):
                tb_dict["require_producer_event_id_on_inputs"] = True

        event = TypedAuthorizationEvent(
            event_id=event_id,
            session_id=sid,
            step_id=step_id,
            step_seq=seq,
            subject=TypedEventSubject(user_id=user_id, effective_subject=user_id),
            tool_name=tool_name,
            action=_tool_action(tool_name),
            required_actions=req_list,
            resource_scope=_event_resource_scope(rs),
            purpose=purpose,
            conditions=TypedEventConditions(
                time=_T0,
                environment=_event_environment(step_conditions),
                tenant="tenant_tracebench",
                runtime_labels=_runtime_labels_merged(
                    case.get("initial_conditions") or {}, step_conditions
                ),
            ),
            delegation=TypedEventDelegation(
                delegated=delegated,
                delegatee=delegatee,
                delegator=user_id if delegated else None,
                delegation_depth=1 if delegated else 0,
            ),
            input_anchors=in_anchors,
            advisory_predecessor_hints=advisory,
            metadata=ev_meta,
        )

        oa = _output_anchor_for_step(st, event_id=event_id, session_id=sid, trace_metadata=trace_meta)
        if oa is not None:
            producer_by_anchor[oa.anchor_id] = event_id

        exp_step = st.get("expected_step_decision", "ALLOW")
        step_expected_rule = _step_expected_rule_from_tracebench(st)

        trace_steps.append(
            TraceStep(
                name=step_id,
                event=event,
                grant=grant,
                output_anchor=oa,
                expected_decision=_decision(str(exp_step)),
                expected_rule=step_expected_rule,
            )
        )

    grant_tpl = case.get("grant_templates") or []
    tpl_list = [str(x) for x in grant_tpl] if isinstance(grant_tpl, list) else []

    init_basis = None
    grant_templates_path = ""
    if tpl_list:
        if tb_root is None:
            raise FileNotFoundError(
                "Cannot build TraceBench initial_basis: set RAC_TRACEBENCH_ROOT or install grant templates "
                "under RAC_DATA_DIR (default ../rac-data/tracebench/paired or tracebench/...)."
            )
        gpath = tb_root / "grants" / "sample_grant_templates_v06.yaml"
        grant_templates_path = str(gpath.resolve())
        init_basis = initial_basis_from_grant_templates(
            grant,
            tpl_list,
            grant_templates_root=build_tracebench_grant_templates_root(tb_root),
        )

    return ControlledTrace(
        name=trace_id,
        description=str(case.get("trace_name")) if case.get("trace_name") else None,
        steps=trace_steps,
        grant_templates=tpl_list,
        initial_basis=init_basis,
        expected_final_decision=_decision(str(case.get("expected_decision", "ALLOW"))),
        metadata={
            "rac_tracebench": {
                "trace_family": case.get("trace_family"),
                "tools_used": case.get("tools_used"),
                "oracle_basis": case.get("oracle_basis"),
                "notes": case.get("notes"),
                "expected_violation_types": case.get("expected_violation_types"),
                "source_path": case.get("_source_path"),
                "grant_templates_path": grant_templates_path,
            }
        },
    )


def iter_oracle_labels(doc: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for row in doc.get("labels") or []:
        if isinstance(row, dict):
            yield row


def oracle_label_by_trace_id(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r["trace_id"]): r for r in iter_oracle_labels(doc) if r.get("trace_id")}
