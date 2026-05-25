import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { fmtAUD } from "../lib/constants";
import { Plus, ArrowLeft, ChevronRight, AlertTriangle } from "lucide-react";
import { Button } from "../components/ui/button";

const SECTION_LABELS = {
  salary_wages: "Salary & Wages",
  allowances: "Allowances",
  interest: "Interest",
  dividends: "Dividends",
  rental_income: "Rental Income",
  work_related_car: "Work-Related Car",
  work_related_travel: "Work Travel",
  tools_equipment: "Tools & Equipment",
  union_fees: "Union / Professional Fees",
  donations: "Donations / Gifts",
  rental_deductions: "Rental Property Expenses",
  other_deductions: "Other Deductions",
};

export default function TaxYearBreakdown() {
  const { year } = useParams();
  const [breakdown, setBreakdown] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/tax-years/${year}`);
      setBreakdown(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [year]);

  if (loading) return <div className="p-6 text-sm text-zinc-500" data-testid="tax-year-loading">Loading…</div>;
  if (!breakdown) return <div className="p-6 text-sm text-zinc-500">Tax year not found.</div>;

  // Classify each section by inspecting its items. A section's
  // income_or_deduction is uniform in practice (manual + builder both
  // set it explicitly), so reading the first item is safe.
  const incomeSections = breakdown.sections.filter((s) => (s.items[0]?.income_or_deduction) === "income");
  const deductionSections = breakdown.sections.filter((s) => (s.items[0]?.income_or_deduction) === "deduction");

  return (
    <div className="p-6 max-w-[1200px] mx-auto" data-testid="tax-year-breakdown-page">
      <Link to="/tax-years" className="inline-flex items-center gap-1.5 text-sm text-zinc-600 hover:text-zinc-900 mb-3" data-testid="back-to-tax-years">
        <ArrowLeft className="w-4 h-4" /> All tax years
      </Link>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>{year} Tax Return</h1>
          <p className="text-sm text-zinc-500 mt-1">Draft return — every figure is linked to its source.</p>
        </div>
        <Link to={`/manual-entry?year=${year}`} data-testid="add-manual-entry-btn">
          <Button size="sm" className="gap-1.5"><Plus className="w-4 h-4" /> Add manual entry</Button>
        </Link>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <SummaryCard testid="summary-income" label="Total income" value={fmtAUD(breakdown.total_income_cents / 100)} tone="emerald" />
        <SummaryCard testid="summary-deductions" label="Total deductions" value={fmtAUD(breakdown.total_deductions_cents / 100)} tone="blue" />
        <SummaryCard
          testid="summary-items"
          label="Total items"
          value={breakdown.total_items}
          tone="zinc"
          footer={breakdown.total_review_required > 0 ? (
            <div className="text-xs text-amber-700 mt-1 inline-flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {breakdown.total_review_required} need review
            </div>
          ) : null}
        />
      </div>

      <Section title="Income" sections={incomeSections} emptyText="No income items yet." onChanged={load} />
      <Section title="Deductions" sections={deductionSections} emptyText="No deduction items yet." onChanged={load} />
    </div>
  );
}

function SummaryCard({ label, value, tone, footer, testid }) {
  const toneClass = {
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-900",
    blue: "bg-blue-50 border-blue-200 text-blue-900",
    zinc: "bg-zinc-50 border-zinc-200 text-zinc-900",
  }[tone] || "bg-white border-zinc-200";
  return (
    <div className={`p-4 border rounded-lg ${toneClass}`} data-testid={testid}>
      <div className="text-xs uppercase tracking-wide mono opacity-70">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {footer}
    </div>
  );
}

function Section({ title, sections, emptyText, onChanged }) {
  return (
    <div className="mb-6" data-testid={`section-group-${title.toLowerCase()}`}>
      <h2 className="text-lg font-semibold tracking-tight mb-2" style={{ fontFamily: "Chivo" }}>{title}</h2>
      {sections.length === 0 ? (
        <div className="text-sm text-zinc-500 italic px-1">{emptyText}</div>
      ) : (
        <div className="space-y-2">
          {sections.map((s) => <SectionCard key={s.section_name} section={s} onChanged={onChanged} />)}
        </div>
      )}
    </div>
  );
}

function SectionCard({ section, onChanged }) {
  const [open, setOpen] = useState(false);
  const label = SECTION_LABELS[section.section_name] || section.section_name;
  return (
    <div className="border border-zinc-200 rounded-lg overflow-hidden bg-white">
      <button
        onClick={() => setOpen(!open)}
        data-testid={`section-toggle-${section.section_name}`}
        className="w-full p-3 flex items-center justify-between hover:bg-zinc-50"
      >
        <div className="flex items-center gap-3 text-left">
          <ChevronRight className={`w-4 h-4 text-zinc-400 transition-transform ${open ? "rotate-90" : ""}`} />
          <div>
            <div className="font-medium text-zinc-900">{label}</div>
            <div className="text-xs text-zinc-500 mono">
              {section.item_count} item(s)
              {section.review_required_count > 0 && <span className="text-amber-700 ml-1.5">· {section.review_required_count} review</span>}
            </div>
          </div>
        </div>
        <div className="text-lg font-semibold text-zinc-900 mono">{fmtAUD(section.total_amount_cents / 100)}</div>
      </button>
      {open && (
        <div className="border-t border-zinc-200 bg-zinc-50 p-3 space-y-2" data-testid={`section-items-${section.section_name}`}>
          {section.items.map((item) => <ItemRow key={item.id} item={item} onChanged={onChanged} />)}
        </div>
      )}
    </div>
  );
}

function ItemRow({ item, onChanged }) {
  const [busy, setBusy] = useState(false);
  const onDelete = async () => {
    if (!window.confirm(`Remove "${item.description}" from this return? The source document is unaffected.`)) return;
    setBusy(true);
    try {
      await api.delete(`/tax-return-items/${item.id}`);
      onChanged && onChanged();
    } catch (e) {
      window.alert(`Failed to remove: ${e.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="p-2.5 bg-white border border-zinc-200 rounded flex items-center justify-between" data-testid={`tax-item-${item.id}`}>
      <div className="min-w-0 flex-1">
        <div className="font-medium text-zinc-900 text-sm truncate">{item.description}</div>
        <div className="text-xs text-zinc-500 mt-0.5 flex flex-wrap items-center gap-1.5">
          <span>Source: {item.source_filename || (item.source_type === "manual_entry" ? "Manual entry" : "—")}</span>
          {item.manual_override && <Badge tone="blue">Manual</Badge>}
          {item.source_type === "bank_transaction" && <Badge tone="violet">Bank txn</Badge>}
          {item.accountant_review_required && <Badge tone="amber">Review</Badge>}
        </div>
      </div>
      <div className="flex items-center gap-3 ml-3 shrink-0">
        <div className="font-semibold text-zinc-900 mono">{fmtAUD(item.amount_cents / 100)}</div>
        <button
          onClick={onDelete}
          disabled={busy}
          data-testid={`tax-item-delete-${item.id}`}
          className="text-xs text-zinc-500 hover:text-red-600 disabled:opacity-50"
        >Remove</button>
      </div>
    </div>
  );
}

function Badge({ tone, children }) {
  const map = {
    blue: "bg-blue-50 text-blue-800 border-blue-200",
    amber: "bg-amber-50 text-amber-800 border-amber-200",
    violet: "bg-violet-50 text-violet-800 border-violet-200",
  };
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${map[tone] || ""}`}>{children}</span>;
}
