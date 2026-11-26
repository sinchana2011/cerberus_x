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
          className="fixed inset-0 z-30 bg-[#292820]/30 backdrop-blur-xs lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col border-r border-[#E8E4DA] bg-white text-[#292820] transition-all duration-200 lg:static lg:translate-x-0",
          collapsed ? "w-20" : "w-64",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand */}
        <div className="flex h-16 items-center justify-between border-b border-[#E8E4DA] px-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[#D9B98C] bg-[#F6F5F0] text-[#C87620]">
              <FileSearch className="h-5 w-5" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="truncate text-sm font-bold tracking-wider text-[#C87620]">
                  CERBERUS-X
                </div>
                <div className="truncate text-[11px] text-[#77736A]">
                  Evidence Intelligence
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onToggleCollapse}
            className="hidden rounded-[10px] p-1.5 text-[#77736A] hover:bg-[#F6F5F0] hover:text-[#C87620] lg:inline-flex"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-2.5 py-4" aria-label="Primary">
          {!collapsed && (
            <div className="px-2.5 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#77736A]">
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
                    "group flex items-center gap-3 rounded-[10px] px-3 py-2 text-sm transition-all duration-150",
                    collapsed && "justify-center px-2",
                    isActive
                      ? "bg-[#C87620]/10 font-semibold text-[#C87620] ring-1 ring-[#C87620]/30"
                      : "font-medium text-[#77736A] hover:bg-[#F6F5F0] hover:text-[#292820]"
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      className={cn(
                        "h-4 w-4 shrink-0 transition-colors",
                        isActive ? "text-[#C87620]" : "text-[#77736A] group-hover:text-[#292820]"
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
        <div className="border-t border-[#E8E4DA] p-3">
          {collapsed ? (
            <div className="flex flex-col items-center gap-2.5 py-1">
              <span
                title={`Backend: ${backendOnline ? "Online" : "Offline"}`}
                className={cn(
                  "h-2.5 w-2.5 rounded-full",
                  backendOnline ? "bg-[#638568]" : "bg-[#C65D50]"
                )}
              />
              <span
                title={`Ollama (${health?.ollama_model ?? "llama3.2:3b"}): ${
                  ollamaOnline ? "Online" : "Offline"
                }`}
                className={cn(
                  "h-2.5 w-2.5 rounded-full",
                  ollamaOnline ? "bg-[#638568]" : "bg-[#D49A45]"
                )}
              />
            </div>
          ) : (
            <div className="space-y-2.5 rounded-xl border border-[#E8E4DA] bg-[#F6F5F0] p-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[#77736A]">FastAPI Backend</span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 font-medium",
                    backendOnline ? "text-[#48664D]" : "text-[#C65D50]"
                  )}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {backendOnline ? "ONLINE" : "OFFLINE"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 text-[#77736A]">
                  <BrainCircuit className="h-3.5 w-3.5 text-[#C87620]" />
                  Ollama ({health?.ollama_model ?? "llama3.2:3b"})
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 font-medium",
                    ollamaOnline ? "text-[#48664D]" : "text-[#94661F]"
                  )}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {ollamaOnline ? "READY" : "OFFLINE"}
                </span>
              </div>

              <div className="border-t border-[#E8E4DA] pt-2">
                <div className="text-[10px] uppercase tracking-wider text-[#77736A]">
                  Active Investigation
                </div>
                <div className="mt-0.5 truncate font-mono text-[11px] font-medium text-[#C87620]">
                  {activeAnalysisId ?? "None selected"}
                </div>
                {activeAnalysis && (
                  <div className="mt-0.5 text-[10px] text-[#77736A]">
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
