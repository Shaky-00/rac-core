"""Derive RQ2 workflow metadata (scenario type, violation families) from TraceBench v1 cases."""

from __future__ import annotations

import json
from typing import Any

from rac_core.validation.rac_tracebench_v1_adapter import VIOLATION_TYPE_TO_RULES

# Canonical drift-family labels for blind-spot reporting (not 1:1 with generator quotas).
VIOLATION_TYPE_TO_FAMILY: dict[str, str] = {
    "ACTION_ESCALATION": "action_escalation",
    "RESOURCE_EXPANSION": "resource_drift",
    "RESOURCE_ORIGIN_UNVERIFIABLE": "resource_drift",
    "PURPOSE_DRIFT": "purpose_drift",
    "DELEGATION_AMPLIFICATION": "delegation_amplification",
    "CONDITION_WEAKENING": "condition_weakening",
    "OUTPUT_ANCHOR_MISMATCH": "output_anchor_violation",
    "LINEAGE_INVALID": "lineage_violation",
    "LINEAGE_FORGERY": "lineage_violation",
    "MULTI_PREDECESSOR_UNSUPPORTED": "multi_predecessor",
}

_RULE_TO_VIOLATION_TYPE: dict[str, str] = {}
for vtype, rules in VIOLATION_TYPE_TO_RULES.items():
    for rule in rules:
        _RULE_TO_VIOLATION_TYPE.setdefault(rule, vtype)


def rules_to_violation_types(rules: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in rules:
        vt = _RULE_TO_VIOLATION_TYPE.get(str(r))
        if vt and vt not in seen:
            seen.add(vt)
            out.append(vt)
    return out


def violation_families_from_types(types: list[str]) -> list[str]:
    fams: list[str] = []
    seen: set[str] = set()
    for t in types:
        fam = VIOLATION_TYPE_TO_FAMILY.get(t)
        if fam and fam not in seen:
            seen.add(fam)
            fams.append(fam)
    return fams


def workflow_id_for_case(case: dict[str, Any], oracle_row: dict[str, Any] | None = None) -> str:
    legacy = case.get("legacy_trace_id")
    if legacy:
        return str(legacy)
    if oracle_row and oracle_row.get("case_id"):
        return str(oracle_row["case_id"])
    return str(case.get("case_id", ""))


def oracle_label_for_case(case: dict[str, Any], oracle_row: dict[str, Any] | None = None) -> str:
    if oracle_row:
        dec = oracle_row.get("expected_decision") or oracle_row.get("expected_workflow_decision")
        if dec:
            return str(dec).upper()
    dec = case.get("expected_workflow_decision") or case.get("expected_decision", "ALLOW")
    return str(dec).upper()


def violation_families_for_case(case: dict[str, Any], oracle_row: dict[str, Any] | None = None) -> list[str]:
    types = list(oracle_row.get("expected_violation_types") or []) if oracle_row else []
    if not types:
        rules = list(case.get("expected_violation_rules") or [])
        types = rules_to_violation_types([str(r) for r in rules])
    return violation_families_from_types([str(t) for t in types])


def primary_family_for_case(
    case: dict[str, Any],
    violation_families: list[str],
) -> str | None:
    raw = str(case.get("family") or "")
    if raw == "benign":
        return None
    if raw and raw != "mixed_drift" and raw in violation_families:
        return raw
    mut = case.get("mutation_metadata") or {}
    pdc = mut.get("primary_dimension_changed")
    if isinstance(pdc, str) and pdc and pdc != "mixed_drift":
        mapped = VIOLATION_TYPE_TO_FAMILY.get(pdc.upper(), pdc)
        if mapped in violation_families:
            return mapped
    return violation_families[0] if violation_families else (raw or None)


def scenario_type_for_case(
    oracle_label: str,
    violation_families: list[str],
    *,
    case_family: str | None = None,
) -> str:
    if oracle_label == "ALLOW":
        return "benign"
    if len(violation_families) >= 2 or (case_family or "") == "mixed_drift":
        return "composite_drift"
    return "single_drift"


def expected_predicates_for_case(case: dict[str, Any]) -> list[str]:
    rules = case.get("expected_violation_rules") or []
    return [str(r) for r in rules if r]


def enrich_case_metadata(case: dict[str, Any], oracle_row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return workflow metadata dict attached to experiment rows."""
    wid = workflow_id_for_case(case, oracle_row)
    oracle_label = oracle_label_for_case(case, oracle_row)
    vfams = violation_families_for_case(case, oracle_row)
    cfam = str(case.get("family") or "")
    stype = scenario_type_for_case(oracle_label, vfams, case_family=cfam)
    pfamily = primary_family_for_case(case, vfams)
    preds = expected_predicates_for_case(case)
    return {
        "workflow_id": wid,
        "oracle_label": oracle_label,
        "scenario_type": stype,
        "violation_families": vfams,
        "primary_family": pfamily or "",
        "expected_predicates": preds,
        "expected_predicates_json": json.dumps(preds, separators=(",", ":")),
        "violation_families_json": json.dumps(vfams, separators=(",", ":")),
    }


def attach_workflow_metadata_to_v06_case(case: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Merge metadata into v0.6-shaped case for downstream consumers."""
    out = dict(case)
    out["workflow_id"] = meta["workflow_id"]
    out["oracle_label"] = meta["oracle_label"]
    out["scenario_type"] = meta["scenario_type"]
    out["violation_families"] = meta["violation_families"]
    out["primary_family"] = meta["primary_family"]
    out["expected_predicates"] = meta["expected_predicates"]
    return out
