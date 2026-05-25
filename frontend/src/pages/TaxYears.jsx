import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { fmtAUD } from "../lib/constants";
import { ChevronRight, AlertTriangle } from "lucide-react";

const FYS = ["FY2024", "FY2025"];

export default function TaxYears() {
  const [years, setYears] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/tax-years");
        setYears(data);
      } catch (e) {
        console.error("Failed to load tax years", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="p-6 max-w-[1200px] mx-auto" data-testid="tax-years-page">
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Tax Years</h1>
        <p className="text-sm text-zinc-500 mt-1">Tax return draft by financial year. Built from documents + confirmed bank transactions + manual entries.</p>
      </div>

      {loading ? (
        <div className="space-y-3" data-testid="tax-years-loading">
          {[1, 2].map((i) => (
            <div key={i} className="h-28 bg-white border border-zinc-200 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {years.map((y) => (
            <Link
              key={y.tax_year}
              to={`/tax-years/${y.tax_year}`}
              data-testid={`tax-year-card-${y.tax_year}`}
              className="block p-5 bg-white border border-zinc-200 rounded-lg hover:border-zinc-900 hover:shadow-sm transition"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="text-xl font-semibold tracking-tight" style={{ fontFamily: "Chivo" }}>{y.tax_year}</div>
                  <div className="mt-3 grid grid-cols-3 gap-6">
                    <Stat label="Income" value={fmtAUD(y.total_income_cents / 100)} color="text-emerald-700" />
                    <Stat label="Deductions" value={fmtAUD(y.total_deductions_cents / 100)} color="text-blue-700" />
                    <Stat label="Items" value={y.total_items} color="text-zinc-800" />
                  </div>
                  {y.total_review_required > 0 && (
                    <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-800 text-xs font-medium" data-testid={`tax-year-review-${y.tax_year}`}>
                      <AlertTriangle className="w-3.5 h-3.5" />
                      {y.total_review_required} item(s) need review
                    </div>
                  )}
                </div>
                <ChevronRight className="w-5 h-5 text-zinc-400 ml-4" />
              </div>
            </Link>
          ))}
          {years.length === 0 && (
            <div className="p-8 text-center text-sm text-zinc-500 border border-dashed border-zinc-300 rounded-lg">
              No tax years configured. Supported years: {FYS.join(", ")}.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div>
      <div className="text-xs text-zinc-500 mono uppercase tracking-wide">{label}</div>
      <div className={`text-lg font-semibold mt-0.5 ${color}`}>{value}</div>
    </div>
  );
}
