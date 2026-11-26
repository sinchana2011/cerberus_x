import * as React from "react";
import { AlertTriangle, Clock, Cpu, GitCommitHorizontal, ShieldAlert } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NoAnalysisEmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { extractApiError, fetchDigitalTwin } from "@/lib/api";
import type { ClaimStatus, DigitalTwinResponse } from "@/types/cerberus";

function statusBadgeVariant(status: ClaimStatus) {
  if (status === "verified") return "success" as const;
  if (status === "disputed") return "danger" as const;
  if (status === "suspicious") return "danger" as const;
  if (status === "superseded") return "purple" as const;
  return "warning" as const;
}

export function DigitalTwinPage() {
  const { activeAnalysisId } = useAnalysis();
  const [twin, setTwin] = React.useState<DigitalTwinResponse | null>(null);
  const [selectedEntityId, setSelectedEntityId] = React.useState<string>("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!activeAnalysisId) {
      setTwin(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDigitalTwin(activeAnalysisId)
      .then((res) => {
        if (!cancelled) {
          setTwin(res);
          setSelectedEntityId((prev) =>
            prev && res.entities.some((e) => e.entity_id === prev)
              ? prev
              : res.entities[0]?.entity_id ?? ""
          );
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

  const activeEntity =
    twin?.entities.find((e) => e.entity_id === selectedEntityId) ?? twin?.entities[0] ?? null;

  const timelineChartData = React.useMemo(() => {
    if (!activeEntity) return [];
    return activeEntity.states.map((s, idx) => ({
      step: `${idx + 1}. ${s.attribute}`,
      reliability: Math.round(s.reliability * 100),
      status: s.status,
      value: s.value,
    }));
  }, [activeEntity]);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="Temporal State Engine"
        title="Entity Digital Twin"
        description="Chronological entity attribute trajectories distinguishing current, historical superseded, disputed, and quarantined states."
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
            Building digital twin state history...
          </CardContent>
        </Card>
      ) : !twin || twin.entities.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-[#77736A]">
            No entity state records were extracted in this investigation.
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Twin summary KPIs */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ["Entities", twin.summary.total_entities ?? twin.entities.length, "text-[#C87620]"],
              ["Total States", twin.summary.total_states ?? twin.states.length, "text-[#292820]"],
              ["Verified", twin.summary.verified_states ?? 0, "text-[#638568]"],
              ["Disputed", twin.summary.disputed_states ?? 0, "text-[#C65D50]"],
              ["Superseded", twin.summary.superseded_states ?? 0, "text-[#7A5226]"],
              ["Suspicious", twin.summary.suspicious_states ?? 0, "text-[#D49A45]"],
            ].map(([label, val, color]) => (
              <Card key={String(label)}>
                <CardContent className="p-4">
                  <div className="text-xs text-[#77736A]">{label}</div>
                  <div className={`mt-1 text-2xl font-bold ${color}`}>{val}</div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-5 lg:grid-cols-12">
            {/* Entity List */}
            <Card className="lg:col-span-4">
              <CardHeader className="pb-3">
                <CardTitle>Tracked Entities ({twin.entities.length})</CardTitle>
                <CardDescription>Select an entity to inspect its Digital Twin</CardDescription>
              </CardHeader>
              <CardContent className="max-h-[680px] space-y-2 overflow-y-auto">
                {twin.entities.map((ent) => {
                  const hasDisputed = ent.states.some((s) => s.status === "disputed");
                  return (
                    <button
                      key={ent.entity_id}
                      type="button"
                      onClick={() => setSelectedEntityId(ent.entity_id)}
                      className={`w-full rounded-[10px] border p-3 text-left transition ${
                        activeEntity?.entity_id === ent.entity_id
                          ? "border-[#C87620]/60 bg-[#C87620]/10"
                          : "border-[#E8E4DA] bg-[#F6F5F0]/70 hover:border-[#D9B98C]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-semibold text-[#292820]">
                          {ent.canonical_name}
                        </span>
                        <Badge variant={hasDisputed ? "danger" : "default"}>
                          {ent.entity_type}
                        </Badge>
                      </div>
                      <div className="mt-1 flex items-center justify-between text-[11px] text-[#77736A]">
                        <span className="font-mono">{ent.entity_id}</span>
                        <span>{ent.states.length} state(s)</span>
                      </div>
                      {ent.aliases.length > 0 && (
                        <div className="mt-1 truncate text-[11px] text-[#C87620]">
                          Aliases: {ent.aliases.join(", ")}
                        </div>
                      )}
                    </button>
                  );
                })}
              </CardContent>
            </Card>

            {/* Entity Digital Twin Detail */}
            {activeEntity && (
              <div className="space-y-5 lg:col-span-8">
                {/* Current Known Attributes */}
                <Card>
                  <CardHeader>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Cpu className="h-4 w-4 text-[#C87620]" />
                        <CardTitle>{activeEntity.canonical_name}</CardTitle>
                      </div>
                      <Badge variant="info" className="font-mono">
                        {activeEntity.entity_id}
                      </Badge>
                    </div>
                    <CardDescription>
                      Latest known usable attribute states (disputed and unverified states are labeled explicitly).
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-3 sm:grid-cols-2">
                    {Object.entries(activeEntity.current_attributes).length === 0 ? (
                      <div className="col-span-2 text-xs text-[#77736A]">
                        No non-suspicious current states available for this entity.
                      </div>
                    ) : (
                      Object.entries(activeEntity.current_attributes).map(([attr, st]) => (
                        <div
                          key={attr}
                          className="rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 p-3.5"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-xs text-[#77736A]">{attr}</span>
                            <Badge variant={statusBadgeVariant(st.status)}>{st.status}</Badge>
                          </div>
                          <div className="mt-1.5 text-base font-bold text-[#292820]">{st.value}</div>
                          <div className="mt-1 text-[11px] text-[#77736A]">
                            {st.valid_from ? st.valid_from.replace("T", " ") : "Undated"} ·{" "}
                            {st.source_filename ?? st.source_id}
                            {st.locator ? ` (${st.locator})` : ""}
                          </div>
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>

                {/* Attribute Reliability Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>State Reliability Trajectory (%)</CardTitle>
                    <CardDescription>Reliability score for each chronological state record</CardDescription>
                  </CardHeader>
                  <CardContent className="h-52">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={timelineChartData} margin={{ top: 8, right: 12, left: -12, bottom: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DA" />
                        <XAxis dataKey="step" tick={{ fill: "#77736A", fontSize: 10 }} />
                        <YAxis domain={[0, 100]} tick={{ fill: "#77736A", fontSize: 10 }} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#FFFFFF",
                            border: "1px solid #E8E4DA",
                            borderRadius: "12px",
                            color: "#292820",
                            fontSize: "12px",
                            boxShadow: "0 4px 12px rgba(41, 40, 32, 0.08)",
                          }}
                        />
                        <Bar dataKey="reliability" radius={[5, 5, 0, 0]}>
                          {timelineChartData.map((entry, idx) => (
                            <Cell
                              key={idx}
                              fill={
                                entry.status === "disputed" || entry.status === "suspicious"
                                  ? "#C65D50"
                                  : entry.status === "superseded"
                                  ? "#D49A45"
                                  : "#638568"
                              }
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Chronological State Timeline */}
                <Card>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-[#C87620]" />
                      <CardTitle>Chronological State Timeline ({activeEntity.states.length})</CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="relative space-y-4 border-l border-[#E8E4DA] pl-5">
                      {activeEntity.states.map((st) => (
                        <div
                          key={`${st.claim_id}-${st.attribute}`}
                          className={`relative rounded-xl border p-3.5 ${
                            st.status === "suspicious"
                              ? "border-[#C65D50]/45 bg-[#FDF5F4]"
                              : st.status === "disputed"
                              ? "border-[#D49A45]/50 bg-[#FCF7EE]"
                              : "border-[#E8E4DA] bg-[#F6F5F0]/70"
                          }`}
                        >
                          <span className="absolute -left-[27px] top-4 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-[#C87620] bg-white">
                            <GitCommitHorizontal className="h-2.5 w-2.5 text-[#C87620]" />
                          </span>
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-medium text-[#C87620]">
                                {st.attribute}
                              </span>
                              <span className="text-sm font-bold text-[#292820]">{st.value}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant={statusBadgeVariant(st.status)}>
                                {st.status === "suspicious" && (
                                  <ShieldAlert className="h-3 w-3" />
                                )}
                                {st.status}
                              </Badge>
                              <span className="font-mono text-[11px] text-[#77736A]">
                                Rel {Math.round(st.reliability * 100)}%
                              </span>
                            </div>
                          </div>

                          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[#77736A]">
                            <span>
                              Valid from:{" "}
                              <strong className="text-[#292820]">
                                {st.valid_from ? st.valid_from.replace("T", " ") : "Unknown"}
                              </strong>
                            </span>
                            <span>
                              Valid to:{" "}
                              <strong className="text-[#292820]">
                                {st.valid_to ? st.valid_to.replace("T", " ") : "Current / Open"}
                              </strong>
                            </span>
                            <span>
                              Source:{" "}
                              <strong className="text-[#292820]">
                                {st.source_filename ?? st.source_id}
                              </strong>
                              {st.locator ? ` (${st.locator})` : ""}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default DigitalTwinPage;
