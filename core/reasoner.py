"""Deterministic, rule-based reasoning for CERBERUS-X (no LLM involved).

``analyze`` finds duplicates and conflicts and assigns claim statuses.
``answer_question`` answers from evidence only, with citations, a rule
explanation, an evidence-strength figure, or an explicit
"Insufficient evidence" response.

Principles:
  * Suspicious claims never enter any rule or answer; they are listed as excluded.
  * The newest claim is never assumed true; a later state is reported as a change.
  * Source reliability is an evidence-strength input, never proof of truth, and it
    never resolves a conflict.
  * Events that could have happened at different times are not contradictions.
  * "Verified" means uncontradicted evidence from a sufficiently reliable,
    untainted source; it does not mean true.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import combinations
from typing import Optional, Sequence

from core.entity_resolver import normalize_name
from core.schemas import (
    Answer, AnswerStatus, Citation, Claim, ClaimStatus, Conflict, ConflictType, Entity,
    SecurityFlagKind, Severity, SourceDocument, SourceType, WorkflowStage,
    compute_reliability, make_id,
)

STAGE_ORDER = {WorkflowStage.ORDERED: 0, WorkflowStage.DISPATCHED: 1,
               WorkflowStage.DELIVERED: 2, WorkflowStage.INVOICED: 3}
_ROLE_WORDS = ["managing director", "general manager", "chairperson", "chairman", "president",
               "ceo", "cfo", "cto", "coo", "director", "manager"]
_STAGE_QUESTION_WORDS = {
    "ordered": WorkflowStage.ORDERED, "dispatched": WorkflowStage.DISPATCHED,
    "shipped": WorkflowStage.DISPATCHED, "delivered": WorkflowStage.DELIVERED,
    "invoiced": WorkflowStage.INVOICED,
}
_FULL_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")


@dataclass(frozen=True)
class ReasonerConfig:
    """Thresholds for the rules."""
    same_event_window: timedelta = timedelta(hours=24)   # same-stage claims this close = same event
    same_instant: timedelta = timedelta(minutes=1)       # "at the same time"
    min_travel_gap: timedelta = timedelta(hours=1)       # different places closer than this = impossible
    min_verified_reliability: float = 0.50
    tainted_document_penalty: float = 0.15               # visible claims in a document with hidden/injected text


@dataclass
class Analysis:
    """Result of ``analyze``: updated claim copies plus all conflicts found."""
    claims: list[Claim] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _fmt_time(value: Optional[datetime]) -> str:
    if value is None:
        return "undated"
    if value.hour == 0 and value.minute == 0:
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d %H:%M")


def _fmt_qty(claim: Claim) -> str:
    if claim.value_num is None:
        return claim.value
    return f"{claim.value_num:g} {claim.unit or 'units'}"


def _val_key(claim: Claim):
    return round(claim.value_num, 6) if claim.value_num is not None else _norm(claim.value)


def _entity_key(claim: Claim) -> str:
    return claim.entity_id or "name:" + normalize_name(claim.entity_name)


def _source_key(claim: Claim) -> tuple[str, str]:
    return (claim.source_id, (claim.source_label or "").casefold())


def _time_key(claim: Claim) -> tuple:
    return (claim.event_time is None, claim.event_time or datetime.min, claim.id)


def _where(claim: Claim, docs: dict[str, SourceDocument]) -> str:
    doc = docs.get(claim.source_id)
    name = doc.filename if doc else claim.source_id
    where = f"{name}, {claim.locator}" if claim.locator else name
    return f"{claim.source_label} in {where}" if claim.source_label else where


def _what(claim: Claim) -> str:
    if claim.predicate == "quantity":
        stage = f"{claim.stage.value} " if claim.stage != WorkflowStage.UNKNOWN else ""
        return f"{stage}{_fmt_qty(claim)}"
    if claim.predicate in ("departed", "arrived"):
        return f"{claim.predicate} {claim.location or claim.value}"
    if claim.predicate == "location":
        return f"located in {claim.value}"
    return f"{claim.predicate}: {claim.value}"


def _describe(claim: Claim, docs: dict[str, SourceDocument]) -> str:
    return f"{_what(claim)} [{_fmt_time(claim.event_time)}; {_where(claim, docs)}]"


def _snippet(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _conflict(ctype: ConflictType, first: Claim, second: Claim, predicate: str,
              explanation: str, severity: Severity, rule: str,
              needs_review: bool = False) -> Conflict:
    ids = [first.id, second.id]
    return Conflict(id=make_id("cfl", ctype.value, *sorted(ids)), conflict_type=ctype,
                    claim_ids=ids, entity_name=first.entity_name, predicate=predicate,
                    explanation=explanation, severity=severity, needs_review=needs_review,
                    rule=rule)


def claim_reliability(claim: Claim, doc: Optional[SourceDocument],
                      config: Optional[ReasonerConfig] = None) -> float:
    """Source-based reliability for one claim.

    A suspicious claim inherits the document's full penalties. An ordinary visible
    claim in a tainted document only loses ``tainted_document_penalty`` (plus any
    low-OCR penalty), so the visible content is not penalised as heavily as the
    hidden content.
    """
    cfg = config or ReasonerConfig()
    if doc is None:
        return compute_reliability(SourceType.UNKNOWN, [])
    if claim.suspicious:
        return doc.reliability
    low_ocr = [f for f in doc.flags if f.kind == SecurityFlagKind.LOW_OCR_CONFIDENCE]
    score = compute_reliability(doc.source_type, low_ocr)
    if doc.is_suspicious:
        score -= cfg.tainted_document_penalty
    return round(max(0.0, min(1.0, score)), 2)


# --------------------------------------------------------------------------- #
# Conflict rules
# --------------------------------------------------------------------------- #
def _same_event(a: Claim, b: Claim, cfg: ReasonerConfig) -> tuple[bool, bool]:
    """Return ``(same_event, certain)``; undated claims are assumed the same event."""
    if a.event_time is None or b.event_time is None:
        return True, False
    return abs(a.event_time - b.event_time) <= cfg.same_event_window, True


def _quantity_rules(group: list[Claim], docs: dict, cfg: ReasonerConfig) -> list[Conflict]:
    quantities = [c for c in group if c.predicate == "quantity" and c.value_num is not None]
    out: list[Conflict] = []
    for a, b in combinations(quantities, 2):
        if abs(a.value_num - b.value_num) < 1e-9:
            continue
        if a.stage == b.stage:
            same, certain = _same_event(a, b, cfg)
            if same:
                note = "" if certain else (" Timestamps are missing, so both are assumed to "
                                           "describe the same event.")
                out.append(_conflict(
                    ConflictType.TRUE_CONFLICT, a, b, "quantity",
                    f"Different {a.stage.value} quantities were reported for the same event: "
                    f"{_fmt_qty(a)} ({_where(a, docs)}) vs {_fmt_qty(b)} ({_where(b, docs)}).{note}",
                    Severity.HIGH, "same entity + same workflow stage + different quantity "
                    "within the same-event window", needs_review=not certain))
            else:
                out.append(_conflict(
                    ConflictType.COMPATIBLE_DIFFERENT_TIME, a, b, "quantity",
                    f"{_fmt_qty(a)} ({_fmt_time(a.event_time)}) and {_fmt_qty(b)} "
                    f"({_fmt_time(b.event_time)}) were reported more than "
                    f"{cfg.same_event_window} apart for the same stage; they may be separate "
                    "events, so no contradiction is declared.",
                    Severity.LOW, "same stage but outside the same-event window"))
        elif a.stage in STAGE_ORDER and b.stage in STAGE_ORDER:
            early, late = (a, b) if STAGE_ORDER[a.stage] < STAGE_ORDER[b.stage] else (b, a)
            over = late.value_num > early.value_num
            text = (f"{_fmt_qty(early)} {early.stage.value} vs {_fmt_qty(late)} {late.stage.value}: "
                    "different workflow stages, not a contradiction.")
            if over:
                text += (f" However {late.stage.value} exceeds {early.stage.value}, which "
                         "needs review.")
            else:
                diff = early.value_num - late.value_num
                text += f" The {diff:g}-unit difference is consistent with partial fulfilment."
            out.append(_conflict(ConflictType.WORKFLOW_STAGE, early, late, "quantity", text,
                                 Severity.MEDIUM if over else Severity.LOW,
                                 "same entity, different workflow stages", needs_review=over))
    # Stage order: a later stage must not precede an earlier one.
    earliest: dict[WorkflowStage, Claim] = {}
    for c in quantities:
        if c.stage in STAGE_ORDER and c.event_time is not None:
            if c.stage not in earliest or c.event_time < earliest[c.stage].event_time:
                earliest[c.stage] = c
    for early_stage, late_stage in combinations(sorted(earliest, key=STAGE_ORDER.get), 2):
        early, late = earliest[early_stage], earliest[late_stage]
        if late.event_time < early.event_time:
            out.append(_conflict(
                ConflictType.IMPOSSIBLE_TIMELINE, early, late, "quantity",
                f"{late.stage.value.capitalize()} ({_fmt_time(late.event_time)}) is dated before "
                f"{early.stage.value} ({_fmt_time(early.event_time)}) for the same entity.",
                Severity.HIGH, "workflow stages must occur in order", needs_review=True))
    return out


def _state_rules(group: list[Claim], docs: dict, cfg: ReasonerConfig) -> list[Conflict]:
    by_predicate: dict[str, list[Claim]] = defaultdict(list)
    for c in group:
        if c.predicate.startswith("role:") or c.predicate == "status":
            by_predicate[c.predicate].append(c)
    out: list[Conflict] = []
    for predicate, items in by_predicate.items():
        for a, b in combinations(items, 2):
            if _norm(a.value) == _norm(b.value):
                continue
            if a.event_time is None or b.event_time is None:
                out.append(_conflict(
                    ConflictType.TRUE_CONFLICT, a, b, predicate,
                    f"{predicate} is reported as '{a.value}' ({_where(a, docs)}) and "
                    f"'{b.value}' ({_where(b, docs)}), but at least one claim is undated, so "
                    "a change over time cannot be established.",
                    Severity.MEDIUM, "state values that differ and cannot be ordered in time",
                    needs_review=True))
            elif abs(a.event_time - b.event_time) <= cfg.same_instant:
                out.append(_conflict(
                    ConflictType.TRUE_CONFLICT, a, b, predicate,
                    f"{predicate} is reported as '{a.value}' and '{b.value}' for the same "
                    f"moment ({_fmt_time(a.event_time)}).", Severity.HIGH,
                    "different state values at the same time"))
            else:
                early, late = sorted((a, b), key=lambda c: c.event_time)
                out.append(_conflict(
                    ConflictType.TEMPORAL_CHANGE, early, late, predicate,
                    f"{predicate} changed from '{early.value}' ({_fmt_time(early.event_time)}, "
                    f"{_where(early, docs)}) to '{late.value}' ({_fmt_time(late.event_time)}, "
                    f"{_where(late, docs)}). A change over time is not a contradiction; the "
                    "newer claim is not assumed true just because it is newer.",
                    Severity.LOW, "state values that differ at different times"))
    return out


def _location_rules(group: list[Claim], docs: dict, cfg: ReasonerConfig) -> list[Conflict]:
    places = [c for c in group if c.predicate == "location" and c.value.strip()]
    out: list[Conflict] = []
    for a, b in combinations(places, 2):
        if _norm(a.value) == _norm(b.value) or a.event_time is None or b.event_time is None:
            continue
        first, second = sorted((a, b), key=lambda c: c.event_time)
        gap = second.event_time - first.event_time
        pair = (f"{first.value} ({_fmt_time(first.event_time)}, {_where(first, docs)}) and "
                f"{second.value} ({_fmt_time(second.event_time)}, {_where(second, docs)})")
        if gap <= cfg.same_instant:
            out.append(_conflict(
                ConflictType.SAME_EVENT_CONFLICT, first, second, "location",
                f"{first.entity_name} is placed in two locations at the same time: {pair}.",
                Severity.HIGH, "one entity cannot be in two places at the same instant"))
        elif gap < cfg.min_travel_gap:
            out.append(_conflict(
                ConflictType.IMPOSSIBLE_TIMELINE, first, second, "location",
                f"{first.entity_name} is placed in two locations only {gap} apart: {pair}. "
                "Travel between them in that time is not plausible.",
                Severity.MEDIUM, "different places closer in time than the minimum travel gap",
                needs_review=True))
        else:
            out.append(_conflict(
                ConflictType.COMPATIBLE_DIFFERENT_TIME, first, second, "location",
                f"{first.entity_name} appears in {pair}. These are at different times and can "
                "both be true.", Severity.LOW, "different places at sufficiently different times"))
    return out


def _sequence_rules(group: list[Claim], docs: dict, cfg: ReasonerConfig) -> list[Conflict]:
    departures = [c for c in group if c.predicate == "departed" and c.event_time]
    arrivals = [c for c in group if c.predicate == "arrived" and c.event_time]
    out: list[Conflict] = []
    for dep in departures:
        for arr in arrivals:
            if arr.event_time >= dep.event_time:
                continue
            gap = dep.event_time - arr.event_time
            if gap <= cfg.same_event_window:
                out.append(_conflict(
                    ConflictType.IMPOSSIBLE_TIMELINE, arr, dep, "arrived/departed",
                    f"Arrival at {arr.location} ({_fmt_time(arr.event_time)}, {_where(arr, docs)}) "
                    f"is recorded before departure from {dep.location} "
                    f"({_fmt_time(dep.event_time)}, {_where(dep, docs)}); one trip cannot arrive "
                    "before it departs.", Severity.HIGH,
                    "arrival must not precede departure within the same-event window",
                    needs_review=True))
            else:
                out.append(_conflict(
                    ConflictType.COMPATIBLE_DIFFERENT_TIME, arr, dep, "arrived/departed",
                    f"Arrival ({_fmt_time(arr.event_time)}) precedes departure "
                    f"({_fmt_time(dep.event_time)}) by more than {cfg.same_event_window}; they may "
                    "belong to different trips.", Severity.LOW,
                    "arrival before departure but far apart in time"))
    return out


# --------------------------------------------------------------------------- #
# analyze
# --------------------------------------------------------------------------- #
def analyze(claims: Sequence[Claim], documents: Sequence[SourceDocument],
            config: Optional[ReasonerConfig] = None) -> Analysis:
    """Detect duplicates and conflicts and assign statuses. Inputs are not modified."""
    cfg = config or ReasonerConfig()
    docs = {d.id: d for d in documents}
    work = [c.model_copy(deep=True) for c in claims]
    for c in work:
        c.reliability = claim_reliability(c, docs.get(c.source_id), cfg)
        c.status = ClaimStatus.SUSPICIOUS if c.suspicious else ClaimStatus.UNVERIFIED

    conflicts: list[Conflict] = []

    # Same-source repeats are duplicates; the same claim from different sources is corroboration.
    first_seen: dict[tuple, Claim] = {}
    for c in work:
        if c.suspicious:
            continue
        key = (_entity_key(c), c.predicate, c.stage, _val_key(c), c.event_time,
               _norm(c.location or ""), _source_key(c))
        if key in first_seen:
            c.status = ClaimStatus.DUPLICATE
            conflicts.append(_conflict(
                ConflictType.DUPLICATE, first_seen[key], c, c.predicate,
                f"{_what(c)} repeats an earlier claim from the same source "
                f"({_where(first_seen[key], docs)}).", Severity.LOW,
                "identical claim repeated by the same source"))
        else:
            first_seen[key] = c

    usable = [c for c in work if c.is_usable]
    groups: dict[str, list[Claim]] = defaultdict(list)
    for c in usable:
        groups[_entity_key(c)].append(c)
    for group in groups.values():
        conflicts += _quantity_rules(group, docs, cfg)
        conflicts += _state_rules(group, docs, cfg)
        conflicts += _location_rules(group, docs, cfg)
        conflicts += _sequence_rules(group, docs, cfg)

    disputed = {i for cf in conflicts if cf.is_real_problem for i in cf.claim_ids}
    superseded = {cf.claim_ids[0] for cf in conflicts
                  if cf.conflict_type == ConflictType.TEMPORAL_CHANGE}
    for c in work:
        if c.suspicious or c.status == ClaimStatus.DUPLICATE:
            continue
        if c.id in disputed:
            c.status = ClaimStatus.DISPUTED
        elif c.id in superseded:
            c.status = ClaimStatus.SUPERSEDED
        else:
            doc = docs.get(c.source_id)
            tainted = doc is not None and doc.is_suspicious
            ok = not tainted and c.reliability >= cfg.min_verified_reliability
            c.status = ClaimStatus.VERIFIED if ok else ClaimStatus.UNVERIFIED

    unique = {cf.id: cf for cf in conflicts}
    ordered = sorted(unique.values(), key=lambda cf: (cf.conflict_type.value, cf.id))
    return Analysis(claims=work, conflicts=ordered)


# --------------------------------------------------------------------------- #
# Question answering
# --------------------------------------------------------------------------- #
@dataclass
class _Intent:
    kind: str = "general"                 # role | quantity | location | sequence | general
    predicates: Optional[set] = None
    stages: Optional[set] = None
    on_date: Optional[date] = None
    as_of: Optional[datetime] = None
    as_of_label: str = ""
    role_label: str = ""
    mentioned_places: list[str] = field(default_factory=list)
    compatibility_query: bool = False


def _has_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def _match_entities(question: str, entities: Sequence[Entity]) -> list[Entity]:
    """Entities whose name/alias (or identifier such as PO-7781) appears in the question."""
    qn = normalize_name(question)
    q_ids = {t.replace("-", "") for t in qn.split() if any(ch.isdigit() for ch in t)}
    matched: list[Entity] = []
    for entity in entities:
        for name in [entity.canonical_name, *entity.aliases]:
            nn = normalize_name(name)
            if not nn:
                continue
            ids = {t.replace("-", "") for t in nn.split() if any(ch.isdigit() for ch in t)}
            if _has_phrase(qn, nn) or (ids and ids <= q_ids):
                matched.append(entity)
                break
    return matched


def _claims_for_entities(claims: Sequence[Claim], entities: Sequence[Entity]) -> list[Claim]:
    ids = {e.id for e in entities}
    names = {normalize_name(n) for e in entities for n in [e.canonical_name, *e.aliases]}
    names.discard("")
    return [c for c in claims
            if c.entity_id in ids
            or (c.predicate in ("succeeds",) or c.predicate.startswith("role:"))
            and normalize_name(c.value) in names]


def _parse_intent(question: str, pool: Sequence[Claim]) -> _Intent:
    ql = question.lower()
    qn = normalize_name(question)
    intent = _Intent()
    full = _FULL_DATE.search(question)
    if full:
        try:
            year, month, day = (int(g) for g in full.groups())
            intent.on_date = date(year, month, day)
            intent.as_of = datetime(year, month, day, 23, 59, 59)
            intent.as_of_label = full.group(0)
        except ValueError:
            pass
    elif _YEAR.search(question):
        year = int(_YEAR.search(question).group(1))
        intent.as_of = datetime(year, 12, 31, 23, 59, 59)
        intent.as_of_label = str(year)

    role = next((r for r in _ROLE_WORDS if re.search(rf"\b{re.escape(r)}\b", ql)), None)
    if role:
        intent.kind = "role"
        intent.predicates = {"role:" + role.replace(" ", "_")}
        intent.role_label = role.upper() if len(role) <= 3 else role.title()
        intent.on_date = None
        return intent

    places = {_norm(c.value) for c in pool if c.predicate == "location"}
    mentioned_places = sorted({p for p in places if _has_phrase(qn, p)})
    keyword = any(w in ql for w in ("where was", "located", "same time", "in both"))
    if places and (mentioned_places or keyword):
        intent.kind, intent.predicates = "location", {"location"}
        intent.mentioned_places = mentioned_places
        asks_possibility = bool(re.search(r"\b(?:can|could|possible|might)\b", ql))
        asks_simultaneous = any(w in ql for w in ("same time", "simultaneously", "at once"))
        if asks_possibility and not asks_simultaneous and intent.on_date is None and len(mentioned_places) >= 2:
            intent.compatibility_query = True
        return intent
    if (any(w in ql for w in ("arriv", "depart", "before", "after"))
            and any(c.predicate in ("departed", "arrived") for c in pool)):
        intent.kind, intent.predicates = "sequence", {"departed", "arrived"}
        return intent

    tokens = set(re.findall(r"[a-z]+", ql))
    stages = {s for w, s in _STAGE_QUESTION_WORDS.items() if w in tokens}
    if stages or "how many" in ql or "quantity" in ql or "units" in tokens:
        intent.kind, intent.predicates = "quantity", {"quantity"}
        intent.stages = stages or None
    intent.on_date = None
    return intent


def _filter_claims(pool: Sequence[Claim], intent: _Intent) -> list[Claim]:
    out = []
    for c in pool:
        if intent.predicates is not None and c.predicate not in intent.predicates:
            continue
        if intent.stages is not None and c.stage not in intent.stages:
            continue
        if (intent.on_date is not None and c.event_time is not None
                and c.event_time.date() != intent.on_date):
            continue
        out.append(c)
    return sorted(out, key=_time_key)


def _strength(supporting: Sequence[Claim]) -> float:
    """Evidence strength: mean source reliability plus a corroboration bonus."""
    if not supporting:
        return 0.0
    base = sum(c.reliability for c in supporting) / len(supporting)
    agree: dict[tuple, set] = defaultdict(set)
    for c in supporting:
        agree[(_entity_key(c), c.predicate, c.stage, _val_key(c))].add(_source_key(c))
    bonus = min(0.2, 0.1 * (max(len(s) for s in agree.values()) - 1))
    return round(max(0.0, min(0.95, base + bonus)), 2)


def _citations(claims: Sequence[Claim], docs: dict[str, SourceDocument]) -> list[Citation]:
    out = []
    for c in claims:
        doc = docs.get(c.source_id)
        out.append(Citation(source_id=c.source_id, filename=doc.filename if doc else c.source_id,
                            snippet=_snippet(c.raw_text), locator=c.locator,
                            reliability=c.reliability, claim_id=c.id))
    return out


def _insufficient(question: str, text: str, notes: Optional[list[str]] = None,
                  status: AnswerStatus = AnswerStatus.INSUFFICIENT_EVIDENCE,
                  excluded: Optional[list[str]] = None) -> Answer:
    return Answer(question=question, status=status, answer_text=text, confidence=0.0,
                  notes=notes or [], excluded_claim_ids=excluded or [])


def _compose_quantity(usable: list[Claim], intent: _Intent) -> tuple[str, list[Claim], list[str]]:
    by_stage: dict[WorkflowStage, list[Claim]] = defaultdict(list)
    for c in usable:
        by_stage[c.stage].append(c)
    parts = []
    for stage in sorted(by_stage, key=lambda s: STAGE_ORDER.get(s, 99)):
        distinct: dict = {}
        for c in sorted(by_stage[stage], key=_time_key):
            distinct.setdefault(_val_key(c), []).append(c)
        pieces = []
        for group in distinct.values():
            when = f" on {_fmt_time(group[0].event_time)}" if len(distinct) > 1 else ""
            pieces.append(f"{_fmt_qty(group[0])}{when}")
        label = stage.value if stage != WorkflowStage.UNKNOWN else "recorded"
        parts.append(f"{label} " + " and ".join(pieces))
    notes = ["Rule: quantities are compared per entity and workflow stage; different stages "
             "are not contradictions, and same-stage claims conflict only inside the "
             "same-event window."]
    if intent.stages:
        missing = sorted(s.value for s in intent.stages - {c.stage for c in usable})
        if missing:
            notes.append("No usable evidence for requested stage(s): " + ", ".join(missing) + ".")
    return f"{usable[0].entity_name}: " + "; ".join(parts) + ".", list(usable), notes


def _compose_state(usable: list[Claim], intent: _Intent
                   ) -> Optional[tuple[str, list[Claim], list[str]]]:
    label = intent.role_label or usable[0].predicate
    subject = usable[0].entity_name
    timed = sorted((c for c in usable if c.event_time), key=lambda c: c.event_time)
    untimed = [c for c in usable if c.event_time is None]
    notes = ["Rule: state claims are ordered by timestamp; a later value is reported as a change, "
             "not a contradiction, and is not assumed true merely because it is newer."]
    later: list[Claim] = []
    candidates = timed
    if intent.as_of:
        candidates = [c for c in timed if c.event_time <= intent.as_of]
        later = [c for c in timed if c.event_time > intent.as_of]
    if candidates:
        chosen = candidates[-1]
        earlier = [c for c in candidates[:-1] if _norm(c.value) != _norm(chosen.value)]
        when = f"as of {intent.as_of_label}" if intent.as_of else "latest recorded"
        text = (f"{label} of {chosen.entity_name} ({when}): {chosen.value}, per evidence dated "
                f"{_fmt_time(chosen.event_time)}.")
        if earlier:
            text += " Earlier recorded: " + "; ".join(
                f"{c.value} ({_fmt_time(c.event_time)})" for c in earlier) + "."
        if not intent.as_of:
            notes.append("This is the latest known state in the evidence, not a confirmed "
                         "current state; newer evidence could supersede it.")
        if later:
            notes.append(f"A later change is recorded ({later[0].value}, "
                         f"{_fmt_time(later[0].event_time)}) but falls after the requested date.")
        return text, [chosen, *earlier], notes
    if untimed:
        values = ", ".join(sorted({c.value for c in untimed}))
        notes.append("The supporting evidence has no timestamps, so it cannot be placed in time.")
        return (f"{label} of {subject}: {values} (undated evidence).", list(untimed), notes)
    return None


def _compose_timeline(usable: list[Claim], docs: dict, conflicts: Sequence[Conflict]
                      ) -> tuple[str, list[Claim], list[str]]:
    ids = {c.id for c in usable}
    notes = ["Rule: records are listed chronologically; events at different times are not "
             "treated as contradictions."]
    if any(cf.conflict_type == ConflictType.COMPATIBLE_DIFFERENT_TIME
           and all(i in ids for i in cf.claim_ids) for cf in conflicts):
        notes.append("Some records are at different times and can both be true.")
    text = f"Records for {usable[0].entity_name}: " + "; ".join(
        _describe(c, docs) for c in usable) + "."
    return text, list(usable), notes


def _compatible_location_claims(
    usable: list[Claim],
    conflicts: Sequence[Conflict],
    mentioned_places: list[str],
    cfg: ReasonerConfig,
) -> Optional[list[Claim]]:
    """Find usable location claims at different times covering the asked places."""
    if len(mentioned_places) < 2:
        return None
    wanted = set(mentioned_places)
    by_id = {c.id: c for c in usable}
    compatible_claims: list[Claim] = []
    seen_ids: set[str] = set()

    for cf in conflicts:
        if cf.conflict_type != ConflictType.COMPATIBLE_DIFFERENT_TIME:
            continue
        pair = [by_id[cid] for cid in cf.claim_ids if cid in by_id]
        if len(pair) == 2 and {_norm(c.value) for c in pair} & wanted:
            for c in pair:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    compatible_claims.append(c)

    if not compatible_claims:
        for a, b in combinations([c for c in usable if c.event_time is not None], 2):
            if _norm(a.value) == _norm(b.value):
                continue
            if abs(a.event_time - b.event_time) >= cfg.min_travel_gap:
                for c in (a, b):
                    if c.id not in seen_ids:
                        seen_ids.add(c.id)
                        compatible_claims.append(c)

    covered = {_norm(c.value) for c in compatible_claims}
    if not wanted.issubset(covered):
        return None
    return sorted(compatible_claims, key=_time_key)


def answer_question(question: str, claims: Sequence[Claim], conflicts: Sequence[Conflict],
                    documents: Sequence[SourceDocument], entities: Sequence[Entity],
                    config: Optional[ReasonerConfig] = None) -> Answer:
    """Answer from evidence only, with citations, reasoning rule and evidence strength.

    Returns ``INSUFFICIENT_EVIDENCE`` when no usable claim supports an answer,
    ``SUSPICIOUS_ONLY`` when only suspicious claims exist, ``CONFLICTING`` when usable
    claims contain a real conflict, otherwise ``ANSWERED``.
    """
    cfg = config or ReasonerConfig()
    docs = {d.id: d for d in documents}
    q = (question or "").strip()
    if not q:
        return _insufficient(q, "Insufficient evidence: the question is empty.")
    matched = _match_entities(q, entities)
    if not matched:
        return _insufficient(
            q, "Insufficient evidence: the question does not mention any entity found in the "
               "uploaded evidence.", ["Known entities: " + ", ".join(
                   sorted(e.canonical_name for e in entities)[:10])] if entities else [])
    pool = _claims_for_entities(claims, matched)
    names = ", ".join(e.canonical_name for e in matched)
    if not pool:
        return _insufficient(q, f"Insufficient evidence: no claims about {names} were extracted.")

    intent = _parse_intent(q, pool)
    relevant = _filter_claims(pool, intent)
    usable = [c for c in relevant if c.is_usable]
    suspicious = [c for c in relevant if c.suspicious]
    excluded = [c.id for c in suspicious]

    if not usable:
        if suspicious:
            return _insufficient(
                q, f"Only suspicious evidence exists for this question ({len(suspicious)} claim(s)). "
                   "It was not used as fact and is kept for forensic review. Insufficient evidence "
                   "for a verified answer.",
                ["Suspicious claims: " + ", ".join(excluded)], AnswerStatus.SUSPICIOUS_ONLY, excluded)
        available = sorted({c.predicate for c in pool if c.is_usable})
        hint = f" Available evidence covers: {', '.join(available)}." if available else ""
        return _insufficient(q, f"Insufficient evidence: no usable claims match this question "
                                f"for {names}.{hint}")

    ids = {c.id for c in usable}
    real = [cf for cf in conflicts if cf.is_real_problem and cf.claim_ids
            and all(i in ids for i in cf.claim_ids)]
    notes: list[str] = []
    if excluded:
        notes.append(f"{len(excluded)} suspicious claim(s) excluded from this answer and kept for "
                     f"forensic review: {', '.join(excluded)}.")

    compatible = (
        _compatible_location_claims(usable, conflicts, intent.mentioned_places, cfg)
        if intent.compatibility_query
        else None
    )

    if compatible:
        status = AnswerStatus.ANSWERED
        places_str = " and ".join(c.value for c in compatible)
        text = (
            f"Yes, {compatible[0].entity_name} has records in {places_str} at different times, "
            f"which can both be true: "
            + "; ".join(_describe(c, docs) for c in compatible)
            + "."
        )
        supporting = compatible
        notes.insert(
            0,
            "Rule: events at sufficiently different times are compatible and are not contradictions.",
        )
        if real:
            notes.append(
                "Note: separate records for this entity also contain a conflict on another "
                f"timestamp ({'; '.join(cf.explanation for cf in real)})."
            )
        confidence = _strength(supporting)
    elif real:
        text = ("The available evidence conflicts. " + " ".join(cf.explanation for cf in real)
                + " Records considered: " + "; ".join(_describe(c, docs) for c in usable) + ".")
        notes.insert(0, "Rule: " + "; ".join(sorted({cf.rule for cf in real if cf.rule})) + ".")
        notes.append("Conflicting evidence is not resolved by recency or source reliability.")
        supporting = usable
        confidence = min(0.4, _strength(supporting))
        status = AnswerStatus.CONFLICTING
    else:
        status = AnswerStatus.ANSWERED
        if intent.kind == "role":
            composed = _compose_state(usable, intent)
        elif intent.kind == "quantity":
            composed = _compose_quantity(usable, intent)
        else:
            composed = _compose_timeline(usable, docs, conflicts)
        if composed is None:
            return _insufficient(q, f"Insufficient evidence: the evidence about {names} only "
                                    f"covers dates after {intent.as_of_label}.", notes,
                                 excluded=excluded)
        text, supporting, extra = composed
        notes = extra + notes
        if intent.kind == "quantity":
            stage_notes = [cf.explanation for cf in conflicts
                           if cf.conflict_type == ConflictType.WORKFLOW_STAGE
                           and all(i in ids for i in cf.claim_ids)]
            notes += stage_notes
        confidence = _strength(supporting)

    unverified = [c for c in supporting if not c.is_verified]
    if unverified:
        notes.append(f"{len(unverified)} supporting claim(s) are unverified (single or "
                     "less-reliable source, or a document containing suspicious content).")
    tainted = [c for c in supporting if docs.get(c.source_id) and docs[c.source_id].is_suspicious]
    if tainted:
        notes.append("A supporting document also contains suspicious content; treat it with care.")
    notes.append("Evidence strength reflects source reliability and corroboration; it is not a "
                 "probability that the answer is true.")
    return Answer(question=q, status=status, answer_text=text, confidence=confidence,
                  citations=_citations(supporting, docs),
                  conflict_ids=[cf.id for cf in real], excluded_claim_ids=excluded, notes=notes)


class EvidenceReasoner:
    """
    Object-oriented interface for asking questions about an AnalysisResult.

    Uses the existing deterministic answer_question() function.
    No LLM is involved.
    """

    def __init__(self, result, config=None):
        self.result = result
        self.config = config

    def ask(self, question: str) -> Answer:
        """Answer a question using the evidence in the analysis result."""

        return answer_question(
            question=question,
            claims=self.result.claims,
            conflicts=self.result.conflicts,
            documents=self.result.documents,
            entities=self.result.entities,
            config=self.config,
        )
