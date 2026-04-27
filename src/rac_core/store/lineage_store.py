from __future__ import annotations

from rac_core.models import (
    CausalLineageRecord,
    InputAnchorRef,
    PredecessorResolutionResult,
)


class InMemoryCausalLineageStore:
    def __init__(self) -> None:
        self._records_by_step: dict[tuple[str, str], CausalLineageRecord] = {}
        self._records_by_hash: dict[str, CausalLineageRecord] = {}
        self._records_by_output_anchor: dict[str, CausalLineageRecord] = {}
        self._max_seq_by_session: dict[str, int] = {}

    def append_step(self, record: CausalLineageRecord) -> None:
        step_key = (record.session_id, record.step_id)
        if step_key in self._records_by_step:
            raise ValueError("Duplicate step_id in same session.")

        max_seq = self._max_seq_by_session.get(record.session_id)
        if max_seq is not None and record.step_seq <= max_seq:
            raise ValueError("step_seq must be strictly monotonic increasing in session.")

        if not self.verify_parent_hash(
            record.parent_hash, session_id=record.session_id
        ):
            raise ValueError("Unknown parent_hash.")

        if record.output_anchor is not None:
            anchor = record.output_anchor
            if anchor.producer_event_id != record.event_id:
                raise ValueError(
                    "output_anchor.producer_event_id must match record.event_id."
                )
            if not anchor.verified_by_controller:
                raise ValueError("output_anchor must be verified_by_controller=True.")
            if anchor.session_id is not None and anchor.session_id != record.session_id:
                raise ValueError("output_anchor.session_id does not match record.session_id.")
            if anchor.anchor_id in self._records_by_output_anchor:
                raise ValueError("Duplicate output_anchor.anchor_id.")

        if record.step_hash is None:
            raise ValueError("step_hash must not be None.")
        if not record.verify_step_hash():
            raise ValueError("record.step_hash does not match record content.")
        if record.step_hash in self._records_by_hash:
            raise ValueError("Duplicate step_hash.")

        self._records_by_step[step_key] = record
        self._records_by_hash[record.step_hash] = record
        if record.output_anchor is not None:
            self._records_by_output_anchor[record.output_anchor.anchor_id] = record
        self._max_seq_by_session[record.session_id] = record.step_seq

    def get_step(
        self, step_id: str, session_id: str | None = None
    ) -> CausalLineageRecord | None:
        if session_id is not None:
            return self._records_by_step.get((session_id, step_id))

        matches = [
            record
            for (sess_id, sid), record in self._records_by_step.items()
            if sid == step_id and sess_id
        ]
        return matches[0] if len(matches) == 1 else None

    def get_by_hash(self, step_hash: str) -> CausalLineageRecord | None:
        return self._records_by_hash.get(step_hash)

    def get_by_output_anchor(self, anchor_id: str) -> CausalLineageRecord | None:
        return self._records_by_output_anchor.get(anchor_id)

    def verify_parent_hash(
        self, parent_hash: str | None, session_id: str | None = None
    ) -> bool:
        if parent_hash is None:
            return True
        parent_record = self._records_by_hash.get(parent_hash)
        if parent_record is None:
            return False
        if session_id is not None and parent_record.session_id != session_id:
            return False
        return True

    def verify_input_anchor(
        self,
        anchor_id: str,
        content_hash: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        producer_record = self.get_by_output_anchor(anchor_id)
        if producer_record is None:
            return False
        output_anchor = producer_record.output_anchor
        if output_anchor is None:
            return False
        if not output_anchor.verified_by_controller:
            return False
        if content_hash is not None and output_anchor.content_hash != content_hash:
            return False
        if session_id is not None and producer_record.session_id != session_id:
            return False
        return True

    def next_step_seq(self, session_id: str) -> int:
        max_seq = self._max_seq_by_session.get(session_id)
        if max_seq is None:
            return 0
        return max_seq + 1

    def resolve_predecessor(
        self,
        input_anchors: list[InputAnchorRef],
        advisory_hints: list[str],
        session_id: str,
    ) -> PredecessorResolutionResult:
        if not input_anchors:
            return PredecessorResolutionResult(status="NO_PREDECESSOR", valid=True)

        producer_records: list[CausalLineageRecord] = []
        producer_event_ids: list[str] = []
        input_anchor_ids: list[str] = []

        for anchor_ref in input_anchors:
            producer = self.get_by_output_anchor(anchor_ref.anchor_id)
            if producer is None:
                return PredecessorResolutionResult(
                    status="INPUT_ANCHOR_NOT_FOUND",
                    valid=False,
                    reason=f"Input anchor {anchor_ref.anchor_id} not found.",
                )
            if producer.session_id != session_id:
                return PredecessorResolutionResult(
                    status="CROSS_SESSION_ANCHOR",
                    valid=False,
                    reason="Input anchor producer belongs to another session.",
                    input_anchor_ids=input_anchor_ids + [anchor_ref.anchor_id],
                    producer_event_ids=producer_event_ids + [producer.event_id],
                )
            if (
                anchor_ref.producer_event_id is not None
                and anchor_ref.producer_event_id != producer.event_id
            ):
                return PredecessorResolutionResult(
                    status="INPUT_ANCHOR_PRODUCER_MISMATCH",
                    valid=False,
                    reason="Input anchor producer_event_id does not match runtime lineage.",
                    input_anchor_ids=input_anchor_ids + [anchor_ref.anchor_id],
                    producer_event_ids=producer_event_ids + [producer.event_id],
                )
            if (
                producer.output_anchor is None
                or not producer.output_anchor.verified_by_controller
            ):
                return PredecessorResolutionResult(
                    status="UNVERIFIED_INPUT_ANCHOR",
                    valid=False,
                    reason="Producer output anchor is missing or not verified.",
                )
            if (
                anchor_ref.content_hash is not None
                and producer.output_anchor.content_hash != anchor_ref.content_hash
            ):
                return PredecessorResolutionResult(
                    status="INPUT_ANCHOR_HASH_MISMATCH",
                    valid=False,
                    reason="Input anchor content_hash mismatch.",
                )
            producer_records.append(producer)
            producer_event_ids.append(producer.event_id)
            input_anchor_ids.append(anchor_ref.anchor_id)

        distinct_events = set(producer_event_ids)
        if len(distinct_events) > 1:
            return PredecessorResolutionResult(
                status="MULTI_PREDECESSOR_UNSUPPORTED",
                valid=False,
                multi_predecessor=True,
                producer_event_ids=producer_event_ids,
                input_anchor_ids=input_anchor_ids,
                reason="Multiple distinct predecessor events are unsupported in v0.4.",
            )

        predecessor = producer_records[0]
        warnings: list[str] = []
        if advisory_hints:
            if (
                predecessor.event_id not in advisory_hints
                and predecessor.step_id not in advisory_hints
            ):
                warnings.append("ADVISORY_HINT_CONFLICT_RUNTIME_LINEAGE_USED")

        return PredecessorResolutionResult(
            status="VALID",
            valid=True,
            predecessor_step_id=predecessor.step_id,
            predecessor_event_id=predecessor.event_id,
            predecessor_hash=predecessor.step_hash,
            producer_event_ids=producer_event_ids,
            input_anchor_ids=input_anchor_ids,
            warnings=warnings,
        )


class RelaxedAnchorLineageStore(InMemoryCausalLineageStore):
    """Ablation / evaluation only: allow unverified output anchors to persist."""

    def append_step(self, record: CausalLineageRecord) -> None:
        if record.output_anchor is not None and not record.output_anchor.verified_by_controller:
            oa = record.output_anchor.model_copy(update={"verified_by_controller": True})
            record = record.model_copy(update={"output_anchor": oa})
        super().append_step(record)
