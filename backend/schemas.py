"""Frontend-friendly API request and response schemas for CERBERUS-X."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from core.schemas import (
    AnswerStatus,
    Citation,
    Claim,
    ClaimStatus,
    ConflictType,
    Entity,
    FileType,
    SecurityFlag,
    Severity,
    SourceType,
    TwinState,
    WorkflowStage,
)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "cerberus-x"
    database: str = "sqlite"
    ocr_available: bool
    ocr_message: str
    ollama_available: bool = False
    ollama_model: str = "llama3.2:3b"
    ollama_model_installed: bool = False
    ollama_message: str = ""
    supported_extensions: list[str] = Field(default_factory=list)


class AnalysisCounts(BaseModel):
    documents: int
    entities: int
    claims: int
    conflicts: int
    twin_states: int


class DocumentDTO(BaseModel):
    id: str
    filename: str
    file_type: FileType
    source_type: SourceType
    sha256: str
    extraction_method: str
    reliability: float
    is_suspicious: bool
    flags: list[SecurityFlag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    duplicate_of: Optional[str] = None
    ingested_at: datetime


class ConflictClaimDTO(BaseModel):
    id: str
    source_id: str
    source_filename: Optional[str] = None
    source_label: Optional[str] = None
    value: str
    unit: Optional[str] = None
    stage: WorkflowStage
    event_time: Optional[datetime] = None
    location: Optional[str] = None
    locator: Optional[str] = None
    status: ClaimStatus
    reliability: float = 0.0
    raw_text: str


class ConflictDTO(BaseModel):
    id: str
    conflict_type: ConflictType
    claim_ids: list[str]
    entity_name: str
    predicate: str
    explanation: str
    severity: Severity
    needs_review: bool
    is_real_problem: bool
    rule: str = ""
    claims: list[ConflictClaimDTO] = Field(default_factory=list)


class UploadAnalysisResponse(BaseModel):
    analysis_id: str
    created_at: datetime
    counts: AnalysisCounts
    warnings: list[str] = Field(default_factory=list)
    documents: list[DocumentDTO] = Field(default_factory=list)


class AnalysisListItem(BaseModel):
    analysis_id: str
    created_at: datetime
    counts: AnalysisCounts


class AnalysisListResponse(BaseModel):
    total_investigations: int
    aggregate_counts: AnalysisCounts
    investigations: list[AnalysisListItem] = Field(default_factory=list)


class AnalysisDetailResponse(BaseModel):
    analysis_id: str
    created_at: datetime
    counts: AnalysisCounts
    documents: list[DocumentDTO]
    entities: list[Entity]
    claims: list[Claim]
    conflicts: list[ConflictDTO]
    twin_states: list[TwinState]
    warnings: list[str] = Field(default_factory=list)


class ReactFlowPosition(BaseModel):
    x: float
    y: float


class ReactFlowNode(BaseModel):
    id: str
    type: str
    position: ReactFlowPosition
    data: dict[str, Any]


class ReactFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    type: str = "smoothstep"
    animated: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class GraphStatistics(BaseModel):
    nodes: int
    edges: int
    documents: int
    entities: int
    claims: int
    conflicts: int


class GraphResponse(BaseModel):
    analysis_id: str
    nodes: list[ReactFlowNode]
    edges: list[ReactFlowEdge]
    statistics: GraphStatistics


class ConflictsResponse(BaseModel):
    analysis_id: str
    total: int
    real_problem_count: int
    conflicts: list[ConflictDTO]


class DigitalTwinEntityView(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: str = "unknown"
    aliases: list[str] = Field(default_factory=list)
    states: list[TwinState]
    current_attributes: dict[str, TwinState] = Field(default_factory=dict)


class DigitalTwinResponse(BaseModel):
    analysis_id: str
    summary: dict[str, int]
    entities: list[DigitalTwinEntityView]
    states: list[TwinState]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    use_llm: bool = False

    @field_validator("question")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question must not be empty or whitespace.")
        return cleaned


class AskResponse(BaseModel):
    analysis_id: str
    question: str
    status: AnswerStatus
    answer_text: str
    confidence: float
    citations: list[Citation] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    excluded_claim_ids: list[str] = Field(default_factory=list)
    used_llm: bool = False
    model: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class BriefResponse(BaseModel):
    analysis_id: str
    summary: str
    highlights: list[str] = Field(default_factory=list)
    used_llm: bool = False
    model: str = "llama3.2:3b"
    notes: list[str] = Field(default_factory=list)


class DeleteAnalysisResponse(BaseModel):
    analysis_id: str
    deleted: bool


class ForensicDocumentDTO(BaseModel):
    id: str
    filename: str
    file_type: FileType
    source_type: SourceType
    sha256: str
    extraction_method: str
    reliability: float
    is_suspicious: bool
    flags: list[SecurityFlag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    raw_text: str


class ForensicsResponse(BaseModel):
    analysis_id: str
    total_documents: int
    suspicious_documents: int
    total_flags: int
    documents: list[ForensicDocumentDTO]
