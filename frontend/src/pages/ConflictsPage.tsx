import * as React from "react";
import { AlertTriangle, LayoutGrid, Search, Table as TableIcon, X } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NoAnalysisEmptyState, PageHeader } from "@/components/ui/PageHeader";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAnalysis } from "@/context/AnalysisContext";
import { extractApiError, fetchConflicts } from "@/lib/api";
import type { ConflictDTO, ConflictType, Severity } from "@/types/cerberus";

const TYPE_OPTIONS: Array<{ value: "" | ConflictType; label: string }> = [
  { value: "", label: "All Types" },
  { value: "true_conflict", label: "True Conflict" },
  { value: "same_event_conflict", label: "Same Event Conflict" },
  { value: "impossible_timeline", label: "Impossible Timeline" },
  { value: "temporal_change", label: "Temporal Change" },
  { value: "workflow_stage", label: "Workflow Stage" },
  { value: "compatible_different_time", label: "Compatible Different Time" },
  { value: "duplicate", label: "Duplicate" },
];

export function ConflictsPage() {
  const { activeAnalysisId } = useAnalysis();
  const [conflicts, setConflicts] = React.useState<ConflictDTO[]>([]);
  const [realCount, setRealCount] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [typeFilter, setTypeFilter] = React.useState<"" | ConflictType>("");
  const [severityFilter, setSeverityFilter] = React.useState<"" | Severity>("");
  const [onlyReal, setOnlyReal] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [viewMode, setViewMode] = React.useState<"cards" | "table">("cards");
  const [selected, setSelected] = React.useState<ConflictDTO | null>(null);

  React.useEffect(() => {
    if (!activeAnalysisId) {
      setConflicts([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchConflicts(activeAnalysisId, {
      conflict_type: typeFilter || undefined,
      severity: severityFilter || undefined,
      only_real_problems: onlyReal || undefined,
    })
      .then((res) => {
        if (!cancelled) {
          setConflicts(res.conflicts);
          setRealCount(res.real_problem_count);
          setSelected((prev) =>
            prev ? res.conflicts.find((c) => c.id === prev.id) ?? null : null
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
  }, [activeAnalysisId, onlyReal, severityFilter, typeFilter]);

  const visible = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return conflicts;
    return conflicts.filter(
      (c) =>
        c.entity_name.toLowerCase().includes(q) ||
        c.predicate.toLowerCase().includes(q) ||
        c.explanation.toLowerCase().includes(q) ||
        c.claims.some((cl) => (cl.source_filename ?? "").toLowerCase().includes(q))
    );
  }, [conflicts, search]);

  return (
    <div className="animate-fade-in space-y-5">
      <PageHeader
        eyebrow="Cross-Modal Contradictions"
        title="Conflict Detection"
        description="Inspect deterministic contradictions, impossible timelines, workflow stage progressions, and temporal state changes."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant={viewMode === "cards" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("cards")}
            >
              <LayoutGrid className="h-4 w-4" /> Cards
            </Button>
            <Button
              variant={viewMode === "table" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("table")}
            >
              <TableIcon className="h-4 w-4" /> Table
            </Button>
          </div>
        }
      />

      {!activeAnalysisId ? (
        <NoAnalysisEmptyState />
      ) : (
        <>
          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="text-xs">{error}</div>
            </Alert>
          )}

          {/* Filters */}
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="flex flex-wrap items-center gap-2.5">
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#77736A]" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search entity, rule, source..."
                    className="h-9 w-56 rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] pl-9 pr-3 text-xs text-[#292820] placeholder:text-[#77736A] outline-none focus:border-[#C87620]"
                  />
                </div>

                <select
                  aria-label="Filter by conflict type"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as "" | ConflictType)}
                  className="h-9 rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] px-3 text-xs text-[#292820] outline-none focus:border-[#C87620]"
                >
                  {TYPE_OPTIONS.map((opt) => (
                    <option key={opt.label} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>

                <select
                  aria-label="Filter by severity"
                  value={severityFilter}
                  onChange={(e) => setSeverityFilter(e.target.value as "" | Severity)}
                  className="h-9 rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0] px-3 text-xs text-[#292820] outline-none focus:border-[#C87620]"
                >
                  <option value="">All Severities</option>
                  <option value="high">High Severity</option>
                  <option value="medium">Medium Severity</option>
                  <option value="low">Low Severity</option>
                </select>

                <button
                  type="button"
                  onClick={() => setOnlyReal((v) => !v)}
                  className={`h-9 rounded-[10px] border px-3 text-xs font-medium transition ${
                    onlyReal
                      ? "border-[#C65D50]/50 bg-[#C65D50]/12 text-[#A6463B]"
                      : "border-[#E8E4DA] bg-[#F6F5F0] text-[#77736A] hover:text-[#292820]"
                  }`}
                >
                  Real Contradictions Only ({realCount})
                </button>
              </div>

              <div className="text-xs text-[#77736A]">
                Showing <span className="font-semibold text-[#292820]">{visible.length}</span> conflict(s)
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-5 lg:grid-cols-12">
            <div className={selected ? "lg:col-span-7" : "lg:col-span-12"}>
              {loading ? (
                <Card>
                  <CardContent className="p-8 text-center text-sm text-[#77736A]">
                    Loading conflicts...
                  </CardContent>
                </Card>
              ) : visible.length === 0 ? (
                <Card>
                  <CardContent className="p-8 text-center text-sm text-[#77736A]">
                    No conflicts match the active filters.
                  </CardContent>
                </Card>
              ) : viewMode === "cards" ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {visible.map((c) => (
                    <Card
                      key={c.id}
                      onClick={() => setSelected(c)}
                      className={`cursor-pointer transition hover:border-[#D9B98C] ${
                        selected?.id === c.id ? "border-[#C87620] ring-1 ring-[#C87620]/30" : ""
                      }`}
                    >
                      <CardHeader className="pb-2">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <CardTitle>{c.entity_name}</CardTitle>
                            <CardDescription className="font-mono">{c.predicate}</CardDescription>
                          </div>
                          <div className="flex flex-wrap justify-end gap-1.5">
                            <Badge variant={c.is_real_problem ? "danger" : "info"}>
                              {c.conflict_type.replace(/_/g, " ")}
                            </Badge>
                            <Badge
                              variant={
                                c.severity === "high"
                                  ? "danger"
                                  : c.severity === "medium"
                                  ? "warning"
                                  : "neutral"
                              }
                            >
                              {c.severity}
                            </Badge>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <p className="text-xs leading-relaxed text-[#292820]">{c.explanation}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {c.claims.map((cl) => (
                            <span
                              key={cl.id}
                              className="rounded-md border border-[#E8E4DA] bg-[#F6F5F0] px-2 py-1 text-[11px] text-[#77736A]"
                            >
                              <span className="font-semibold text-[#C87620]">{cl.value}</span> ·{" "}
                              {cl.source_filename ?? cl.source_id}
                            </span>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              ) : (
                <Card>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Entity</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Severity</TableHead>
                        <TableHead>Values</TableHead>
                        <TableHead>Sources</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visible.map((c) => (
                        <TableRow
                          key={c.id}
                          onClick={() => setSelected(c)}
                          className={`cursor-pointer ${
                            selected?.id === c.id ? "bg-[#C87620]/8" : ""
                          }`}
                        >
                          <TableCell>
                            <div className="font-medium text-[#292820]">{c.entity_name}</div>
                            <div className="font-mono text-[11px] text-[#77736A]">{c.predicate}</div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={c.is_real_problem ? "danger" : "info"}>
                              {c.conflict_type.replace(/_/g, " ")}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                c.severity === "high"
                                  ? "danger"
                                  : c.severity === "medium"
                                  ? "warning"
                                  : "neutral"
                              }
                            >
                              {c.severity}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs text-[#C87620]">
                            {c.claims.map((cl) => cl.value).join(" vs ")}
                          </TableCell>
                          <TableCell className="text-xs text-[#77736A]">
                            {c.claims.map((cl) => cl.source_filename ?? cl.source_id).join(", ")}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              )}
            </div>

            {selected && (
              <Card className="lg:col-span-5">
                <CardHeader className="flex flex-row items-start justify-between space-y-0 border-b border-[#E8E4DA] pb-3">
                  <div>
                    <CardTitle>{selected.entity_name}</CardTitle>
                    <CardDescription className="font-mono">{selected.id}</CardDescription>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelected(null)}
                    className="rounded-lg p-1 text-[#77736A] hover:bg-[#F6F5F0] hover:text-[#292820]"
                    aria-label="Close detail panel"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </CardHeader>
                <CardContent className="space-y-4 pt-4 text-xs">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#77736A]">
                      Explanation
                    </div>
                    <p className="mt-1 leading-relaxed text-[#292820]">{selected.explanation}</p>
                  </div>

                  {selected.rule && (
                    <div className="rounded-[10px] border border-[#D9B98C] bg-[#FAF6EE] p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#C87620]">
                        Detection Rule
                      </div>
                      <p className="mt-1 text-[#292820]">{selected.rule}</p>
                    </div>
                  )}

                  <div className="space-y-2.5">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#77736A]">
                      Involved Claims ({selected.claims.length})
                    </div>
                    {selected.claims.map((cl) => (
                      <div
                        key={cl.id}
                        className="rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 p-3"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-[#C87620]">
                            {cl.value} {cl.unit ?? ""}
                          </span>
                          <Badge variant="neutral">Rel {Math.round(cl.reliability * 100)}%</Badge>
                        </div>
                        <div className="mt-1 text-[11px] text-[#77736A]">
                          {cl.source_filename ?? cl.source_id}
                          {cl.locator ? ` · ${cl.locator}` : ""}
                          {cl.event_time ? ` · ${cl.event_time}` : " · undated"}
                        </div>
                        <p className="mt-2 rounded-lg border border-[#E8E4DA] bg-white p-2 font-mono text-[11px] text-[#292820]">
                          {cl.raw_text}
                        </p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default ConflictsPage;
