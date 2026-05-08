"""AuthorizationBasis issuance from CompiledGrantProfile (v0.6 bridge)."""

from __future__ import annotations

from rac_core.action_semantics import (
    ActionSemanticsRegistry,
    GrantProfileExpander,
    default_grant_templates_yaml_path,
    default_semantics_yaml_path,
)
from rac_core.models import (
    AuthorizationBasis,
    BasisResourceScope,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
)


def _expander() -> GrantProfileExpander:
    reg = ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())
    return GrantProfileExpander.load_from_yaml(default_grant_templates_yaml_path(), reg)


def _minimal_profile():
    from rac_core.action_semantics.grant_template import CompiledGrantProfile

    return CompiledGrantProfile(
        source_templates=["t_a", "t_b"],
        allowed_action_labels=["meta.describe_tool", "acquire.read_object"],
        purpose_scope=["internal_analysis"],
        conditions={"state_mutation": False, "external_disclosure": False},
        delegation={"allow_delegation": False},
    )


def test_from_compiled_grant_profile_builds_basis() -> None:
    profile = _minimal_profile()
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="basis_issued",
        subjects={"user_1"},
        resource_scope=BasisResourceScope(type="file", ids={"file_A"}),
    )
    assert basis.basis_id == "basis_issued"
    assert basis.subjects == {"user_1"}


def test_allowed_action_labels_written() -> None:
    profile = _minimal_profile()
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b1",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
    )
    assert basis.allowed_action_labels == ["meta.describe_tool", "acquire.read_object"]


def test_purpose_scope_written() -> None:
    profile = _minimal_profile()
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b1",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
    )
    assert basis.purpose_scope == {"internal_analysis"}


def test_compiled_grant_conditions_and_delegation_written() -> None:
    profile = _minimal_profile()
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b1",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
    )
    assert basis.compiled_grant_conditions == {
        "state_mutation": False,
        "external_disclosure": False,
    }
    assert basis.compiled_grant_delegation == {"allow_delegation": False}


def test_source_templates_written() -> None:
    profile = _minimal_profile()
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b1",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
    )
    assert basis.source_templates == ["t_a", "t_b"]


def test_effective_allowed_prefers_labels() -> None:
    profile = _minimal_profile()
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b1",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
        legacy_actions={"read", "summarize"},
    )
    eff = basis.effective_allowed_action_labels()
    assert eff == ["meta.describe_tool", "acquire.read_object"]
    assert eff != sorted(basis.actions)


def test_effective_allowed_fallback_when_labels_empty() -> None:
    basis = AuthorizationBasis(
        basis_id="b1",
        subjects={"u"},
        actions={"read", "summarize"},
        allowed_action_labels=[],
        resource_scope=BasisResourceScope(type="file", ids=set()),
        purpose_scope=set(),
    )
    assert basis.effective_allowed_action_labels() == ["read", "summarize"]


def test_coarse_basis_actions_preserved_when_present() -> None:
    profile = _minimal_profile()
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b1",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
        legacy_actions={"read", "summarize"},
    )
    assert basis.actions == {"read", "summarize"}


def test_internal_analysis_profile_includes_summarize() -> None:
    ex = _expander()
    profile = ex.expand_templates(["internal_analysis"])
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b_ia",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids={"f"}),
        legacy_actions={"read", "summarize"},
    )
    assert "transform.summarize" in basis.allowed_action_labels
    assert "transform.summarize" in basis.effective_allowed_action_labels()


def test_read_only_retrieval_excludes_summarize() -> None:
    ex = _expander()
    profile = ex.expand_templates(["read_only_retrieval"])
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b_ro",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
        legacy_actions={"read"},
    )
    assert "transform.summarize" not in basis.allowed_action_labels


def test_multi_template_order_preserved_on_basis() -> None:
    ex = _expander()
    profile = ex.expand_templates(["tool_inspection", "read_only_retrieval"])
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b_m",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
    )
    assert basis.source_templates == ["tool_inspection", "read_only_retrieval"]
    assert basis.allowed_action_labels == [
        "meta.describe_tool",
        "meta.inspect_status",
        "meta.list_capabilities",
        "acquire.read_metadata",
        "acquire.read_object",
        "acquire.query_collection",
    ]


def test_basis_store_roundtrip_preserves_labels() -> None:
    from rac_core.store import InMemoryBasisStore

    ex = _expander()
    profile = ex.expand_templates(["internal_analysis"])
    basis = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="b_store",
        subjects={"u"},
        resource_scope=BasisResourceScope(type="file", ids={"f"}),
        legacy_actions={"read", "summarize"},
    )
    store = InMemoryBasisStore()
    store.save_basis("sess_x", "step_1", basis)
    loaded = store.load_finalized_basis("sess_x", "step_1")
    assert loaded is not None
    assert "transform.summarize" in loaded.effective_allowed_action_labels()
    assert loaded.source_templates == ["internal_analysis"]


def test_from_grant_envelope_leaves_v06_fields_empty() -> None:
    grant = GrantEnvelope(
        grant_id="g1",
        session_id="s1",
        subject=GrantSubject(user_id="u1", effective_subject="subj"),
        allowed_actions={"read"},
        allowed_tools={"read_file"},
        resource_scope=ResourceScope(type="file", allowed_ids={"f"}),
        purpose_scope={"internal_summarization"},
        conditions=GrantConditions(),
    )
    basis = AuthorizationBasis.from_grant_envelope(grant, basis_id="init")
    assert basis.allowed_action_labels == []
    assert basis.source_templates == []
    assert basis.compiled_grant_conditions == {}
    assert basis.compiled_grant_delegation == {}
