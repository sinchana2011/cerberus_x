import axios from "axios";

import type {
  AnalysisDetailResponse,
  AnalysisListResponse,
  AskResponse,
  BriefResponse,
  ConflictType,
  ConflictsResponse,
  DeleteAnalysisResponse,
  DigitalTwinResponse,
  ForensicsResponse,
  GraphResponse,
  HealthResponse,
  Severity,
  UploadAnalysisResponse,
} from "@/types/cerberus";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60_000,
});

export function extractApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
    if (detail) return detail;
    if (error.code === "ERR_NETWORK") {
      return `Cannot reach local CERBERUS-X backend at ${API_BASE_URL}. Ensure FastAPI is running on localhost:8000.`;
    }
    return error.message || "Request failed";
  }
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>("/api/health");
  return data;
}

export async function uploadEvidenceFiles(
  files: File[],
  onProgress?: (percent: number) => void
): Promise<UploadAnalysisResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const { data } = await apiClient.post<UploadAnalysisResponse>("/api/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total) {
        onProgress(Math.round((evt.loaded * 100) / evt.total));
      }
    },
  });
  return data;
}

export async function runDemoAnalysis(): Promise<UploadAnalysisResponse> {
  const { data } = await apiClient.post<UploadAnalysisResponse>("/api/demo");
  return data;
}

export async function fetchAnalyses(): Promise<AnalysisListResponse> {
  const { data } = await apiClient.get<AnalysisListResponse>("/api/analyses");
  return data;
}

export async function fetchAnalysis(analysisId: string): Promise<AnalysisDetailResponse> {
  const { data } = await apiClient.get<AnalysisDetailResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}`
  );
  return data;
}

export async function deleteAnalysis(analysisId: string): Promise<DeleteAnalysisResponse> {
  const { data } = await apiClient.delete<DeleteAnalysisResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}`
  );
  return data;
}

export async function fetchGraph(analysisId: string): Promise<GraphResponse> {
  const { data } = await apiClient.get<GraphResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}/graph`
  );
  return data;
}

export async function fetchConflicts(
  analysisId: string,
  filters?: {
    conflict_type?: ConflictType;
    severity?: Severity;
    only_real_problems?: boolean;
  }
): Promise<ConflictsResponse> {
  const { data } = await apiClient.get<ConflictsResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}/conflicts`,
    { params: filters }
  );
  return data;
}

export async function fetchDigitalTwin(
  analysisId: string,
  entityId?: string
): Promise<DigitalTwinResponse> {
  const { data } = await apiClient.get<DigitalTwinResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}/digital-twin`,
    { params: entityId ? { entity_id: entityId } : undefined }
  );
  return data;
}

export async function askAnalysisQuestion(
  analysisId: string,
  question: string,
  useLlm = false
): Promise<AskResponse> {
  const { data } = await apiClient.post<AskResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}/ask`,
    { question, use_llm: useLlm }
  );
  return data;
}

export async function generateAnalysisBrief(analysisId: string): Promise<BriefResponse> {
  const { data } = await apiClient.post<BriefResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}/brief`
  );
  return data;
}

export async function fetchForensics(analysisId: string): Promise<ForensicsResponse> {
  const { data } = await apiClient.get<ForensicsResponse>(
    `/api/analysis/${encodeURIComponent(analysisId)}/forensics`
  );
  return data;
}
