from rac_core.models import (
    AuthorizationBasis,
    AuthorizationProfile,
    CausalLineageRecord,
    EffectProfile,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    InputAnchorRef,
    ResourceMapping,
    ResourceScope,
    ToolManifest,
    TypedAuthorizationEvent,
    TypedEventResourceScope,
    TypedEventSubject,
    VerifiedStructuredOutputAnchor,
)


def build_grant() -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_1",
        session_id="sess_1",
        subject=GrantSubject(user_id="user_1", effective_subject="subj_1"),
        allowed_actions={"read", "summarize"},
        allowed_tools={"read_file", "summarize_file"},
        resource_scope=ResourceScope(
            type="file", allowed_ids={"file_A"}, allowed_labels={"internal"}
        ),
        purpose_scope={"internal_summarization"},
        conditions=GrantConditions(environment="trusted_workspace", tenant="tenant_X"),
    )


def test_grant_envelope_creation() -> None:
    grant = build_grant()
    assert grant.grant_id == "grant_1"
    assert grant.resource_scope.type == "file"


def test_tool_manifest_creation() -> None:
    manifest = ToolManifest(
        tool_name="read_file",
        operation="read",
        resource_arg="file_id",
        resource_type="file",
        authorization_profile=AuthorizationProfile(
            required_actions=["acquire.read_object"],
            resource_mappings=[
                ResourceMapping(
                    arg="file_id",
                    resource_role="target",
                    resource_type="file",
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
            commit_type="read",
        ),
    )
    assert manifest.operation == "read"
    assert manifest.authorization_profile is not None


def test_verified_structured_output_anchor_creation() -> None:
    anchor = VerifiedStructuredOutputAnchor(
        anchor_id="out_1",
        producer_event_id="evt_1",
        content_hash="hash_1",
        verified_by_controller=True,
    )
    assert anchor.anchor_id == "out_1"
    assert anchor.verified_by_controller is True


def test_typed_authorization_event_creation_with_advisory_hints() -> None:
    event = TypedAuthorizationEvent(
        event_id="evt_2",
        session_id="sess_1",
        step_id="step_2",
        step_seq=2,
        subject=TypedEventSubject(user_id="user_1", effective_subject="subj_1"),
        tool_name="summarize_file",
        action="summarize",
        resource_scope=TypedEventResourceScope(type="file", ids={"file_A"}),
        purpose="internal_summarization",
        input_anchors=[InputAnchorRef(anchor_id="out_1")],
        advisory_predecessor_hints=["evt_1", "step_1"],
    )
    assert event.advisory_predecessor_hints == ["evt_1", "step_1"]


def test_authorization_basis_from_grant_envelope() -> None:
    grant = build_grant()
    basis = AuthorizationBasis.from_grant_envelope(grant)
    assert basis.basis_id == "basis_initial"
    assert basis.subjects == {"subj_1"}
    assert basis.resource_scope.ids == {"file_A"}
    assert basis.resource_scope.labels == {"internal"}


def test_causal_lineage_record_auto_generates_step_hash() -> None:
    record = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        tool_name="read_file",
        action="read",
        purpose="internal_summarization",
        basis_id="basis_1",
    )
    assert record.step_hash is not None


def test_same_content_generates_same_step_hash() -> None:
    base = dict(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        tool_name="read_file",
        action="read",
        purpose="internal_summarization",
        basis_id="basis_1",
        resource_ids={"file_A"},
    )
    r1 = CausalLineageRecord(**base)
    r2 = CausalLineageRecord(**base)
    assert r1.step_hash == r2.step_hash


def test_session_change_changes_step_hash() -> None:
    common = dict(
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        tool_name="read_file",
        action="read",
        purpose="internal_summarization",
        basis_id="basis_1",
    )
    r1 = CausalLineageRecord(session_id="sess_1", **common)
    r2 = CausalLineageRecord(session_id="sess_2", **common)
    assert r1.step_hash != r2.step_hash


def test_verify_step_hash_true_when_not_tampered() -> None:
    record = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        tool_name="read_file",
        action="read",
        purpose="internal_summarization",
        basis_id="basis_1",
    )
    assert record.verify_step_hash() is True


def test_verify_step_hash_false_after_tamper() -> None:
    record = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        tool_name="read_file",
        action="read",
        purpose="internal_summarization",
        basis_id="basis_1",
    )
    record.purpose = "external_sharing"
    assert record.verify_step_hash() is False


def test_verify_step_hash_false_after_output_anchor_content_hash_tamper() -> None:
    record = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        tool_name="read_file",
        action="read",
        purpose="internal_summarization",
        basis_id="basis_1",
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out_1",
            producer_event_id="evt_1",
            content_hash="hash_original",
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    assert record.verify_step_hash() is True
    assert record.output_anchor is not None
    record.output_anchor.content_hash = "hash_tampered"
    assert record.verify_step_hash() is False


def test_verify_step_hash_false_after_output_anchor_resource_ids_tamper() -> None:
    record = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        tool_name="read_file",
        action="read",
        purpose="internal_summarization",
        basis_id="basis_1",
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out_1",
            producer_event_id="evt_1",
            content_hash="hash_1",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    assert record.verify_step_hash() is True
    assert record.output_anchor is not None
    record.output_anchor.resource_ids = {"file_B"}
    assert record.verify_step_hash() is False
