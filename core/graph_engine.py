"""Evidence graph for CERBERUS-X, built on NetworkX.

Node kinds (ids are stable and reused across runs, so re-adding is idempotent):
    entity  id = Entity.id        source  id = SourceDocument.id
    claim   id = Claim.id

Edge relations (MultiDiGraph; the key is the relation, so repeats do not duplicate):
    claim  -ABOUT->  entity            source -ASSERTS->  claim   (filename + locator)
    claim  -CONTRADICTS-> claim        claim  -STAGE_DIFFERENCE-> claim
    later  -SUPERSEDES->  earlier      claim  -COMPATIBLE_WITH-> claim
    dup    -DUPLICATE_OF-> original

Pydantic objects are stored as JSON-safe dicts in the ``data`` node attribute, so
the graph exports to plain JSON without NetworkX version quirks.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Optional, Union

import networkx as nx

from core.schemas import AnalysisResult, Claim, Conflict, ConflictType, Entity, SourceDocument

KIND_ENTITY = "entity"
KIND_CLAIM = "claim"
KIND_SOURCE = "source"

REL_ABOUT = "ABOUT"
REL_ASSERTS = "ASSERTS"
REL_CONTRADICTS = "CONTRADICTS"
REL_STAGE = "STAGE_DIFFERENCE"
REL_SUPERSEDES = "SUPERSEDES"
REL_COMPATIBLE = "COMPATIBLE_WITH"
REL_DUPLICATE_OF = "DUPLICATE_OF"
_NON_CLAIM_RELATIONS = {REL_ABOUT, REL_ASSERTS}

_CONFLICT_RELATION = {
    ConflictType.TRUE_CONFLICT: REL_CONTRADICTS,
    ConflictType.SAME_EVENT_CONFLICT: REL_CONTRADICTS,
    ConflictType.IMPOSSIBLE_TIMELINE: REL_CONTRADICTS,
    ConflictType.WORKFLOW_STAGE: REL_STAGE,
    ConflictType.TEMPORAL_CHANGE: REL_SUPERSEDES,
    ConflictType.COMPATIBLE_DIFFERENT_TIME: REL_COMPATIBLE,
    ConflictType.DUPLICATE: REL_DUPLICATE_OF,
}


def _claim_sort_key(claim: Claim) -> tuple:
    return (claim.event_time is None, claim.event_time or datetime.min, claim.id)


class EvidenceGraph:
    """Entities, claims and sources with typed relationships."""

    def __init__(self) -> None:
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()

    # ---- adding evidence --------------------------------------------------- #
    def add_document(self, doc: SourceDocument) -> None:
        """Add (or update) a source node. The full text is not stored in the graph."""
        self.graph.add_node(doc.id, kind=KIND_SOURCE, label=doc.filename,
                            data=doc.model_dump(mode="json", exclude={"text"}))

    def add_entity(self, entity: Entity) -> None:
        """Add (or update) an entity node."""
        self.graph.add_node(entity.id, kind=KIND_ENTITY, label=entity.canonical_name,
                            data=entity.model_dump(mode="json"))

    def add_claim(self, claim: Claim) -> None:
        """Add (or update) a claim and link it to its entity and source."""
        self.graph.add_node(
            claim.id, kind=KIND_CLAIM, label=f"{claim.predicate}={claim.value}",
            status=claim.status.value, suspicious=claim.suspicious,
            data=claim.model_dump(mode="json"))
        if claim.entity_id:
            if claim.entity_id not in self.graph:
                self.add_entity(Entity(id=claim.entity_id, canonical_name=claim.entity_name))
            self.graph.add_edge(claim.id, claim.entity_id, key=REL_ABOUT, relation=REL_ABOUT)
        if claim.source_id not in self.graph:
            self.graph.add_node(claim.source_id, kind=KIND_SOURCE, label=claim.source_id,
                                data={"id": claim.source_id, "filename": claim.source_id,
                                      "file_type": "unknown", "sha256": ""})
        document = self.get_document(claim.source_id)
        self.graph.add_edge(
            claim.source_id, claim.id, key=REL_ASSERTS, relation=REL_ASSERTS,
            locator=claim.locator, source_label=claim.source_label,
            filename=document.filename if document else claim.source_id)

    def add_conflict(self, conflict: Conflict) -> None:
        """Add claim-to-claim edges for a conflict (all claim pairs it names)."""
        relation = _CONFLICT_RELATION[conflict.conflict_type]
        present = [cid for cid in conflict.claim_ids if cid in self.graph]
        for a, b in combinations(present, 2):
            src, dst = (b, a) if relation in (REL_SUPERSEDES, REL_DUPLICATE_OF) else (a, b)
            self.graph.add_edge(
                src, dst, key=f"{relation}:{conflict.id}", relation=relation,
                conflict_id=conflict.id, conflict_type=conflict.conflict_type.value,
                severity=conflict.severity.value, explanation=conflict.explanation)

    def add_analysis(self, result: AnalysisResult) -> None:
        """Add everything in an ``AnalysisResult`` (idempotent)."""
        for entity in result.entities:
            self.add_entity(entity)
        for doc in result.documents:
            self.add_document(doc)
        for claim in result.claims:
            self.add_claim(claim)
        for conflict in result.conflicts:
            self.add_conflict(conflict)

    @classmethod
    def from_analysis(cls, result: AnalysisResult) -> "EvidenceGraph":
        graph = cls()
        graph.add_analysis(result)
        return graph

    # ---- retrieval --------------------------------------------------------- #
    def _nodes_of(self, kind: str) -> list[str]:
        return [n for n, a in self.graph.nodes(data=True) if a.get("kind") == kind]

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        if claim_id not in self.graph or self.graph.nodes[claim_id].get("kind") != KIND_CLAIM:
            return None
        return Claim.model_validate(self.graph.nodes[claim_id]["data"])

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        if entity_id not in self.graph or self.graph.nodes[entity_id].get("kind") != KIND_ENTITY:
            return None
        return Entity.model_validate(self.graph.nodes[entity_id]["data"])

    def get_document(self, doc_id: str) -> Optional[SourceDocument]:
        if doc_id not in self.graph or self.graph.nodes[doc_id].get("kind") != KIND_SOURCE:
            return None
        try:
            return SourceDocument.model_validate(self.graph.nodes[doc_id]["data"])
        except Exception:
            return None

    def entities(self) -> list[Entity]:
        return [e for e in (self.get_entity(n) for n in self._nodes_of(KIND_ENTITY)) if e]

    def documents(self) -> list[SourceDocument]:
        return [d for d in (self.get_document(n) for n in self._nodes_of(KIND_SOURCE)) if d]

    def all_claims(self, include_suspicious: bool = True) -> list[Claim]:
        claims = [c for c in (self.get_claim(n) for n in self._nodes_of(KIND_CLAIM)) if c]
        return [c for c in claims if include_suspicious or not c.suspicious]

    def claims_about(self, entity_id: str, include_suspicious: bool = True) -> list[Claim]:
        """Claims whose subject is ``entity_id``, oldest first (undated last)."""
        if entity_id not in self.graph:
            return []
        found: list[Claim] = []
        for src, _dst, _key, attrs in self.graph.in_edges(entity_id, keys=True, data=True):
            if attrs.get("relation") != REL_ABOUT:
                continue
            claim = self.get_claim(src)
            if claim and (include_suspicious or not claim.suspicious):
                found.append(claim)
        return sorted(found, key=_claim_sort_key)

    def sources_for_claim(self, claim_id: str) -> list[SourceDocument]:
        """Documents that assert the claim."""
        if claim_id not in self.graph:
            return []
        docs = []
        for src, _dst, _key, attrs in self.graph.in_edges(claim_id, keys=True, data=True):
            if attrs.get("relation") == REL_ASSERTS:
                doc = self.get_document(src)
                if doc:
                    docs.append(doc)
        return docs

    def related_claims(self, claim_id: str) -> list[tuple[str, str]]:
        """``(relation, other_claim_id)`` for every claim-to-claim edge touching the claim."""
        if claim_id not in self.graph:
            return []
        out: list[tuple[str, str]] = []
        for _u, v, _k, a in self.graph.out_edges(claim_id, keys=True, data=True):
            if a.get("relation") not in _NON_CLAIM_RELATIONS:
                out.append((a["relation"], v))
        for u, _v, _k, a in self.graph.in_edges(claim_id, keys=True, data=True):
            if a.get("relation") not in _NON_CLAIM_RELATIONS:
                out.append((a["relation"], u))
        return out

    # ---- summary / export -------------------------------------------------- #
    def summary(self) -> dict:
        """Counts and highlights, ready for display."""
        kinds = Counter(a.get("kind") for _n, a in self.graph.nodes(data=True))
        relations = Counter(a.get("relation") for _u, _v, a in self.graph.edges(data=True))
        statuses = Counter(a.get("status") for _n, a in self.graph.nodes(data=True)
                           if a.get("kind") == KIND_CLAIM)
        conflicts: dict[str, str] = {}
        for _u, _v, a in self.graph.edges(data=True):
            if a.get("conflict_id"):
                conflicts[a["conflict_id"]] = a.get("conflict_type", "")
        per_entity = []
        for node in self._nodes_of(KIND_ENTITY):
            count = sum(1 for _s, _d, a in self.graph.in_edges(node, data=True)
                        if a.get("relation") == REL_ABOUT)
            per_entity.append({"entity_id": node, "name": self.graph.nodes[node]["label"],
                               "claims": count})
        per_entity.sort(key=lambda r: (-r["claims"], r["name"]))
        return {
            "nodes": self.graph.number_of_nodes(), "edges": self.graph.number_of_edges(),
            "entities": kinds.get(KIND_ENTITY, 0), "claims": kinds.get(KIND_CLAIM, 0),
            "sources": kinds.get(KIND_SOURCE, 0),
            "suspicious_claims": sum(1 for _n, a in self.graph.nodes(data=True)
                                     if a.get("kind") == KIND_CLAIM and a.get("suspicious")),
            "claims_by_status": dict(statuses), "relations": dict(relations),
            "conflicts_by_type": dict(Counter(conflicts.values())),
            "top_entities": per_entity[:5],
        }

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "nodes": [{"id": n, **a} for n, a in self.graph.nodes(data=True)],
            "edges": [{"source": u, "target": v, "key": k, **a}
                      for u, v, k, a in self.graph.edges(keys=True, data=True)],
            "summary": self.summary(),
        }

    def save_json(self, path: Union[str, Path]) -> None:
        """Write the graph as UTF-8 JSON (creates parent folders)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Union[str, Path]) -> "EvidenceGraph":
        """Load a graph saved by ``save_json``; raises ``ValueError`` if invalid."""
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            graph = cls()
            for node in payload["nodes"]:
                attrs = dict(node)
                graph.graph.add_node(attrs.pop("id"), **attrs)
            for edge in payload["edges"]:
                attrs = dict(edge)
                graph.graph.add_edge(attrs.pop("source"), attrs.pop("target"),
                                     key=attrs.pop("key"), **attrs)
            return graph
        except Exception as exc:
            raise ValueError(f"Could not load graph from {path}: {exc}") from exc
