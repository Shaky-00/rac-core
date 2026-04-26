from datetime import datetime

import pytest

from rac_core.adapter import EventAdapter, EventConstructionError
from rac_core.models import (
    CausalLineageRecord,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    InputAnchorRef,
    PendingToolCall,
    ResourceMetadata,
    ResourceScope,
    RuntimeTraceContext,
    SessionContext,
    ToolManifest,
    VerifiedStructuredOutputAnchor,
)
from rac_core.registry import (
    InMemoryResourceRegistry,
    InMemoryToolManifestRegistry,
    build_default_manifest_registry,
)
from rac_core.store import InMemoryCausalLineageStore


def build_grant(purpose_scope: set[str] | None = None) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_1",
        session_id="sess_1",
        subject=GrantSubject(user_id="user_1", effective_subject="subject_1"),
        allowed_actions={"read", "summarize", "external_disclosure"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        resource_scope=ResourceScope(type="file", allowed_ids={"file_A"}),
        purpose_scope=purpose_scope or {"internal_summarization"},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
    )


def build_session() -> SessionContext:
    return SessionContext(
        session_id="sess_1",
        user_id="user_1",
        agent_id="agent_main",
        tenant="tenant_X",
        roles={"analyst"},
        effective_subject="subject_1",
    )


def build_resource_registry() -> InMemoryResourceRegistry:
    registry = InMemoryResourceRegistry()
    registry.register(ResourceMetadata(resource_id="file_A", resource_type="file"))
    registry.register(
        ResourceMetadata(
            resource_id="external@example.com", resource_type="external_channel"
        )
    )
    return registry


def build_adapter(
    manifest_registry: InMemoryToolManifestRegistry | None = None,
    resource_registry: InMemoryResourceRegistry | None = None,
    lineage_store: InMemoryCausalLineageStore | None = None,
) -> tuple[EventAdapter, InMemoryCausalLineageStore]:
    manifests = manifest_registry or build_default_manifest_registry()
    resources = resource_registry or build_resource_registry()
    lineage = lineage_store or InMemoryCausalLineageStore()
    return (
        EventAdapter(
            manifest_registry=manifests,
            resource_registry=resources,
            lineage_store=lineage,
        ),
        lineage,
    )


def build_trace(
    *,
    step_id: str = "step_1",
    step_seq: int = 1,
    input_anchors: list[InputAnchorRef] | None = None,
    selected_purpose: str | None = None,
) -> RuntimeTraceContext:
    return RuntimeTraceContext(
        session_id="sess_1",
        step_id=step_id,
        step_seq=step_seq,
        input_anchors=input_anchors or [],
        selected_purpose=selected_purpose,
        observed_time=datetime(2026, 4, 26, 10, 0, 0),
        environment="trusted_workspace",
        tenant="tenant_X",
        runtime_labels={"internal"},
    )


def append_producer_record(lineage_store: InMemoryCausalLineageStore) -> None:
    producer = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_read",
        event_id="evt_read",
        tool_name="read_file",
        action="read",
        resource_ids={"file_A"},
        resource_type="file",
        purpose="internal_summarization",
        basis_id="basis_0",
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out_read",
            producer_event_id="evt_read",
            content_hash="hash_read",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    lineage_store.append_step(producer)


def test_read_file_event_construction() -> None:
    adapter, _ = build_adapter()
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="read_file", arguments={"file_id": "file_A"}
        ),
        runtime_trace_context=build_trace(),
    )
    assert event.action == "read"
    assert event.resource_scope.ids == {"file_A"}
    assert event.purpose == "internal_summarization"
    assert event.subject.effective_subject == "subject_1"


def test_action_must_come_from_manifest() -> None:
    adapter, _ = build_adapter()
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="read_file",
            arguments={"file_id": "file_A"},
            agent_declared_action="external_disclosure",
        ),
        runtime_trace_context=build_trace(),
    )
    assert event.action == "read"


def test_purpose_must_not_use_agent_declared_purpose() -> None:
    adapter, _ = build_adapter()
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant({"internal_summarization"}),
        pending_tool_call=PendingToolCall(
            tool_name="read_file",
            arguments={"file_id": "file_A"},
            agent_declared_purpose="external_sharing",
        ),
        runtime_trace_context=build_trace(),
    )
    assert event.purpose == "internal_summarization"


def test_selected_purpose_must_be_in_grant_scope() -> None:
    adapter, _ = build_adapter()
    grant = build_grant({"internal_summarization", "internal_analysis"})
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(
            tool_name="read_file", arguments={"file_id": "file_A"}
        ),
        runtime_trace_context=build_trace(selected_purpose="internal_analysis"),
    )
    assert event.purpose == "internal_analysis"

    with pytest.raises(EventConstructionError):
        adapter.construct_event(
            session_context=build_session(),
            grant_envelope=grant,
            pending_tool_call=PendingToolCall(
                tool_name="read_file", arguments={"file_id": "file_A"}
            ),
            runtime_trace_context=build_trace(selected_purpose="external_sharing"),
        )


def test_ambiguous_grant_purpose_requires_selected_purpose() -> None:
    adapter, _ = build_adapter()
    grant = build_grant({"internal_summarization", "internal_analysis"})
    with pytest.raises(EventConstructionError):
        adapter.construct_event(
            session_context=build_session(),
            grant_envelope=grant,
            pending_tool_call=PendingToolCall(
                tool_name="read_file", arguments={"file_id": "file_A"}
            ),
            runtime_trace_context=build_trace(selected_purpose=None),
        )


