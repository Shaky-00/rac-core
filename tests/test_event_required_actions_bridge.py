"""Runtime bridge: TypedAuthorizationEvent.required_actions and AuthorizationBasis.allowed_action_labels."""

from __future__ import annotations

from datetime import datetime

import pytest

from rac_core.action_semantics import ActionSemanticsRegistry, default_semantics_yaml_path
from rac_core.adapter import (
    EventAdapter,
    EventConstructionError,
    load_tool_manifests_from_yaml,
    sample_tool_manifests_yaml_path,
)
from rac_core.models import (
    AuthorizationBasis,
    AuthorizationProfile,
    BasisResourceScope,
    EffectProfile,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    PendingToolCall,
    ResourceMapping,
    ResourceMetadata,
    ResourceScope,
    RuntimeTraceContext,
    SessionContext,
    ToolManifest,
    TypedAuthorizationEvent,
    TypedEventResourceScope,
    TypedEventSubject,
)
from rac_core.registry import InMemoryResourceRegistry, InMemoryToolManifestRegistry
from rac_core.store import InMemoryCausalLineageStore


def _semantics() -> ActionSemanticsRegistry:
    return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())


def _session() -> SessionContext:
    return SessionContext(
        session_id="sess_1",
        user_id="user_1",
        agent_id="agent_main",
        tenant="tenant_X",
        roles={"analyst"},
        effective_subject="subject_1",
    )


def _grant() -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_1",
        session_id="sess_1",
        subject=GrantSubject(user_id="user_1", effective_subject="subject_1"),
        allowed_actions={"read", "summarize"},
        allowed_tools={"read_file", "dual_action_tool"},
        resource_scope=ResourceScope(type="file", allowed_ids={"file_A"}),
        purpose_scope={"internal_summarization"},
        conditions=GrantConditions(environment="trusted_workspace", tenant="tenant_X"),
    )


def _resources() -> InMemoryResourceRegistry:
    r = InMemoryResourceRegistry()
    r.register(ResourceMetadata(resource_id="file_A", resource_type="file"))
    return r


def _trace() -> RuntimeTraceContext:
    return RuntimeTraceContext(
        session_id="sess_1",
        step_id="step_1",
        step_seq=1,
        input_anchors=[],
        selected_purpose="internal_summarization",
        observed_time=datetime(2026, 4, 26, 10, 0, 0),
        environment="trusted_workspace",
        tenant="tenant_X",
        runtime_labels={"internal"},
    )


def _profile_dual_actions() -> AuthorizationProfile:
    return AuthorizationProfile(
        required_actions=["acquire.read_object", "meta.describe_tool"],
        resource_mappings=[
            ResourceMapping(
                arg="file_id",
                resource_role="target",
                resource_type="file",
                resource_pattern="file:*",
            )
        ],
        effects=EffectProfile(
            state_mutation=False,
            external_disclosure=False,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=False,
            produces_anchor=True,
            effect_boundary="internal",
        ),
        output_anchor_fields=["output_id"],
        commit_type="read",
    )


def test_manifest_without_authorization_profile_unchanged() -> None:
    manifests = InMemoryToolManifestRegistry()
    manifests.register(
        ToolManifest(
            tool_name="read_file",
            operation="read",
            resource_arg="file_id",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
        )
    )
    adapter = EventAdapter(
        manifest_registry=manifests,
        resource_registry=_resources(),
        lineage_store=InMemoryCausalLineageStore(),
        action_semantics_registry=_semantics(),
    )
    event = adapter.construct_event(
        session_context=_session(),
        grant_envelope=_grant(),
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(),
    )
    assert event.action == "read"
    assert event.required_actions == []
    assert event.metadata.get("manifest_authorization_profile") is None


def test_v06_manifest_populates_required_actions() -> None:
    sample = load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path())["read_file"]
    manifests = InMemoryToolManifestRegistry()
    manifests.register(sample)
    adapter = EventAdapter(
        manifest_registry=manifests,
        resource_registry=_resources(),
        lineage_store=InMemoryCausalLineageStore(),
        action_semantics_registry=_semantics(),
    )
    event = adapter.construct_event(
        session_context=_session(),
        grant_envelope=_grant(),
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(),
    )
    assert event.required_actions == ["acquire.read_object"]
    assert event.action == "read"
    assert event.metadata.get("manifest_authorization_profile") is True


