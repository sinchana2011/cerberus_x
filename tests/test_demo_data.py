"""End-to-end validation of the CERBERUS-X pipeline against demo_ground_truth/expected.json."""

import json
from pathlib import Path

from core.reasoner import EvidenceReasoner
from core.schemas import ConflictType, SecurityFlagKind
from generate_demo_data import generate
from pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[1]


def _load_demo_inputs():
    demo_dir = ROOT / "demo_data"
    truth_path = ROOT / "demo_ground_truth" / "expected.json"
    questions_path = demo_dir / "demo_questions.json"

    files = [
        demo_dir / "case1_quantity_conflict.csv",
        demo_dir / "case2_order_vs_dispatch.txt",
        demo_dir / "case3_leadership.txt",
        demo_dir / "case4_hidden_instruction.pdf",
        demo_dir / "case5_timeline.txt",
    ]
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    expected = json.loads(truth_path.read_text(encoding="utf-8"))
    return files, questions, expected


def test_generate_demo_data_creates_expected_structure(tmp_path):
    out = generate(tmp_path)
    assert len(out["cases"]) == 5
    for path in out["cases"]:
        assert path.exists()
    assert out["bonus"].exists()
    assert out["questions"].exists()
    assert out["ground_truth"].exists()


def test_demo_cases_match_ground_truth():
    files, _, expected = _load_demo_inputs()
    result = run_pipeline(files)

    doc_by_name = {doc.filename: doc for doc in result.documents}
    assert set(doc_by_name) == {f.name for f in files}

    for case in expected["cases"]:
        doc = doc_by_name[case["file"]]
        doc_claim_ids = {c.id for c in result.claims if c.source_id == doc.id}
        doc_conflicts = [
            conf for conf in result.conflicts
            if doc_claim_ids.intersection(conf.claim_ids)
        ]
        conflict_types = {conf.conflict_type.value for conf in doc_conflicts}

        for expected_type in case.get("expect_conflicts", []):
            assert expected_type in conflict_types, (
                f"Case {case['case']} missing {expected_type}; got {conflict_types}"
            )

        for forbidden_type in case.get("expect_not", []):
            assert forbidden_type not in conflict_types, (
                f"Case {case['case']} unexpectedly produced {forbidden_type}"
            )

        if case.get("expect_duplicate"):
            assert ConflictType.DUPLICATE.value in conflict_types

        if case.get("expect_compatible_different_time"):
            assert ConflictType.COMPATIBLE_DIFFERENT_TIME.value in conflict_types

        if "expect_alias_merge" in case:
            expected_names = set(case["expect_alias_merge"])
            merged = any(
                expected_names.issubset({ent.canonical_name, *ent.aliases})
                for ent in result.entities
            )
            assert merged, (
                f"Expected alias merge {expected_names}; entities={result.entities}"
            )

        if case.get("expect_suspicious"):
            assert doc.is_suspicious
            assert SecurityFlagKind.HIDDEN_TEXT in {f.kind for f in doc.flags}
            snippet = case["suspicious_text_contains"]
            assert any(snippet in f.evidence for f in doc.flags)
            # Withheld text must never enter factual claims as non-suspicious.
            assert not any(
                snippet in c.raw_text and not c.suspicious
                for c in result.claims
            )


def test_demo_questions_match_ground_truth():
    files, questions, expected = _load_demo_inputs()
    result = run_pipeline(files)
    reasoner = EvidenceReasoner(result)

    expected_by_id = {q["id"]: q for q in expected["questions"]}
    for q in questions:
        spec = expected_by_id[q["id"]]
        ans = reasoner.ask(q["question"])

        assert ans.status.value == spec["expected_status"], (
            f"{q['id']} ({q['question']}): expected {spec['expected_status']}, "
            f"got {ans.status.value} ({ans.answer_text})"
        )

        for phrase in spec.get("must_mention", []):
            assert phrase.lower() in ans.answer_text.lower(), (
                f"{q['id']} answer missing '{phrase}': {ans.answer_text}"
            )

        current_clause = ans.answer_text.split("Earlier")[0]
        for forbidden in spec.get("must_not_state_as_current", []):
            assert forbidden.lower() not in current_clause.lower(), (
                f"{q['id']} improperly stated '{forbidden}' as current: {ans.answer_text}"
            )

        for forbidden in spec.get("must_not_state_as_fact", []):
            assert forbidden.lower() not in ans.answer_text.lower(), (
                f"{q['id']} leaked suspicious fact '{forbidden}': {ans.answer_text}"
            )

        if spec["expected_status"] != "insufficient_evidence":
            assert ans.citations, f"{q['id']} should include traceable citations"
