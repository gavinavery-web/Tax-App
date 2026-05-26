import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { fmtAUD } from "../lib/constants";
import { ChevronRight, AlertTriangle, Plus, Power, PowerOff, Lock, Unlock, Trash2 } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { toast } from "sonner";
import useTaxYears, { refreshTaxYears } from "../lib/useTaxYears";

export default function TaxYears() {
  const { all: years, refresh } = useTaxYears();
  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);

  const loadSummaries = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/tax-years");
      setSummaries(data);
    } catch (e) {
      console.error("Failed to load tax years", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    loadSummaries();
  }, []);

  const toggleActive = async (ty) => {
    try {
      await api.patch(`/tax-years/config/${ty.id}`, { active: !ty.active });
      toast.success(`${ty.name} ${!ty.active ? "activated" : "deactivated"}`);
      await refreshTaxYears();
      loadSummaries();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const toggleLocked = async (ty) => {
    try {
      await api.patch(`/tax-years/config/${ty.id}`, { locked: !ty.locked });
      toast.success(`${ty.name} ${!ty.locked ? "locked" : "unlocked"}`);
      await refreshTaxYears();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const removeYear = async (ty) => {
    if (!window.confirm(`Delete ${ty.name}? This is only allowed if no documents reference it.`)) return;
    try {
      await api.delete(`/tax-years/config/${ty.id}`);
      toast.success(`${ty.name} deleted`);
      await refreshTaxYears();
      loadSummaries();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Cannot delete (documents still reference it)");
    }
  };

  // Match summaries to active config names so deactivated years are hidden.
  const visibleSummaries = summaries.filter((s) =>
    years.some((y) => y.name === s.tax_year && y.active),
  );

  return (
    <div className="p-6 max-w-[1200px] mx-auto" data-testid="tax-years-page">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Tax Years</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Active years receive uploads, classification, transaction matching and dashboard summaries. Deactivated years are hidden but data is preserved.
          </p>
        </div>
        <Button onClick={() => setShowAdd((v) => !v)} variant="outline" className="rounded-sm gap-2" data-testid="add-year-toggle">
          <Plus className="w-4 h-4" /> Add tax year
        </Button>
      </div>

      {/* Configuration table */}
      <div className="bg-white border border-zinc-200 rounded-sm mb-6" data-testid="tax-years-config">
        <div className="px-4 py-2.5 border-b border-zinc-200 flex items-center justify-between">
          <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>Configuration</div>
          <div className="text-[11px] text-zinc-500 mono">{years.filter((y) => y.active).length} active · {years.length} total</div>
        </div>
        {showAdd && <AddYearForm onDone={() => { setShowAdd(false); refreshTaxYears(); loadSummaries(); }} onCancel={() => setShowAdd(false)} existing={years} />}
        <table className="w-full dense-table text-sm">
          <thead>
            <tr>
              <th>Name</th>
              <th>Range</th>
              <th>Status</th>
              <th>Locked</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {years.map((ty) => {
              const isCurrent = new Date() >= new Date(ty.start_date) && new Date() <= new Date(ty.end_date);
              return (
                <tr key={ty.id} data-testid={`ty-row-${ty.id}`}>
                  <td className="font-medium">
                    {ty.name}
                    {isCurrent && <span className="ml-2 px-1.5 py-0.5 text-[10px] bg-blue-50 text-blue-800 border border-blue-200 rounded uppercase tracking-wide">Current</span>}
                  </td>
                  <td className="mono text-xs text-zinc-600">{ty.start_date} → {ty.end_date}</td>
                  <td>
                    {ty.active ? (
                      <span className="pill" style={{ background: "#F0FDF4", color: "#166534", borderColor: "#BBF7D0" }}>Active</span>
                    ) : (
                      <span className="pill" style={{ background: "#FAFAFA", color: "#52525B", borderColor: "#E4E4E7" }}>Inactive</span>
                    )}
                    {isCurrent && ty.active && (
                      <span className="ml-1.5 text-[10px] text-amber-700 mono">In progress — not ready to lodge</span>
                    )}
                  </td>
                  <td className="mono text-xs">{ty.locked ? "Locked" : "—"}</td>
                  <td className="text-right">
                    <div className="inline-flex items-center gap-1">
                      <button
                        onClick={() => toggleActive(ty)}
                        className="text-zinc-500 hover:text-zinc-900 p-1"
                        title={ty.active ? "Deactivate" : "Activate"}
                        data-testid={`ty-toggle-active-${ty.id}`}
                      >
                        {ty.active ? <PowerOff className="w-3.5 h-3.5" /> : <Power className="w-3.5 h-3.5" />}
                      </button>
                      <button
                        onClick={() => toggleLocked(ty)}
                        className="text-zinc-500 hover:text-zinc-900 p-1"
                        title={ty.locked ? "Unlock" : "Lock"}
                        data-testid={`ty-toggle-locked-${ty.id}`}
                      >
                        {ty.locked ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
                      </button>
                      <button
                        onClick={() => removeYear(ty)}
                        className="text-zinc-400 hover:text-red-700 p-1"
                        title="Delete (only if no documents reference it)"
                        data-testid={`ty-delete-${ty.id}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Summaries */}
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Active year summaries</div>
      {loading ? (
        <div className="space-y-3" data-testid="tax-years-loading">
          {[1, 2].map((i) => (
            <div key={i} className="h-28 bg-white border border-zinc-200 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {visibleSummaries.map((y) => (
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
          {visibleSummaries.length === 0 && (
            <div className="p-8 text-center text-sm text-zinc-500 border border-dashed border-zinc-300 rounded-lg">
              No active tax years. Activate one above to begin collecting documents.
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

function AddYearForm({ onDone, onCancel, existing }) {
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [busy, setBusy] = useState(false);

  // Suggest the next FY based on max(existing.end_date)
  useEffect(() => {
    if (existing.length === 0) return;
    const sorted = [...existing].sort((a, b) => (a.order || 0) - (b.order || 0));
    const last = sorted[sorted.length - 1];
    const m = (last.name || "").match(/^FY(\d{4})$/);
    if (m) {
      const next = parseInt(m[1], 10) + 1;
      setName(`FY${next}`);
      setStartDate(`${next - 1}-07-01`);
      setEndDate(`${next}-06-30`);
    }
  }, [existing]);

  const submit = async () => {
    if (!name || !startDate || !endDate) { toast.error("Name, start, end are all required"); return; }
    setBusy(true);
    try {
      await api.post("/tax-years/config", { name, start_date: startDate, end_date: endDate, active: true });
      toast.success(`${name} added`);
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to add tax year");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-200" data-testid="add-year-form">
      <div className="grid grid-cols-4 gap-2">
        <div>
          <label className="text-[11px] uppercase tracking-wider text-zinc-500 mono">Name</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="FY2027" data-testid="add-year-name" />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-wider text-zinc-500 mono">Start</label>
          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} data-testid="add-year-start" />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-wider text-zinc-500 mono">End</label>
          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} data-testid="add-year-end" />
        </div>
        <div className="flex items-end gap-1">
          <Button onClick={submit} disabled={busy} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="add-year-submit">
            {busy ? "Saving…" : "Save"}
          </Button>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}
