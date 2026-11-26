"""Pydantic data contracts shared by every CERBERUS-X module.

Everything the pipeline produces (documents, claims, conflicts, twin states,
answers) is defined here so modules stay decoupled and results can be saved
to / loaded from JSON.

Key invariant: a claim flagged ``suspicious`` is never ``VERIFIED``.

Batch 3 additions (all optional / defaulted, so Batch 1-2 code is unaffected):
  Claim.reliability, Conflict.rule, Citation.claim_id,
  TwinState.source_filename, TwinState.locator, Answer.excluded_claim_ids.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_id(prefix: str, *parts: object) -> str:
    """Return a deterministic short id such as ``clm_1a2b3c4d5e``."""
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"


def _utcnow() -> datetime:
    """Naive UTC 'now' (all timestamps in CERBERUS-X are naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware datetime to naive UTC; pass naive/None through."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class FileType(str, Enum):
    PDF = "pdf"
    IMAGE = "image"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    TEXT = "text"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    """Coarse provenance class used for the base reliability score."""
    SYSTEM_EXPORT = "system_export"          # e.g. CSV from a warehouse system
    OFFICIAL_DOCUMENT = "official_document"  # e.g. PDF report / press release
    FREEFORM_NOTE = "freeform_note"          # plain text notes
    OCR_IMAGE = "ocr_image"                  # text recovered through OCR
    UNKNOWN = "unknown"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SecurityFlagKind(str, Enum):
    HIDDEN_TEXT = "hidden_text"
    PROMPT_INJECTION = "prompt_injection"
    LOW_OCR_CONFIDENCE = "low_ocr_confidence"


class WorkflowStage(str, Enum):
    ORDERED = "ordered"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    INVOICED = "invoiced"
    UNKNOWN = "unknown"


class ClaimStatus(str, Enum):
    UNVERIFIED = "unverified"   # extracted, not yet assessed
    VERIFIED = "verified"       # assessed, uncontradicted, sufficiently reliable source
    DISPUTED = "disputed"       # part of a true conflict
    SUPERSEDED = "superseded"   # replaced by a later state (temporal change)
    DUPLICATE = "duplicate"     # repeats another claim from the same source
    SUSPICIOUS = "suspicious"   # from hidden text / injection; never a fact


class ConflictType(str, Enum):
    TRUE_CONFLICT = "true_conflict"                # same event, incompatible values
    WORKFLOW_STAGE = "workflow_stage"              # different stages, not a conflict
    TEMPORAL_CHANGE = "temporal_change"            # state changed over time
    SAME_EVENT_CONFLICT = "same_event_conflict"    # same time, incompatible places
    IMPOSSIBLE_TIMELINE = "impossible_timeline"    # e.g. arrival before departure
    COMPATIBLE_DIFFERENT_TIME = "compatible_different_time"  # can both be true
    DUPLICATE = "duplicate"


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    CONFLICTING = "conflicting"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SUSPICIOUS_ONLY = "suspicious_only"


class UIMode(str, Enum):
    SIMPLE = "simple"
    FORENSIC = "forensic"


# --------------------------------------------------------------------------- #
# Reliability model (source-based)
# --------------------------------------------------------------------------- #
SOURCE_BASE_RELIABILITY: dict[SourceType, float] = {
    SourceType.SYSTEM_EXPORT: 0.85,
    SourceType.OFFICIAL_DOCUMENT: 0.80,
    SourceType.FREEFORM_NOTE: 0.55,
    SourceType.OCR_IMAGE: 0.45,
    SourceType.UNKNOWN: 0.40,
}

FLAG_PENALTY: dict[SecurityFlagKind, float] = {
    SecurityFlagKind.HIDDEN_TEXT: 0.35,
    SecurityFlagKind.PROMPT_INJECTION: 0.50,
    SecurityFlagKind.LOW_OCR_CONFIDENCE: 0.15,
}


class SecurityFlag(BaseModel):
    """A sanitizer finding attached to a document."""
    kind: SecurityFlagKind
    severity: Severity
    description: str
    evidence: str = ""              # short snippet that triggered the flag
    page: Optional[int] = None


def compute_reliability(source_type: SourceType, flags: list[SecurityFlag]) -> float:
    """Base score for the source type minus one penalty per distinct flag kind.

    Returns a value rounded to 2 decimals and clamped to [0.0, 1.0].
    """
    score = SOURCE_BASE_RELIABILITY.get(source_type, 0.40)
    for kind in {f.kind for f in flags}:
        score -= FLAG_PENALTY.get(kind, 0.0)
    return round(max(0.0, min(1.0, score)), 2)


# --------------------------------------------------------------------------- #
# Core models
# --------------------------------------------------------------------------- #
class SourceDocument(BaseModel):
    """One ingested file (after extraction and sanitization)."""
    id: str
    filename: str
    file_type: FileType
    source_type: SourceType = SourceType.UNKNOWN
    sha256: str
    stored_path: Optional[str] = None
    text: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)
    flags: list[SecurityFlag] = Field(default_factory=list)
    extraction_method: str = "none"          # e.g. "pymupdf", "tesseract", "pandas"
    warnings: list[str] = Field(default_factory=list)
    duplicate_of: Optional[str] = None       # id of an identical earlier document
    ingested_at: datetime = Field(default_factory=_utcnow)

    @property
    def reliability(self) -> float:
        return compute_reliability(self.source_type, self.flags)

    @property
    def is_suspicious(self) -> bool:
        return any(
            f.kind in (SecurityFlagKind.HIDDEN_TEXT, SecurityFlagKind.PROMPT_INJECTION)
            for f in self.flags
        )


