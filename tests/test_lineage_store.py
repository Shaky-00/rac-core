import pytest

from rac_core.models import CausalLineageRecord, InputAnchorRef, VerifiedStructuredOutputAnchor
from rac_core.store import InMemoryCausalLineageStore


def build_record(
    *,
    session_id: str,
    step_seq: int,
    step_id: str,
    event_id: str,
    tool_name: str = "read_file",
    action: str = "read",
    purpose: str = "internal_summarization",
    basis_id: str = "basis_1",
    parent_hash: str | None = None,
    anchor_id: str | None = None,
    anchor_verified: bool = True,
    anchor_session_id: str | None = None,
    anchor_producer_event_id: str | None = None,
    content_hash: str = "hash_out",
) -> CausalLineageRecord:
    output_anchor = None
    if anchor_id is not None:
        producer_eid = (
            anchor_producer_event_id if anchor_producer_event_id is not None else event_id
        )
        output_anchor = VerifiedStructuredOutputAnchor(
            anchor_id=anchor_id,
            producer_event_id=producer_eid,
            content_hash=content_hash,
            verified_by_controller=anchor_verified,
            session_id=anchor_session_id,
        )
    return CausalLineageRecord(
        session_id=session_id,
        step_seq=step_seq,
        step_id=step_id,
        event_id=event_id,
        parent_hash=parent_hash,
        tool_name=tool_name,
        action=action,
        purpose=purpose,
        basis_id=basis_id,
        output_anchor=output_anchor,
    )


def test_append_first_step_with_verified_output_anchor_success() -> None:
    store = InMemoryCausalLineageStore()
    record = build_record(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        anchor_id="out_1",
        anchor_session_id="sess_1",
    )
    store.append_step(record)
    assert store.get_step("step_1", "sess_1") == record


def test_next_step_seq_empty_session_returns_zero() -> None:
    store = InMemoryCausalLineageStore()
    assert store.next_step_seq("sess_1") == 0


def test_next_step_seq_after_append_returns_max_plus_one() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            anchor_session_id="sess_1",
        )
    )
    assert store.next_step_seq("sess_1") == 1


def test_get_step_get_by_hash_get_by_output_anchor() -> None:
    store = InMemoryCausalLineageStore()
    record = build_record(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        anchor_id="out_1",
        anchor_session_id="sess_1",
    )
    store.append_step(record)
    assert store.get_step("step_1", "sess_1") == record
    assert store.get_by_hash(record.step_hash or "") == record
    assert store.get_by_output_anchor("out_1") == record


def test_duplicate_step_id_same_session_rejected() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            anchor_session_id="sess_1",
        )
    )
    with pytest.raises(ValueError):
        store.append_step(
            build_record(
                session_id="sess_1",
                step_seq=1,
                step_id="step_1",
                event_id="evt_2",
                anchor_id="out_2",
                anchor_session_id="sess_1",
            )
        )


def test_append_rejects_forged_step_hash() -> None:
    store = InMemoryCausalLineageStore()
    r1 = build_record(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        anchor_id="out_1",
        anchor_session_id="sess_1",
    )
    store.append_step(r1)
    r2 = build_record(
        session_id="sess_1",
        step_seq=1,
        step_id="step_2",
        event_id="evt_2",
        anchor_id="out_2",
        anchor_session_id="sess_1",
    )
    r2.step_hash = "fake_hash"
    with pytest.raises(ValueError, match="record.step_hash does not match record content"):
        store.append_step(r2)


def test_unknown_parent_hash_rejected() -> None:
    store = InMemoryCausalLineageStore()
    with pytest.raises(ValueError):
        store.append_step(
            build_record(
                session_id="sess_1",
                step_seq=0,
                step_id="step_1",
                event_id="evt_1",
                parent_hash="unknown_hash",
                anchor_id="out_1",
                anchor_session_id="sess_1",
            )
        )


def test_unverified_output_anchor_rejected() -> None:
    store = InMemoryCausalLineageStore()
    with pytest.raises(ValueError):
        store.append_step(
            build_record(
                session_id="sess_1",
                step_seq=0,
                step_id="step_1",
                event_id="evt_1",
                anchor_id="out_1",
                anchor_verified=False,
                anchor_session_id="sess_1",
            )
        )


def test_output_anchor_session_mismatch_rejected() -> None:
    store = InMemoryCausalLineageStore()
    with pytest.raises(ValueError):
        store.append_step(
            build_record(
                session_id="sess_1",
                step_seq=0,
                step_id="step_1",
                event_id="evt_1",
                anchor_id="out_1",
                anchor_session_id="sess_other",
            )
        )


def test_verify_input_anchor_with_matching_hash_passes() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            content_hash="hash_ok",
            anchor_session_id="sess_1",
        )
    )
    assert store.verify_input_anchor("out_1", content_hash="hash_ok", session_id="sess_1")


