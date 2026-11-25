import pytest

from core.entity_resolver import (EntityResolver, MatchDecision, ResolverConfig,
                                  normalize_name)


def test_normalize_name_basics():
    assert normalize_name("  Northwind  Logistics Pvt. Ltd. ") == "northwind logistics"
    assert normalize_name("Dr. Meera Das") == "meera das"
    assert normalize_name("Shipment SH-1042") == "shipment sh-1042"
    assert normalize_name("Café Ünï") == "cafe uni"


def test_normalize_name_preserves_non_latin_scripts():
    assert normalize_name("राहुल शर्मा") == "राहुल शर्मा"


def test_exact_name_matching():
    r = EntityResolver()
    first = r.resolve("Rahul Sharma", "person")
    second = r.resolve("rahul sharma", "person")
    assert first.decision == MatchDecision.NEW
    assert second.decision == MatchDecision.EXACT
    assert second.entity_id == first.entity_id and second.confidence == 1.0
    assert len(r.entities) == 1


def test_company_suffix_variants_merge_after_normalisation():
    r = EntityResolver()
    a = r.resolve("Northwind Logistics", "organization")
    b = r.resolve("Northwind Logistics Pvt Ltd", "organization")
    assert b.decision == MatchDecision.NORMALIZED and b.entity_id == a.entity_id
    assert "Northwind Logistics Pvt Ltd" in r.entities[0].aliases


def test_similar_name_with_typo_matches_with_confidence():
    r = EntityResolver()
    a = r.resolve("Northwind Logistics", "organization")
    b = r.resolve("Northwnd Logistics", "organization")
    assert b.decision == MatchDecision.FUZZY and b.entity_id == a.entity_id
    assert b.confidence >= 0.9 and "similarity" in b.explanation


def test_alias_resolution():
    r = EntityResolver()
    entity = r.add_entity("Priya Nair", "person", aliases=["The CEO"])
    res = r.resolve("the ceo", "person")
    assert res.decision == MatchDecision.ALIAS
    assert res.entity_id == entity.id and res.confidence == 1.0


def test_initial_matches_full_name_for_people():
    r = EntityResolver()
    full = r.resolve("Rahul Sharma", "person")
    short = r.resolve("R. Sharma", "person")
    assert short.decision == MatchDecision.INITIAL and short.entity_id == full.entity_id
    assert "initial" in short.explanation
    assert "R. Sharma" in r.entities[0].aliases


def test_ambiguous_name_is_kept_separate_by_default():
    r = EntityResolver()
    rahul = r.resolve("Rahul Sharma", "person")
    ravi = r.resolve("Ravi Sharma", "person")
    res = r.resolve("R. Sharma", "person")
    assert res.decision == MatchDecision.AMBIGUOUS and res.needs_review
    assert res.entity_id not in (rahul.entity_id, ravi.entity_id)
    assert {c.entity_id for c in res.candidates} == {rahul.entity_id, ravi.entity_id}
    assert len(r.entities) == 3


def test_ambiguous_name_can_be_attached_by_configuration():
    r = EntityResolver(ResolverConfig(keep_ambiguous_separate=False))
    rahul = r.resolve("Rahul Sharma", "person")
    r.resolve("Ravi Sharma", "person")
    res = r.resolve("R. Sharma", "person")
    assert res.entity_id == rahul.entity_id and res.needs_review
    assert res.decision == MatchDecision.INITIAL


def test_unrelated_entities_remain_separate():
    r = EntityResolver()
    ids = {r.resolve(n).entity_id for n in
           ("Acme Corp", "Northwind Logistics", "Meera Das", "Rahul Sharma")}
    assert len(ids) == 4


def test_different_identifiers_never_merge():
    r = EntityResolver()
    a = r.resolve("Shipment SH-1042")
    b = r.resolve("Shipment SH-1043")
    assert a.entity_id != b.entity_id and b.decision == MatchDecision.NEW
    c = r.resolve("Annual Report 2024")
    d = r.resolve("Annual Report 2026")
    assert c.entity_id != d.entity_id


def test_same_identifier_merges_even_with_different_wording():
    r = EntityResolver()
    a = r.resolve("Shipment SH-1042")
    b = r.resolve("SH-1042")
    assert b.decision == MatchDecision.IDENTIFIER and b.entity_id == a.entity_id


def test_conflicting_entity_types_do_not_merge():
    r = EntityResolver()
    a = r.resolve("Mercury", "organization")
    b = r.resolve("Mercury", "person")
    assert a.entity_id != b.entity_id and len(r.entities) == 2


def test_config_validation():
    with pytest.raises(ValueError):
        ResolverConfig(match_threshold=0.5, review_threshold=0.9)
    with pytest.raises(ValueError):
        ResolverConfig(match_threshold=1.5)


def test_find_does_not_change_state():
    r = EntityResolver()
    res = r.find("Nobody Here")
    assert res.decision == MatchDecision.NEW and res.entity_id is None
    assert r.entities == []


def test_empty_name_is_rejected():
    r = EntityResolver()
    with pytest.raises(ValueError):
        r.resolve("   ")
    with pytest.raises(ValueError):
        r.resolve("...")


def test_alias_belonging_to_another_entity_is_rejected():
    r = EntityResolver()
    r.add_entity("Rahul Sharma", "person")
    priya = r.add_entity("Priya Nair", "person")
    with pytest.raises(ValueError):
        r.add_alias(priya.id, "Rahul Sharma")