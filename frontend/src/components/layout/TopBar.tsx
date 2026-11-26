import {
  Activity,
  BrainCircuit,
  Database,
  Menu,
  Play,
  RefreshCw,
  ShieldCheck,
  WifiOff,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAnalysis } from "@/context/AnalysisContext";
import { useNotifications } from "@/context/NotificationContext";

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const {
    health,
    healthLoading,
    refreshHealth,
    activeAnalysisId,
    history,
    selectAnalysis,
    loadDemoDataset,
    demoLoading,
  } = useAnalysis();
  const { notify } = useNotifications();
  const isOnline = health?.status === "ok";
  const ollamaOnline = Boolean(health?.ollama_available);

  const handleLoadDemo = async () => {
    const id = await loadDemoDataset();
    if (id) {
      notify("success", "Demo dataset analyzed", `Investigation ${id} is now active.`);
    } else {
      notify("error", "Failed to run demo", "Check backend availability on localhost:8000.");
    }
  };

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-slate-800/90 bg-[#071026]/90 px-4 backdrop-blur-md sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onOpenMobileNav}
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </Button>

        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h1 className="truncate text-sm font-semibold text-white sm:text-base">
              Multimodal Intelligence Command Center
            </h1>
            {activeAnalysisId && (
              <Badge variant="default" className="hidden font-mono sm:inline-flex">
                {activeAnalysisId}
              </Badge>
            )}
          </div>
          <p className="hidden text-xs text-slate-400 md:block">
            Cross-modal conflict reasoning · Knowledge graph · Traceable forensics
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {history.length > 0 && (
          <select
            aria-label="Switch active investigation"
            value={activeAnalysisId ?? ""}
            onChange={(e) => {
              if (e.target.value) {
                void selectAnalysis(e.target.value);
              }
            }}
            className="hidden h-8 max-w-[200px] rounded-lg border border-slate-700 bg-[#0b1736] px-2.5 font-mono text-xs text-slate-200 outline-none focus:border-cyan-500 xl:block"
          >
            {history.map((item) => (
              <option key={item.analysis_id} value={item.analysis_id}>
                {item.analysis_id} ({item.counts.documents}d / {item.counts.conflicts}c)
              </option>
            ))}
          </select>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={() => void handleLoadDemo()}
          disabled={demoLoading || !isOnline}
          title="Run built-in 5-case multimodal demo"
          className="hidden sm:inline-flex"
        >
          <Play className="h-3.5 w-3.5 text-cyan-400" />
          <span>{demoLoading ? "Running..." : "Run Demo"}</span>
        </Button>

        <Badge variant="neutral" className="hidden gap-1.5 md:inline-flex">
          <Database className="h-3 w-3 text-cyan-400" />
          <span>SQLite Local</span>
        </Badge>

        <Badge variant={ollamaOnline ? "purple" : "warning"} className="hidden gap-1.5 sm:inline-flex">
          <BrainCircuit className="h-3 w-3" />
          <span>{ollamaOnline ? `Ollama · ${health?.ollama_model}` : "Ollama Offline"}</span>
        </Badge>

        <Badge
          variant={healthLoading ? "neutral" : isOnline ? "success" : "danger"}
          className="gap-1.5"
        >
          {isOnline ? (
            <ShieldCheck className="h-3.5 w-3.5" />
          ) : healthLoading ? (
            <Activity className="h-3.5 w-3.5" />
          ) : (
            <WifiOff className="h-3.5 w-3.5" />
          )}
          <span>
            {healthLoading ? "Checking..." : isOnline ? "API Online" : "API Offline"}
          </span>
        </Badge>

        <Button
          variant="outline"
          size="icon"
          onClick={() => void refreshHealth()}
          disabled={healthLoading}
          title="Refresh system health"
          aria-label="Refresh system health"
          className="h-8 w-8"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${healthLoading ? "animate-spin" : ""}`} />
        </Button>
      </div>
    </header>
  );
}
