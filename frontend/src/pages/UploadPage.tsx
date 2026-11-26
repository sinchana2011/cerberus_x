import * as React from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  Play,
  ShieldAlert,
  Trash2,
  UploadCloud,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { useNotifications } from "@/context/NotificationContext";
import { extractApiError, uploadEvidenceFiles } from "@/lib/api";
import type { UploadAnalysisResponse } from "@/types/cerberus";

const SUPPORTED_ACCEPT =
  ".pdf,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.gif,.webp,.csv,.xlsx,.xls,.json,.txt,.md,.log";

export function UploadPage() {
  const { health, selectAnalysis, loadDemoDataset, demoLoading } = useAnalysis();
  const { notify } = useNotifications();

  const [files, setFiles] = React.useState<File[]>([]);
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [lastUpload, setLastUpload] = React.useState<UploadAnalysisResponse | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const next = Array.from(incoming);
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const merged = [...prev];
      for (const f of next) {
        if (!seen.has(`${f.name}:${f.size}`)) {
          merged.push(f);
        }
      }
      return merged;
    });
    setError(null);
  };

  const handleUpload = async () => {
    if (files.length === 0 || uploading) return;
    setUploading(true);
    setProgress(0);
    setError(null);
    try {
      const res = await uploadEvidenceFiles(files, setProgress);
      setLastUpload(res);
      const ok = await selectAnalysis(res.analysis_id);
      if (!ok) {
        throw new Error("Upload succeeded, but analysis details could not be retrieved.");
      }
      notify(
        "success",
        "Evidence pipeline completed",
        `${res.counts.documents} document(s) · ${res.counts.claims} claim(s) · ${res.counts.conflicts} conflict(s)`
      );
      setFiles([]);
      setProgress(100);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      const msg = extractApiError(err);
      setError(msg);
      notify("error", "Ingestion failed", msg);
    } finally {
      setUploading(false);
    }
  };

  const handleRunDemo = async () => {
    setError(null);
    const id = await loadDemoDataset();
    if (id) {
      notify("success", "Demo dataset processed", `Investigation ${id} saved to SQLite.`);
    } else {
      const msg = "Could not run demo dataset. Check backend connectivity.";
      setError(msg);
      notify("error", "Demo failed", msg);
    }
  };

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="Multimodal Ingestion"
        title="Upload Evidence"
        description="Ingest PDFs, images, spreadsheets, JSON datasets, and text logs into a unified SQLite investigation."
        actions={
          <Button variant="outline" onClick={() => void handleRunDemo()} disabled={demoLoading || uploading}>
            <Play className="h-4 w-4 text-[#C87620]" />
            {demoLoading ? "Processing Demo..." : "Run 5-Case Demo Dataset"}
          </Button>
        }
      />

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <div className="font-semibold">Ingestion Error</div>
            <div className="mt-0.5 text-xs opacity-90">{error}</div>
          </div>
        </Alert>
      )}

      {/* Dropzone */}
      <Card>
        <CardContent className="p-6">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addFiles(e.dataTransfer.files);
            }}
            onClick={() => inputRef.current?.click()}
            className={`cursor-pointer rounded-xl border-2 border-dashed px-6 py-12 text-center transition-all ${
              dragging
                ? "border-[#C87620] bg-[#C87620]/8"
                : "border-[#D9B98C] bg-[#F6F5F0]/60 hover:border-[#C87620]"
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={SUPPORTED_ACCEPT}
              disabled={uploading}
              onChange={(e) => addFiles(e.target.files)}
              className="hidden"
            />
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#C87620]/10 text-[#C87620] ring-1 ring-[#C87620]/25">
              <UploadCloud className="h-7 w-7" />
            </div>
            <h3 className="mt-4 text-base font-semibold text-[#292820]">
              Drag & drop evidence files here, or click to browse
            </h3>
            <p className="mt-1.5 text-xs text-[#77736A]">
              Supported:{" "}
              {(health?.supported_extensions?.length
                ? health.supported_extensions
                : [".pdf", ".png", ".jpg", ".csv", ".xlsx", ".xls", ".json", ".txt", ".md"]
              )
                .map((e) => e.replace(".", "").toUpperCase())
                .join(" · ")}
            </p>
            {!health?.ocr_available && (
              <p className="mt-2 text-[11px] text-[#94661F]">
                Note: Tesseract OCR is currently unavailable; images will be ingested without OCR text extraction.
              </p>
            )}
          </div>

          {files.length > 0 && (
            <div className="mt-6 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-[#C87620]">
                  Queued Files ({files.length})
                </h4>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setFiles([]);
                    if (inputRef.current) inputRef.current.value = "";
                  }}
                  disabled={uploading}
                >
                  Clear Queue
                </Button>
              </div>

              <div className="space-y-2">
                {files.map((file, idx) => (
                  <div
                    key={`${file.name}-${file.size}`}
                    className="flex items-center justify-between gap-3 rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 px-4 py-3"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <FileText className="h-4 w-4 shrink-0 text-[#C87620]" />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-[#292820]">
                          {file.name}
                        </div>
                        <div className="text-xs text-[#77736A]">
                          {(file.size / 1024).toFixed(1)} KB ·{" "}
                          {file.name.split(".").pop()?.toUpperCase() || "FILE"}
                        </div>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={uploading}
                      onClick={() => setFiles((prev) => prev.filter((_, i) => i !== idx))}
                      aria-label={`Remove ${file.name}`}
                    >
                      <Trash2 className="h-4 w-4 text-[#C65D50]" />
                    </Button>
                  </div>
                ))}
              </div>

              {uploading && (
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-[#77736A]">
                    <span>Uploading & running extraction, graph, and conflict analysis...</span>
                    <span className="font-mono font-medium text-[#C87620]">{progress}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[#E8E4DA]">
                    <div
                      className="h-full rounded-full bg-[#C87620] transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}

              <Button onClick={() => void handleUpload()} disabled={uploading} className="w-full">
                <UploadCloud className="h-4 w-4" />
                {uploading ? "Analyzing Evidence Pipeline..." : "Upload & Analyze"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extraction & Pipeline Outcome */}
      {lastUpload && (
        <Card className="border-[#638568]/40">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-[#638568]" />
                <CardTitle>Investigation Persisted: {lastUpload.analysis_id}</CardTitle>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm" variant="outline">
                  <Link to="/graph">
                    Evidence Graph <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
                <Button asChild size="sm" variant="outline">
                  <Link to="/conflicts">
                    Conflicts ({lastUpload.counts.conflicts}) <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
                <Button asChild size="sm">
                  <Link to="/ask">
                    Ask CERBERUS <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              </div>
            </div>
            <CardDescription>
              {lastUpload.counts.documents} documents · {lastUpload.counts.entities} entities ·{" "}
              {lastUpload.counts.claims} claims · {lastUpload.counts.conflicts} conflicts ·{" "}
              {lastUpload.counts.twin_states} twin states
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {lastUpload.documents.map((doc) => (
              <div
                key={doc.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 px-4 py-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[#292820]">{doc.filename}</span>
                    <Badge variant="info">{doc.file_type.toUpperCase()}</Badge>
                    <Badge variant="neutral">{doc.extraction_method}</Badge>
                  </div>
                  {doc.warnings.length > 0 && (
                    <div className="mt-1 text-xs text-[#94661F]">{doc.warnings.join(" · ")}</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-[#77736A]">
                    Rel: {Math.round(doc.reliability * 100)}%
                  </span>
                  {doc.is_suspicious ? (
                    <Badge variant="danger">
                      <ShieldAlert className="h-3 w-3" /> Suspicious ({doc.flags.length})
                    </Badge>
                  ) : (
                    <Badge variant="success">Extracted</Badge>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default UploadPage;
