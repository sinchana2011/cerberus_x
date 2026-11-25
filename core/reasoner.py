from __future__ import annotations

from core.schemas import (
    AnalysisResult,
    Answer,
    AnswerStatus,
    Citation,
    ClaimStatus,
    ConflictType,
)


def _make_citation(claim, result):

    document = result.doc_by_id(claim.source_id)

    if document is None:
        return None

    return Citation(
        source_id=document.id,
        filename=document.filename,
        snippet=claim.raw_text[:300],
        locator=claim.locator,
        reliability=document.reliability,
    )


def _matches_question(claim, question):

    q = question.casefold()

    entity_terms = (
        claim.entity_name.casefold().split()
        + claim.value.casefold().split()
        + claim.predicate.casefold().split()
    )

    return any(
        term in q
        for term in entity_terms
        if len(term) > 2
    )


def answer_question(
    question: str,
    result: AnalysisResult,
) -> Answer:

    usable = [
        c for c in result.claims
        if not c.suspicious
        and c.status != ClaimStatus.DUPLICATE
    ]

    matches = [
        c for c in usable
        if _matches_question(c, question)
    ]

    if not matches:
        return Answer(
            question=question,
            status=AnswerStatus.INSUFFICIENT_EVIDENCE,
            answer_text=(
                "There is insufficient reliable evidence "
                "to answer this question."
            ),
            confidence=0.0,
        )

    matched_ids = {c.id for c in matches}

    related_conflicts = [
        conflict for conflict in result.conflicts
        if matched_ids.intersection(conflict.claim_ids)
    ]

    real_conflicts = [
        conflict for conflict in related_conflicts
        if conflict.conflict_type in (
            ConflictType.TRUE_CONFLICT,
            ConflictType.SAME_EVENT_CONFLICT,
            ConflictType.IMPOSSIBLE_TIMELINE,
        )
    ]

    citations = []

    for claim in matches:
        citation = _make_citation(claim, result)

        if citation and citation not in citations:
            citations.append(citation)

    if real_conflicts:

        details = []

        for claim in matches:
            details.append(
                f"{claim.value} "
                f"(source: {claim.source_label or claim.source_id})"
            )

        return Answer(
            question=question,
            status=AnswerStatus.CONFLICTING,
            answer_text=(
                "Conflicting evidence was found. "
                + "; ".join(details)
                + ". The system cannot safely select one value."
            ),
            confidence=0.5,
            citations=citations,
            conflict_ids=[c.id for c in real_conflicts],
            notes=[
                "Conflicting claims are presented without "
                "automatically selecting a winner."
            ],
        )

    matches.sort(
        key=lambda c: (
            c.event_time is not None,
            c.event_time,
        ),
        reverse=True,
    )

    latest = matches[0]

    if latest.status == ClaimStatus.SUSPICIOUS:
        return Answer(
            question=question,
            status=AnswerStatus.SUSPICIOUS_ONLY,
            answer_text=(
                "The available evidence is suspicious "
                "and cannot be used as a verified fact."
            ),
            citations=citations,
        )

    answer = (
        f"Based on the available evidence, "
        f"{latest.entity_name}: "
        f"{latest.predicate} = {latest.value}."
    )

    return Answer(
        question=question,
        status=AnswerStatus.ANSWERED,
        answer_text=answer,
        confidence=round(
            max(0.0, min(1.0, latest_confidence(result, latest))),
            2,
        ),
        citations=citations,
        notes=[
            "Answer generated using local rule-based reasoning."
        ],
    )


def latest_confidence(result, claim):

    document = result.doc_by_id(claim.source_id)

    if document is None:
        return 0.3

    if claim.status == ClaimStatus.VERIFIED:
        return document.reliability

    return document.reliability * 0.7


class EvidenceReasoner:

    def __init__(self, result: AnalysisResult):
        self.result = result

    def ask(self, question: str) -> Answer:
        return answer_question(question, self.result)

    def ask_many(self, questions: list[str]) -> list[Answer]:
        return [
            self.ask(question)
            for question in questions
        ]