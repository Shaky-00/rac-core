"""Adapt RAC-TraceBench v1 JSON cases to v0.6 loader shape (no RAC semantics changes)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

VIOLATION_TYPE_TO_RULES: dict[str, list[str]] = {
    "ACTION_ESCALATION": ["ActionCoverage"],
    "RESOURCE_EXPANSION": ["ResourceContainment"],
    "RESOURCE_ORIGIN_UNVERIFIABLE": ["ResourceOrigin"],
    "PURPOSE_DRIFT": ["PurposePreservation"],
    "DELEGATION_AMPLIFICATION": ["DelegationNonAmplification"],
    "CONDITION_WEAKENING": ["ConditionPreservation"],
    "OUTPUT_ANCHOR_MISMATCH": ["OutputAnchorIntegrity"],
    "LINEAGE_INVALID": ["LineageValidity"],
    "LINEAGE_FORGERY": ["LineageValidity"],
    "MULTI_PREDECESSOR_UNSUPPORTED": ["MultiPredecessorUnsupported"],
}

FAMILY_MIXED = "mixed_drift"


def is_v1_bundle_root(root: Path) -> bool:
    return (root / "controlled_traces" / "core").is_dir()


def _rules_to_violation_types(rules: list[str]) -> list[str]:
    out: list[str] = []
    for vt, preds in VIOLATION_TYPE_TO_RULES.items():
        if any(p in rules for p in preds):
            out.append(vt)
    return out


def v1_to_v06_adapter(case: dict[str, Any]) -> dict[str, Any]:
    gp = case.get("grant_profile") or {}
    legacy_tid = case.get("legacy_trace_id") or case.get("case_id", "")
    trace_id = str(legacy_tid)
    steps06: list[dict[str, Any]] = []
    for st in case.get("steps") or []:
        if not isinstance(st, dict):
            continue
        sid = str(st.get("step_id", ""))
        tool = str(st.get("tool") or st.get("tool_name", ""))
        labels = st.get("action_labels") or st.get("action_label") or []
        if isinstance(labels, str):
            labels = [labels]
        resource_ids = st.get("resource_ids") or []
        oas = st.get("output_anchors") or []
        oa = oas[0] if oas else st.get("output_anchor")
        vrules = st.get("expected_violation_rules") or []
        vtypes = _rules_to_violation_types([str(x) for x in vrules])
        step06: dict[str, Any] = {
            "step_id": sid,
            "tool_name": tool,
            "required_actions": list(labels),
            "resource_scope": {"resource_ids": list(resource_ids)},
            "purpose": st.get("purpose", "internal_analysis"),
            "conditions": dict(st.get("runtime_conditions") or st.get("conditions") or {}),
            "input_anchors": copy.deepcopy(st.get("input_anchors") or []),
            "output_anchor": copy.deepcopy(oa) if oa else None,
            "predecessor": st.get("predecessor_hint"),
            "expected_step_decision": st.get("expected_step_decision", "ALLOW"),
            "expected_step_violation_types": vtypes,
            "mutation_from_benign": st.get("mutation_from_benign"),
            "rationale": st.get("rationale") or "",
        }
        if isinstance(st.get("delegation"), dict):
            step06["delegation"] = copy.deepcopy(st["delegation"])
        steps06.append(step06)
    pair_role = case.get("pair_role") or (
        "benign" if case.get("expected_workflow_decision") == "ALLOW" else "violation"
    )
    return {
        "trace_id": trace_id,
        "trace_name": case.get("case_name", ""),
        "trace_family": case.get("subfamily") or case.get("family", ""),
        "pair_id": case.get("pair_id") or f"PAIR-{case.get('case_id', 'UNK')}",
        "pair_role": pair_role,
        "expected_decision": case.get("expected_workflow_decision", "ALLOW"),
        "expected_violation_types": _rules_to_violation_types(case.get("expected_violation_rules") or []),
        "grant_templates": list(gp.get("grant_template_ids") or []),
        "initial_resource_scope": copy.deepcopy(gp.get("initial_resource_scope") or {}),
        "initial_purpose_scope": copy.deepcopy(gp.get("initial_purpose_scope") or {}),
        "initial_conditions": copy.deepcopy(gp.get("initial_conditions") or {}),
        "tools_used": list(case.get("tools_used") or []),
        "steps": steps06,
        "oracle_basis": case.get("oracle_basis", ""),
        "notes": case.get("oracle_notes", ""),
        "_source_path": str(case.get("_source_path", "")),
        "_v1": {
            "case_id": case.get("case_id"),
            "suite": case.get("suite"),
            "family": case.get("family"),
            "expected_block_step": case.get("expected_block_step"),
        },
    }


def rq2_composite_overlay_dir() -> Path:
    """Optional composite-overlay traces (rac-data or legacy rac-core data path)."""
    from rac_core.evaluation.data_paths import composite_overlay_traces_dir

    return composite_overlay_traces_dir()


def load_v1_cases_from_dirs(
    root: Path,
    *,
    suite: str = "all",
    include_mixed: bool = True,
    include_rq2_overlay: bool = False,
) -> list[dict[str, Any]]:
    """Load v1 JSON cases and return v0.6-shaped dicts for the existing loader."""
    import json

    from rac_core.validation.tracebench_workflow_metadata import (
        attach_workflow_metadata_to_v06_case,
        enrich_case_metadata,
    )

    suites: list[tuple[str, Path]] = []
    core_dir = root / "controlled_traces" / "core"
    exp_dir = root / "controlled_traces" / "expanded"
    s = (suite or "all").strip().lower()
    if s in ("all", "core") and core_dir.is_dir():
        suites.append(("core", core_dir))
    if s in ("all", "expanded") and exp_dir.is_dir():
        suites.append(("expanded", exp_dir))
    if include_rq2_overlay and s in ("all", "expanded"):
        overlay = rq2_composite_overlay_dir()
        if overlay.is_dir():
            suites.append(("rq2_composite_overlay", overlay))

    out: list[dict[str, Any]] = []
    for _, d in suites:
        for p in sorted(d.glob("*.json")):
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not include_mixed and raw.get("family") == FAMILY_MIXED:
                continue
            raw["_source_path"] = str(p.resolve())
            meta = enrich_case_metadata(raw)
            adapted = attach_workflow_metadata_to_v06_case(v1_to_v06_adapter(raw), meta)
            out.append(adapted)
    return out


def load_v1_oracle_doc(
    root: Path,
    *,
    suite: str = "all",
    include_rq2_overlay: bool = False,
) -> dict[str, Any]:
    import json

    labels: list[dict[str, Any]] = []
    s = (suite or "all").strip().lower()
    if s in ("all", "core"):
        p = root / "oracle_labels" / "core_oracle_labels.json"
        if p.is_file():
            labels.extend(json.loads(p.read_text(encoding="utf-8")).get("labels") or [])
    if s in ("all", "expanded"):
        p = root / "oracle_labels" / "expanded_oracle_labels.json"
        if p.is_file():
            labels.extend(json.loads(p.read_text(encoding="utf-8")).get("labels") or [])
    if include_rq2_overlay and s in ("all", "expanded"):
        op = rq2_composite_overlay_dir().parent / "oracle_labels" / "rq2_composite_overlay_oracle_labels.json"
        if op.is_file():
            labels.extend(json.loads(op.read_text(encoding="utf-8")).get("labels") or [])
    return {"labels": labels, "version": "1.0.0"}


def oracle_rows_by_trace_id(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index oracle rows by replay trace_id (legacy_trace_id or case_id)."""
    out: dict[str, dict[str, Any]] = {}
    for row in doc.get("labels") or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("case_id", ""))
        legacy = row.get("legacy_trace_id")
        tid = str(legacy) if legacy else cid
        # Normalize expected_decision for experiment compatibility
        adapted = dict(row)
        adapted["trace_id"] = tid
        adapted["expected_decision"] = row.get("expected_decision") or row.get(
            "expected_workflow_decision", "ALLOW"
        )
        adapted["expected_violation_types"] = row.get("expected_violation_types") or []
        out[tid] = adapted
        if cid:
            out[cid] = adapted
    return out
