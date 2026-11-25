"""Entity resolution for CERBERUS-X using RapidFuzz.

Decides whether a name refers to a known entity, with a score, a method and a
plain-language explanation. Designed to avoid false merges:

  * Names with identifiers (SH-1042 vs SH-1043, "Report 2024" vs "Report 2026")
    never merge when their identifiers differ.
  * Entities of conflicting known types never merge.
  * "R. Sharma" ~ "Rahul Sharma" (initial matching) applies to person names only.
  * If two or more existing entities match about equally, the name is AMBIGUOUS
    and (by default) kept as a separate entity flagged for review.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from core.schemas import Entity, make_id

NORMALIZED_SCORE = 0.98
IDENTIFIER_SCORE = 0.93
INITIAL_SCORE = 0.90

_ORG_SUFFIXES = {"pvt", "private", "ltd", "limited", "llp", "llc", "inc", "incorporated",
                 "corp", "corporation", "co", "company", "plc", "gmbh", "pte"}
_HONORIFICS = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "shri", "smt", "sri", "sir"}


class MatchDecision(str, Enum):
    NEW = "new"
    EXACT = "exact"
    NORMALIZED = "normalized"
    ALIAS = "alias"
    IDENTIFIER = "identifier"
    INITIAL = "initial"
    FUZZY = "fuzzy"
    AMBIGUOUS = "ambiguous"


_METHOD_DECISION = {
    "exact": MatchDecision.EXACT, "normalized": MatchDecision.NORMALIZED,
    "alias": MatchDecision.ALIAS, "identifier": MatchDecision.IDENTIFIER,
    "initial": MatchDecision.INITIAL, "fuzzy": MatchDecision.FUZZY,
}


@dataclass(frozen=True)
class ResolverConfig:
    """Tunable thresholds (all scores are 0-1)."""
    match_threshold: float = 0.90        # >= this: merge into an existing entity
    review_threshold: float = 0.80       # >= this but below match: new entity, flagged
    ambiguity_margin: float = 0.03       # top candidates this close => ambiguous
    keep_ambiguous_separate: bool = True  # safe default: do not merge ambiguous names
    strip_org_suffixes: bool = True

    def __post_init__(self) -> None:
        for name in ("match_threshold", "review_threshold", "ambiguity_margin"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1 (got {value}).")
        if self.review_threshold > self.match_threshold:
            raise ValueError("review_threshold must not exceed match_threshold.")


class Candidate(BaseModel):
    entity_id: str
    canonical_name: str
    score: float
    method: str                     # exact | normalized | alias | identifier | initial | fuzzy
    matched_name: str


class MatchResult(BaseModel):
    """Outcome of resolving one name.

    ``confidence`` is the match score when merged; for NEW / AMBIGUOUS results it
    is the score of the best candidate that was *not* merged (0.0 if none).
    """
    query: str
    decision: MatchDecision
    entity_id: Optional[str] = None
    canonical_name: Optional[str] = None
    confidence: float = 0.0
    needs_review: bool = False
    explanation: str = ""
    candidates: list[Candidate] = Field(default_factory=list)

    @property
    def merged(self) -> bool:
        return self.decision not in (MatchDecision.NEW, MatchDecision.AMBIGUOUS)


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
def normalize_name(name: str, *, strip_suffixes: bool = True) -> str:
    """Case-fold, strip accents (Latin only), drop punctuation, honorifics and
    trailing company suffixes. Non-Latin scripts are preserved."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    text = stripped if stripped.isascii() else unicodedata.normalize("NFKC", name)
    text = text.casefold().replace("&", " and ")
    text = "".join(
        " " if ch == "_" or (unicodedata.category(ch)[0] in "PS" and ch != "-") else ch
        for ch in text)
    tokens = [t.strip("-") for t in text.split()]
    tokens = [t for t in tokens if t]
    while len(tokens) > 1 and tokens[0] in _HONORIFICS:
        tokens.pop(0)
    if strip_suffixes:
        while len(tokens) > 1 and tokens[-1] in _ORG_SUFFIXES:
            tokens.pop()
    return " ".join(tokens)


def _id_tokens(normalized: str) -> frozenset[str]:
    return frozenset(t.replace("-", "") for t in normalized.split()
                     if any(ch.isdigit() for ch in t))


def _clean_type(entity_type: Optional[str]) -> Optional[str]:
    if not entity_type or entity_type.strip().lower() == "unknown":
        return None
    return entity_type.strip().lower()


def _types_conflict(a: Optional[str], b: Optional[str]) -> bool:
    a, b = _clean_type(a), _clean_type(b)
    return a is not None and b is not None and a != b


def _has_initial(name: str) -> bool:
    tokens = normalize_name(name).split()
    return bool(tokens) and len(tokens[0]) == 1


