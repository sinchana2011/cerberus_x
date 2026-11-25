from __future__ import annotations

from itertools import combinations
from typing import Optional

import networkx as nx

from core.schemas import (
    AnalysisResult,
    Claim,
    ClaimStatus,
    Conflict,
    ConflictType,
    Severity,
    WorkflowStage,
    make_id,
)


class EvidenceGraph:

    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_document(self, document):
        self.graph.add_node(
            document.id,
            node_type="document",
            label=document.filename,
            reliability=document.reliability,
        )

    def add_entity(self, entity):
        self.graph.add_node(
            entity.id,
            node_type="entity",
            label=entity.canonical_name,
            entity_type=entity.entity_type,
        )

    def add_claim(self, claim):
        self.graph.add_node(
            claim.id,
            node_type="claim",
            label=f"{claim.predicate}: {claim.value}",
            status=claim.status.value,
            suspicious=claim.suspicious,
        )

        self.graph.add_edge(
            claim.source_id,
            claim.id,
            relation="SUPPORTS",
        )

        if claim.entity_id:
            self.graph.add_edge(
                claim.id,
                claim.entity_id,
                relation="ABOUT",
            )

    def add_conflict(self, conflict):
        self.graph.add_node(
            conflict.id,
            node_type="conflict",
            label=conflict.conflict_type.value,
            severity=conflict.severity.value,
        )

        for claim_id in conflict.claim_ids:
            self.graph.add_edge(
                claim_id,
                conflict.id,
                relation="PARTICIPATES_IN",
            )

    def build(self, result: AnalysisResult):

        self.graph.clear()

        for document in result.documents:
            self.add_document(document)

        for entity in result.entities:
            self.add_entity(entity)

        for claim in result.claims:
            self.add_claim(claim)

        for conflict in result.conflicts:
            self.add_conflict(conflict)

        return self.graph

    def statistics(self):
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "documents": sum(
                1 for _, d in self.graph.nodes(data=True)
                if d.get("node_type") == "document"
            ),
            "entities": sum(
                1 for _, d in self.graph.nodes(data=True)
                if d.get("node_type") == "entity"
            ),
            "claims": sum(
                1 for _, d in self.graph.nodes(data=True)
                if d.get("node_type") == "claim"
            ),
            "conflicts": sum(
                1 for _, d in self.graph.nodes(data=True)
                if d.get("node_type") == "conflict"
            ),
        }


def _same_time(a, b):
    return (
        a.event_time is not None
        and b.event_time is not None
        and a.event_time == b.event_time
    )


def _same_value(a, b):
    return (
        a.value.strip().casefold()
        == b.value.strip().casefold()
    )


def detect_conflicts(claims: list[Claim]) -> list[Conflict]:

    conflicts = []
    seen = set()

    usable = [c for c in claims if not c.suspicious]

    for a, b in combinations(usable, 2):

        if not a.entity_id or a.entity_id != b.entity_id:
            continue

        if a.predicate != b.predicate:
            continue

        conflict_type: Optional[ConflictType] = None
        explanation = ""

        if _same_value(a, b):

            if (
                a.source_id == b.source_id
                and a.raw_text.strip() == b.raw_text.strip()
            ):
                conflict_type = ConflictType.DUPLICATE
                explanation = "Repeated evidence with identical content."

        elif (
            a.predicate == "quantity"
            and a.stage != b.stage
            and a.stage != WorkflowStage.UNKNOWN
            and b.stage != WorkflowStage.UNKNOWN
        ):
            conflict_type = ConflictType.WORKFLOW_STAGE
            explanation = (
                f"Different workflow stages: "
                f"{a.stage.value}={a.value}, "
                f"{b.stage.value}={b.value}. "
                "These values are not directly contradictory."
            )

        elif _same_time(a, b):
            if a.location and b.location and a.location != b.location:
                conflict_type = ConflictType.SAME_EVENT_CONFLICT
                explanation = (
                    f"The same entity is reported at "
                    f"{a.location} and {b.location} "
                    f"at the same time."
                )

            else:
                conflict_type = ConflictType.TRUE_CONFLICT
                explanation = (
                    f"Incompatible values for {a.predicate}: "
                    f"{a.value} versus {b.value}."
                )

        elif (
            a.event_time
            and b.event_time
            and a.event_time != b.event_time
        ):
            conflict_type = ConflictType.TEMPORAL_CHANGE
            explanation = (
                f"The recorded value changed over time: "
                f"{a.value} to {b.value}."
            )

        if conflict_type is None:
            continue

        pair = tuple(sorted([a.id, b.id]))
        key = (pair, conflict_type)

        if key in seen:
            continue

        seen.add(key)

        if conflict_type == ConflictType.DUPLICATE:
            a.status = ClaimStatus.DUPLICATE
            b.status = ClaimStatus.DUPLICATE

        elif conflict_type in (
            ConflictType.TRUE_CONFLICT,
            ConflictType.SAME_EVENT_CONFLICT,
        ):
            a.status = ClaimStatus.DISPUTED
            b.status = ClaimStatus.DISPUTED

        elif conflict_type == ConflictType.TEMPORAL_CHANGE:
            older, newer = sorted(
                [a, b],
                key=lambda c: c.event_time or c.event_time.min
            )
            older.status = ClaimStatus.SUPERSEDED
            newer.status = ClaimStatus.VERIFIED

        else:
            if a.status == ClaimStatus.UNVERIFIED:
                a.status = ClaimStatus.VERIFIED
            if b.status == ClaimStatus.UNVERIFIED:
                b.status = ClaimStatus.VERIFIED

        conflicts.append(
            Conflict(
                id=make_id("conf", a.id, b.id, conflict_type.value),
                conflict_type=conflict_type,
                claim_ids=[a.id, b.id],
                entity_name=a.entity_name,
                predicate=a.predicate,
                explanation=explanation,
                severity=(
                    Severity.HIGH
                    if conflict_type in (
                        ConflictType.TRUE_CONFLICT,
                        ConflictType.SAME_EVENT_CONFLICT,
                    )
                    else Severity.MEDIUM
                ),
                needs_review=conflict_type != ConflictType.DUPLICATE,
            )
        )

    # Detect arrival-before-departure timelines.
    for entity_id in {c.entity_id for c in usable if c.entity_id}:

        entity_claims = [
            c for c in usable
            if c.entity_id == entity_id and c.event_time
        ]

        departures = [
            c for c in entity_claims
            if c.predicate == "departed"
        ]

        arrivals = [
            c for c in entity_claims
            if c.predicate == "arrived"
        ]

        for departure in departures:
            for arrival in arrivals:

                if arrival.event_time < departure.event_time:

                    key = tuple(sorted([departure.id, arrival.id]))

                    if key in seen:
                        continue

                    seen.add(key)

                    conflicts.append(
                        Conflict(
                            id=make_id(
                                "conf",
                                departure.id,
                                arrival.id,
                                "impossible_timeline",
                            ),
                            conflict_type=ConflictType.IMPOSSIBLE_TIMELINE,
                            claim_ids=[departure.id, arrival.id],
                            entity_name=departure.entity_name,
                            predicate="timeline",
                            explanation=(
                                "Arrival is recorded before departure."
                            ),
                            severity=Severity.HIGH,
                            needs_review=True,
                        )
                    )

                    departure.status = ClaimStatus.DISPUTED
                    arrival.status = ClaimStatus.DISPUTED

    return conflicts