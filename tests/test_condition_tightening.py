from datetime import datetime

import pytest

from rac_core.checker import ConditionTightener
from rac_core.models import BasisConditions, TimeWindow, TypedEventConditions


def test_event_time_within_basis_time_window_passes() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(time=datetime(2026, 4, 26, 12, 0, 0)),
        BasisConditions(
            time_window=TimeWindow(
                start=datetime(2026, 4, 26, 0, 0, 0),
                end=datetime(2026, 4, 26, 23, 59, 59),
            )
        ),
    )
    assert result.valid


def test_event_time_outside_basis_time_window_fails() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(time=datetime(2026, 4, 27, 0, 0, 0)),
        BasisConditions(
            time_window=TimeWindow(
                start=datetime(2026, 4, 26, 0, 0, 0),
                end=datetime(2026, 4, 26, 23, 59, 59),
            )
        ),
    )
    assert not result.valid
    assert result.rule == "CONDITION_WEAKENING"


def test_event_time_missing_while_basis_has_time_window_fails() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(time=None),
        BasisConditions(
            time_window=TimeWindow(
                start=datetime(2026, 4, 26, 0, 0, 0),
                end=datetime(2026, 4, 26, 23, 59, 59),
            )
        ),
    )
    assert not result.valid
    assert result.rule == "CONDITION_WEAKENING"


def test_environment_exact_match_passes() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(environment="trusted_workspace"),
        BasisConditions(environment="trusted_workspace"),
    )
    assert result.valid


def test_environment_mismatch_fails() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(environment="external_workspace"),
        BasisConditions(environment="trusted_workspace"),
    )
    assert not result.valid
    assert result.rule == "CONDITION_WEAKENING"


def test_tenant_exact_match_passes() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(tenant="tenant_X"),
        BasisConditions(tenant="tenant_X"),
    )
    assert result.valid


def test_tenant_mismatch_fails() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(tenant="tenant_Y"),
        BasisConditions(tenant="tenant_X"),
    )
    assert not result.valid
    assert result.rule == "CONDITION_WEAKENING"


def test_runtime_labels_subset_passes() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(runtime_labels={"internal"}),
        BasisConditions(runtime_labels={"internal", "confidential"}),
    )
    assert result.valid


def test_runtime_labels_expansion_fails() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(runtime_labels={"internal", "external"}),
        BasisConditions(runtime_labels={"internal"}),
    )
    assert not result.valid
    assert result.rule == "CONDITION_WEAKENING"


def test_runtime_labels_missing_while_basis_has_labels_fails() -> None:
    tightener = ConditionTightener()
    result = tightener.check_event_conditions(
        TypedEventConditions(runtime_labels=set()),
        BasisConditions(runtime_labels={"internal"}),
    )
    assert not result.valid
    assert result.rule == "CONDITION_WEAKENING"


def test_tighten_conditions_raises_when_not_valid() -> None:
    tightener = ConditionTightener()
    with pytest.raises(ValueError):
        tightener.tighten_conditions(
            TypedEventConditions(environment="external"),
            BasisConditions(environment="trusted"),
        )
