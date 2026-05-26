import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Info, Upload } from "lucide-react";
import { api } from "../lib/api";
import { fmtAUD } from "../lib/constants";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import useTaxYears from "../lib/useTaxYears";

const SECTIONS = [
  { value: "salary_wages", label: "Salary & Wages", side: "income" },
  { value: "interest", label: "Interest", side: "income" },
  { value: "dividends", label: "Dividends", side: "income" },
  { value: "rental_income", label: "Rental Income", side: "income" },
  { value: "work_related_car", label: "Work-Related Car", side: "deduction" },
  { value: "work_related_travel", label: "Work Travel", side: "deduction" },
  { value: "tools_equipment", label: "Tools & Equipment", side: "deduction" },
  { value: "union_fees", label: "Union / Professional Fees", side: "deduction" },
  { value: "donations", label: "Donations", side: "deduction" },
  { value: "rental_deductions", label: "Rental Property Expenses", side: "deduction" },
  { value: "other_deductions", label: "Other Deductions", side: "deduction" },
];

const STATUS_OPTIONS = [
  { value: "needs_action", label: "Needs action (default)" },
  { value: "all", label: "All transactions" },
  { value: "candidate", label: "Candidate (unresolved)" },
  { value: "added", label: "Added to a return" },
  { value: "private", label: "Private / ignored" },
];

export default function BankTransactions() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("needs_action");
  const [propertyFilter, setPropertyFilter] = useState("all");
  const [addModalTx, setAddModalTx] = useState(null);

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
    // Default view: only show transactions that still need user action —
    // not already added to a return, not marked private, not auto-ignored noise.
    if (status === "needs_action") {
      if (t.used_in_return) return false;
      if (t.evidence_status === "private") return false;
      if (t.category_suggested === "noise_tiny_amount") return false;
      if (t.category_suggested === "internal_transfer") return false;
    } else if (status === "added") {
      if (!t.used_in_return) return false;
    } else if (status !== "all") {
      if (t.evidence_status !== status) return false;
    }
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

  const ignore = async (txId) => {
    try {
      await api.post(`/bank-transactions/${txId}/ignore`);
      toast.success("Marked as private");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not ignore transaction");
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
          {filtered.map((t) => <TransactionRow key={t.id} t={t} onUse={() => promote(t.id)} onAdd={() => setAddModalTx(t)} onIgnore={() => ignore(t.id)} />)}
        </div>
      )}
      <AddToReturnModal tx={addModalTx} onClose={() => setAddModalTx(null)} onSuccess={() => { setAddModalTx(null); load(); }} />
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

