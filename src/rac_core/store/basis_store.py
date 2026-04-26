from __future__ import annotations

from rac_core.models import AuthorizationBasis


class InMemoryBasisStore:
    def __init__(self) -> None:
        self._basis_by_step: dict[tuple[str, str], AuthorizationBasis] = {}
        self._basis_by_id: dict[str, AuthorizationBasis] = {}

    def save_basis(self, session_id: str, step_id: str, basis: AuthorizationBasis) -> None:
        if not session_id:
            raise ValueError("session_id must be non-empty.")
        if not step_id:
            raise ValueError("step_id must be non-empty.")
        if not basis.basis_id:
            raise ValueError("basis.basis_id must be non-empty.")

        step_key = (session_id, step_id)
        if step_key in self._basis_by_step:
            raise ValueError("Duplicate session_id + step_id.")
        if basis.basis_id in self._basis_by_id:
            raise ValueError("Duplicate basis_id.")

        self._basis_by_step[step_key] = basis
        self._basis_by_id[basis.basis_id] = basis

    def load_finalized_basis(self, session_id: str, step_id: str) -> AuthorizationBasis | None:
        return self._basis_by_step.get((session_id, step_id))

    def load_basis_by_id(self, basis_id: str) -> AuthorizationBasis | None:
        return self._basis_by_id.get(basis_id)

    def has_step(self, session_id: str, step_id: str) -> bool:
        return (session_id, step_id) in self._basis_by_step

    def has_basis(self, basis_id: str) -> bool:
        return basis_id in self._basis_by_id
