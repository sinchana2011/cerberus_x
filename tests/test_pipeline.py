<<<<<<< HEAD
import json

import pytest

import pipeline
from core.graph_engine import EvidenceGraph
from core.schemas import AnalysisResult, AnswerStatus, ClaimStatus, ConflictType
from generate_demo_data import generate
from pipeline import load_result, run_pipeline


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo")
    out = generate(root)
    result = run_pipeline(out["cases"], output_dir=root / "out", enable_ocr=False)
    truth = json.loads(out["ground_truth"].read_text(encoding="utf-8"))
    questions = json.loads(out["questions"].read_text(encoding="utf-8"))
    return result, truth, questions, root


def _types_by_file(result):
    docs = {d.id: d.filename for d in result.analysis.documents}
    claims = {c.id: c for c in result.analysis.claims}
    types: dict[str, set] = {name: set() for name in docs.values()}
    for cf in result.analysis.conflicts:
        for cid in cf.claim_ids:
            types[docs[claims[cid].source_id]].add(cf.conflict_type.value)
    return types


def test_demo_cases_match_ground_truth(demo):
    result, truth, _q, _root = demo
    types = _types_by_file(result)
    for case in truth["cases"]:
        found = types[case["file"]]
        for expected in case.get("expect_conflicts", []):
            assert expected in found, (case["file"], expected, found)
        for forbidden in case.get("expect_not", []):
            assert forbidden not in found, (case["file"], forbidden, found)
        if case.get("expect_duplicate"):
            assert "duplicate" in found
        if case.get("expect_compatible_different_time"):
            assert "compatible_different_time" in found
        if "expect_alias_merge" in case:
            canonical, alias = case["expect_alias_merge"]
            entity = next(e for e in result.analysis.entities if e.canonical_name == canonical)
            assert alias in entity.aliases


def test_demo_questions_match_ground_truth(demo):
    result, truth, questions, _root = demo
    text_by_id = {q["id"]: q["question"] for q in questions}
    for expected in truth["questions"]:
        answer = result.ask(text_by_id[expected["id"]])
        assert answer.status.value == expected["expected_status"], (expected["id"], answer)
        for needle in expected["must_mention"]:
            assert needle in answer.answer_text, (expected["id"], needle, answer.answer_text)
        for needle in expected.get("must_not_state_as_fact", []):
            assert needle not in answer.answer_text
        for needle in expected.get("must_not_state_as_current", []):
            assert needle not in answer.answer_text.split("Earlier")[0]


def test_hidden_pdf_claim_stays_visible_but_is_never_verified(demo):
    result, _t, _q, _root = demo
    suspicious = result.suspicious_claims()
    assert suspicious and all(c.status == ClaimStatus.SUSPICIOUS for c in suspicious)
    assert any(c.value == "100" for c in suspicious)
    assert not any(c.is_verified for c in suspicious)
    report = next(r for r in result.file_reports if r.filename.endswith(".pdf"))
    assert report.suspicious and "Ignore all previous instructions" in report.suspicious[0].text
    assert result.graph.summary()["suspicious_claims"] == len(suspicious)


def test_results_are_saved_locally_and_reload(demo):
    result, _t, _q, root = demo
    out = root / "out"
    for name in ("analysis.json", "evidence_graph.json", "file_reports.json"):
        assert (out / name).exists()
    reloaded = AnalysisResult.load_json(out / "analysis.json")
    assert len(reloaded.claims) == len(result.analysis.claims)
    assert EvidenceGraph.load_json(out / "evidence_graph.json").summary()["claims"] == len(
        result.analysis.claims)
    again = load_result(out)
    assert again.ask("Who is the CFO of Northwind Logistics?").status == \
        AnswerStatus.INSUFFICIENT_EVIDENCE


