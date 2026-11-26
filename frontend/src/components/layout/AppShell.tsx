import * as React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useNotifications, type NotificationKind } from "@/context/NotificationContext";
import { cn } from "@/lib/utils";

const KIND_STYLES: Record<NotificationKind, string> = {
  info: "border-[#D9B98C] bg-white text-[#292820]",
  success: "border-[#638568]/45 bg-white text-[#292820]",
  warning: "border-[#D49A45]/50 bg-white text-[#292820]",
  error: "border-[#C65D50]/50 bg-white text-[#292820]",
};

function NotificationIcon({ kind }: { kind: NotificationKind }) {
  if (kind === "success") return <CheckCircle2 className="h-4 w-4 text-[#638568]" />;
  if (kind === "warning") return <AlertTriangle className="h-4 w-4 text-[#D49A45]" />;
  if (kind === "error") return <AlertCircle className="h-4 w-4 text-[#C65D50]" />;
  return <Info className="h-4 w-4 text-[#C87620]" />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const { notifications, dismiss } = useNotifications();

  return (
    <div className="flex min-h-screen bg-[#F6F5F0] text-[#292820]">
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
                "animate-fade-in flex items-start gap-3 rounded-xl border p-3.5 shadow-lg shadow-[#292820]/10 backdrop-blur-md",
                KIND_STYLES[item.kind]
              )}
            >
              <div className="mt-0.5 shrink-0">
                <NotificationIcon kind={item.kind} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-[#292820]">{item.title}</div>
                {item.message && (
                  <div className="mt-0.5 text-xs text-[#77736A]">{item.message}</div>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                className="rounded-lg p-1 text-[#77736A] hover:bg-[#F6F5F0] hover:text-[#292820]"
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
