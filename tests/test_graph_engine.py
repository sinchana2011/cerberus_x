from core.graph_engine import (EvidenceGraph, KIND_CLAIM, KIND_ENTITY, KIND_SOURCE,
                               REL_ABOUT, REL_ASSERTS, REL_CONTRADICTS)
from core.schemas import Conflict, ConflictType, Severity, WorkflowStage
from tests.helpers import make_claim, make_doc, make_entity

D = WorkflowStage.DISPATCHED


def _graph() -> EvidenceGraph:
    g = EvidenceGraph()
    g.add_document(make_doc("d1", "ops.csv"))
    g.add_entity(make_entity())
    g.add_claim(make_claim("c1", stage=D, locator="row 2", source_label="Warehouse"))
    return g


def test_nodes_and_relationships():
    g = _graph()
    assert g.graph.nodes["e1"]["kind"] == KIND_ENTITY
    assert g.graph.nodes["c1"]["kind"] == KIND_CLAIM
    assert g.graph.nodes["d1"]["kind"] == KIND_SOURCE
    assert g.graph.has_edge("c1", "e1", key=REL_ABOUT)
    assert g.graph.has_edge("d1", "c1", key=REL_ASSERTS)


def test_adding_the_same_evidence_twice_creates_no_duplicates():
    g = _graph()
    before = (g.graph.number_of_nodes(), g.graph.number_of_edges())
    g.add_document(make_doc("d1", "ops.csv"))
    g.add_entity(make_entity())
    g.add_claim(make_claim("c1", stage=D, locator="row 2", source_label="Warehouse"))
    assert (g.graph.number_of_nodes(), g.graph.number_of_edges()) == before


def test_exact_and_similar_claims_with_different_ids_stay_distinct():
    g = _graph()
    g.add_claim(make_claim("c2", stage=D, locator="row 4"))              # identical content
    g.add_claim(make_claim("c3", value="85.0", value_num=85.0, stage=D, locator="row 5"))
    assert {c.id for c in g.all_claims()} == {"c1", "c2", "c3"}


def test_claims_about_entity_and_suspicious_filter():
    g = _graph()
    g.add_claim(make_claim("c9", value="100", suspicious=True, locator="page 1, hidden text #1"))
    assert {c.id for c in g.claims_about("e1")} == {"c1", "c9"}
    assert [c.id for c in g.claims_about("e1", include_suspicious=False)] == ["c1"]
    assert g.claims_about("missing") == []


def test_source_filename_and_location_are_preserved():
    g = _graph()
    edge = g.graph.edges["d1", "c1", REL_ASSERTS]
    assert edge["filename"] == "ops.csv" and edge["locator"] == "row 2"
    assert edge["source_label"] == "Warehouse"
    assert [d.filename for d in g.sources_for_claim("c1")] == ["ops.csv"]


def test_conflict_adds_claim_to_claim_edges():
    g = _graph()
    g.add_claim(make_claim("c2", value="100", stage=D))
    g.add_conflict(Conflict(id="cfl_1", conflict_type=ConflictType.TRUE_CONFLICT,
                            claim_ids=["c1", "c2"], entity_name="Shipment SH-1",
                            predicate="quantity", explanation="85 vs 100",
                            severity=Severity.HIGH))
    assert g.graph.has_edge("c1", "c2", key=f"{REL_CONTRADICTS}:cfl_1")
    assert ("CONTRADICTS", "c2") in g.related_claims("c1")
    assert g.summary()["conflicts_by_type"] == {"true_conflict": 1}


def test_unknown_source_or_entity_does_not_crash():
    g = EvidenceGraph()
    g.add_claim(make_claim("c1", source_id="ghost", entity_id="ghost_ent"))
    assert g.get_claim("c1") is not None
    assert g.get_entity("ghost_ent").canonical_name == "Shipment SH-1"
    assert g.get_document("ghost") is not None
    assert g.get_claim("nope") is None


def test_summary_is_ui_ready():
    g = _graph()
    g.add_claim(make_claim("c9", suspicious=True))
    s = g.summary()
    assert s["entities"] == 1 and s["claims"] == 2 and s["sources"] == 1
    assert s["suspicious_claims"] == 1
    assert s["claims_by_status"]["suspicious"] == 1
    assert s["top_entities"][0] == {"entity_id": "e1", "name": "Shipment SH-1", "claims": 2}


def test_json_roundtrip(tmp_path):
    g = _graph()
    g.add_claim(make_claim("c2", value="100", stage=D))
    g.add_conflict(Conflict(id="cfl_1", conflict_type=ConflictType.TRUE_CONFLICT,
                            claim_ids=["c1", "c2"], entity_name="x", predicate="quantity",
                            explanation="e"))
    path = tmp_path / "out" / "graph.json"
    g.save_json(path)
    loaded = EvidenceGraph.load_json(path)
    assert loaded.graph.number_of_nodes() == g.graph.number_of_nodes()
    assert loaded.graph.number_of_edges() == g.graph.number_of_edges()
    assert loaded.get_claim("c2").value == "100"