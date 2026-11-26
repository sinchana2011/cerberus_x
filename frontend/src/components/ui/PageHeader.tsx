import * as React from "react";
import { Link } from "react-router-dom";
import { Play, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAnalysis } from "@/context/AnalysisContext";
import { useNotifications } from "@/context/NotificationContext";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col justify-between gap-4 border-b border-[#E8E4DA] pb-5 md:flex-row md:items-end">
      <div>
        {eyebrow && (
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#77736A]">
            {eyebrow}
          </div>
        )}
        <h2 className="text-2xl font-bold tracking-tight text-[#C87620]">{title}</h2>
        <p className="mt-1 max-w-2xl text-sm text-[#77736A]">{description}</p>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function NoAnalysisEmptyState({
  title = "No Investigation Selected",
  description = "Upload multimodal evidence files or run the built-in 5-case demo dataset to populate this workspace.",
}: {
  title?: string;
  description?: string;
}) {
  const { loadDemoDataset, demoLoading } = useAnalysis();
  const { notify } = useNotifications();

  const handleDemo = async () => {
    const id = await loadDemoDataset();
    if (id) {
      notify("success", "Demo investigation loaded", `Analysis ${id} saved to SQLite.`);
    } else {
      notify("error", "Demo load failed", "Ensure the FastAPI backend is running on localhost:8000.");
    }
  };

  return (
    <div className="animate-fade-in rounded-xl border border-dashed border-[#D9B98C] bg-white p-10 text-center shadow-[0_1px_3px_rgba(41,40,32,0.04)]">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-[#C87620]/10 text-[#C87620] ring-1 ring-[#C87620]/25">
        <UploadCloud className="h-6 w-6" />
      </div>
      <h3 className="mt-4 text-base font-semibold text-[#C87620]">{title}</h3>
      <p className="mx-auto mt-1.5 max-w-md text-sm text-[#77736A]">{description}</p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Button asChild>
          <Link to="/upload">
            <UploadCloud className="h-4 w-4" />
            Upload Evidence
          </Link>
        </Button>
        <Button variant="outline" onClick={() => void handleDemo()} disabled={demoLoading}>
          <Play className="h-4 w-4 text-[#C87620]" />
          {demoLoading ? "Running Demo Pipeline..." : "Load Demo Dataset"}
        </Button>
      </div>
    </div>
  );
}
