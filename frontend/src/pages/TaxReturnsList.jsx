import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Plus, FileText } from "lucide-react";

const STATUS_TONE = {
  collecting_evidence: "bg-blue-50 text-blue-800 border-blue-200",
  ready_for_review: "bg-amber-50 text-amber-800 border-amber-200",
  ready_for_accountant: "bg-violet-50 text-violet-800 border-violet-200",
  lodged: "bg-emerald-50 text-emerald-800 border-emerald-200",
  archived: "bg-zinc-100 text-zinc-600 border-zinc-200",
};

export default function TaxReturnsList() {
  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/tax-returns")
      .then((r) => { setReturns(r.data || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto" data-testid="tax-returns-list">
      <div className="flex justify-between items-center mb-5">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Tax Returns</h1>
          <p className="text-sm text-zinc-500 mt-1">Each return is a working container for one year × one entity. Open one to see its workspace.</p>
        </div>
        <Link to="/tax-returns/new">
          <Button className="rounded-sm gap-1.5 bg-zinc-950 hover:bg-zinc-800" data-testid="new-return-btn">
            <Plus className="w-4 h-4" /> New tax return
          </Button>
        </Link>
      </div>

      {loading ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : returns.length === 0 ? (
        <div className="p-8 text-center text-sm text-zinc-500 border border-dashed border-zinc-300 rounded-lg" data-testid="no-returns-empty">
          No tax returns yet. Click <strong>New tax return</strong> to start.
        </div>
      ) : (
        <div className="space-y-2">
          {returns.map((r) => (
            <Link
              key={r.id}
              to={`/tax-returns/${r.id}`}
              className="block bg-white border border-zinc-200 rounded-lg p-4 hover:border-zinc-900 hover:shadow-sm transition"
              data-testid={`tr-row-${r.id}`}
            >
              <div className="flex justify-between items-start gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <FileText className="w-4 h-4 text-zinc-500 shrink-0" />
                    <div className="font-semibold tracking-tight truncate" style={{ fontFamily: "Chivo" }}>
                      {r.tax_year} · {r.return_type.replace(/_/g, " ")}
                    </div>
                    <span className="text-zinc-400">·</span>
                    <span className="text-sm text-zinc-700 truncate">{r.entity_name}</span>
                  </div>
                  <div className="text-[11px] text-zinc-500 mono mt-1">Created {new Date(r.created_at).toLocaleDateString()}</div>
                </div>
                <span className={`px-2 py-0.5 rounded text-[10px] font-medium border capitalize shrink-0 ${STATUS_TONE[r.status] || "bg-white border-zinc-300 text-zinc-700"}`}>
                  {r.status.replace(/_/g, " ")}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
