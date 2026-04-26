from rac_core.checker import ActionLattice


def test_read_to_summarize_allowed() -> None:
    lattice = ActionLattice()
    assert lattice.is_action_allowed("summarize", {"read"})


def test_read_to_derived_compute_allowed() -> None:
    lattice = ActionLattice()
    assert lattice.is_action_allowed("derived_compute", {"read"})


def test_read_to_write_blocked() -> None:
    lattice = ActionLattice()
    assert not lattice.is_action_allowed("write", {"read"})


def test_read_to_external_disclosure_blocked() -> None:
    lattice = ActionLattice()
    assert not lattice.is_action_allowed("external_disclosure", {"read"})


def test_summarize_to_external_disclosure_blocked() -> None:
    lattice = ActionLattice()
    assert not lattice.is_action_allowed("external_disclosure", {"summarize"})


def test_read_to_delete_blocked() -> None:
    lattice = ActionLattice()
    assert not lattice.is_action_allowed("delete", {"read"})


def test_external_disclosure_to_external_disclosure_allowed() -> None:
    lattice = ActionLattice()
    assert lattice.is_action_allowed("external_disclosure", {"external_disclosure"})