class Entity(BaseModel):
    """A canonical entity with the aliases that were merged into it."""
    id: str
    canonical_name: str
    entity_type: str = "unknown"             # person | organization | shipment | order | ...
    aliases: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    """An atomic statement extracted from a source."""
    id: str
    source_id: str
    source_label: Optional[str] = None       # e.g. CSV 'source' column value
    entity_name: str                         # as written in the source
    entity_id: Optional[str] = None          # filled by the entity resolver
    predicate: str                           # e.g. "quantity", "role:ceo", "departed"
    value: str
    value_num: Optional[float] = None
    unit: Optional[str] = None
    stage: WorkflowStage = WorkflowStage.UNKNOWN
    event_time: Optional[datetime] = None
    location: Optional[str] = None
    raw_text: str
    locator: Optional[str] = None            # "page 1", "row 3", "line 12"
    suspicious: bool = False
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    reliability: float = Field(default=0.0, ge=0.0, le=1.0)   # set by the reasoner (Batch 3)

    @field_validator("event_time")
    @classmethod
    def _normalise_time(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v)

    @model_validator(mode="after")
    def _suspicious_is_never_verified(self) -> "Claim":
        if self.suspicious:
            self.status = ClaimStatus.SUSPICIOUS
        return self

    @property
    def is_verified(self) -> bool:
        return self.status == ClaimStatus.VERIFIED and not self.suspicious

    @property
    def is_usable(self) -> bool:
        """Whether the claim may be used to answer questions."""
        return not self.suspicious and self.status != ClaimStatus.DUPLICATE


class Citation(BaseModel):
    source_id: str
    filename: str
    snippet: str
    locator: Optional[str] = None
    reliability: float = Field(default=0.0, ge=0.0, le=1.0)
    claim_id: Optional[str] = None


class Conflict(BaseModel):
    id: str
    conflict_type: ConflictType
    claim_ids: list[str]
    entity_name: str
    predicate: str
    explanation: str
    severity: Severity = Severity.MEDIUM
    needs_review: bool = False
    rule: str = ""                           # the deterministic rule that produced this

    @property
    def is_real_problem(self) -> bool:
        """True conflicts / impossible timelines; stage and temporal changes are not."""
        return self.conflict_type in (
            ConflictType.TRUE_CONFLICT,
            ConflictType.SAME_EVENT_CONFLICT,
            ConflictType.IMPOSSIBLE_TIMELINE,
        )


class TwinState(BaseModel):
    """One known state of an entity attribute over a time interval."""
    entity_id: str
    entity_name: str
    attribute: str
    value: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None      # None = still current / unknown end
    claim_id: str
    source_id: str
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    reliability: float = Field(default=0.0, ge=0.0, le=1.0)
    source_filename: Optional[str] = None
    locator: Optional[str] = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def _normalise_time(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v)


class Answer(BaseModel):
    question: str
    status: AnswerStatus
    answer_text: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    excluded_claim_ids: list[str] = Field(default_factory=list)  # suspicious, not used
    used_llm: bool = False
    notes: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Everything the pipeline produces; this is what gets saved to disk."""
    documents: list[SourceDocument] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    twin_states: list[TwinState] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)

    def doc_by_id(self, doc_id: str) -> Optional[SourceDocument]:
        return next((d for d in self.documents if d.id == doc_id), None)

    def claim_by_id(self, claim_id: str) -> Optional[Claim]:
        return next((c for c in self.claims if c.id == claim_id), None)

    def save_json(self, path: Path) -> None:
        """Write the analysis to ``path`` as UTF-8 JSON (creates parent dirs)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> "AnalysisResult":
        """Load a previously saved analysis; raises ``ValueError`` if invalid."""
        try:
            return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # pydantic ValidationError, OSError, ...
            raise ValueError(f"Could not load analysis from {path}: {exc}") from exc