function TransactionRow({ t, onUse, onAdd, onIgnore }) {
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
          <div className="font-medium text-zinc-900 text-sm">
            {t.source_document_id ? (
              <Link
                to={`/register?open=${encodeURIComponent(t.source_document_id)}`}
                className="text-blue-700 hover:text-blue-900 hover:underline"
                title={`Open source: ${t.source_filename || "document"}`}
                data-testid={`txn-source-link-${t.id}`}
              >
                {t.description_cleaned || t.description_raw}
              </Link>
            ) : (
              <span>{t.description_cleaned || t.description_raw}</span>
            )}
          </div>
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
          {t.used_in_return ? (
            <div className="mt-1.5 text-[11px] px-2 py-1 rounded bg-emerald-100 text-emerald-800 border border-emerald-200 font-medium">✓ In return</div>
          ) : t.evidence_status === "private" ? (
            <div className="mt-1.5 text-[11px] px-2 py-1 rounded bg-zinc-100 text-zinc-600 border border-zinc-200">Private</div>
          ) : (
            <div className="mt-1.5 flex flex-col gap-1">
              <button
                onClick={onAdd}
                className="text-xs px-2 py-1 rounded bg-zinc-900 text-white hover:bg-zinc-800"
                data-testid={`add-txn-${t.id}`}
              >Add to return…</button>
              {(t.confidence === "Confirmed" || t.confidence === "Likely") && (
                <button
                  onClick={onUse}
                  className="text-[10px] px-2 py-0.5 rounded border border-zinc-300 text-zinc-700 hover:bg-zinc-50"
                  title="Use the AI's suggested year/section as-is"
                  data-testid={`use-txn-${t.id}`}
                >Quick add ({t.confidence})</button>
              )}
              <button
                onClick={onIgnore}
                className="text-[10px] px-2 py-0.5 rounded text-zinc-500 hover:text-red-600"
                title="Mark as private / not tax related"
                data-testid={`ignore-txn-${t.id}`}
              >Ignore</button>
            </div>
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

// ----------- Add-to-Return modal (manual year/section/amount override) -----------
function AddToReturnModal({ tx, onClose, onSuccess }) {
  const { activeNames } = useTaxYears();
  const [taxYear, setTaxYear] = useState(activeNames[0] || "FY2025");
  const [side, setSide] = useState("deduction");
  const [section, setSection] = useState("other_deductions");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!tx) return;
    // Default the year from the txn date (Australian FY) — fallback to first
    // active year if the derived year isn't currently active.
    let fy = activeNames[0] || "FY2025";
    try {
      const d = new Date(tx.transaction_date);
      const derived = (d.getMonth() + 1) >= 7 ? `FY${d.getFullYear() + 1}` : `FY${d.getFullYear()}`;
      if (activeNames.includes(derived)) fy = derived;
    } catch (e) { /* keep default */ }
    setTaxYear(fy);
    // Default income/deduction from the credit/debit of the txn.
    const isDebit = (tx.debit_credit || "").toLowerCase() === "debit";
    setSide(isDebit ? "deduction" : "income");
    const candidate = tx.tax_section_suggested && SECTIONS.find((s) => s.value === tx.tax_section_suggested);
    if (candidate) {
      setSection(candidate.value);
      setSide(candidate.side);
    } else {
      setSection(isDebit ? "other_deductions" : "interest");
    }
    setAmount(((tx.amount_cents || 0) / 100).toFixed(2));
    setDescription(tx.description_cleaned || tx.description_raw || "");
    setNotes("");
  }, [tx]);

  if (!tx) return null;

  const availableSections = SECTIONS.filter((s) => s.side === side);

  const onSideChange = (v) => {
    setSide(v);
    const first = SECTIONS.find((s) => s.side === v);
    if (first) setSection(first.value);
  };

  const submit = async () => {
    const amtNum = parseFloat(amount);
    if (!isFinite(amtNum) || amtNum <= 0) { toast.error("Amount must be > 0"); return; }
    if (!description.trim()) { toast.error("Description is required"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/bank-transactions/${tx.id}/add-to-return`, {
        tax_year: taxYear,
        section,
        income_or_deduction: side,
        amount_cents: Math.round(amtNum * 100),
        description: description.trim(),
        notes,
      });
      toast.success(`Added to ${data.tax_year} tax return`);
      onSuccess && onSuccess();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not add to return");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={!!tx} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="add-to-return-modal" className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add transaction to tax return</DialogTitle>
        </DialogHeader>
        <div className="text-xs text-zinc-500 -mt-2 mb-2 mono truncate" title={tx.description_raw}>
          From: {tx.source_filename} · {tx.transaction_date}
        </div>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Tax year</Label>
              <Select value={taxYear} onValueChange={setTaxYear}>
                <SelectTrigger data-testid="add-modal-year"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(activeNames.length ? activeNames : ["FY2024", "FY2025"]).map((y) => (
                    <SelectItem key={y} value={y}>{y}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Type</Label>
              <Select value={side} onValueChange={onSideChange}>
                <SelectTrigger data-testid="add-modal-side"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="income">Income</SelectItem>
                  <SelectItem value="deduction">Deduction</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Section</Label>
            <Select value={section} onValueChange={setSection}>
              <SelectTrigger data-testid="add-modal-section"><SelectValue /></SelectTrigger>
              <SelectContent>
                {availableSections.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Amount (AUD)</Label>
              <Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="add-modal-amount" />
            </div>
            <div>
              <Label>Description</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} data-testid="add-modal-desc" />
            </div>
          </div>
          <div>
            <Label>Notes (optional)</Label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} data-testid="add-modal-notes" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy} data-testid="add-modal-submit">{busy ? "Adding…" : "Add to return"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Label({ children }) {
  return <div className="text-[11px] mono uppercase text-zinc-500 tracking-wide mb-1">{children}</div>;
}
