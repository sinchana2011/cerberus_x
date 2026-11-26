import * as React from "react";
import { AlertTriangle, CheckCircle2, FileWarning, ShieldAlert, ShieldCheck } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NoAnalysisEmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { extractApiError, fetchForensics } from "@/lib/api";
import type { ForensicsResponse } from "@/types/cerberus";

export function ForensicsPage() {
  const { activeAnalysisId } = useAnalysis();
  const [forensics, setForensics] = React.useState<ForensicsResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!activeAnalysisId) {
      setForensics(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchForensics(activeAnalysisId)
      .then((res) => {
        if (!cancelled) setForensics(res);
      })
      .catch((err) => {
        if (!cancelled) setError(extractApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeAnalysisId]);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="Sanitization & Provenance Audit"
        title="Forensic Inspector"
        description="Inspect hidden PDF layers, prompt-injection heuristics, OCR confidence penalties, and raw extracted content."
      />

      {!activeAnalysisId ? (
        <NoAnalysisEmptyState />
      ) : error ? (
        <Alert variant="destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="text-xs">{error}</div>
        </Alert>
      ) : loading ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-[#77736A]">
            Loading forensic audit records...
          </CardContent>
        </Card>
      ) : !forensics ? null : (
        <>
          <Alert variant="info">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#C87620]" />
            <div className="text-xs">
              All suspicious segments (hidden white-on-white text, invisible render modes, or prompt injections) are quarantined with{" "}
              <span className="font-mono font-semibold text-[#C87620]">status=suspicious</span> and excluded from verified answers while remaining visible here for analyst review.
            </div>
          </Alert>

          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-[#77736A]">Inspected Documents</div>
                <div className="mt-1 text-2xl font-bold text-[#292820]">
                  {forensics.total_documents}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-[#77736A]">Suspicious Documents</div>
                <div className="mt-1 text-2xl font-bold text-[#C65D50]">
                  {forensics.suspicious_documents}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-[#77736A]">Security Flags Raised</div>
                <div className="mt-1 text-2xl font-bold text-[#D49A45]">
                  {forensics.total_flags}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            {forensics.documents.map((doc) => (
              <Card
                key={doc.id}
                className={doc.is_suspicious ? "border-[#C65D50]/50" : "border-[#E8E4DA]"}
              >
                <CardHeader>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        {doc.is_suspicious ? (
                          <ShieldAlert className="h-4 w-4 text-[#C65D50]" />
                        ) : (
                          <CheckCircle2 className="h-4 w-4 text-[#638568]" />
                        )}
                        <CardTitle className="text-base">{doc.filename}</CardTitle>
                      </div>
                      <CardDescription className="mt-1 font-mono">
                        {doc.file_type.toUpperCase()} · {doc.source_type} · {doc.extraction_method} · sha256:{" "}
                        {doc.sha256.slice(0, 14)}…
                      </CardDescription>
                    </div>

                    <div className="flex items-center gap-2">
                      <Badge variant="default">
                        Reliability {Math.round(doc.reliability * 100)}%
                      </Badge>
                      <Badge variant={doc.is_suspicious ? "danger" : "success"}>
                        {doc.is_suspicious ? "Quarantined Signals" : "Verified Clean"}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4 text-xs">
                  {/* Reliability progress */}
                  <div>
                    <div className="mb-1 flex justify-between text-[11px] text-[#77736A]">
                      <span>Source Reliability Score</span>
                      <span className="font-mono font-medium text-[#292820]">
                        {doc.reliability.toFixed(2)} / 1.00
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[#E8E4DA]">
                      <div
                        className={`h-full rounded-full ${
                          doc.is_suspicious ? "bg-[#C65D50]" : "bg-[#638568]"
                        }`}
                        style={{ width: `${Math.round(doc.reliability * 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Security Flags */}
                  {doc.flags.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-[#A6463B]">
                        Security Flags ({doc.flags.length})
                      </div>
                      {doc.flags.map((flag, fIdx) => (
                        <div
                          key={fIdx}
                          className="rounded-[10px] border border-[#C65D50]/35 bg-[#FDF5F4] p-3"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="flex items-center gap-1.5 font-semibold text-[#A6463B]">
                              <FileWarning className="h-3.5 w-3.5" />
                              {flag.kind.replace(/_/g, " ").toUpperCase()}
                            </span>
                            <div className="flex items-center gap-2">
                              {flag.page !== null && (
                                <Badge variant="neutral">Page {flag.page}</Badge>
                              )}
                              <Badge variant="danger">{flag.severity}</Badge>
                            </div>
                          </div>
                          <p className="mt-1 text-[#292820]">{flag.description}</p>
                          {flag.evidence && (
                            <pre className="mt-2 whitespace-pre-wrap rounded-lg border border-[#C65D50]/25 bg-white p-2 font-mono text-[11px] text-[#A6463B]">
                              {flag.evidence}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Warnings */}
                  {doc.warnings.length > 0 && (
                    <div className="rounded-[10px] border border-[#D49A45]/40 bg-[#FCF7EE] p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#94661F]">
                        Extraction & Sanitizer Warnings
                      </div>
                      <ul className="mt-1 list-disc space-y-1 pl-4 text-[#292820]">
                        {doc.warnings.map((w, wIdx) => (
                          <li key={wIdx}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Raw Text Viewer */}
                  <div>
                    <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#77736A]">
                      Original Extracted Text (Untrusted Evidence)
                    </div>
                    <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] p-3 font-mono text-[11px] leading-relaxed text-[#292820]">
                      {doc.raw_text || "(No text extracted)"}
                    </pre>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default ForensicsPage;
