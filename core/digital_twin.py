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
        }