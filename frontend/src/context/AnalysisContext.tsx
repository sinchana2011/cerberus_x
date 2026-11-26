import * as React from "react";

import {
  deleteAnalysis,
  extractApiError,
  fetchAnalyses,
  fetchAnalysis,
  fetchHealth,
  runDemoAnalysis,
} from "@/lib/api";
import type {
  AnalysisCounts,
  AnalysisDetailResponse,
  AnalysisListItem,
  HealthResponse,
} from "@/types/cerberus";

const STORAGE_ACTIVE_KEY = "cerberus_active_analysis_id";

interface AnalysisContextValue {
  health: HealthResponse | null;
  healthLoading: boolean;
  healthError: string | null;
  refreshHealth: () => Promise<void>;
  activeAnalysisId: string | null;
  activeAnalysis: AnalysisDetailResponse | null;
  analysisLoading: boolean;
  analysisError: string | null;
  history: AnalysisListItem[];
  historyLoading: boolean;
  aggregateCounts: AnalysisCounts;
  refreshHistory: () => Promise<AnalysisListItem[]>;
  selectAnalysis: (analysisId: string) => Promise<boolean>;
  deleteAnalysisById: (analysisId: string) => Promise<boolean>;
  loadDemoDataset: () => Promise<string | null>;
  demoLoading: boolean;
  clearActiveAnalysis: () => void;
}

const EMPTY_COUNTS: AnalysisCounts = {
  documents: 0,
  entities: 0,
  claims: 0,
  conflicts: 0,
  twin_states: 0,
};

const AnalysisContext = React.createContext<AnalysisContextValue | undefined>(undefined);

export function AnalysisProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = React.useState<boolean>(true);
  const [healthError, setHealthError] = React.useState<string | null>(null);

  const [activeAnalysisId, setActiveAnalysisId] = React.useState<string | null>(() => {
    try {
      return window.localStorage.getItem(STORAGE_ACTIVE_KEY);
    } catch {
      return null;
    }
  });
  const [activeAnalysis, setActiveAnalysis] = React.useState<AnalysisDetailResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = React.useState<boolean>(false);
  const [analysisError, setAnalysisError] = React.useState<string | null>(null);

  const [history, setHistory] = React.useState<AnalysisListItem[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState<boolean>(false);
  const [aggregateCounts, setAggregateCounts] = React.useState<AnalysisCounts>(EMPTY_COUNTS);
  const [demoLoading, setDemoLoading] = React.useState<boolean>(false);

  const refreshHealth = React.useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err) {
      setHealth(null);
      setHealthError(extractApiError(err));
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const refreshHistory = React.useCallback(async (): Promise<AnalysisListItem[]> => {
    setHistoryLoading(true);
    try {
      const res = await fetchAnalyses();
      setHistory(res.investigations);
      setAggregateCounts(res.aggregate_counts);
      return res.investigations;
    } catch {
      return [];
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const selectAnalysis = React.useCallback(
    async (analysisId: string): Promise<boolean> => {
      const trimmed = analysisId.trim();
      if (!trimmed) return false;
      setAnalysisLoading(true);
      setAnalysisError(null);
      try {
        const detail = await fetchAnalysis(trimmed);
        setActiveAnalysisId(trimmed);
        setActiveAnalysis(detail);
        try {
          window.localStorage.setItem(STORAGE_ACTIVE_KEY, trimmed);
        } catch {
          // Ignore storage failures.
        }
        void refreshHistory();
        return true;
      } catch (err) {
        setAnalysisError(extractApiError(err));
        return false;
      } finally {
        setAnalysisLoading(false);
      }
    },
    [refreshHistory]
  );

  const clearActiveAnalysis = React.useCallback(() => {
    setActiveAnalysisId(null);
    setActiveAnalysis(null);
    setAnalysisError(null);
    try {
      window.localStorage.removeItem(STORAGE_ACTIVE_KEY);
    } catch {
      // Ignore storage failures.
    }
  }, []);

  const deleteAnalysisById = React.useCallback(
    async (analysisId: string): Promise<boolean> => {
      try {
        await deleteAnalysis(analysisId);
        const remaining = await refreshHistory();
        if (activeAnalysisId === analysisId) {
          if (remaining.length > 0) {
            await selectAnalysis(remaining[0].analysis_id);
          } else {
            clearActiveAnalysis();
          }
        }
        return true;
      } catch (err) {
        setAnalysisError(extractApiError(err));
        return false;
      }
    },
    [activeAnalysisId, clearActiveAnalysis, refreshHistory, selectAnalysis]
  );

  const loadDemoDataset = React.useCallback(async (): Promise<string | null> => {
    setDemoLoading(true);
    setAnalysisError(null);
    try {
      const res = await runDemoAnalysis();
      await selectAnalysis(res.analysis_id);
      return res.analysis_id;
    } catch (err) {
      setAnalysisError(extractApiError(err));
      return null;
    } finally {
      setDemoLoading(false);
    }
  }, [selectAnalysis]);

  React.useEffect(() => {
    let mounted = true;
    const bootstrap = async () => {
      await refreshHealth();
      const items = await refreshHistory();
      if (!mounted) return;
      const preferred =
        activeAnalysisId && items.some((i) => i.analysis_id === activeAnalysisId)
          ? activeAnalysisId
          : items[0]?.analysis_id ?? null;
      if (preferred) {
        await selectAnalysis(preferred);
      } else if (activeAnalysisId) {
        clearActiveAnalysis();
      }
    };
    void bootstrap();
    return () => {
      mounted = false;
    };
    // Run once on initial mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AnalysisContext.Provider
      value={{
        health,
        healthLoading,
        healthError,
        refreshHealth,
        activeAnalysisId,
        activeAnalysis,
        analysisLoading,
        analysisError,
        history,
        historyLoading,
        aggregateCounts,
        refreshHistory,
        selectAnalysis,
        deleteAnalysisById,
        loadDemoDataset,
        demoLoading,
        clearActiveAnalysis,
      }}
    >
      {children}
    </AnalysisContext.Provider>
  );
}

export function useAnalysis() {
  const ctx = React.useContext(AnalysisContext);
  if (!ctx) {
    throw new Error("useAnalysis must be used inside AnalysisProvider");
  }
  return ctx;
}
