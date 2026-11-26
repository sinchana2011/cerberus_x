import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Database,
  FileSearch,
  RefreshCw,
  ScanSearch,
  Server,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { API_BASE_URL } from "@/lib/api";

export function SettingsPage() {
  const { health, healthLoading, healthError, refreshHealth } = useAnalysis();

  const backendOk = health?.status === "ok";
  const ollamaOk = Boolean(health?.ollama_available);
  const modelOk = Boolean(health?.ollama_model_installed);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="Diagnostics & Local Runtime"
        title="System Settings & Health"
        description="Live verification of FastAPI backend, SQLite database, Ollama local model, and document extraction dependencies."
        actions={
          <Button variant="outline" size="sm" onClick={() => void refreshHealth()} disabled={healthLoading}>
            <RefreshCw className={`h-4 w-4 ${healthLoading ? "animate-spin" : ""}`} />
            Re-check Health
          </Button>
        }
      />

      {healthError && (
        <Alert variant="destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="text-xs">{healthError}</div>
        </Alert>
      )}

      <div className="grid gap-5 md:grid-cols-2">
        {/* FastAPI Backend */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Server className="h-4 w-4 text-[#C87620]" />
                Python FastAPI Backend
              </CardTitle>
              <Badge variant={backendOk ? "success" : "danger"}>
                {backendOk ? "ONLINE" : "OFFLINE"}
              </Badge>
            </div>
            <CardDescription>Endpoint: {API_BASE_URL}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-[#292820]">
            <div className="flex justify-between rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] p-3">
              <span className="text-[#77736A]">Service Name</span>
              <span className="font-mono">{health?.service ?? "cerberus-x"}</span>
            </div>
            <div className="flex justify-between rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] p-3">
              <span className="text-[#77736A]">Network Policy</span>
              <span className="font-medium text-[#48664D]">127.0.0.1 Localhost Isolated</span>
            </div>
          </CardContent>
        </Card>

        {/* SQLite */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Database className="h-4 w-4 text-[#C87620]" />
                SQLite Persistence
              </CardTitle>
              <Badge variant={backendOk ? "success" : "neutral"}>
                {health?.database?.toUpperCase() ?? "SQLITE"}
              </Badge>
            </div>
            <CardDescription>Local relational store for analyses, claims, conflicts & twin states</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-[#292820]">
            <div className="flex justify-between rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] p-3">
              <span className="text-[#77736A]">Foreign Key Cascade</span>
              <span className="font-medium text-[#48664D]">Enabled</span>
            </div>
            <div className="flex justify-between rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] p-3">
              <span className="text-[#77736A]">Cloud Sync</span>
              <span>Disabled (Offline Only)</span>
            </div>
          </CardContent>
        </Card>

        {/* Ollama Local AI */}
        <Card className={ollamaOk ? "border-[#638568]/45" : "border-[#D49A45]/50"}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <BrainCircuit className="h-4 w-4 text-[#C87620]" />
                Ollama Local LLM
              </CardTitle>
              <Badge variant={ollamaOk && modelOk ? "success" : "warning"}>
                {ollamaOk ? (modelOk ? "READY" : "MODEL MISSING") : "OFFLINE"}
              </Badge>
            </div>
            <CardDescription>Configured Model: {health?.ollama_model ?? "llama3.2:3b"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] p-3 text-[#292820]">
              {health?.ollama_message || "Run health check to inspect Ollama status."}
            </div>
            {!ollamaOk && (
              <Alert variant="info">
                <Activity className="mt-0.5 h-4 w-4 shrink-0 text-[#C87620]" />
                <div className="space-y-1 text-xs">
                  <div className="font-semibold text-[#292820]">Deterministic Reasoning Continues Normally</div>
                  <p className="text-[#77736A]">
                    When Ollama is offline, all extraction, conflict detection, Digital Twin, and Ask CERBERUS answers continue running deterministically without breaking. To enable LLM narrative synthesis, start Ollama locally (`ollama serve`) with `llama3.2:3b`.
                  </p>
                </div>
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Extraction & OCR */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <ScanSearch className="h-4 w-4 text-[#C87620]" />
                Extraction & OCR Engine
              </CardTitle>
              <Badge variant={health?.ocr_available ? "success" : "warning"}>
                {health?.ocr_available ? "OCR READY" : "OCR UNAVAILABLE"}
              </Badge>
            </div>
            <CardDescription>PyMuPDF · Pandas · Pillow · Tesseract (optional)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="flex items-start gap-2 rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] p-3 text-[#292820]">
              {health?.ocr_available ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#638568]" />
              ) : (
                <FileSearch className="mt-0.5 h-4 w-4 shrink-0 text-[#D49A45]" />
              )}
              <span>{health?.ocr_message ?? "Checking OCR availability..."}</span>
            </div>

            <div>
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#77736A]">
                Supported Formats
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(health?.supported_extensions ?? []).map((ext) => (
                  <Badge key={ext} variant="info" className="font-mono">
                    {ext}
                  </Badge>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default SettingsPage;