def test_a_failing_file_does_not_stop_the_run(tmp_path):
    good = tmp_path / "note.txt"
    good.write_text("Date: 2026-03-12\nX dispatched 85 units on Shipment SH-5.\n", encoding="utf-8")
    bad_type = tmp_path / "report.docx"
    bad_type.write_bytes(b"PK")
    result = run_pipeline([tmp_path / "missing.txt", bad_type, good], output_dir=tmp_path / "o")
    assert [r.status for r in result.file_reports] == ["failed", "failed", "ok"]
    assert len(result.analysis.documents) == 3 and len(result.analysis.claims) == 1
    assert any("not found" in w.lower() for w in result.analysis.warnings)
    assert any("Unsupported" in w for w in result.analysis.warnings)


def test_an_extractor_crash_is_contained(tmp_path, monkeypatch):
    good = tmp_path / "ok.txt"
    good.write_text("X dispatched 5 units on Shipment SH-9.\n", encoding="utf-8")
    boom = tmp_path / "boom.txt"
    boom.write_text("anything", encoding="utf-8")
    real = pipeline.extract_file

    def flaky(path, **kw):
        if path.name == "boom.txt":
            raise RuntimeError("disk exploded")
        return real(path, **kw)

    monkeypatch.setattr(pipeline, "extract_file", flaky)
    result = run_pipeline([boom, good], output_dir=tmp_path / "o")
    assert [r.status for r in result.file_reports] == ["failed", "ok"]
    assert "disk exploded" in result.file_reports[0].error


def test_identical_files_are_not_reprocessed(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("X dispatched 5 units on Shipment SH-9.\n", encoding="utf-8")
    b = tmp_path / "copy_of_a.txt"
    b.write_text(a.read_text(encoding="utf-8"), encoding="utf-8")
    result = run_pipeline([a, b], output_dir=tmp_path / "o")
    assert [r.status for r in result.file_reports] == ["ok", "duplicate"]
    assert len(result.analysis.claims) == 1
    assert result.analysis.documents[1].duplicate_of == result.analysis.documents[0].id


def test_multiple_files_share_entities(tmp_path):
    one = tmp_path / "1.txt"
    one.write_text("Date: 2026-03-01\nA ordered 100 units on Purchase Order PO-1.\n", encoding="utf-8")
    two = tmp_path / "2.txt"
    two.write_text("Date: 2026-03-05\nB dispatched 85 units on Purchase Order PO-1.\n", encoding="utf-8")
    result = run_pipeline([one, two], output_dir=tmp_path / "o")
    assert len(result.analysis.entities) == 1 and len(result.analysis.claims) == 2
    assert [c.conflict_type for c in result.analysis.conflicts] == [ConflictType.WORKFLOW_STAGE]
    assert result.twin().history(result.analysis.entities[0].id)


def test_empty_input_and_unwritable_output_are_safe(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    result = run_pipeline([], output_dir=blocker / "sub")
    assert result.analysis.claims == [] and result.file_reports == []
    assert any("No evidence files" in w for w in result.analysis.warnings)
    assert any("Could not save" in w for w in result.analysis.warnings)
    assert result.ask("Who is the CEO of Anyone?").status == AnswerStatus.INSUFFICIENT_EVIDENCE
=======
"""Integration tests for the CERBERUS-X pipeline."""

from pathlib import Path

from pipeline import run_pipeline


def test_pipeline_processes_demo_files():

    root = Path(__file__).resolve().parents[1]
    demo_dir = root / "demo_data"

    files = [
        demo_dir / "case1_quantity_conflict.csv",
        demo_dir / "case2_order_vs_dispatch.txt",
        demo_dir / "case3_leadership.txt",
        demo_dir / "case4_hidden_instruction.pdf",
        demo_dir / "case5_timeline.txt"
    ]

    if not all(path.exists() for path in files):
        return

    result = run_pipeline(files)

    assert len(result.documents) == 5
    assert len(result.claims) > 0


def test_pipeline_does_not_read_ground_truth():

    root = Path(__file__).resolve().parents[1]

    demo_dir = root / "demo_data"

    assert not (demo_dir / "expected.json").exists()
>>>>>>> 4682e39edabba11574378524c8a1f84a103cb8cf
