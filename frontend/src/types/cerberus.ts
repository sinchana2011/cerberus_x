export type FileType =
  | "pdf"
  | "image"
  | "csv"
  | "excel"
  | "json"
  | "text"
  | "unknown";

export type SourceType =
  | "system_export"
  | "official_document"
  | "freeform_note"
  | "ocr_image"
  | "unknown";

export type Severity = "low" | "medium" | "high";

export type SecurityFlagKind =
  | "hidden_text"
  | "prompt_injection"
  | "low_ocr_confidence";

export type WorkflowStage =
  | "ordered"
  | "dispatched"
  | "delivered"
  | "invoiced"
  | "unknown";

export type ClaimStatus =
  | "unverified"
  | "verified"
  | "disputed"
  | "superseded"
  | "duplicate"
  | "suspicious";

export type ConflictType =
  | "true_conflict"
  | "workflow_stage"
  | "temporal_change"
  | "same_event_conflict"
  | "impossible_timeline"
  | "compatible_different_time"
  | "duplicate";

export type AnswerStatus =
  | "answered"
  | "conflicting"
  | "insufficient_evidence"
  | "suspicious_only";

export interface HealthResponse {
  status: string;
  service: string;
  database: string;
  ocr_available: boolean;
  ocr_message: string;
  ollama_available: boolean;
  ollama_model: string;
  ollama_model_installed: boolean;
  ollama_message: string;
  supported_extensions: string[];
}

export interface AnalysisCounts {
  documents: number;
  entities: number;
  claims: number;
  conflicts: number;
  twin_states: number;
}

export interface SecurityFlag {
  kind: SecurityFlagKind;
  severity: Severity;
  description: string;
  evidence: string;
  page: number | null;
}

export interface DocumentDTO {
  id: string;
  filename: string;
  file_type: FileType;
  source_type: SourceType;
  sha256: string;
  extraction_method: string;
  reliability: number;
  is_suspicious: boolean;
  flags: SecurityFlag[];
  warnings: string[];
  metadata: Record<string, string>;
  duplicate_of: string | null;
  ingested_at: string;
}

export interface Entity {
  id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
}

export interface Claim {
  id: string;
  source_id: string;
  source_label: string | null;
  entity_name: string;
  entity_id: string | null;
  predicate: string;
  value: string;
  value_num: number | null;
  unit: string | null;
  stage: WorkflowStage;
  event_time: string | null;
  location: string | null;
  raw_text: string;
  locator: string | null;
  suspicious: boolean;
  status: ClaimStatus;
  reliability: number;
}

export interface ConflictClaimDTO {
  id: string;
  source_id: string;
  source_filename: string | null;
  source_label: string | null;
  value: string;
  unit: string | null;
  stage: WorkflowStage;
  event_time: string | null;
  location: string | null;
  locator: string | null;
  status: ClaimStatus;
  reliability: number;
  raw_text: string;
}

export interface ConflictDTO {
  id: string;
  conflict_type: ConflictType;
  claim_ids: string[];
  entity_name: string;
  predicate: string;
  explanation: string;
  severity: Severity;
  needs_review: boolean;
  is_real_problem: boolean;
  rule: string;
  claims: ConflictClaimDTO[];
}

export interface TwinState {
  entity_id: string;
  entity_name: string;
  attribute: string;
  value: string;
  valid_from: string | null;
  valid_to: string | null;
  claim_id: string;
  source_id: string;
  status: ClaimStatus;
  reliability: number;
  source_filename?: string | null;
  locator?: string | null;
}

export interface UploadAnalysisResponse {
  analysis_id: string;
  created_at: string;
  counts: AnalysisCounts;
  warnings: string[];
  documents: DocumentDTO[];
}

export interface AnalysisListItem {
  analysis_id: string;
  created_at: string;
  counts: AnalysisCounts;
}

export interface AnalysisListResponse {
  total_investigations: number;
  aggregate_counts: AnalysisCounts;
  investigations: AnalysisListItem[];
}

export interface AnalysisDetailResponse {
  analysis_id: string;
  created_at: string;
  counts: AnalysisCounts;
  documents: DocumentDTO[];
  entities: Entity[];
  claims: Claim[];
  conflicts: ConflictDTO[];
  twin_states: TwinState[];
  warnings: string[];
}

export interface DeleteAnalysisResponse {
  analysis_id: string;
  deleted: boolean;
}

export interface GraphResponse {
  analysis_id: string;
  nodes: Array<{
    id: string;
    type: string;
    position: { x: number; y: number };
    data: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    label: string;
    type: string;
    animated: boolean;
    data: Record<string, unknown>;
  }>;
  statistics: {
    nodes: number;
    edges: number;
    documents: number;
    entities: number;
    claims: number;
    conflicts: number;
  };
}

export interface ConflictsResponse {
  analysis_id: string;
  total: number;
  real_problem_count: number;
  conflicts: ConflictDTO[];
}

export interface DigitalTwinEntityView {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
  states: TwinState[];
  current_attributes: Record<string, TwinState>;
}

export interface DigitalTwinResponse {
  analysis_id: string;
  summary: Record<string, number>;
  entities: DigitalTwinEntityView[];
  states: TwinState[];
}

export interface Citation {
  source_id: string;
  filename: string;
  snippet: string;
  locator: string | null;
  reliability: number;
  claim_id?: string | null;
}

export interface AskResponse {
  analysis_id: string;
  question: string;
  status: AnswerStatus;
  answer_text: string;
  confidence: number;
  citations: Citation[];
  conflict_ids: string[];
  excluded_claim_ids: string[];
  used_llm: boolean;
  model?: string | null;
  notes: string[];
}

export interface BriefResponse {
  analysis_id: string;
  summary: string;
  highlights: string[];
  used_llm: boolean;
  model: string;
  notes: string[];
}

export interface ForensicDocumentDTO extends DocumentDTO {
  raw_text: string;
}

export interface ForensicsResponse {
  analysis_id: string;
  total_documents: number;
  suspicious_documents: number;
  total_flags: number;
  documents: ForensicDocumentDTO[];
}
