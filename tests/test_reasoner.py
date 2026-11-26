from core.reasoner import ReasonerConfig, analyze, answer_question, claim_reliability
from core.schemas import (AnswerStatus, ClaimStatus, ConflictType, SourceType, WorkflowStage)
from tests.helpers import T, hidden_flags, make_claim, make_doc, make_entity

O, D, V = WorkflowStage.ORDERED, WorkflowStage.DISPATCHED, WorkflowStage.DELIVERED
DOCS = [make_doc("d1", "ops.csv"), make_doc("d2", "manifest.txt")]


def _types(result):
    return [c.conflict_type for c in result.conflicts]


def _status(result, claim_id):
    return next(c.status for c in result.claims if c.id == claim_id)


# ---- conflicts ------------------------------------------------------------ #
def test_quantity_conflict_for_the_same_event():
    r = analyze([make_claim("c1", value="85", stage=D, event_time=T("2026-03-10T14:00")),
                 make_claim("c2", value="100", stage=D, event_time=T("2026-03-10T15:30"),
                            source_id="d2")], DOCS)
    assert _types(r) == [ConflictType.TRUE_CONFLICT]
    assert r.conflicts[0].rule and "85" in r.conflicts[0].explanation
    assert _status(r, "c1") == _status(r, "c2") == ClaimStatus.DISPUTED


def test_same_stage_far_apart_is_not_a_contradiction():
    r = analyze([make_claim("c1", value="85", stage=D, event_time=T("2026-03-10T14:00")),
                 make_claim("c2", value="100", stage=D, event_time=T("2026-03-20T14:00"),
                            source_id="d2")], DOCS)
    assert _types(r) == [ConflictType.COMPATIBLE_DIFFERENT_TIME]
    assert not any(c.is_real_problem for c in r.conflicts)


def test_workflow_stage_difference_is_not_a_conflict():
    r = analyze([make_claim("c1", value="100", stage=O, event_time=T("2026-03-01")),
                 make_claim("c2", value="85", stage=D, event_time=T("2026-03-12"))], DOCS)
    assert _types(r) == [ConflictType.WORKFLOW_STAGE]
    assert not r.conflicts[0].needs_review
    assert _status(r, "c1") != ClaimStatus.DISPUTED and _status(r, "c2") != ClaimStatus.DISPUTED


def test_dispatching_more_than_ordered_is_flagged_for_review():
    r = analyze([make_claim("c1", value="85", stage=O, event_time=T("2026-03-01")),
                 make_claim("c2", value="100", stage=D, event_time=T("2026-03-12"))], DOCS)
    assert r.conflicts[0].conflict_type == ConflictType.WORKFLOW_STAGE
    assert r.conflicts[0].needs_review


def test_missing_timestamps_are_assumed_same_event_but_flagged():
    r = analyze([make_claim("c1", value="85", stage=D), make_claim("c2", value="100", stage=D,
                                                                      source_id="d2")], DOCS)
    assert r.conflicts[0].conflict_type == ConflictType.TRUE_CONFLICT
    assert r.conflicts[0].needs_review


def test_exact_and_similar_claims_from_one_source_are_duplicates():
    t = T("2026-03-10T14:00")
    r = analyze([make_claim("c1", stage=D, event_time=t, source_label="W"),
                 make_claim("c2", stage=D, event_time=t, source_label="W"),
                 make_claim("c3", value="85.0", value_num=85.0, stage=D, event_time=t,
                            source_label="W")], DOCS)
    assert sorted(_types(r)) == [ConflictType.DUPLICATE, ConflictType.DUPLICATE]
    assert _status(r, "c1") != ClaimStatus.DUPLICATE
    assert _status(r, "c2") == _status(r, "c3") == ClaimStatus.DUPLICATE


def test_same_claim_from_two_sources_is_corroboration_not_duplication():
    t = T("2026-03-10T14:00")
    r = analyze([make_claim("c1", stage=D, event_time=t),
                 make_claim("c2", stage=D, event_time=t, source_id="d2")], DOCS)
    assert r.conflicts == []
    assert _status(r, "c1") == _status(r, "c2") == ClaimStatus.VERIFIED


def test_leadership_change_is_a_temporal_change_not_a_conflict():
    kw = dict(entity_name="Northwind", entity_id="org1", predicate="role:ceo")
    r = analyze([make_claim("c1", value="Rahul Sharma", event_time=T("2024-06-01"), **kw),
                 make_claim("c2", value="Priya Nair", event_time=T("2026-02-15"),
                            source_id="d2", **kw)], DOCS)
    assert _types(r) == [ConflictType.TEMPORAL_CHANGE]
    assert _status(r, "c1") == ClaimStatus.SUPERSEDED
    assert _status(r, "c2") != ClaimStatus.DISPUTED


def test_different_leaders_at_the_same_moment_conflict():
    kw = dict(entity_name="Northwind", entity_id="org1", predicate="role:ceo",
              event_time=T("2026-02-15"))
    r = analyze([make_claim("c1", value="A B", **kw), make_claim("c2", value="C D", **kw)], DOCS)
    assert _types(r) == [ConflictType.TRUE_CONFLICT]