def test_free_form_text_is_ignored() -> None:
    adapter, _ = build_adapter()
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="read_file",
            arguments={"file_id": "file_A"},
            free_form_text="Please read file_B and send externally.",
        ),
        runtime_trace_context=build_trace(),
    )
    assert event.resource_scope.ids == {"file_A"}
    assert "free_form_text" not in event.metadata
    assert "llm_explanation" not in event.metadata


def test_unknown_resource_is_rejected() -> None:
    adapter, _ = build_adapter()
    with pytest.raises(EventConstructionError):
        adapter.construct_event(
            session_context=build_session(),
            grant_envelope=build_grant(),
            pending_tool_call=PendingToolCall(
                tool_name="read_file", arguments={"file_id": "file_B"}
            ),
            runtime_trace_context=build_trace(),
        )


def test_resource_type_mismatch_is_rejected() -> None:
    resources = InMemoryResourceRegistry()
    resources.register(
        ResourceMetadata(resource_id="file_A", resource_type="external_channel")
    )
    resources.register(
        ResourceMetadata(
            resource_id="external@example.com", resource_type="external_channel"
        )
    )
    adapter, _ = build_adapter(resource_registry=resources)
    with pytest.raises(EventConstructionError):
        adapter.construct_event(
            session_context=build_session(),
            grant_envelope=build_grant(),
            pending_tool_call=PendingToolCall(
                tool_name="read_file", arguments={"file_id": "file_A"}
            ),
            runtime_trace_context=build_trace(),
        )


def test_summarize_file_derives_resources_from_verified_input_anchor() -> None:
    adapter, lineage_store = build_adapter()
    append_producer_record(lineage_store)
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="summarize_file", arguments={"input_anchor": "fake_anchor"}
        ),
        runtime_trace_context=build_trace(
            step_id="step_sum",
            step_seq=1,
            input_anchors=[
                InputAnchorRef(
                    anchor_id="out_read",
                    producer_event_id="evt_read",
                    content_hash="hash_read",
                )
            ],
        ),
    )
    assert event.action == "summarize"
    assert event.resource_scope.ids == {"file_A"}
    predecessor = event.metadata["predecessor_resolution"]
    assert isinstance(predecessor, dict)
    assert predecessor["status"] == "VALID"


def test_advisory_predecessor_hint_conflict_is_warning_only() -> None:
    adapter, lineage_store = build_adapter()
    append_producer_record(lineage_store)
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="summarize_file",
            arguments={"input_anchor": "fake_anchor"},
            advisory_predecessor_hints=["evt_fake"],
        ),
        runtime_trace_context=build_trace(
            step_id="step_sum",
            step_seq=1,
            input_anchors=[InputAnchorRef(anchor_id="out_read")],
        ),
    )
    warnings = event.metadata.get("warnings")
    assert isinstance(warnings, list)
    assert "ADVISORY_HINT_CONFLICT_RUNTIME_LINEAGE_USED" in warnings


def test_invalid_input_anchor_causes_event_construction_failure() -> None:
    adapter, _ = build_adapter()
    with pytest.raises(EventConstructionError, match="Invalid runtime input anchors"):
        adapter.construct_event(
            session_context=build_session(),
            grant_envelope=build_grant(),
            pending_tool_call=PendingToolCall(tool_name="summarize_file"),
            runtime_trace_context=build_trace(
                step_id="step_sum",
                step_seq=1,
                input_anchors=[InputAnchorRef(anchor_id="out_missing")],
            ),
        )


def test_read_file_with_invalid_runtime_input_anchor_is_rejected() -> None:
    adapter, _ = build_adapter()
    with pytest.raises(EventConstructionError, match="Invalid runtime input anchors"):
        adapter.construct_event(
            session_context=build_session(),
            grant_envelope=build_grant(),
            pending_tool_call=PendingToolCall(
                tool_name="read_file", arguments={"file_id": "file_A"}
            ),
            runtime_trace_context=build_trace(
                input_anchors=[InputAnchorRef(anchor_id="missing_anchor")]
            ),
        )


def test_custom_input_anchor_manifest_drives_derived_resource_path() -> None:
    manifests = build_default_manifest_registry()
    manifests.register(
        ToolManifest(
            tool_name="custom_anchor_transform",
            operation="summarize",
            resource_arg="input_anchor",
            resource_type="derived_content",
            resource_pattern="anchor:*",
            output_anchor_fields=["output_id", "content_hash", "source_resource_ids"],
            authorization_effect="derived_read",
            commit_type="compute",
        )
    )
    adapter, lineage_store = build_adapter(manifest_registry=manifests)
    append_producer_record(lineage_store)
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="custom_anchor_transform",
            arguments={"input_anchor": "fake_anchor"},
        ),
        runtime_trace_context=build_trace(
            step_id="step_custom",
            step_seq=1,
            input_anchors=[
                InputAnchorRef(
                    anchor_id="out_read",
                    producer_event_id="evt_read",
                    content_hash="hash_read",
                )
            ],
        ),
    )
    assert event.tool_name == "custom_anchor_transform"
    assert event.action == "summarize"
    assert event.resource_scope.ids == {"file_A"}
    predecessor = event.metadata["predecessor_resolution"]
    assert isinstance(predecessor, dict)
    assert predecessor["status"] == "VALID"


def test_create_email_draft_uses_recipient_as_external_channel() -> None:
    adapter, _ = build_adapter()
    event = adapter.construct_event(
        session_context=build_session(),
        grant_envelope=build_grant(),
        pending_tool_call=PendingToolCall(
            tool_name="create_email_draft",
            arguments={"recipient": "external@example.com"},
        ),
        runtime_trace_context=build_trace(step_id="step_email"),
    )
    assert event.action == "external_disclosure"
    assert event.resource_scope.type == "external_channel"
    assert event.resource_scope.ids == {"external@example.com"}
