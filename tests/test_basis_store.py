import pytest

from rac_core.models import AuthorizationBasis, BasisResourceScope
from rac_core.store import InMemoryBasisStore


def build_basis(basis_id: str) -> AuthorizationBasis:
    return AuthorizationBasis(
        basis_id=basis_id,
        subjects={"user_1"},
        actions={"read"},
        resource_scope=BasisResourceScope(type="file", ids={"file_A"}),
        purpose_scope={"internal_summarization"},
    )


def test_save_basis_and_load_by_session_step() -> None:
    store = InMemoryBasisStore()
    basis = build_basis("basis_1")
    store.save_basis("sess_1", "step_1", basis)
    assert store.load_finalized_basis("sess_1", "step_1") == basis


def test_save_basis_and_load_by_basis_id() -> None:
    store = InMemoryBasisStore()
    basis = build_basis("basis_1")
    store.save_basis("sess_1", "step_1", basis)
    assert store.load_basis_by_id("basis_1") == basis


def test_has_step_and_has_basis() -> None:
    store = InMemoryBasisStore()
    basis = build_basis("basis_1")
    store.save_basis("sess_1", "step_1", basis)
    assert store.has_step("sess_1", "step_1")
    assert store.has_basis("basis_1")


def test_empty_basis_id_rejected() -> None:
    store = InMemoryBasisStore()
    basis = build_basis("basis_x")
    basis.basis_id = ""
    with pytest.raises(ValueError):
        store.save_basis("sess_1", "step_1", basis)


def test_duplicate_session_step_rejected() -> None:
    store = InMemoryBasisStore()
    store.save_basis("sess_1", "step_1", build_basis("basis_1"))
    with pytest.raises(ValueError):
        store.save_basis("sess_1", "step_1", build_basis("basis_2"))


def test_duplicate_basis_id_rejected() -> None:
    store = InMemoryBasisStore()
    store.save_basis("sess_1", "step_1", build_basis("basis_1"))
    with pytest.raises(ValueError):
        store.save_basis("sess_2", "step_2", build_basis("basis_1"))


def test_same_step_id_different_session_allowed_if_basis_id_unique() -> None:
    store = InMemoryBasisStore()
    b1 = build_basis("basis_1")
    b2 = build_basis("basis_2")
    store.save_basis("sess_1", "step_same", b1)
    store.save_basis("sess_2", "step_same", b2)
    assert store.load_finalized_basis("sess_1", "step_same") == b1
    assert store.load_finalized_basis("sess_2", "step_same") == b2
