import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.optional

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def gen_mod():
    spec = importlib.util.spec_from_file_location(
        "rac_generate_validation_tables",
        REPO / "scripts" / "paper_optional" / "generate_validation_tables.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generate_validation_tables_writes_files(gen_mod, tmp_path: Path) -> None:
    written = gen_mod.generate_validation_tables(tmp_path, print_paths=False)
    names = {p.name for p in written}
    expected = {
        "controlled_trace_validation.md",
        "controlled_trace_validation.csv",
        "controlled_trace_validation.tex",
        "ablation_matrix.md",
        "ablation_matrix.csv",
        "ablation_matrix.tex",
        "ablation_summary.md",
        "ablation_summary.csv",
        "ablation_summary.tex",
        "ablation_summary.json",
    }
    assert expected <= names

    cv_md = (tmp_path / "controlled_trace_validation.md").read_text(encoding="utf-8")
    am_md = (tmp_path / "ablation_matrix.md").read_text(encoding="utf-8")
    su_md = (tmp_path / "ablation_summary.md").read_text(encoding="utf-8")
    assert len(cv_md) > 0
    assert len(am_md) > 0
    assert len(su_md) > 0

    assert "Benign" in cv_md
    assert "Action escalation" in cv_md
    assert "full_rac" in am_md or "Full RAC" in am_md

    for base in (
        "controlled_trace_validation",
        "ablation_matrix",
        "ablation_summary",
    ):
        tex = (tmp_path / f"{base}.tex").read_text(encoding="utf-8")
        assert "\\begin{tabular}" in tex