def test_verify_input_anchor_with_mismatching_hash_fails() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            content_hash="hash_ok",
            anchor_session_id="sess_1",
        )
    )
    assert not store.verify_input_anchor(
        "out_1", content_hash="hash_wrong", session_id="sess_1"
    )


def test_resolve_predecessor_from_input_anchor() -> None:
    store = InMemoryCausalLineageStore()
    producer = build_record(
        session_id="sess_1",
        step_seq=0,
        step_id="step_1",
        event_id="evt_1",
        anchor_id="out_1",
        content_hash="hash_ok",
        anchor_session_id="sess_1",
    )
    store.append_step(producer)
    result = store.resolve_predecessor(
        input_anchors=[InputAnchorRef(anchor_id="out_1", content_hash="hash_ok")],
        advisory_hints=[],
        session_id="sess_1",
    )
    assert result.valid is True
    assert result.status == "VALID"
    assert result.predecessor_event_id == "evt_1"
    assert result.predecessor_step_id == "step_1"


def test_advisory_conflict_runtime_lineage_wins_with_warning() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            anchor_session_id="sess_1",
        )
    )
    result = store.resolve_predecessor(
        input_anchors=[InputAnchorRef(anchor_id="out_1")],
        advisory_hints=["evt_other"],
        session_id="sess_1",
    )
    assert result.valid is True
    assert "ADVISORY_HINT_CONFLICT_RUNTIME_LINEAGE_USED" in result.warnings


def test_cross_session_anchor_rejected() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            anchor_session_id="sess_1",
        )
    )
    result = store.resolve_predecessor(
        input_anchors=[InputAnchorRef(anchor_id="out_1")],
        advisory_hints=[],
        session_id="sess_2",
    )
    assert result.valid is False
    assert result.status == "CROSS_SESSION_ANCHOR"


def test_cross_session_parent_hash_rejected() -> None:
    store = InMemoryCausalLineageStore()
    parent = build_record(
        session_id="sess_1",
        step_seq=0,
        step_id="step_parent",
        event_id="evt_parent",
        anchor_id="out_parent",
        anchor_session_id="sess_1",
    )
    store.append_step(parent)
    parent_hash = parent.step_hash
    assert parent_hash is not None
    with pytest.raises(ValueError, match="Unknown parent_hash"):
        store.append_step(
            build_record(
                session_id="sess_2",
                step_seq=0,
                step_id="step_child",
                event_id="evt_child",
                parent_hash=parent_hash,
                anchor_id="out_child",
                anchor_session_id="sess_2",
            )
        )


def test_append_rejects_output_anchor_producer_event_id_mismatch() -> None:
    store = InMemoryCausalLineageStore()
    with pytest.raises(
        ValueError, match="output_anchor.producer_event_id must match record.event_id"
    ):
        store.append_step(
            build_record(
                session_id="sess_1",
                step_seq=0,
                step_id="step_1",
                event_id="evt_1",
                anchor_id="out_1",
                anchor_producer_event_id="evt_other",
                anchor_session_id="sess_1",
            )
        )


def test_resolve_predecessor_rejects_producer_event_id_mismatch() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            content_hash="hash_ok",
            anchor_session_id="sess_1",
        )
    )
    result = store.resolve_predecessor(
        input_anchors=[
            InputAnchorRef(anchor_id="out_1", producer_event_id="evt_fake", content_hash="hash_ok")
        ],
        advisory_hints=[],
        session_id="sess_1",
    )
    assert result.valid is False
    assert result.status == "INPUT_ANCHOR_PRODUCER_MISMATCH"
    assert "out_1" in result.input_anchor_ids
    assert "evt_1" in result.producer_event_ids


def test_resolve_predecessor_valid_with_matching_producer_event_id() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            content_hash="hash_ok",
            anchor_session_id="sess_1",
        )
    )
    result = store.resolve_predecessor(
        input_anchors=[
            InputAnchorRef(
                anchor_id="out_1", producer_event_id="evt_1", content_hash="hash_ok"
            )
        ],
        advisory_hints=[],
        session_id="sess_1",
    )
    assert result.valid is True
    assert result.status == "VALID"
    assert result.predecessor_event_id == "evt_1"


def test_multi_predecessor_unsupported() -> None:
    store = InMemoryCausalLineageStore()
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=0,
            step_id="step_1",
            event_id="evt_1",
            anchor_id="out_1",
            anchor_session_id="sess_1",
        )
    )
    store.append_step(
        build_record(
            session_id="sess_1",
            step_seq=1,
            step_id="step_2",
            event_id="evt_2",
            parent_hash=store.get_step("step_1", "sess_1").step_hash,
            anchor_id="out_2",
            anchor_session_id="sess_1",
        )
    )
    result = store.resolve_predecessor(
        input_anchors=[InputAnchorRef(anchor_id="out_1"), InputAnchorRef(anchor_id="out_2")],
        advisory_hints=[],
        session_id="sess_1",
    )
    assert result.valid is False
    assert result.status == "MULTI_PREDECESSOR_UNSUPPORTED"
    assert result.multi_predecessor is True
