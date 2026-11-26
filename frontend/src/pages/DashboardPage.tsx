import * as React from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  FileText,
  GitCompare,
  Network,
  ShieldAlert,
  Sparkles,
  UploadCloud,
  Users,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NoAnalysisEmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { useNotifications } from "@/context/NotificationContext";
import { extractApiError, generateAnalysisBrief } from "@/lib/api";
import type { BriefResponse } from "@/types/cerberus";

const MODALITY_COLORS = ["#C87620", "#638568", "#D49A45", "#8C7A65", "#C65D50", "#D9B98C"];

const TOOLTIP_STYLE = {
  backgroundColor: "#FFFFFF",
  border: "1px solid #E8E4DA",
  borderRadius: "12px",
  color: "#292820",
  fontSize: "12px",
  boxShadow: "0 4px 12px rgba(41, 40, 32, 0.08)",
};

export function DashboardPage() {
  const {
    healthError,
    activeAnalysisId,
    activeAnalysis,
    history,
    aggregateCounts,
    selectAnalysis,
  } = useAnalysis();
  const { notify } = useNotifications();

  const [brief, setBrief] = React.useState<BriefResponse | null>(null);
  const [briefLoading, setBriefLoading] = React.useState(false);

  React.useEffect(() => {
    setBrief(null);
  }, [activeAnalysisId]);

  const handleGenerateBrief = async () => {
    if (!activeAnalysisId) return;
    setBriefLoading(true);
    try {
      const res = await generateAnalysisBrief(activeAnalysisId);
      setBrief(res);
      notify(
        "success",
        res.used_llm ? `Brief synthesized (${res.model})` : "Deterministic brief generated",
        res.used_llm
          ? "Local Ollama summarized grounded evidence."
          : "Generated from deterministic evidence metrics."
      );
    } catch (err) {
      notify("error", "Brief generation failed", extractApiError(err));
    } finally {
      setBriefLoading(false);
    }
  };

  const docs = activeAnalysis?.documents ?? [];
  const claims = activeAnalysis?.claims ?? [];
  const conflicts = activeAnalysis?.conflicts ?? [];

  const suspiciousDocs = docs.filter((d) => d.is_suspicious).length;
  const verifiedClaims = claims.filter((c) => c.status === "verified").length;
  const disputedClaims = claims.filter((c) => c.status === "disputed").length;
  const realConflicts = conflicts.filter((c) => c.is_real_problem).length;

  const modalityData = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of docs) {
      const key = d.file_type.toUpperCase();
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries()).map(([name, value]) => ({ name, value }));
  }, [docs]);

  const conflictData = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const c of conflicts) {
      const key = c.conflict_type.replace(/_/g, " ");
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries()).map(([name, count]) => ({ name, count }));
  }, [conflicts]);

  const reliabilityData = React.useMemo(
    () =>
      docs.map((d) => ({
        name: d.filename.length > 18 ? `${d.filename.slice(0, 16)}…` : d.filename,
        fullName: d.filename,
        reliability: Math.round(d.reliability * 100),
        suspicious: d.is_suspicious,
      })),
    [docs]
  );

  const activityData = React.useMemo(
    () =>
      [...history]
        .slice(0, 8)
        .reverse()
        .map((item) => ({
          id: item.analysis_id.slice(0, 10),
          documents: item.counts.documents,
          claims: item.counts.claims,
          conflicts: item.counts.conflicts,
        })),
    [history]
  );

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="CERBERUS-X · Command Overview"
        title="Evidence Intelligence Dashboard"
        description="Real-time multimodal ingestion telemetry, cross-modal contradiction metrics, and SQLite investigation state."
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <Link to="/upload">
                <UploadCloud className="h-4 w-4 text-[#C87620]" />
                Ingest Evidence
              </Link>
            </Button>
            {activeAnalysis && (
              <Button
                size="sm"
                onClick={() => void handleGenerateBrief()}
                disabled={briefLoading}
              >
                <Sparkles className="h-4 w-4" />
                {briefLoading ? "Synthesizing..." : "Generate Intelligence Brief"}
              </Button>
            )}
          </>
        }
      />

      {healthError && (
        <Alert variant="destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <div className="font-semibold">Backend Connection Unavailable</div>
            <div className="mt-0.5 text-xs opacity-90">{healthError}</div>
          </div>
        </Alert>
      )}

      {!activeAnalysis ? (
        <NoAnalysisEmptyState />
      ) : (
        <>
          {/* Primary KPI Strip */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-7">
            {[
              {
                label: "Documents",
                value: activeAnalysis.counts.documents,
                sub: `${aggregateCounts.documents} total in DB`,
                icon: FileText,
                accent: "text-[#C87620] bg-[#C87620]/10 border-[#C87620]/25",
              },
              {
                label: "Entities",
                value: activeAnalysis.counts.entities,
                sub: "Resolved canonical",
                icon: Users,
                accent: "text-[#7A5226] bg-[#D9B98C]/25 border-[#D9B98C]",
              },
              {
                label: "Total Claims",
                value: activeAnalysis.counts.claims,
                sub: "Extracted facts",
                icon: Network,
                accent: "text-[#77736A] bg-[#F6F5F0] border-[#E8E4DA]",
              },
              {
                label: "Verified Claims",
                value: verifiedClaims,
                sub: "Untainted sources",
                icon: CheckCircle2,
                accent: "text-[#48664D] bg-[#638568]/12 border-[#638568]/30",
              },
              {
                label: "Disputed Claims",
                value: disputedClaims,
                sub: "In real conflicts",
                icon: Activity,
                accent: "text-[#94661F] bg-[#D49A45]/15 border-[#D49A45]/35",
              },
              {
                label: "Conflicts",
                value: activeAnalysis.counts.conflicts,
                sub: `${realConflicts} real contradictions`,
                icon: GitCompare,
                accent: "text-[#A6463B] bg-[#C65D50]/12 border-[#C65D50]/30",
              },
              {
                label: "Suspicious Docs",
                value: suspiciousDocs,
                sub: "Quarantined signals",
                icon: ShieldAlert,
                accent:
                  suspiciousDocs > 0
                    ? "text-[#A6463B] bg-[#C65D50]/12 border-[#C65D50]/30"
                    : "text-[#48664D] bg-[#638568]/12 border-[#638568]/30",
              },
            ].map((kpi) => {
              const Icon = kpi.icon;
              return (
                <Card key={kpi.label} className="hover:border-[#D9B98C]">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-[#77736A]">{kpi.label}</span>
                      <span className={`rounded-[10px] border p-1.5 ${kpi.accent}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                    </div>
                    <div className="mt-2.5 text-2xl font-bold tracking-tight text-[#292820]">
                      {kpi.value}
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-[#77736A]">{kpi.sub}</div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Executive Brief (Ollama + Deterministic) */}
          {brief && (
            <Card className="border-[#D9B98C] bg-white">
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <BrainCircuit className="h-4 w-4 text-[#C87620]" />
                    <CardTitle>Intelligence Briefing</CardTitle>
                  </div>
                  <Badge variant={brief.used_llm ? "info" : "default"}>
                    {brief.used_llm ? `Ollama · ${brief.model}` : "Deterministic Digest"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm leading-relaxed text-[#292820]">{brief.summary}</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {brief.highlights.map((h, i) => (
                    <div
                      key={i}
                      className="rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] px-3 py-2 text-xs text-[#292820]"
                    >
                      {h}
                    </div>
                  ))}
                </div>
                {brief.notes.length > 0 && (
                  <p className="text-[11px] text-[#77736A]">{brief.notes.join(" · ")}</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* 4 Interactive Recharts Visualizations */}
          <div className="grid gap-5 lg:grid-cols-2">
            {/* 1. Documents by Type */}
            <Card>
              <CardHeader>
                <CardTitle>Documents by Modality</CardTitle>
                <CardDescription>Format breakdown in active investigation</CardDescription>
              </CardHeader>
              <CardContent className="h-64">
                {modalityData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={modalityData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={52}
                        outerRadius={86}
                        paddingAngle={3}
                      >
                        {modalityData.map((entry, idx) => (
                          <Cell
                            key={entry.name}
                            fill={MODALITY_COLORS[idx % MODALITY_COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-[#77736A]">
                    No document modality data
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 2. Conflict Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>Conflict & Temporal Distribution</CardTitle>
                <CardDescription>Deterministic classifications across extracted claims</CardDescription>
              </CardHeader>
              <CardContent className="h-64">
                {conflictData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={conflictData} margin={{ top: 8, right: 12, left: -12, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DA" />
                      <XAxis
                        dataKey="name"
                        tick={{ fill: "#77736A", fontSize: 11 }}
                        angle={-15}
                        textAnchor="end"
                      />
                      <YAxis allowDecimals={false} tick={{ fill: "#77736A", fontSize: 11 }} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="count" fill="#C87620" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-[#77736A]">
                    No conflicts detected in this investigation
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 3. Evidence Reliability */}
            <Card>
              <CardHeader>
                <CardTitle>Source Reliability Scores (%)</CardTitle>
                <CardDescription>Computed provenance confidence minus security penalties</CardDescription>
              </CardHeader>
              <CardContent className="h-64">
                {reliabilityData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={reliabilityData}
                      layout="vertical"
                      margin={{ top: 4, right: 16, left: 10, bottom: 4 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DA" />
                      <XAxis type="number" domain={[0, 100]} tick={{ fill: "#77736A", fontSize: 11 }} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={120}
                        tick={{ fill: "#292820", fontSize: 11 }}
                      />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="reliability" radius={[0, 6, 6, 0]}>
                        {reliabilityData.map((entry) => (
                          <Cell
                            key={entry.fullName}
                            fill={entry.suspicious ? "#C65D50" : "#638568"}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-[#77736A]">
                    No documents scored
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 4. SQLite Analysis Activity */}
            <Card>
              <CardHeader>
                <CardTitle>SQLite Investigation Activity</CardTitle>
                <CardDescription>Saved investigations across local persistence store</CardDescription>
              </CardHeader>
              <CardContent className="h-64">
                {activityData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={activityData} margin={{ top: 8, right: 12, left: -12, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DA" />
                      <XAxis dataKey="id" tick={{ fill: "#77736A", fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fill: "#77736A", fontSize: 11 }} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="documents" fill="#638568" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="claims" fill="#D9B98C" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="conflicts" fill="#C87620" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-[#77736A]">
                    No historical runs stored yet
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Recent Activity Lists */}
          <div className="grid gap-5 lg:grid-cols-3">
            {/* Uploaded Documents */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                <div>
                  <CardTitle>Ingested Sources</CardTitle>
                  <CardDescription>{docs.length} document(s)</CardDescription>
                </div>
                <Link to="/forensics" className="text-xs font-medium text-[#C87620] hover:underline">
                  Inspect <ArrowRight className="inline h-3 w-3" />
                </Link>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {docs.slice(0, 5).map((d) => (
                  <div
                    key={d.id}
                    className="flex items-center justify-between gap-2 rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold text-[#292820]">
                        {d.filename}
                      </div>
                      <div className="text-[11px] text-[#77736A]">
                        {d.file_type.toUpperCase()} · rel {Math.round(d.reliability * 100)}%
                      </div>
                    </div>
                    <Badge variant={d.is_suspicious ? "danger" : "success"}>
                      {d.is_suspicious ? "Flagged" : "Clean"}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Latest Conflicts */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                <div>
                  <CardTitle>Detected Conflicts</CardTitle>
                  <CardDescription>{realConflicts} real problem(s)</CardDescription>
                </div>
                <Link to="/conflicts" className="text-xs font-medium text-[#C87620] hover:underline">
                  View all <ArrowRight className="inline h-3 w-3" />
                </Link>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {conflicts.length === 0 ? (
                  <div className="text-xs text-[#77736A]">No conflicts detected.</div>
                ) : (
                  conflicts.slice(0, 4).map((c) => (
                    <div
                      key={c.id}
                      className="rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs font-semibold text-[#292820]">
                          {c.entity_name}
                        </span>
                        <Badge variant={c.is_real_problem ? "danger" : "info"}>
                          {c.conflict_type.replace(/_/g, " ")}
                        </Badge>
                      </div>
                      <p className="mt-1 line-clamp-2 text-[11px] text-[#77736A]">
                        {c.explanation}
                      </p>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Recent SQLite Investigations */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                <div>
                  <CardTitle>Recent SQLite Runs</CardTitle>
                  <CardDescription>{history.length} saved analysis run(s)</CardDescription>
                </div>
                <Link to="/history" className="text-xs font-medium text-[#C87620] hover:underline">
                  History <ArrowRight className="inline h-3 w-3" />
                </Link>
              </CardHeader>
              <CardContent className="space-y-2">
                {history.slice(0, 5).map((item) => (
                  <button
                    key={item.analysis_id}
                    type="button"
                    onClick={() => void selectAnalysis(item.analysis_id)}
                    className={`flex w-full items-center justify-between rounded-[10px] border px-3 py-2 text-left transition ${
                      item.analysis_id === activeAnalysisId
                        ? "border-[#C87620]/50 bg-[#C87620]/10"
                        : "border-[#E8E4DA] bg-[#F6F5F0]/70 hover:border-[#D9B98C]"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="truncate font-mono text-xs font-semibold text-[#C87620]">
                        {item.analysis_id}
                      </div>
                      <div className="text-[11px] text-[#77736A]">
                        {item.counts.documents} docs · {item.counts.claims} claims ·{" "}
                        {item.counts.conflicts} conflicts
                      </div>
                    </div>
                    {item.analysis_id === activeAnalysisId && (
                      <Badge variant="default">Active</Badge>
                    )}
                  </button>
                ))}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

export default DashboardPage;
