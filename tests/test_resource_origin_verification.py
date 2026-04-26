from rac_core.models import (
    CausalLineageRecord,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    InputAnchorRef,
    ResourceScope,
    TypedAuthorizationEvent,
    TypedEventResourceScope,
    TypedEventSubject,
    VerifiedStructuredOutputAnchor,
)
from rac_core.store import InMemoryCausalLineageStore
from rac_core.verification import ResourceOriginVerifier


def build_grant(*, session_id: str = "sess_1", allowed_ids: set[str]) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_1",
        session_id=session_id,
        subject=GrantSubject(user_id="user_1"),
        resource_scope=ResourceScope(type="file", allowed_ids=allowed_ids),
        purpose_scope={"internal_summarization"},
        conditions=GrantConditions(),
    )


def append_verified_producer(
    store: InMemoryCausalLineageStore,
    *,
    session_id: str,
    event_id: str,
    step_id: str,
    anchor_id: str,
    content_hash: str,
    resource_ids: set[str],
    step_seq: int = 0,
) -> None:
    store.append_step(
        CausalLineageRecord(
            session_id=session_id,
            step_seq=step_seq,
            step_id=step_id,
            event_id=event_id,
            tool_name="read_file",
            action="read",
            purpose="internal_summarization",
            basis_id="basis_0",
            output_anchor=VerifiedStructuredOutputAnchor(
                anchor_id=anchor_id,
                producer_event_id=event_id,
                content_hash=content_hash,
                resource_ids=resource_ids,
                verified_by_controller=True,
                session_id=session_id,
            ),
        )
    )


def test_resource_in_grant_envelope_passes() -> None:
    grant = build_grant(allowed_ids={"file_A"})
    verifier = ResourceOriginVerifier(InMemoryCausalLineageStore())
    result = verifier.verify_resource_origin(
        resource_id="file_A",
        grant_envelope=grant,
        input_anchors=[],
    )
    assert result.valid is True
    assert result.source == "GRANT_ENVELOPE"


def test_resource_not_in_grant_and_no_input_anchors_fails() -> None:
    grant = build_grant(allowed_ids={"file_A"})
    verifier = ResourceOriginVerifier(InMemoryCausalLineageStore())
    result = verifier.verify_resource_origin(
        resource_id="file_B",
        grant_envelope=grant,
        input_anchors=[],
    )
    assert result.valid is False
    assert result.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"
    assert result.reason is not None and "not in grant envelope" in result.reason


def test_resource_from_verified_input_anchor_passes() -> None:
    store = InMemoryCausalLineageStore()
    grant = build_grant(allowed_ids={"file_A"})
    append_verified_producer(
        store,
        session_id="sess_1",
        event_id="evt_1",
        step_id="step_0",
        anchor_id="out_1",
        content_hash="hash_1",
        resource_ids={"file_B"},
    )
    verifier = ResourceOriginVerifier(store)
    result = verifier.verify_resource_origin(
        resource_id="file_B",
        grant_envelope=grant,
        input_anchors=[
            InputAnchorRef(
                anchor_id="out_1",
                producer_event_id="evt_1",
                content_hash="hash_1",
            )
        ],
    )
    assert result.valid is True
    assert result.source == "VERIFIED_INPUT_ANCHOR"
    assert result.matched_anchor_id == "out_1"
    assert result.matched_producer_event_id == "evt_1"


def test_registry_existence_alone_is_not_enough_semantic() -> None:
    """file_B may exist in a registry elsewhere; without grant or verified anchor it fails."""
    grant = build_grant(allowed_ids={"file_A"})
    verifier = ResourceOriginVerifier(InMemoryCausalLineageStore())
    result = verifier.verify_resource_origin(
        resource_id="file_B",
        grant_envelope=grant,
        input_anchors=[],
    )
    assert result.valid is False
    assert result.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"


def test_input_anchor_content_hash_mismatch_fails() -> None:
    store = InMemoryCausalLineageStore()
    grant = build_grant(allowed_ids={"file_A"})
    append_verified_producer(
        store,
        session_id="sess_1",
        event_id="evt_1",
        step_id="step_0",
        anchor_id="out_1",
        content_hash="hash_ok",
        resource_ids={"file_B"},
    )
    verifier = ResourceOriginVerifier(store)
    result = verifier.verify_resource_origin(
        resource_id="file_B",
        grant_envelope=grant,
        input_anchors=[
            InputAnchorRef(
                anchor_id="out_1",
                producer_event_id="evt_1",
                content_hash="hash_wrong",
            )
        ],
    )
    assert result.valid is False
    assert result.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"


def test_input_anchor_producer_event_id_mismatch_fails() -> None:
    store = InMemoryCausalLineageStore()
    grant = build_grant(allowed_ids={"file_A"})
    append_verified_producer(
        store,
        session_id="sess_1",
        event_id="evt_1",
        step_id="step_0",
        anchor_id="out_1",
        content_hash="hash_1",
        resource_ids={"file_B"},
    )
    verifier = ResourceOriginVerifier(store)
    result = verifier.verify_resource_origin(
        resource_id="file_B",
        grant_envelope=grant,
        input_anchors=[
            InputAnchorRef(
                anchor_id="out_1",
                producer_event_id="evt_fake",
                content_hash="hash_1",
            )
        ],
    )
    assert result.valid is False
    assert result.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"


