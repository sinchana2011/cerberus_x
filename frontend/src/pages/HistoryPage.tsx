import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Database, ExternalLink, RefreshCw, Search, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAnalysis } from "@/context/AnalysisContext";
import { useNotifications } from "@/context/NotificationContext";

export function HistoryPage() {
  const navigate = useNavigate();
  const {
    history,
    historyLoading,
    aggregateCounts,
    activeAnalysisId,
    refreshHistory,
    selectAnalysis,
    deleteAnalysisById,
  } = useAnalysis();
  const { notify } = useNotifications();

  const [search, setSearch] = React.useState("");
  const [dateFilter, setDateFilter] = React.useState("");
  const [confirmDeleteId, setConfirmDeleteId] = React.useState<string | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return history.filter((item) => {
      if (q && !item.analysis_id.toLowerCase().includes(q)) return false;
      if (dateFilter && !item.created_at.startsWith(dateFilter)) return false;
      return true;
    });
  }, [dateFilter, history, search]);

  const handleOpen = async (id: string) => {
    const ok = await selectAnalysis(id);
    if (ok) {
      notify("success", "Investigation loaded", `Switched to ${id}`);
      navigate("/");
    } else {
      notify("error", "Load failed", `Could not load ${id}`);
    }
  };

  const handleDelete = async (id: string) => {
    setDeleting(true);
    const ok = await deleteAnalysisById(id);
    setDeleting(false);
    setConfirmDeleteId(null);
    if (ok) {
      notify("success", "Analysis deleted", `${id} removed from SQLite.`);
    } else {
      notify("error", "Delete failed", `Could not delete ${id}.`);
    }
  };

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="SQLite Persistence"
        title="Analysis History"
        description="Browse, reopen, and manage persistent investigations stored in your local SQLite database."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refreshHistory()}
            disabled={historyLoading}
          >
            <RefreshCw className={`h-4 w-4 ${historyLoading ? "animate-spin" : ""}`} />
            Refresh SQLite
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {[
          ["Investigations", history.length],
          ["Total Documents", aggregateCounts.documents],
          ["Total Entities", aggregateCounts.entities],
          ["Total Claims", aggregateCounts.claims],
          ["Total Conflicts", aggregateCounts.conflicts],
          ["Twin States", aggregateCounts.twin_states],
        ].map(([label, val]) => (
          <Card key={String(label)}>
            <CardContent className="p-4">
              <div className="text-xs text-slate-400">{label}</div>
              <div className="mt-1 text-2xl font-bold text-cyan-300">{val}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-4 w-4 text-cyan-400" />
              Saved SQLite Investigations ({filtered.length})
            </CardTitle>
            <CardDescription>Persisted across backend and browser restarts</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search analysis ID..."
                className="h-9 w-48 rounded-lg border border-slate-700 bg-[#071026] pl-9 pr-3 text-xs text-white outline-none focus:border-cyan-500"
              />
            </div>
            <input
              type="date"
              aria-label="Filter by date"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="h-9 rounded-lg border border-slate-700 bg-[#071026] px-3 text-xs text-slate-200 outline-none focus:border-cyan-500"
            />
            {dateFilter && (
              <Button variant="ghost" size="sm" onClick={() => setDateFilter("")}>
                Clear Date
              </Button>
            )}
          </div>
        </CardHeader>

        <CardContent>
          {filtered.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-400">
              No SQLite investigations match your filter.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Analysis ID</TableHead>
                  <TableHead>Created (UTC)</TableHead>
                  <TableHead>Docs</TableHead>
                  <TableHead>Entities</TableHead>
                  <TableHead>Claims</TableHead>
                  <TableHead>Conflicts</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((item) => {
                  const isActive = item.analysis_id === activeAnalysisId;
                  return (
                    <TableRow key={item.analysis_id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-semibold text-cyan-300">
                            {item.analysis_id}
                          </span>
                          {isActive && <Badge variant="default">Active</Badge>}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-slate-400">
                        {item.created_at.replace("T", " ").slice(0, 19)}
                      </TableCell>
                      <TableCell>{item.counts.documents}</TableCell>
                      <TableCell>{item.counts.entities}</TableCell>
                      <TableCell>{item.counts.claims}</TableCell>
                      <TableCell>
                        <Badge variant={item.counts.conflicts > 0 ? "danger" : "neutral"}>
                          {item.counts.conflicts}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void handleOpen(item.analysis_id)}
                          >
                            <ExternalLink className="h-3.5 w-3.5" /> Open
                          </Button>
                          {confirmDeleteId === item.analysis_id ? (
                            <div className="flex items-center gap-1.5">
                              <Button
                                size="sm"
                                variant="destructive"
                                disabled={deleting}
                                onClick={() => void handleDelete(item.analysis_id)}
                              >
                                Confirm
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setConfirmDeleteId(null)}
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setConfirmDeleteId(item.analysis_id)}
                              aria-label={`Delete ${item.analysis_id}`}
                            >
                              <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default HistoryPage;
