<<<<<<< HEAD
"""Lightweight Digital Twin: an entity's known states over time.

Built from the evidence graph. Every state keeps its claim id, source filename,
locator, timestamp, reliability and status (verified / disputed / suspicious ...).
The twin never treats the newest claim as automatically true: ``current_states``
returns the latest *known* state per attribute and returns every disputed state
together when an attribute is disputed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from core.graph_engine import EvidenceGraph
from core.schemas import Claim, ClaimStatus, TwinState, WorkflowStage

_EXCLUDED_FROM_CURRENT = {ClaimStatus.SUSPICIOUS, ClaimStatus.DUPLICATE, ClaimStatus.SUPERSEDED}


def attribute_label(claim: Claim) -> str:
    """Attribute name shown in the twin, e.g. ``quantity (dispatched)`` or ``role:ceo``."""
    if claim.predicate == "quantity" and claim.stage != WorkflowStage.UNKNOWN:
        return f"quantity ({claim.stage.value})"
    return claim.predicate


def _is_state(attribute: str) -> bool:
    return attribute.startswith("role:") or attribute == "status"


def _claim_key(claim: Claim) -> tuple:
    return (claim.event_time is None, claim.event_time or datetime.min, claim.id)


def _state_key(state: TwinState) -> tuple:
    return (state.valid_from is None, state.valid_from or datetime.min, state.attribute,
            state.claim_id)


class DigitalTwin:
    """Query an entity's chronological state history."""

    def __init__(self, graph: EvidenceGraph) -> None:
        self.graph = graph

    def entity_ids(self) -> list[str]:
        return [e.id for e in self.graph.entities()]

    def history(self, entity_id: str, attribute: Optional[str] = None,
                include_suspicious: bool = True) -> list[TwinState]:
        """All known states, oldest first (undated last). Empty for unknown entities."""
        claims = self.graph.claims_about(entity_id, include_suspicious=include_suspicious)
        if not claims:
            return []
        entity = self.graph.get_entity(entity_id)
        name = entity.canonical_name if entity else claims[0].entity_name
        by_attribute: dict[str, list[Claim]] = defaultdict(list)
        for claim in claims:
            by_attribute[attribute_label(claim)].append(claim)
        states: list[TwinState] = []
        for attr, items in by_attribute.items():
            if attribute is not None and attr != attribute:
                continue
            ordered = sorted(items, key=_claim_key)
            for i, claim in enumerate(ordered):
                valid_to = None
                if _is_state(attr) and claim.is_usable and claim.event_time:
                    for later in ordered[i + 1:]:
                        if (later.is_usable and later.event_time
                                and later.event_time > claim.event_time
                                and later.value.strip().casefold() != claim.value.strip().casefold()):
                            valid_to = later.event_time
                            break
                doc = self.graph.get_document(claim.source_id)
                states.append(TwinState(
                    entity_id=entity_id, entity_name=name, attribute=attr, value=claim.value,
                    valid_from=claim.event_time, valid_to=valid_to, claim_id=claim.id,
                    source_id=claim.source_id, status=claim.status,
                    reliability=claim.reliability,
                    source_filename=doc.filename if doc else None, locator=claim.locator))
        return sorted(states, key=_state_key)

    def current_states(self, entity_id: str) -> list[TwinState]:
        """Latest known usable state per attribute (not a confirmed current truth).

        Suspicious, duplicate and superseded states are excluded. If an attribute has
        disputed states, all of them are returned and none is picked.
        """
        by_attribute: dict[str, list[TwinState]] = defaultdict(list)
        for state in self.history(entity_id, include_suspicious=False):
            if state.status not in _EXCLUDED_FROM_CURRENT:
                by_attribute[state.attribute].append(state)
        current: list[TwinState] = []
        for states in by_attribute.values():
            disputed = [s for s in states if s.status == ClaimStatus.DISPUTED]
            if disputed:
                current.extend(disputed)
                continue
            dated = [s for s in states if s.valid_from is not None]
            if dated:
                latest = max(s.valid_from for s in dated)
                current.extend(s for s in dated if s.valid_from == latest)
            else:
                current.extend(states)
        return sorted(current, key=_state_key)

    def build_all(self, include_suspicious: bool = True) -> list[TwinState]:
        """Histories of every entity, for storing in ``AnalysisResult.twin_states``."""
        states: list[TwinState] = []
        for entity_id in self.entity_ids():
            states.extend(self.history(entity_id, include_suspicious=include_suspicious))
        return states

    def rows(self, entity_id: str, include_suspicious: bool = True) -> list[dict]:
        """Flat dict rows (chronological) ready for ``st.dataframe``."""
        def stamp(value: Optional[datetime]) -> str:
            return value.strftime("%Y-%m-%d %H:%M") if value else "unknown"
        return [{
            "attribute": s.attribute, "value": s.value, "valid_from": stamp(s.valid_from),
            "valid_to": stamp(s.valid_to) if s.valid_to else "",
            "status": s.status.value, "reliability": s.reliability,
            "source": s.source_filename or s.source_id, "location": s.locator or "",
            "claim_id": s.claim_id,
        } for s in self.history(entity_id, include_suspicious=include_suspicious)]

    def summary(self, entity_id: str) -> dict:
        """Counts and current states for one entity (safe for unknown ids)."""
        history = self.history(entity_id)
        entity = self.graph.get_entity(entity_id)
        return {
            "entity_id": entity_id,
            "name": entity.canonical_name if entity else None,
            "states": len(history),
            "undated_states": sum(1 for s in history if s.valid_from is None),
            "disputed": sum(1 for s in history if s.status == ClaimStatus.DISPUTED),
            "suspicious": sum(1 for s in history if s.status == ClaimStatus.SUSPICIOUS),
            "current": self.current_states(entity_id),
=======
from __future__ import annotations

from collections import defaultdict

from core.schemas import (
    AnalysisResult,
    TwinState,
    ClaimStatus,
)


def build_twin_states(
    result: AnalysisResult,
) -> list[TwinState]:

    grouped = defaultdict(list)

    for claim in result.claims:

        if claim.suspicious:
            continue

        if claim.status == ClaimStatus.DUPLICATE:
            continue

        if not claim.entity_id:
            continue

        grouped[
            (claim.entity_id, claim.predicate)
        ].append(claim)

    states = []

    for (entity_id, attribute), claims in grouped.items():

        claims.sort(
            key=lambda c: (
                c.event_time is not None,
                c.event_time,
            )
        )

        for index, claim in enumerate(claims):

            valid_from = claim.event_time
            valid_to = None

            if index + 1 < len(claims):
                valid_to = claims[index + 1].event_time

            document = result.doc_by_id(claim.source_id)

            reliability = (
                document.reliability
                if document
                else 0.0
            )

            states.append(
                TwinState(
                    entity_id=entity_id,
                    entity_name=claim.entity_name,
                    attribute=attribute,
                    value=claim.value,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    claim_id=claim.id,
                    source_id=claim.source_id,
                    status=claim.status,
                    reliability=reliability,
                )
            )

    return states


class DigitalTwin:

    def __init__(self, result: AnalysisResult):

        self.result = result
        self.states = build_twin_states(result)

    def get_entity_history(self, entity_id: str):

        return [
            state for state in self.states
            if state.entity_id == entity_id
        ]

    def get_entity_state(
        self,
        entity_id: str,
        attribute: str,
        at_time=None,
    ):

        candidates = [
            state for state in self.states
            if state.entity_id == entity_id
            and state.attribute == attribute
        ]

        if at_time is not None:

            candidates = [
                state for state in candidates
                if (
                    state.valid_from is None
                    or state.valid_from <= at_time
                )
                and (
                    state.valid_to is None
                    or at_time < state.valid_to
                )
            ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda s: (
                s.valid_from is not None,
                s.valid_from,
            ),
            reverse=True,
        )

        return candidates[0]

    def summary(self):

        return {
            "total_states": len(self.states),
            "entities": len({
                state.entity_id
                for state in self.states
            }),
            "attributes": len({
                state.attribute
                for state in self.states
            }),
>>>>>>> 4682e39edabba11574378524c8a1f84a103cb8cf
        }