def test_cross_session_input_anchor_fails() -> None:
    store = InMemoryCausalLineageStore()
    grant = build_grant(allowed_ids={"file_A"})
    append_verified_producer(
        store,
        session_id="sess_other",
        event_id="evt_1",
        step_id="step_0",
        anchor_id="out_1",
        content_hash="hash_1",
        resource_ids={"file_B"},
    )
    verifier = ResourceOriginVerifier(store)
    result = verifier.verify_resource_origin(
        resource_id="file_B",
        grant_envelope=grant,
        input_anchors=[
            InputAnchorRef(anchor_id="out_1", producer_event_id="evt_1", content_hash="hash_1")
        ],
    )
    assert result.valid is False
    assert result.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"
    assert result.reason is not None
    assert (
        "CROSS_SESSION" in result.reason
        or "cross session" in result.reason.lower()
        or "predecessor resolution invalid" in result.reason
    )


def test_missing_input_anchor_fails_origin() -> None:
    """No verified producer in lineage for anchor; verifier must not treat as trusted source."""
    grant = build_grant(allowed_ids={"file_A"})
    verifier = ResourceOriginVerifier(InMemoryCausalLineageStore())
    result = verifier.verify_resource_origin(
        resource_id="file_B",
        grant_envelope=grant,
        input_anchors=[InputAnchorRef(anchor_id="out_missing")],
    )
    assert result.valid is False
    assert result.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"


def test_event_batch_all_resources_valid_passes() -> None:
    store = InMemoryCausalLineageStore()
    grant = build_grant(allowed_ids={"file_A"})
    append_verified_producer(
        store,
        session_id="sess_1",
        event_id="evt_1",
        step_id="step_0",
        anchor_id="out_1",
        content_hash="hash_1",
        resource_ids={"file_B"},
    )
    verifier = ResourceOriginVerifier(store)
    event = TypedAuthorizationEvent(
        event_id="evt_sum",
        session_id="sess_1",
        step_id="step_sum",
        step_seq=1,
        subject=TypedEventSubject(user_id="user_1"),
        tool_name="summarize_file",
        action="summarize",
        resource_scope=TypedEventResourceScope(type="file", ids={"file_A", "file_B"}),
        purpose="internal_summarization",
        input_anchors=[
            InputAnchorRef(
                anchor_id="out_1",
                producer_event_id="evt_1",
                content_hash="hash_1",
            )
        ],
    )
    batch = verifier.verify_event_resource_origins(event, grant)
    assert batch.valid is True
    assert all(r.valid for r in batch.results)


def test_event_batch_one_resource_invalid_fails() -> None:
    store = InMemoryCausalLineageStore()
    grant = build_grant(allowed_ids={"file_A"})
    append_verified_producer(
        store,
        session_id="sess_1",
        event_id="evt_1",
        step_id="step_0",
        anchor_id="out_1",
        content_hash="hash_1",
        resource_ids={"file_B"},
    )
    verifier = ResourceOriginVerifier(store)
    event = TypedAuthorizationEvent(
        event_id="evt_sum",
        session_id="sess_1",
        step_id="step_sum",
        step_seq=1,
        subject=TypedEventSubject(user_id="user_1"),
        tool_name="summarize_file",
        action="summarize",
        resource_scope=TypedEventResourceScope(type="file", ids={"file_A", "file_C"}),
        purpose="internal_summarization",
        input_anchors=[
            InputAnchorRef(
                anchor_id="out_1",
                producer_event_id="evt_1",
                content_hash="hash_1",
            )
        ],
    )
    batch = verifier.verify_event_resource_origins(event, grant)
    assert batch.valid is False
    assert batch.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"
    assert batch.failed_resource_ids == {"file_C"}
    assert batch.reason is not None


def test_event_batch_session_mismatch_fails_even_if_resource_in_grant() -> None:
    store = InMemoryCausalLineageStore()
    verifier = ResourceOriginVerifier(store)
    grant = build_grant(session_id="sess_1", allowed_ids={"file_A"})
    event = TypedAuthorizationEvent(
        event_id="evt_cross",
        session_id="sess_2",
        step_id="step_cross",
        step_seq=1,
        subject=TypedEventSubject(user_id="user_1"),
        tool_name="read_file",
        action="read",
        resource_scope=TypedEventResourceScope(type="file", ids={"file_A"}),
        purpose="internal_summarization",
        input_anchors=[],
    )
    batch = verifier.verify_event_resource_origins(event, grant)
    assert batch.valid is False
    assert batch.rule == "RESOURCE_ORIGIN_UNVERIFIABLE"
    assert batch.failed_resource_ids == {"file_A"}
    assert batch.reason is not None and "session_id" in batch.reason
    assert batch.metadata["event_session_id"] == "sess_2"
    assert batch.metadata["grant_session_id"] == "sess_1"
