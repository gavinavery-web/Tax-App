import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Info, Upload } from "lucide-react";
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

      <div className="mb-5 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-3" data-testid="bank-upload-guide">
        <Info className="w-5 h-5 text-blue-700 mt-0.5 shrink-0" />
        <div className="flex-1 text-sm text-zinc-800">
          <div className="font-semibold text-blue-900 mb-1">How to add bank statements</div>
          <ol className="list-decimal ml-5 space-y-0.5 text-xs leading-relaxed">
            <li>Upload your bank statement (CSV or PDF) via the <strong>Evidence Register</strong>.</li>
            <li>Pick category <strong>Bank Statement</strong>. The app auto-detects the format and extracts each row.</li>
            <li>The extracted transactions appear here. Confirmed/Likely ones get an <strong>Add to return</strong> button.</li>
          </ol>
        </div>
        <Link to="/register" className="shrink-0">
          <Button size="sm" className="gap-1.5" data-testid="goto-upload-btn"><Upload className="w-3.5 h-3.5" /> Upload statements</Button>
        </Link>
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
  const date = t.transaction_date ? new Date(t.transaction_date).toLocaleDateString("en-AU", { day: "2-digit", month: "short", year: "numeric" }) : "—";
  const amountStr = fmtAUD((t.amount_cents || 0) / 100);
  const isDebit = (t.debit_credit || "").toLowerCase() === "debit";
  const amountColor = isDebit ? "text-red-700" : "text-emerald-700";
  const amountSign = isDebit ? "-" : "+";
  const hasRawDistinct = t.description_raw && t.description_cleaned && t.description_raw !== t.description_cleaned;

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
          {hasRawDistinct && (
            <div className="mt-1.5 p-1.5 bg-zinc-50 border-l-2 border-zinc-300 rounded-sm">
              <div className="text-[10px] uppercase tracking-wide text-zinc-500 mono">Raw bank line</div>
              <div className="text-xs text-zinc-700 mono break-all">{t.description_raw}</div>
            </div>
          )}
          {t.review_required && t.review_reason && (
            <div className="mt-1.5 p-1.5 bg-amber-50 border-l-2 border-amber-400 rounded-sm text-xs text-amber-900">
              <span className="font-semibold">Review: </span>{t.review_reason}
            </div>
          )}
          <div className="text-xs text-zinc-500 mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
            {t.category_suggested && <span><span className="font-medium text-zinc-700">Category:</span> {t.category_suggested}</span>}
            {t.tax_section_suggested && <span>· <span className="font-medium text-zinc-700">Tax:</span> {t.tax_section_suggested}</span>}
            {t.confidence && <span>· <span className={t.confidence === "Confirmed" ? "text-emerald-700 font-medium" : t.confidence === "Likely" ? "text-blue-700 font-medium" : "text-zinc-600"}>{t.confidence}</span></span>}
            {t.classification_method && <span>· <span className="text-zinc-600">{t.classification_method === "rules" ? "rules (no AI cost)" : t.classification_method}</span></span>}
            {t.source_filename && <span className="truncate">· From: {t.source_filename}</span>}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-lg font-semibold mono ${amountColor}`}>{amountSign}{amountStr}</div>
          <div className="text-xs mono text-zinc-500">{t.debit_credit || "—"}</div>
          {t.balance_cents !== null && t.balance_cents !== undefined && (
            <div className="text-[10px] mono text-zinc-400 mt-0.5">bal {fmtAUD(t.balance_cents / 100)}</div>
          )}
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
