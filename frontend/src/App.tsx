import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { AnalysisProvider } from "@/context/AnalysisContext";
import { NotificationProvider } from "@/context/NotificationContext";
import { AskPage } from "@/pages/AskPage";
import { ConflictReasoningPage } from "@/pages/ConflictReasoningPage";
import { ConflictsPage } from "@/pages/ConflictsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DigitalTwinPage } from "@/pages/DigitalTwinPage";
import { EvidenceGraphPage } from "@/pages/EvidenceGraphPage";
import { ForensicsPage } from "@/pages/ForensicsPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { UploadPage } from "@/pages/UploadPage";

export function App() {
  return (
    <NotificationProvider>
      <AnalysisProvider>
        <BrowserRouter>
          <AppShell>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/graph" element={<EvidenceGraphPage />} />
              <Route path="/conflicts" element={<ConflictsPage />} />
              <Route path="/reasoning" element={<ConflictReasoningPage />} />
              <Route path="/digital-twin" element={<DigitalTwinPage />} />
              <Route path="/ask" element={<AskPage />} />
              <Route path="/forensics" element={<ForensicsPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AppShell>
        </BrowserRouter>
      </AnalysisProvider>
    </NotificationProvider>
  );
}

export default App;
