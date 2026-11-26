import {
  AlertTriangle,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
  Cpu,
  FileSearch,
  GitBranch,
  History,
  LayoutDashboard,
  MessageSquareText,
  Scale,
  Settings,
  ShieldAlert,
  UploadCloud,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAnalysis } from "@/context/AnalysisContext";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/upload", label: "Upload Evidence", icon: UploadCloud },
  { to: "/graph", label: "Evidence Graph", icon: GitBranch },
  { to: "/conflicts", label: "Conflict Detection", icon: AlertTriangle },
  { to: "/reasoning", label: "Conflict Reasoning", icon: Scale },
  { to: "/digital-twin", label: "Digital Twin", icon: Cpu },
  { to: "/ask", label: "Ask CERBERUS", icon: MessageSquareText },
  { to: "/forensics", label: "Forensic Inspector", icon: ShieldAlert },
  { to: "/history", label: "Analysis History", icon: History },
  { to: "/settings", label: "System Settings", icon: Settings },
];

export function Sidebar({
  mobileOpen,
  onClose,
  collapsed,
  onToggleCollapse,
}: {
  mobileOpen: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const { health, activeAnalysisId, activeAnalysis } = useAnalysis();
  const backendOnline = health?.status === "ok";
  const ollamaOnline = Boolean(health?.ollama_available);

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/65 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col border-r border-slate-800/90 bg-[#071026] text-slate-200 transition-all duration-200 lg:static lg:translate-x-0",
          collapsed ? "w-20" : "w-64",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand */}
        <div className="flex h-16 items-center justify-between border-b border-slate-800/80 px-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/30 text-cyan-400 ring-1 ring-cyan-400/30">
              <FileSearch className="h-5 w-5" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="truncate text-sm font-bold tracking-wider text-white">
                  CERBERUS-X
                </div>
                <div className="truncate text-[11px] text-cyan-400/80">
                  Evidence Intelligence
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onToggleCollapse}
            className="hidden rounded-lg p-1.5 text-slate-400 hover:bg-slate-800/70 hover:text-cyan-300 lg:inline-flex"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-2.5 py-4" aria-label="Primary">
          {!collapsed && (
            <div className="px-2.5 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              Command Modules
            </div>
          )}
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onClick={onClose}
                title={collapsed ? item.label : undefined}
                className={({ isActive }) =>
                  cn(
                    "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150",
                    collapsed && "justify-center px-2",
                    isActive
                      ? "bg-gradient-to-r from-cyan-500/20 to-blue-600/15 text-white ring-1 ring-cyan-400/35"
                      : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      className={cn(
                        "h-4 w-4 shrink-0 transition-colors",
                        isActive ? "text-cyan-400" : "text-slate-400 group-hover:text-cyan-300"
                      )}
                    />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Live telemetry footer */}
        <div className="border-t border-slate-800/80 p-3">
          {collapsed ? (
            <div className="flex flex-col items-center gap-2.5 py-1">
              <span
                title={`Backend: ${backendOnline ? "Online" : "Offline"}`}
                className={cn(
                  "h-2.5 w-2.5 rounded-full",
                  backendOnline ? "bg-emerald-400" : "bg-rose-400"
                )}
              />
              <span
                title={`Ollama (${health?.ollama_model ?? "llama3.2:3b"}): ${
                  ollamaOnline ? "Online" : "Offline"
                }`}
                className={cn(
                  "h-2.5 w-2.5 rounded-full",
                  ollamaOnline ? "bg-purple-400" : "bg-amber-400"
                )}
              />
            </div>
          ) : (
            <div className="space-y-2.5 rounded-xl border border-slate-800 bg-[#0a1530]/90 p-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">FastAPI Backend</span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 font-medium",
                    backendOnline ? "text-emerald-400" : "text-rose-400"
                  )}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {backendOnline ? "ONLINE" : "OFFLINE"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 text-slate-400">
                  <BrainCircuit className="h-3.5 w-3.5 text-purple-400" />
                  Ollama ({health?.ollama_model ?? "llama3.2:3b"})
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 font-medium",
                    ollamaOnline ? "text-cyan-400" : "text-amber-400"
                  )}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {ollamaOnline ? "READY" : "OFFLINE"}
                </span>
              </div>

              <div className="border-t border-slate-800/80 pt-2">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">
                  Active Investigation
                </div>
                <div className="mt-0.5 truncate font-mono text-[11px] text-cyan-300">
                  {activeAnalysisId ?? "None selected"}
                </div>
                {activeAnalysis && (
                  <div className="mt-0.5 text-[10px] text-slate-400">
                    {activeAnalysis.counts.documents} docs · {activeAnalysis.counts.conflicts}{" "}
                    conflicts
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
