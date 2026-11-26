import * as React from "react";
import { AlertTriangle, CheckCircle2, Clock, Scale, ShieldAlert } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NoAnalysisEmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { extractApiError, fetchConflicts } from "@/lib/api";
import type { ConflictClaimDTO, ConflictDTO } from "@/types/cerberus";

function SourceClaimCard({
  label,
  claim,
}: {
  label: string;
  claim?: ConflictClaimDTO;
}) {
  if (!claim) {
    return (
      <Card className="border-slate-800/80">
        <CardContent className="p-5 text-xs text-slate-500">No claim record available.</CardContent>
      </Card>
    );
  }
  return (
    <Card className="border-slate-800 bg-[#091533]">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <Badge variant="info">{label}</Badge>
          <Badge variant="neutral">Reliability {Math.round(claim.reliability * 100)}%</Badge>
        </div>
        <CardTitle className="mt-2 text-base">
          {claim.source_filename ?? claim.source_id}
        </CardTitle>
        <CardDescription className="font-mono">
          {claim.locator ?? "Unknown locator"} {claim.source_label ? `· ${claim.source_label}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-slate-800 bg-[#060e23] p-2.5">
            <div className="text-[10px] uppercase text-slate-500">Claimed Value</div>
            <div className="mt-0.5 font-mono text-sm font-semibold text-cyan-300">
              {claim.value} {claim.unit ?? ""}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-[#060e23] p-2.5">
            <div className="text-[10px] uppercase text-slate-500">Timestamp</div>
            <div className="mt-0.5 font-mono text-slate-200">
              {claim.event_time ? claim.event_time.replace("T", " ") : "Undated"}
            </div>
          </div>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase text-slate-500">Source Excerpt</div>
          <div className="rounded-lg border border-slate-800 bg-[#060e23] p-2.5 font-mono text-[11px] leading-relaxed text-slate-300">
            {claim.raw_text}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function canBothBeTrue(conflict: ConflictDTO): { answer: string; detail: string; positive: boolean } {
  switch (conflict.conflict_type) {
    case "workflow_stage":
      return {
        answer: "Yes — Different Workflow Stages",
        detail: "Quantities belong to distinct stages (e.g. ordered vs dispatched) and reflect normal fulfilment progression.",
        positive: true,
      };
    case "temporal_change":
      return {
        answer: "Yes — State Changed Over Time",
        detail: "Both claims describe valid states at different timestamps; the later claim does not invalidate the earlier one.",
        positive: true,
      };
    case "compatible_different_time":
      return {
        answer: "Yes — Compatible Different Times",
        detail: "Timestamps are separated by enough time that both observations can be true.",
        positive: true,
      };
    case "duplicate":
      return {
        answer: "Repeated Claim (Same Source)",
        detail: "The same source repeated an identical statement; treated as duplication, not corroboration.",
        positive: true,
      };
    default:
      return {
        answer: "No — Real Contradiction / Impossible Timeline",
        detail: "Deterministic rules classify these claims as mutually incompatible; CERBERUS-X refuses to pick a winner automatically.",
        positive: false,
      };
  }
}

export function ConflictReasoningPage() {
  const { activeAnalysisId } = useAnalysis();
  const [conflicts, setConflicts] = React.useState<ConflictDTO[]>([]);
  const [selectedId, setSelectedId] = React.useState<string>("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!activeAnalysisId) {
      setConflicts([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchConflicts(activeAnalysisId)
      .then((res) => {
        if (!cancelled) {
          setConflicts(res.conflicts);
          setSelectedId(res.conflicts[0]?.id ?? "");
        }
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

  const active = conflicts.find((c) => c.id === selectedId) ?? conflicts[0] ?? null;

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="Deterministic Forensic Logic"
        title="Conflict Reasoning"
        description="Side-by-side Source A vs Source B evidence comparison with timeline plausibility and reliability weighting."
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
          <CardContent className="p-8 text-center text-sm text-slate-400">
            Loading conflict reasoning records...
          </CardContent>
        </Card>
      ) : conflicts.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-slate-400">
            No conflicts or temporal comparisons exist in this investigation.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-12">
          {/* Selector list */}
          <Card className="lg:col-span-4">
            <CardHeader className="pb-3">
              <CardTitle>Conflicts & Comparisons ({conflicts.length})</CardTitle>
              <CardDescription>Select an item to inspect reasoning</CardDescription>
            </CardHeader>
            <CardContent className="max-h-[650px] space-y-2 overflow-y-auto">
              {conflicts.map((cf) => (
                <button
                  key={cf.id}
                  type="button"
                  onClick={() => setSelectedId(cf.id)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    active?.id === cf.id
                      ? "border-cyan-400/60 bg-cyan-500/10"
                      : "border-slate-800 bg-[#071026] hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold text-white">
                      {cf.entity_name}
                    </span>
                    <Badge variant={cf.is_real_problem ? "danger" : "info"}>
                      {cf.conflict_type.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <div className="mt-1 font-mono text-[11px] text-slate-400">
                    {cf.predicate} · {cf.severity.toUpperCase()}
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>

          {/* Side-by-side comparator */}
          {active && (
            <div className="space-y-4 lg:col-span-8">
              <div className="grid gap-4 md:grid-cols-2">
                <SourceClaimCard label="Source A" claim={active.claims[0]} />
                <SourceClaimCard label="Source B" claim={active.claims[1]} />
              </div>

              {(() => {
                const compatibility = canBothBeTrue(active);
                const c0 = active.claims[0];
                const c1 = active.claims[1];
                const relDiff =
                  c0 && c1
                    ? `${Math.round(c0.reliability * 100)}% vs ${Math.round(c1.reliability * 100)}%`
                    : "N/A";

                return (
                  <Card className="border-cyan-500/25">
                    <CardHeader className="pb-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Scale className="h-4 w-4 text-cyan-400" />
                          <CardTitle>Deterministic Reasoning Verdict</CardTitle>
                        </div>
                        <Badge variant={active.is_real_problem ? "danger" : "success"}>
                          {active.conflict_type.replace(/_/g, " ").toUpperCase()}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4 text-xs">
                      <div className="rounded-lg border border-slate-800 bg-[#071026] p-3.5">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                          Why They Contradict / Differ
                        </div>
                        <p className="mt-1 text-sm leading-relaxed text-slate-100">
                          {active.explanation}
                        </p>
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="rounded-lg border border-slate-800 bg-[#071026] p-3.5">
                          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                            {compatibility.positive ? (
                              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                            ) : (
                              <ShieldAlert className="h-3.5 w-3.5 text-rose-400" />
                            )}
                            Could Both Be True?
                          </div>
                          <div className="mt-1 font-semibold text-white">{compatibility.answer}</div>
                          <p className="mt-1 text-slate-400">{compatibility.detail}</p>
                        </div>

                        <div className="rounded-lg border border-slate-800 bg-[#071026] p-3.5">
                          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                            <Clock className="h-3.5 w-3.5 text-cyan-400" />
                            Timeline & Reliability Analysis
                          </div>
                          <div className="mt-1 font-semibold text-white">
                            Reliability Comparison: {relDiff}
                          </div>
                          <p className="mt-1 text-slate-400">
                            Rule: <span className="text-slate-200">{active.rule || active.conflict_type}</span>.
                            Source reliability weights evidence strength but never overrides or resolves a real conflict.
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ConflictReasoningPage;
