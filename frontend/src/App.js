import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
import Dashboard from "@/pages/Dashboard";
import EvidenceRegister from "@/pages/EvidenceRegister";
import MissingEvidence from "@/pages/MissingEvidence";
import Reports from "@/pages/Reports";
import Settings from "@/pages/Settings";
import TaxYears from "@/pages/TaxYears";
import TaxYearBreakdown from "@/pages/TaxYearBreakdown";
import BankTransactions from "@/pages/BankTransactions";
import RubbishBin from "@/pages/RubbishBin";
import Properties from "@/pages/Properties";
import ManualEntry from "@/pages/ManualEntry";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <ErrorBoundary>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/register" element={<EvidenceRegister />} />
              <Route path="/missing-evidence" element={<MissingEvidence />} />
              <Route path="/missing" element={<MissingEvidence />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/settings" element={<Settings />} />
              {/* Stage 7 Phase 3 */}
              <Route path="/tax-years" element={<TaxYears />} />
              <Route path="/tax-years/:year" element={<TaxYearBreakdown />} />
              <Route path="/bank-transactions" element={<BankTransactions />} />
              <Route path="/rubbish-bin" element={<RubbishBin />} />
              <Route path="/properties" element={<Properties />} />
              <Route path="/manual-entry" element={<ManualEntry />} />
            </Route>
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </div>
  );
}

export default App;
