from core.digital_twin import DigitalTwin
from core.graph_engine import EvidenceGraph
from core.reasoner import analyze
from core.schemas import ClaimStatus, SourceType
from tests.helpers import T, hidden_flags, make_claim, make_doc, make_entity

ROLE = dict(entity_name="Northwind", entity_id="org1", predicate="role:ceo")


def _twin(claims, docs=None, entity=None):
    docs = docs or [make_doc("d1", "report.txt"), make_doc("d2", "press.txt")]
    analysed = analyze(claims, docs)
    g = EvidenceGraph()
    g.add_entity(entity or make_entity("org1", "Northwind", "organization"))
    for d in docs:
        g.add_document(d)
    for c in analysed.claims:
        g.add_claim(c)
    return DigitalTwin(g)


def _role_claims():
    return [make_claim("c2", value="Priya Nair", event_time=T("2026-02-15"), source_id="d2",
                       locator="line 4", **ROLE),
            make_claim("c1", value="Rahul Sharma", event_time=T("2024-06-01"), locator="line 2",
                       **ROLE)]


def test_history_is_chronological_and_closes_replaced_states():
    twin = _twin(_role_claims())
    history = twin.history("org1")
    assert [s.value for s in history] == ["Rahul Sharma", "Priya Nair"]
    assert history[0].valid_to == T("2026-02-15") and history[1].valid_to is None


def test_source_filename_locator_and_timestamp_are_preserved():
    state = _twin(_role_claims()).history("org1")[1]
    assert (state.source_filename, state.locator) == ("press.txt", "line 4")
    assert state.valid_from == T("2026-02-15") and state.claim_id == "c2"


def test_current_state_is_latest_known_and_excludes_superseded():
    current = _twin(_role_claims()).current_states("org1")
    assert [s.value for s in current] == ["Priya Nair"]


def test_missing_timestamps_sort_last_and_do_not_crash():
    twin = _twin([make_claim("c1", value="Anon Person", **ROLE),
                  make_claim("c2", value="Rahul Sharma", event_time=T("2024-06-01"), **ROLE)])
    assert twin.history("org1")[-1].valid_from is None
    assert twin.summary("org1")["undated_states"] == 1
    assert twin.rows("org1")[-1]["valid_from"] == "unknown"


def test_disputed_states_are_all_returned_and_none_is_chosen():
    twin = _twin([make_claim("c1", value="A B", event_time=T("2026-02-15"), **ROLE),
                  make_claim("c2", value="C D", event_time=T("2026-02-15"), source_id="d2",
                             **ROLE)])
    current = twin.current_states("org1")
    assert {s.status for s in current} == {ClaimStatus.DISPUTED} and len(current) == 2


def test_suspicious_state_is_visible_in_history_but_never_current():
    doc = make_doc("d1", "audit.pdf", SourceType.OFFICIAL_DOCUMENT, hidden_flags())
    twin = _twin([make_claim("c1", value="Rahul Sharma", event_time=T("2024-06-01"), **ROLE),
                  make_claim("c2", value="Mallory X", event_time=T("2026-01-01"),
                             suspicious=True, **ROLE)], docs=[doc])
    assert ClaimStatus.SUSPICIOUS in {s.status for s in twin.history("org1")}
    assert ClaimStatus.SUSPICIOUS not in {s.status for s in twin.history("org1",
                                                                        include_suspicious=False)}
    assert [s.value for s in twin.current_states("org1")] == ["Rahul Sharma"]


def test_unknown_or_empty_entity_returns_empty_results():
    twin = _twin(_role_claims())
    assert twin.history("nope") == [] and twin.current_states("nope") == []
    assert twin.rows("nope") == []
    assert twin.summary("nope")["states"] == 0 and twin.summary("nope")["name"] is None
    assert DigitalTwin(EvidenceGraph()).build_all() == []


def test_quantity_states_are_labelled_by_stage():
    from core.schemas import WorkflowStage
    twin = _twin([make_claim("c1", entity_id="org1", value="100", stage=WorkflowStage.ORDERED,
                             event_time=T("2026-03-01")),
                  make_claim("c2", entity_id="org1", value="85", stage=WorkflowStage.DISPATCHED,
                             event_time=T("2026-03-12"))])
    assert {s.attribute for s in twin.history("org1")} == {"quantity (ordered)",
                                                           "quantity (dispatched)"}
    assert len(twin.history("org1", attribute="quantity (ordered)")) == 1