"""Rule-based claim extraction for CERBERUS-X (no LLM, fully local).

Turns the located segments produced by the extractor + sanitizer into ``Claim``
objects and resolves entity names through an ``EntityResolver``.

Recognised patterns (English only):
  * CSV rows with entity/attribute/value/unit/timestamp/source columns
  * "<X> ordered|dispatched|shipped|delivered N units ... on <Order/Shipment id>"
  * "<Order/Shipment id> delivered N units"  /  "N units of <id> were delivered"
  * "<Person> is the CEO of <Org>"            -> predicate ``role:ceo``
  * "<Person> succeeds <Person>"              -> predicate ``succeeds``
  * "Truck TR-55 departed|arrived <Place> on <date> at <time>"
  * "<Person> signed|attended|visited ... in/at <Place> on <date> at <time>"
  * "Date: YYYY-MM-DD" header lines give a default date to following text

Suspicious segments (hidden text, injection) are extracted too but the claims are
flagged ``suspicious=True`` so they stay visible for forensic review and can
never become verified facts. Text in a suspicious segment never sets the date
context.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from core.entity_resolver import EntityResolver, MatchResult
from core.sanitizer import SanitizationResult, SanitizedSegment
from core.schemas import Claim, SourceDocument, WorkflowStage, make_id

# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #
_TS_RE = re.compile(
    r"(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})"
    r"(?:[ T]+(?:at\s+)?(?P<h>\d{1,2}):(?P<mi>\d{2}))?"
)
_HEADER_DATE_RE = re.compile(r"^\s*date\s*[:\-]\s*(?P<ts>.+?)\s*$", re.IGNORECASE)


def parse_timestamp(text: Optional[str]) -> Optional[datetime]:
    """Parse the first ``YYYY-MM-DD[ HH:MM]`` found in ``text`` (naive); else ``None``."""
    if not text:
        return None
    match = _TS_RE.search(text)
    if not match:
        return None
    try:
        return datetime(int(match["y"]), int(match["mo"]), int(match["d"]),
                        int(match["h"] or 0), int(match["mi"] or 0))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Patterns
# --------------------------------------------------------------------------- #
_TS = r"\d{4}-\d{2}-\d{2}(?:\s+(?:at\s+)?\d{1,2}:\d{2})?"
_NAME = r"(?:[A-Z]\.|[A-Z][a-z]+)(?:\s+(?:[A-Z]\.|[A-Z][a-z]+)){1,3}"
_ORG = r"[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4}"
_ROLE = (r"(?i:CEO|CFO|CTO|COO|Chairman|Chairperson|President|Managing Director|"
         r"General Manager|Director|Manager)")
_ITEM = r"(?:(?:Purchase Order|Order|Shipment|Consignment)\s+)?[A-Z]{2,4}-\d+"
_UNIT = r"(?i:units?|pieces|pcs|items|boxes|pallets)"
_VERB = r"(?i:ordered|dispatched|shipped|delivered|invoiced)"
_PLACE = r"[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*"

_ROLE_RE = re.compile(
    "(?P<person>" + _NAME + r")\s+(?i:is|was|serves\s+as)\s+the\s+(?P<role>" + _ROLE
    + r")\s+of\s+(?P<org>" + _ORG + ")")
_SUCCESSION_RE = re.compile(
    "(?P<new>" + _NAME + r")\s+(?i:succeeds|replaces|replaced)\s+(?P<old>" + _NAME + ")")
_QTY_A = re.compile(
    "(?P<verb>" + _VERB + r")\s+(?P<qty>\d[\d,]*)\s+(?P<unit>" + _UNIT
    + r")\b(?:\s+of\s+[^.]*?)?\s+(?i:on|against|under|for)\s+(?P<ent>" + _ITEM + ")")
_QTY_B = re.compile(
    "(?P<ent>" + _ITEM + r")\s+(?P<verb>" + _VERB + r")\s+(?P<qty>\d[\d,]*)\s+(?P<unit>"
    + _UNIT + r")\b")
_QTY_C = re.compile(
    r"(?P<qty>\d[\d,]*)\s+(?P<unit>" + _UNIT + r")\s+of\s+(?P<ent>" + _ITEM
    + r")\s+(?:were|was)\s+(?P<verb>" + _VERB + ")")
_TRAVEL_RE = re.compile(
    r"(?P<ent>(?:Truck|Vehicle|Flight|Train|Vessel|Van)\s+[A-Z0-9]{1,5}(?:-[A-Z0-9]+)+)\s+"
    r"(?P<verb>(?i:departed|arrived|left|reached))\s+(?:(?i:from|in|at|to)\s+)?"
    r"(?P<loc>" + _PLACE + r")\s+on\s+(?P<ts>" + _TS + ")")
_PRESENCE_RE = re.compile(
    "(?P<person>" + _NAME + r")\s+(?P<verb>signed|attended|visited|inspected|audited|"
    r"reviewed|joined)\s+(?P<rest>.+?)\s+on\s+(?P<ts>" + _TS + ")")
_LOC_OFFICE = re.compile(
    r"\bthe\s+(" + _PLACE + r")\s+(?:office|warehouse|site|depot|plant|branch|hub|facility)\b")
_LOC_IN = re.compile(r"\b(?:in|at)\s+(" + _PLACE + ")")

_TITLES = {"inspector", "auditor", "manager", "officer", "engineer", "supervisor",
           "dr", "mr", "mrs", "ms", "prof"}
_STAGE_WORDS = {
    "ordered": WorkflowStage.ORDERED, "order": WorkflowStage.ORDERED,
    "dispatched": WorkflowStage.DISPATCHED, "dispatch": WorkflowStage.DISPATCHED,
    "shipped": WorkflowStage.DISPATCHED, "shipment": WorkflowStage.DISPATCHED,
    "delivered": WorkflowStage.DELIVERED, "delivery": WorkflowStage.DELIVERED,
    "invoiced": WorkflowStage.INVOICED, "invoice": WorkflowStage.INVOICED,
}
_TRAVEL_VERBS = {"departed": "departed", "left": "departed",
                 "arrived": "arrived", "reached": "arrived"}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def stage_from_word(word: Optional[str]) -> WorkflowStage:
    """Map a verb/noun such as ``dispatched`` to a workflow stage."""
    return _STAGE_WORDS.get((word or "").strip().lower(), WorkflowStage.UNKNOWN)


def infer_entity_type(name: str) -> Optional[str]:
    """Guess an entity type from a leading keyword (``Shipment ...`` -> shipment)."""
    low = name.strip().lower()
    if low.startswith(("purchase order", "order ")):
        return "order"
    if low.startswith(("shipment", "consignment")):
        return "shipment"
    if low.startswith(("truck", "vehicle", "van", "flight", "train", "vessel")):
        return "vehicle"
    return None


def _clean(name: str) -> str:
    return " ".join(name.split()).strip(" .,;:")


def _strip_titles(name: str) -> str:
    tokens = name.split()
    while len(tokens) > 1 and tokens[0].strip(".").lower() in _TITLES:
        tokens.pop(0)
    return " ".join(tokens)


def _to_number(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def _norm_unit(unit: Optional[str]) -> Optional[str]:
    if not unit or not unit.strip():
        return None
    low = unit.strip().lower()
    return "units" if low == "unit" else low


def _location_from(rest: str) -> Optional[str]:
    office = _LOC_OFFICE.search(rest)
    if office:
        return office.group(1)
    found = _LOC_IN.findall(rest)
    return found[-1] if found else None


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #
class _Builder:
    """Collects claims for one document and resolves entities."""

    def __init__(self, doc: SourceDocument, resolver: EntityResolver) -> None:
        self.doc = doc
        self.resolver = resolver
        self.claims: list[Claim] = []
        self.notes: list[str] = []
        self.item: Optional[SanitizedSegment] = None
        self._seen: set[tuple] = set()
        self._n = 0

    def _resolve(self, name: str, entity_type: Optional[str]) -> Optional[MatchResult]:
        try:
            result = self.resolver.resolve(name, entity_type)
        except ValueError:
            return None
        if result.needs_review and self.item is not None:
            self.notes.append(f"{self.doc.filename} ({self.item.segment.locator}): "
                              f"{result.explanation}")
        return result

    def add(self, *, entity_name: str, entity_type: Optional[str], predicate: str,
            value: str, stage: WorkflowStage = WorkflowStage.UNKNOWN,
            value_num: Optional[float] = None, unit: Optional[str] = None,
            event_time: Optional[datetime] = None, location: Optional[str] = None,
            source_label: Optional[str] = None,
            value_entity_type: Optional[str] = None) -> None:
        assert self.item is not None
        name = _clean(entity_name)
        result = self._resolve(name, entity_type)
        if result is None:
            return
        value = _clean(value)
        if value_entity_type:
            value_result = self._resolve(value, value_entity_type)
            if value_result is not None and value_result.canonical_name:
                value = value_result.canonical_name
        seg = self.item.segment
        key = (result.entity_id, predicate, stage, value, event_time, location,
               source_label, seg.locator)
        if key in self._seen:
            return
        self._seen.add(key)
        self._n += 1
        self.claims.append(Claim(
            id=make_id("clm", self.doc.id, seg.locator, self._n, predicate, value),
            source_id=self.doc.id, source_label=source_label, entity_name=name,
            entity_id=result.entity_id, predicate=predicate, value=value,
            value_num=value_num, unit=_norm_unit(unit), stage=stage,
            event_time=event_time, location=location, raw_text=seg.text.strip(),
            locator=seg.locator, suspicious=self.item.suspicious))


# --------------------------------------------------------------------------- #
# Segment handlers
# --------------------------------------------------------------------------- #
def _csv_claims(b: _Builder, fields: dict[str, str]) -> None:
    f = {k.strip().lower(): (v or "").strip() for k, v in fields.items()}
    entity = f.get("entity") or f.get("subject")
    attribute = (f.get("attribute") or f.get("predicate") or "").lower().replace(" ", "_")
    value = f.get("value", "")
    if not entity or not attribute or not value:
        return
    when = parse_timestamp(f.get("timestamp") or f.get("time") or f.get("date"))
    label = f.get("source") or f.get("source_label") or None
    match = re.match(r"^(?:quantity|qty)(?:_(?P<stage>[a-z]+))?$", attribute)
    if match:
        number = _to_number(value)
        if number is None:
            return
        stage = stage_from_word(match.group("stage") or f.get("stage"))
        b.add(entity_name=entity, entity_type=infer_entity_type(entity), predicate="quantity",
              value=f"{number:g}", value_num=number, unit=f.get("unit"), stage=stage,
              event_time=when, source_label=label)
    else:
        b.add(entity_name=entity, entity_type=infer_entity_type(entity), predicate=attribute,
              value=value, stage=stage_from_word(f.get("stage")), event_time=when,
              source_label=label)


def _text_claims(b: _Builder, text: str, default_time: Optional[datetime]) -> None:
    sentence_time = parse_timestamp(text) or default_time

    for m in _ROLE_RE.finditer(text):
        role = m["role"].lower().replace(" ", "_")
        b.add(entity_name=m["org"], entity_type="organization", predicate=f"role:{role}",
              value=m["person"], event_time=sentence_time, value_entity_type="person")

    for m in _SUCCESSION_RE.finditer(text):
        b.add(entity_name=m["new"], entity_type="person", predicate="succeeds",
              value=m["old"], event_time=sentence_time, value_entity_type="person")

    for pattern in (_QTY_A, _QTY_B, _QTY_C):
        for m in pattern.finditer(text):
            number = _to_number(m["qty"])
            if number is None:
                continue
            ent = _clean(m["ent"])
            b.add(entity_name=ent, entity_type=infer_entity_type(ent), predicate="quantity",
                  value=f"{number:g}", value_num=number, unit=m["unit"],
                  stage=stage_from_word(m["verb"]), event_time=sentence_time)

    for m in _TRAVEL_RE.finditer(text):
        verb = _TRAVEL_VERBS[m["verb"].lower()]
        place = _clean(m["loc"])
        b.add(entity_name=m["ent"], entity_type=infer_entity_type(m["ent"]), predicate=verb,
              value=place, location=place, event_time=parse_timestamp(m["ts"]))

    for m in _PRESENCE_RE.finditer(text):
        place = _location_from(m["rest"])
        if not place:
            continue
        b.add(entity_name=_strip_titles(m["person"]), entity_type="person",
              predicate="location", value=place, location=place,
              event_time=parse_timestamp(m["ts"]))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def extract_claims(sanitized: SanitizationResult,
                   resolver: EntityResolver) -> tuple[list[Claim], list[str]]:
    """Extract claims from every segment of a sanitized document.

    Returns ``(claims, notes)``; ``notes`` holds entity-resolution remarks that need
    human review. Claims from suspicious segments are included and flagged.
    """
    builder = _Builder(sanitized.document, resolver)
    current_date: Optional[datetime] = None
    for item in sanitized.segments:
        builder.item = item
        seg = item.segment
        try:
            if seg.fields is not None:
                _csv_claims(builder, seg.fields)
                continue
            header = _HEADER_DATE_RE.match(seg.text)
            if header and not item.suspicious:
                current_date = parse_timestamp(header["ts"])
                continue
            _text_claims(builder, seg.text, None if item.suspicious else current_date)
        except Exception as exc:  # one odd line must not abort the document
            builder.notes.append(f"{sanitized.document.filename} ({seg.locator}): "
                                 f"claim extraction failed: {exc}")
    return builder.claims, builder.notes