import * as React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useNotifications, type NotificationKind } from "@/context/NotificationContext";
import { cn } from "@/lib/utils";

const KIND_STYLES: Record<NotificationKind, string> = {
  info: "border-cyan-500/35 bg-[#0b1736]/95 text-slate-100",
  success: "border-emerald-500/35 bg-[#0b1736]/95 text-slate-100",
  warning: "border-amber-500/35 bg-[#0b1736]/95 text-slate-100",
  error: "border-rose-500/40 bg-[#0b1736]/95 text-slate-100",
};

function NotificationIcon({ kind }: { kind: NotificationKind }) {
  if (kind === "success") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
  if (kind === "warning") return <AlertTriangle className="h-4 w-4 text-amber-400" />;
  if (kind === "error") return <AlertCircle className="h-4 w-4 text-rose-400" />;
  return <Info className="h-4 w-4 text-cyan-400" />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const { notifications, dismiss } = useNotifications();

  return (
    <div className="flex min-h-screen bg-[#060d1f] text-slate-100">
      <Sidebar
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenMobileNav={() => setMobileOpen(true)} />

        <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>

      {notifications.length > 0 && (
        <div
          className="fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2 px-4 sm:px-0"
          aria-live="polite"
        >
          {notifications.map((item) => (
            <div
              key={item.id}
              className={cn(
                "animate-fade-in flex items-start gap-3 rounded-xl border p-3.5 shadow-2xl backdrop-blur-md",
                KIND_STYLES[item.kind]
              )}
            >
              <div className="mt-0.5 shrink-0">
                <NotificationIcon kind={item.kind} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-white">{item.title}</div>
                {item.message && (
                  <div className="mt-0.5 text-xs text-slate-300">{item.message}</div>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                aria-label="Dismiss notification"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