def test_v06_multi_required_actions_order_preserved() -> None:
    manifests = InMemoryToolManifestRegistry()
    manifests.register(
        ToolManifest(
            tool_name="dual_action_tool",
            operation="read",
            resource_arg="file_id",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id"],
            authorization_effect="read_only",
            commit_type="read",
            authorization_profile=_profile_dual_actions(),
        )
    )
    adapter = EventAdapter(
        manifest_registry=manifests,
        resource_registry=_resources(),
        lineage_store=InMemoryCausalLineageStore(),
        action_semantics_registry=_semantics(),
    )
    event = adapter.construct_event(
        session_context=_session(),
        grant_envelope=_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="dual_action_tool", arguments={"file_id": "file_A"}
        ),
        runtime_trace_context=_trace(),
    )
    assert event.required_actions == ["acquire.read_object", "meta.describe_tool"]
    assert event.action == "read"


def test_invalid_leaf_in_profile_rejected_at_construct() -> None:
    bad = AuthorizationProfile(
        required_actions=["not.registered.leaf"],
        resource_mappings=[
            ResourceMapping(arg="file_id", resource_role="target", resource_type="file")
        ],
        effects=EffectProfile(
            state_mutation=False,
            external_disclosure=False,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=False,
            produces_anchor=True,
            effect_boundary="internal",
        ),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    manifests = InMemoryToolManifestRegistry()
    manifests.register(
        ToolManifest(
            tool_name="bad_tool",
            operation="read",
            resource_arg="file_id",
            resource_type="file",
            authorization_profile=bad,
        )
    )
    adapter = EventAdapter(
        manifest_registry=manifests,
        resource_registry=_resources(),
        lineage_store=InMemoryCausalLineageStore(),
        action_semantics_registry=_semantics(),
    )
    with pytest.raises(EventConstructionError, match="Unknown or non-leaf"):
        adapter.construct_event(
            session_context=_session(),
            grant_envelope=_grant(),
            pending_tool_call=PendingToolCall(tool_name="bad_tool", arguments={"file_id": "file_A"}),
            runtime_trace_context=_trace(),
        )


def test_category_in_profile_rejected_at_construct() -> None:
    bad = AuthorizationProfile(
        required_actions=["meta"],
        resource_mappings=[
            ResourceMapping(arg="file_id", resource_role="target", resource_type="file")
        ],
        effects=EffectProfile(
            state_mutation=False,
            external_disclosure=False,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=False,
            produces_anchor=True,
            effect_boundary="internal",
        ),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    manifests = InMemoryToolManifestRegistry()
    manifests.register(
        ToolManifest(
            tool_name="bad_cat",
            operation="read",
            resource_arg="file_id",
            resource_type="file",
            authorization_profile=bad,
        )
    )
    adapter = EventAdapter(
        manifest_registry=manifests,
        resource_registry=_resources(),
        lineage_store=InMemoryCausalLineageStore(),
        action_semantics_registry=_semantics(),
    )
    with pytest.raises(EventConstructionError, match="Category label"):
        adapter.construct_event(
            session_context=_session(),
            grant_envelope=_grant(),
            pending_tool_call=PendingToolCall(tool_name="bad_cat", arguments={"file_id": "file_A"}),
            runtime_trace_context=_trace(),
        )


def test_authorization_basis_stores_allowed_action_labels() -> None:
    b = AuthorizationBasis(
        basis_id="b1",
        subjects={"u"},
        actions={"read"},
        allowed_action_labels=["acquire.read_object", "meta.describe_tool"],
        resource_scope=BasisResourceScope(type="file", ids={"file_A"}),
        purpose_scope={"p"},
    )
    assert b.allowed_action_labels == ["acquire.read_object", "meta.describe_tool"]


def test_authorization_basis_effective_allowed_fallback() -> None:
    b = AuthorizationBasis(
        basis_id="b1",
        subjects={"u"},
        actions={"summarize", "read"},
        resource_scope=BasisResourceScope(type="file", ids=set()),
        purpose_scope=set(),
    )
    assert b.effective_allowed_action_labels() == ["read", "summarize"]


def test_typed_event_effective_required_fallback() -> None:
    e = TypedAuthorizationEvent(
        event_id="e1",
        session_id="s",
        step_id="st",
        step_seq=0,
        subject=TypedEventSubject(user_id="u"),
        tool_name="t",
        action="read",
        resource_scope=TypedEventResourceScope(type="file", ids=set()),
        purpose="p",
    )
    assert e.required_actions == []
    assert e.effective_required_actions() == ["read"]


def test_grant_basis_effective_allowed() -> None:
    grant = _grant()
    basis = AuthorizationBasis.from_grant_envelope(grant, basis_id="x")
    assert basis.allowed_action_labels == []
    assert basis.effective_allowed_action_labels() == ["read", "summarize"]