def _initial_match(q_tokens: list[str], n_tokens: list[str]) -> bool:
    if len(q_tokens) < 2 or len(n_tokens) < 2 or q_tokens[-1] != n_tokens[-1]:
        return False
    a, b = q_tokens[0], n_tokens[0]
    if len(a) == 1 and len(b) > 1:
        return b.startswith(a)
    if len(b) == 1 and len(a) > 1:
        return a.startswith(b)
    return False


def _score_pair(q_raw: str, q_norm: str, n_raw: str, n_norm: str,
                person_ok: bool) -> tuple[float, str]:
    """Return (score, method) for one query/known-name pair."""
    if q_raw.strip().casefold() == n_raw.strip().casefold():
        return 1.0, "exact"
    if q_norm == n_norm:
        return NORMALIZED_SCORE, "normalized"
    q_ids, n_ids = _id_tokens(q_norm), _id_tokens(n_norm)
    if q_ids != n_ids:
        return 0.0, "fuzzy"                       # identifier veto
    if q_ids:
        return IDENTIFIER_SCORE, "identifier"
    if person_ok and _initial_match(q_norm.split(), n_norm.split()):
        return INITIAL_SCORE, "initial"
    return round(fuzz.token_sort_ratio(q_norm, n_norm) / 100.0, 4), "fuzzy"


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #
class EntityResolver:
    """Stateful resolver that maintains canonical entities and their aliases."""

    def __init__(self, config: Optional[ResolverConfig] = None) -> None:
        self.config = config or ResolverConfig()
        self._entities: dict[str, Entity] = {}
        self._names: dict[str, dict[str, str]] = {}   # entity id -> {normalised: raw}
        self._order: dict[str, int] = {}

    # ---- public API ------------------------------------------------------- #
    @property
    def entities(self) -> list[Entity]:
        return list(self._entities.values())

    def load(self, entities: Iterable[Entity]) -> None:
        """Load previously saved entities (canonical names and aliases)."""
        for entity in entities:
            self._register(entity.model_copy(deep=True))

    def find(self, name: str, entity_type: Optional[str] = None) -> MatchResult:
        """Decide how ``name`` would resolve, without changing any state."""
        return self._decide(name, entity_type)

    def resolve(self, name: str, entity_type: Optional[str] = None) -> MatchResult:
        """Resolve ``name`` to an entity, registering a new entity or alias as needed."""
        result = self._decide(name, entity_type)
        raw = name.strip()
        q_type = _clean_type(entity_type)
        if result.entity_id is not None:
            entity = self._entities[result.entity_id]
            self._attach(entity, raw, q_type)
            result.canonical_name = entity.canonical_name
        else:
            norm = normalize_name(raw, strip_suffixes=self.config.strip_org_suffixes)
            entity = self._register(Entity(
                id=self._unique_id(make_id("ent", norm, q_type or "unknown")),
                canonical_name=raw, entity_type=q_type or "unknown"))
            result.entity_id = entity.id
            result.canonical_name = entity.canonical_name
        return result

    def resolve_all(self, names: Iterable[str], entity_type: Optional[str] = None
                    ) -> list[MatchResult]:
        return [self.resolve(n, entity_type) for n in names]

    def add_entity(self, name: str, entity_type: Optional[str] = None,
                   aliases: Iterable[str] = ()) -> Entity:
        """Register (or fetch) an entity and attach explicit aliases."""
        entity = self._entities[self.resolve(name, entity_type).entity_id]  # type: ignore[index]
        for alias in aliases:
            self.add_alias(entity.id, alias)
        return entity

    def add_alias(self, entity_id: str, alias: str) -> None:
        """Attach an alias. Raises KeyError for unknown ids and ValueError if the alias
        already belongs to a different entity."""
        if entity_id not in self._entities:
            raise KeyError(f"Unknown entity id: {entity_id}")
        norm = normalize_name(alias, strip_suffixes=self.config.strip_org_suffixes)
        if not norm:
            raise ValueError("Alias must contain letters or digits.")
        for other_id, names in self._names.items():
            if other_id != entity_id and norm in names:
                raise ValueError(f"Alias '{alias}' already belongs to "
                                 f"'{self._entities[other_id].canonical_name}'.")
        self._attach(self._entities[entity_id], alias.strip(), None)

    # ---- internals -------------------------------------------------------- #
    def _unique_id(self, base: str) -> str:
        candidate, n = base, 2
        while candidate in self._entities:
            candidate, n = f"{base}_{n}", n + 1
        return candidate

    def _register(self, entity: Entity) -> Entity:
        entity.id = entity.id or self._unique_id(make_id("ent", entity.canonical_name))
        self._entities[entity.id] = entity
        self._order[entity.id] = len(self._order)
        strip = self.config.strip_org_suffixes
        names = {normalize_name(entity.canonical_name, strip_suffixes=strip): entity.canonical_name}
        for alias in entity.aliases:
            names.setdefault(normalize_name(alias, strip_suffixes=strip), alias)
        self._names[entity.id] = names
        return entity

    def _attach(self, entity: Entity, raw: str, q_type: Optional[str]) -> None:
        norm = normalize_name(raw, strip_suffixes=self.config.strip_org_suffixes)
        self._names[entity.id].setdefault(norm, raw)
        if raw != entity.canonical_name and raw not in entity.aliases:
            if _has_initial(entity.canonical_name) and not _has_initial(raw):
                entity.aliases.append(entity.canonical_name)   # prefer the fuller name
                entity.canonical_name = raw
            else:
                entity.aliases.append(raw)
        if _clean_type(entity.entity_type) is None and q_type:
            entity.entity_type = q_type

    def _score_entity(self, raw: str, norm: str, q_type: Optional[str],
                      entity: Entity) -> Optional[Candidate]:
        person_ok = q_type == "person" or _clean_type(entity.entity_type) == "person"
        canonical_norm = normalize_name(entity.canonical_name,
                                        strip_suffixes=self.config.strip_org_suffixes)
        best: Optional[tuple[float, str, str]] = None
        for n_norm, n_raw in self._names[entity.id].items():
            score, method = _score_pair(raw, norm, n_raw, n_norm, person_ok)
            if method in ("exact", "normalized") and n_norm != canonical_norm:
                method = "alias"
            if best is None or score > best[0]:
                best = (score, method, n_raw)
        if best is None or best[0] <= 0:
            return None
        return Candidate(entity_id=entity.id, canonical_name=entity.canonical_name,
                         score=best[0], method=best[1], matched_name=best[2])

    def _explain(self, raw: str, cand: Candidate) -> str:
        cfg = self.config
        text = {
            "exact": f"'{raw}' is identical (ignoring case) to known name '{cand.matched_name}'.",
            "normalized": (f"'{raw}' equals '{cand.matched_name}' after normalisation "
                           "(case, punctuation, honorifics, company suffixes)."),
            "alias": f"'{raw}' matches the registered alias '{cand.matched_name}'.",
            "identifier": f"'{raw}' and '{cand.matched_name}' contain the same identifier(s).",
            "initial": (f"Surname matches '{cand.matched_name}' and the first name is an initial "
                        "of it (person names only)."),
            "fuzzy": (f"Token-sort similarity {cand.score:.2f} >= threshold "
                      f"{cfg.match_threshold:.2f} with '{cand.matched_name}'; no identifier or "
                      "type conflict."),
        }[cand.method]
        return f"{text} Confidence {cand.score:.2f}."

    def _decide(self, name: str, entity_type: Optional[str]) -> MatchResult:
        raw = (name or "").strip()
        norm = normalize_name(raw, strip_suffixes=self.config.strip_org_suffixes)
        if not norm:
            raise ValueError("Entity name must contain letters or digits.")
        q_type = _clean_type(entity_type)
        cfg = self.config

        candidates: list[Candidate] = []
        for entity in self._entities.values():
            if _types_conflict(q_type, entity.entity_type):
                continue
            cand = self._score_entity(raw, norm, q_type, entity)
            if cand is not None:
                candidates.append(cand)
        candidates.sort(key=lambda c: (-c.score, self._order[c.entity_id]))

        strong = [c for c in candidates if c.score >= cfg.match_threshold]
        if strong:
            best = strong[0]
            ambiguous = len(strong) > 1 and (best.score - strong[1].score) <= cfg.ambiguity_margin
            if ambiguous and cfg.keep_ambiguous_separate:
                names = ", ".join(f"'{c.canonical_name}' ({c.score:.2f})" for c in strong[:3])
                return MatchResult(
                    query=raw, decision=MatchDecision.AMBIGUOUS, confidence=best.score,
                    needs_review=True, candidates=strong[:5],
                    explanation=(f"'{raw}' matches several entities about equally: {names}. "
                                 "Kept as a separate entity for review."))
            explanation = self._explain(raw, best)
            if ambiguous:
                explanation += (" Other candidates scored within the ambiguity margin; attached to "
                                "the earliest-registered one by configuration. Review recommended.")
            return MatchResult(
                query=raw, decision=_METHOD_DECISION[best.method], entity_id=best.entity_id,
                canonical_name=best.canonical_name, confidence=best.score,
                needs_review=ambiguous, explanation=explanation, candidates=strong[:5])

        near = [c for c in candidates if c.score >= cfg.review_threshold]
        top = candidates[0] if candidates else None
        explanation = "No existing entity is similar enough; treated as a new entity."
        if near:
            explanation = (f"Possible match '{near[0].canonical_name}' (score {near[0].score:.2f}) "
                           f"is below the merge threshold {cfg.match_threshold:.2f}; kept separate "
                           "and flagged for review.")
        return MatchResult(query=raw, decision=MatchDecision.NEW,
                           confidence=top.score if top else 0.0, needs_review=bool(near),
                           explanation=explanation, candidates=candidates[:5])