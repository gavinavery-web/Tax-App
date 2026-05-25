import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtAUD } from "../lib/constants";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "candidate", label: "Candidate" },
  { value: "private", label: "Private (skipped)" },
];

export default function BankTransactions() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("all");
  const [propertyFilter, setPropertyFilter] = useState("all");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/bank-transactions");
      setTransactions(data);
    } catch (e) {
      toast.error(`Failed to load transactions: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const propertyOptions = useMemo(() => {
    const set = new Set();
    transactions.forEach((t) => { if (t.property_match) set.add(t.property_match); });
    return ["all", ...Array.from(set).sort()];
  }, [transactions]);

  const filtered = useMemo(() => transactions.filter((t) => {
    if (status !== "all" && t.evidence_status !== status) return false;
    if (propertyFilter !== "all" && t.property_match !== propertyFilter) return false;
    return true;
  }), [transactions, status, propertyFilter]);

  const usable = filtered.filter((t) => t.evidence_status === "candidate" && !t.used_in_return);

  const promote = async (txId) => {
    try {
      await api.post(`/bank-transactions/${txId}/use-in-return`);
      toast.success("Added to tax return");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not promote transaction");
    }
  };

  return (
    <div className="p-6 max-w-[1400px] mx-auto" data-testid="bank-transactions-page">
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Bank Transactions</h1>
          <p className="text-sm text-zinc-500 mt-1">{transactions.length} transaction(s) extracted from bank statements · {usable.length} ready to add to a return.</p>
        </div>
      </div>

      <div className="mb-4 p-3 bg-white border border-zinc-200 rounded-lg flex items-center gap-3" data-testid="bank-transactions-filters">
        <Filter label="Status" value={status} onChange={setStatus} options={STATUS_OPTIONS} testid="filter-status" />
        <Filter
          label="Property"
          value={propertyFilter}
          onChange={setPropertyFilter}
          options={propertyOptions.map((p) => ({ value: p, label: p === "all" ? "All" : p }))}
          testid="filter-property"
        />
        <div className="ml-auto text-xs mono text-zinc-500">{filtered.length} of {transactions.length} shown</div>
      </div>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="p-8 text-center text-sm text-zinc-500 border border-dashed border-zinc-300 rounded-lg">
          {transactions.length === 0 ? "No bank statements uploaded yet — upload a CSV or PDF to extract transactions." : "No transactions match these filters."}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((t) => <TransactionRow key={t.id} t={t} onUse={() => promote(t.id)} />)}
        </div>
      )}
    </div>
  );
}

function Filter({ label, value, onChange, options, testid }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs mono uppercase text-zinc-500 tracking-wide">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-8 w-44" data-testid={testid}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

function TransactionRow({ t, onUse }) {
  const date = t.transaction_date ? new Date(t.transaction_date).toLocaleDateString("en-AU") : "—";
  return (
    <div className="p-3 bg-white border border-zinc-200 rounded-lg" data-testid={`bank-txn-${t.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center flex-wrap gap-1.5 mb-1">
            <span className="text-xs mono text-zinc-500">{date}</span>
            {t.merchant_detected && <Tag tone="blue">{t.merchant_detected}</Tag>}
            {t.property_match && <Tag tone="violet">{t.property_match}</Tag>}
            {t.use_period_match && <Tag tone="emerald">{t.use_period_match}</Tag>}
            {t.evidence_status === "private" && <Tag tone="zinc">Private</Tag>}
            {t.used_in_return && <Tag tone="emerald">In return</Tag>}
            {t.review_required && <Tag tone="amber">Review</Tag>}
          </div>
          <div className="font-medium text-zinc-900 text-sm">{t.description_cleaned || t.description_raw}</div>
          <div className="text-xs text-zinc-500 mt-0.5">
            {t.category_suggested && <span>Suggested: {t.category_suggested}</span>}
            {t.source_filename && <span className="ml-2">· From: {t.source_filename}</span>}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-lg font-semibold text-zinc-900 mono">{fmtAUD((t.amount_cents || 0) / 100)}</div>
          <div className="text-xs mono text-zinc-500">{t.debit_credit || "—"}</div>
          {t.evidence_status === "candidate" && !t.used_in_return && (t.confidence === "Confirmed" || t.confidence === "Likely") && (
            <button
              onClick={onUse}
              className="mt-1.5 text-xs px-2 py-1 rounded bg-zinc-900 text-white hover:bg-zinc-800"
              data-testid={`use-txn-${t.id}`}
            >Add to return</button>
          )}
        </div>
      </div>
    </div>
  );
}

function Tag({ tone, children }) {
  const map = {
    blue: "bg-blue-50 text-blue-800 border-blue-200",
    violet: "bg-violet-50 text-violet-800 border-violet-200",
    emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
    amber: "bg-amber-50 text-amber-800 border-amber-200",
    zinc: "bg-zinc-100 text-zinc-700 border-zinc-200",
  };
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${map[tone] || ""}`}>{children}</span>;
}