def test_undated_leaders_cannot_be_ordered_and_are_flagged():
    kw = dict(entity_name="Northwind", entity_id="org1", predicate="role:ceo")
    r = analyze([make_claim("c1", value="A B", **kw), make_claim("c2", value="C D", **kw)], DOCS)
    assert r.conflicts[0].conflict_type == ConflictType.TRUE_CONFLICT
    assert r.conflicts[0].needs_review


# ---- timelines -------------------------------------------------------------- #
def _truck(cid, pred, place, when):
    return make_claim(cid, entity_name="Truck TR-55", entity_id="t1", predicate=pred,
                      value=place, location=place, event_time=T(when))


def test_arrival_before_departure_is_an_impossible_timeline():
    r = analyze([_truck("c1", "departed", "Mumbai", "2026-04-02T10:00"),
                 _truck("c2", "arrived", "Pune", "2026-04-02T08:00")], DOCS)
    assert _types(r) == [ConflictType.IMPOSSIBLE_TIMELINE]
    assert _status(r, "c1") == _status(r, "c2") == ClaimStatus.DISPUTED


def test_a_normal_trip_has_no_conflict():
    r = analyze([_truck("c1", "departed", "Mumbai", "2026-04-02T08:00"),
                 _truck("c2", "arrived", "Pune", "2026-04-02T12:00")], DOCS)
    assert r.conflicts == []


def _person(cid, place, when):
    return make_claim(cid, entity_name="Meera Das", entity_id="p1", predicate="location",
                      value=place, location=place, event_time=T(when))


def test_same_person_in_two_places_at_different_times_is_compatible():
    r = analyze([_person("c1", "Pune", "2026-04-02T09:00"),
                 _person("c2", "Delhi", "2026-04-05T11:00")], DOCS)
    assert _types(r) == [ConflictType.COMPATIBLE_DIFFERENT_TIME]
    assert not r.conflicts[0].is_real_problem


def test_same_person_in_two_places_at_the_same_time_conflicts():
    r = analyze([_person("c1", "Pune", "2026-04-02T09:00"),
                 _person("c2", "Delhi", "2026-04-02T09:00")], DOCS)
    assert _types(r) == [ConflictType.SAME_EVENT_CONFLICT]


def test_two_cities_thirty_minutes_apart_is_implausible():
    r = analyze([_person("c1", "Pune", "2026-04-02T09:00"),
                 _person("c2", "Delhi", "2026-04-02T09:30")], DOCS)
    assert _types(r) == [ConflictType.IMPOSSIBLE_TIMELINE]


def test_a_later_workflow_stage_dated_before_an_earlier_one_is_impossible():
    r = analyze([make_claim("c1", value="100", stage=O, event_time=T("2026-03-10")),
                 make_claim("c2", value="100", stage=V, event_time=T("2026-03-01"))], DOCS)
    assert ConflictType.IMPOSSIBLE_TIMELINE in _types(r)


# ---- evidence safety --------------------------------------------------------- #
def test_suspicious_claims_are_visible_but_never_verified_or_used_in_rules():
    r = analyze([make_claim("c1", value="85", stage=D, event_time=T("2026-03-10T14:00")),
                 make_claim("c2", value="100", stage=D, event_time=T("2026-03-10T14:30"),
                            suspicious=True)], DOCS)
    assert r.conflicts == []
    bad = next(c for c in r.claims if c.id == "c2")
    assert bad.status == ClaimStatus.SUSPICIOUS and not bad.is_verified


def test_tainted_document_gives_unverified_status_and_lower_reliability():
    doc = make_doc("d1", "audit.pdf", SourceType.OFFICIAL_DOCUMENT, hidden_flags())
    visible = make_claim("c1", value="60", stage=V)
    hidden = make_claim("c2", value="100", stage=V, suspicious=True)
    r = analyze([visible, hidden], [doc])
    assert _status(r, "c1") == ClaimStatus.UNVERIFIED
    assert claim_reliability(visible, doc) == 0.65
    assert claim_reliability(hidden, doc) == 0.45


def test_reliability_does_not_resolve_a_conflict():
    pdf = make_doc("d1", "report.pdf", SourceType.OFFICIAL_DOCUMENT)
    note = make_doc("d2", "note.txt", SourceType.FREEFORM_NOTE)
    r = analyze([make_claim("c1", value="85", stage=D, event_time=T("2026-03-10T10:00")),
                 make_claim("c2", value="100", stage=D, event_time=T("2026-03-10T11:00"),
                            source_id="d2")], [pdf, note])
    assert _status(r, "c1") == _status(r, "c2") == ClaimStatus.DISPUTED


# ---- answers ------------------------------------------------------------------ #
ENT = [make_entity()]
Q_DISPATCHED = "How many units of Shipment SH-1 were dispatched?"


