import * as React from "react";
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  FileText,
  Send,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NoAnalysisEmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { useNotifications } from "@/context/NotificationContext";
import { askAnalysisQuestion, extractApiError } from "@/lib/api";
import type { AnswerStatus, AskResponse } from "@/types/cerberus";

const DEFAULT_SAMPLE_QUESTIONS = [
  "How many units of Shipment SH-1042 were dispatched?",
  "Who is the CEO of Northwind Logistics?",
  "Who was the CEO of Northwind Logistics in 2024?",
  "How many units of Shipment SH-2201 were delivered?",
  "Can Meera Das have been in both Delhi and Pune in April 2026?",
  "Was Meera Das in Pune and Delhi at the same time on 2026-04-02?",
];

function statusVariant(status: AnswerStatus) {
  if (status === "answered") return "success" as const;
  if (status === "conflicting") return "danger" as const;
  if (status === "suspicious_only") return "danger" as const;
  return "warning" as const;
}

export function AskPage() {
  const { health, activeAnalysisId, activeAnalysis } = useAnalysis();
  const { notify } = useNotifications();

  const [question, setQuestion] = React.useState("");
  const [useLlm, setUseLlm] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [responses, setResponses] = React.useState<AskResponse[]>([]);

  const ollamaReady = Boolean(health?.ollama_available && health?.ollama_model_installed);

  React.useEffect(() => {
    setResponses([]);
    setError(null);
  }, [activeAnalysisId]);

  const submitQuestion = async (qText: string) => {
    const trimmed = qText.trim();
    if (!trimmed || !activeAnalysisId || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await askAnalysisQuestion(activeAnalysisId, trimmed, useLlm);
      setResponses((prev) => [res, ...prev]);
      setQuestion("");
    } catch (err) {
      const msg = extractApiError(err);
      setError(msg);
      notify("error", "Question failed", msg);
    } finally {
      setLoading(false);
    }
  };

  const suggestedQuestions = React.useMemo(() => {
    const entities = activeAnalysis?.entities ?? [];
    if (entities.some((e) => e.canonical_name.includes("Northwind"))) {
      return DEFAULT_SAMPLE_QUESTIONS;
    }
    return entities.slice(0, 4).map((e) => `What records exist for ${e.canonical_name}?`);
  }, [activeAnalysis]);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="Traceable Evidence QA"
        title="Ask CERBERUS"
        description="Query your investigation with deterministic conflict-aware reasoning and optional local Ollama (llama3.2:3b) synthesis."
      />

      {!activeAnalysisId ? (
        <NoAnalysisEmptyState />
      ) : (
        <>
          <Card className="border-[#E8E4DA]">
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle>Ask a Question About Active Evidence</CardTitle>
                  <CardDescription>
                    Suspicious segments are strictly excluded from answers; conflicts are never suppressed.
                  </CardDescription>
                </div>

                <button
                  type="button"
                  onClick={() => setUseLlm((v) => !v)}
                  className={`flex items-center gap-2 rounded-[10px] border px-3 py-2 text-xs font-medium transition ${
                    useLlm
                      ? "border-[#C87620]/50 bg-[#C87620]/10 text-[#A85F15]"
                      : "border-[#E8E4DA] bg-[#F6F5F0] text-[#77736A] hover:text-[#292820]"
                  }`}
                >
                  <Sparkles className="h-3.5 w-3.5 text-[#C87620]" />
                  <span>
                    Ollama ({health?.ollama_model ?? "llama3.2:3b"}):{" "}
                    {useLlm ? "Enabled" : "Deterministic Only"}
                  </span>
                </button>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              {useLlm && !ollamaReady && (
                <Alert variant="warning">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#D49A45]" />
                  <div className="text-xs">
                    Local Ollama server ({health?.ollama_model ?? "llama3.2:3b"}) is currently offline.
                    CERBERUS-X will automatically fall back to deterministic evidence reasoning.
                  </div>
                </Alert>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void submitQuestion(question);
                }}
                className="flex flex-col gap-3 sm:flex-row"
              >
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about quantities, leadership timelines, locations, or contradictions..."
                  disabled={loading}
                  className="h-11 flex-1 rounded-xl border border-[#E8E4DA] bg-[#F6F5F0] px-4 text-sm text-[#292820] placeholder:text-[#77736A] outline-none focus:border-[#C87620]"
                />
                <Button type="submit" disabled={!question.trim() || loading} className="h-11 px-6">
                  <Send className="h-4 w-4" />
                  {loading ? "Reasoning..." : "Ask CERBERUS"}
                </Button>
              </form>

              {suggestedQuestions.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {suggestedQuestions.map((sq) => (
                    <button
                      key={sq}
                      type="button"
                      disabled={loading}
                      onClick={() => void submitQuestion(sq)}
                      className="rounded-full border border-[#E8E4DA] bg-[#F6F5F0] px-3 py-1.5 text-xs text-[#292820] transition hover:border-[#C87620] hover:text-[#C87620]"
                    >
                      {sq}
                    </button>
                  ))}
                </div>
              )}

              {error && (
                <Alert variant="destructive">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div className="text-xs">{error}</div>
                </Alert>
              )}
            </CardContent>
          </Card>

          {/* Answers */}
          <div className="space-y-4">
            {responses.map((res, idx) => (
              <Card key={idx} className="animate-fade-in">
                <CardHeader className="border-b border-[#E8E4DA] pb-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-base">{res.question}</CardTitle>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={statusVariant(res.status)}>
                        {res.status === "answered" ? (
                          <CheckCircle2 className="h-3 w-3" />
                        ) : (
                          <AlertTriangle className="h-3 w-3" />
                        )}
                        {res.status.replace(/_/g, " ").toUpperCase()}
                      </Badge>
                      <Badge variant="default">
                        Strength: {Math.round(res.confidence * 100)}%
                      </Badge>
                      <Badge variant={res.used_llm ? "info" : "neutral"}>
                        <BrainCircuit className="h-3 w-3" />
                        {res.used_llm ? `Ollama (${res.model})` : "Deterministic"}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4 pt-4">
                  <p className="text-sm leading-relaxed text-[#292820]">{res.answer_text}</p>

                  {res.excluded_claim_ids.length > 0 && (
                    <Alert variant="warning">
                      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#D49A45]" />
                      <div className="text-xs">
                        Excluded suspicious claim(s) from factual reasoning:{" "}
                        <span className="font-mono">{res.excluded_claim_ids.join(", ")}</span>
                      </div>
                    </Alert>
                  )}

                  {res.citations.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-[#77736A]">
                        Supporting Citations ({res.citations.length})
                      </div>
                      <div className="grid gap-2.5 md:grid-cols-2">
                        {res.citations.map((cit, cIdx) => (
                          <div
                            key={cIdx}
                            className="rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 p-3 text-xs"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="flex items-center gap-1.5 font-semibold text-[#C87620]">
                                <FileText className="h-3.5 w-3.5" />
                                {cit.filename}
                              </span>
                              <Badge variant="neutral">
                                Rel {Math.round(cit.reliability * 100)}%
                              </Badge>
                            </div>
                            <div className="mt-1 font-mono text-[11px] text-[#77736A]">
                              {cit.locator ?? "Unknown locator"}
                              {cit.claim_id ? ` · ${cit.claim_id}` : ""}
                            </div>
                            <p className="mt-2 rounded-lg border border-[#E8E4DA] bg-white p-2 text-[11px] text-[#292820]">
                              {cit.snippet}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {res.conflict_ids.length > 0 && (
                    <div className="text-xs font-medium text-[#A6463B]">
                      Related Conflict IDs:{" "}
                      <span className="font-mono">{res.conflict_ids.join(", ")}</span>
                    </div>
                  )}

                  {res.notes.length > 0 && (
                    <div className="rounded-[10px] border border-[#E8E4DA] bg-[#F6F5F0]/70 p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#77736A]">
                        Reasoning Notes
                      </div>
                      <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-[#292820]">
                        {res.notes.map((n, nIdx) => (
                          <li key={nIdx}>{n}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default AskPage;
