"""Tests for the SQLite persistence layer (AnalysisRepository)."""

from pathlib import Path

from backend.database import AnalysisRepository
from pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_roundtrip_for_demo_analysis(tmp_path):
    db_path = tmp_path / "test_cerberus.db"
    repo = AnalysisRepository(db_path)
    repo.init_db()

    demo_dir = ROOT / "demo_data"
    files = [
        demo_dir / "case1_quantity_conflict.csv",
        demo_dir / "case2_order_vs_dispatch.txt",
        demo_dir / "case3_leadership.txt",
        demo_dir / "case4_hidden_instruction.pdf",
        demo_dir / "case5_timeline.txt",
    ]
    original = run_pipeline(files)

    summary = repo.save_analysis("anl_demo_1", original)
    assert summary["analysis_id"] == "anl_demo_1"
    assert summary["counts"]["documents"] == len(original.documents)
    assert summary["counts"]["entities"] == len(original.entities)
    assert summary["counts"]["claims"] == len(original.claims)
    assert summary["counts"]["conflicts"] == len(original.conflicts)
    assert summary["counts"]["twin_states"] == len(original.twin_states)

    loaded = repo.get_analysis_result("anl_demo_1")
    assert loaded is not None
    assert len(loaded.documents) == len(original.documents)
    assert len(loaded.entities) == len(original.entities)
    assert len(loaded.claims) == len(original.claims)
    assert len(loaded.conflicts) == len(original.conflicts)
    assert len(loaded.twin_states) == len(original.twin_states)
    assert loaded.warnings == original.warnings

    orig_pdf = next(d for d in original.documents if d.filename == "case4_hidden_instruction.pdf")
    loaded_pdf = next(d for d in loaded.documents if d.filename == "case4_hidden_instruction.pdf")
    assert loaded_pdf.is_suspicious == orig_pdf.is_suspicious
    assert loaded_pdf.reliability == orig_pdf.reliability
    assert len(loaded_pdf.flags) == len(orig_pdf.flags)


def test_sqlite_handles_missing_and_deleted_analysis(tmp_path):
    repo = AnalysisRepository(tmp_path / "test_cerberus.db")
    repo.init_db()

    assert repo.get_analysis_summary("nonexistent") is None
    assert repo.get_analysis_result("nonexistent") is None
    assert repo.delete_analysis("nonexistent") is False

    demo_csv = ROOT / "demo_data" / "case1_quantity_conflict.csv"
    result = run_pipeline([demo_csv])
    repo.save_analysis("anl_1", result)
    repo.save_analysis("anl_2", result)

    listed = repo.list_analyses()
    assert len(listed) == 2

    assert repo.delete_analysis("anl_1") is True
    assert repo.get_analysis_result("anl_1") is None
    assert repo.get_analysis_result("anl_2") is not None