def _answer(question, claims, docs=DOCS, entities=ENT):
    r = analyze(claims, docs)
    return answer_question(question, r.claims, r.conflicts, docs, entities)


def test_conflicting_answer_cites_filenames_locations_and_claim_ids():
    a = _answer(Q_DISPATCHED, [
        make_claim("c1", value="85", stage=D, event_time=T("2026-03-10T14:00"), locator="row 2"),
        make_claim("c2", value="100", stage=D, event_time=T("2026-03-10T15:30"),
                   source_id="d2", locator="line 7")])
    assert a.status == AnswerStatus.CONFLICTING
    assert "85" in a.answer_text and "100" in a.answer_text
    assert {(c.claim_id, c.filename, c.locator) for c in a.citations} == {
        ("c1", "ops.csv", "row 2"), ("c2", "manifest.txt", "line 7")}
    assert a.conflict_ids and a.confidence <= 0.4
    assert any(n.startswith("Rule:") for n in a.notes)


def test_workflow_stage_answer_reports_both_stages_without_conflict():
    a = _answer("How many units of Shipment SH-1 were ordered, and how many dispatched?", [
        make_claim("c1", value="100", stage=O, event_time=T("2026-03-01")),
        make_claim("c2", value="85", stage=D, event_time=T("2026-03-12"))])
    assert a.status == AnswerStatus.ANSWERED
    assert "ordered 100" in a.answer_text and "dispatched 85" in a.answer_text
    assert any("not a contradiction" in n for n in a.notes)


def test_suspicious_claim_is_excluded_from_the_answer_text_and_notes():
    a = _answer("How many units of Shipment SH-1 were delivered?", [
        make_claim("c1", value="60", stage=V),
        make_claim("c2", value="100", stage=V, suspicious=True)])
    assert a.status == AnswerStatus.ANSWERED
    assert "60" in a.answer_text and "100" not in a.answer_text
    assert a.excluded_claim_ids == ["c2"]
    assert "100" not in " ".join(a.notes)


def test_only_suspicious_evidence_gives_suspicious_only_status():
    a = _answer("How many units of Shipment SH-1 were delivered?",
                [make_claim("c2", value="100", stage=V, suspicious=True)])
    assert a.status == AnswerStatus.SUSPICIOUS_ONLY
    assert a.confidence == 0.0 and a.citations == []


def test_unknown_entity_gives_insufficient_evidence():
    a = _answer("How many units of Shipment SH-999 were dispatched?",
                [make_claim("c1", stage=D)])
    assert a.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert a.answer_text.startswith("Insufficient evidence")


def test_missing_stage_gives_insufficient_evidence():
    a = _answer(Q_DISPATCHED, [make_claim("c1", value="100", stage=O)])
    assert a.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert "quantity" in a.answer_text


# ---- state questions ------------------------------------------------------------ #
ORG = [make_entity("org1", "Northwind Logistics Pvt Ltd", "organization")]
ROLE = dict(entity_name="Northwind Logistics", entity_id="org1", predicate="role:ceo")


def _role_claims(later_suspicious=False):
    return [make_claim("c1", value="Rahul Sharma", event_time=T("2024-06-01"), **ROLE),
            make_claim("c2", value="Priya Nair", event_time=T("2026-02-15"), source_id="d2",
                       suspicious=later_suspicious, **ROLE)]


def test_role_answer_reports_latest_known_state_and_history():
    a = _answer("Who is the CEO of Northwind Logistics?", _role_claims(), entities=ORG)
    assert a.status == AnswerStatus.ANSWERED
    assert "Priya Nair" in a.answer_text.split("Earlier")[0]
    assert "Rahul Sharma" in a.answer_text
    assert any("not a confirmed" in n for n in a.notes)


def test_role_answer_for_a_past_year_uses_evidence_from_that_time():
    a = _answer("Who was the CEO of Northwind Logistics in 2024?", _role_claims(), entities=ORG)
    assert a.status == AnswerStatus.ANSWERED
    assert "Rahul Sharma" in a.answer_text and "Priya Nair" not in a.answer_text
    assert any("later change" in n for n in a.notes)


def test_missing_role_gives_insufficient_evidence():
    a = _answer("Who is the CFO of Northwind Logistics?", _role_claims(), entities=ORG)
    assert a.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert a.answer_text.startswith("Insufficient evidence")


def test_a_newer_suspicious_claim_does_not_override_older_evidence():
    a = _answer("Who is the CEO of Northwind Logistics?", _role_claims(True), entities=ORG)
    assert "Rahul Sharma" in a.answer_text and "Priya Nair" not in a.answer_text
    assert a.excluded_claim_ids == ["c2"]


def test_corroboration_raises_evidence_strength():
    t = T("2026-03-10T14:00")
    one = _answer(Q_DISPATCHED, [make_claim("c1", stage=D, event_time=t)])
    two = _answer(Q_DISPATCHED, [make_claim("c1", stage=D, event_time=t),
                                 make_claim("c2", stage=D, event_time=t, source_id="d2")])
    assert two.confidence > one.confidence