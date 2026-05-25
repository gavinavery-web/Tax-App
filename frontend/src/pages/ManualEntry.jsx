import React, { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";

const SECTIONS = [
  { value: "salary_wages", label: "Salary & Wages", side: "income" },
  { value: "allowances", label: "Allowances", side: "income" },
  { value: "interest", label: "Interest", side: "income" },
  { value: "dividends", label: "Dividends", side: "income" },
  { value: "rental_income", label: "Rental Income", side: "income" },
  { value: "work_related_car", label: "Work-Related Car", side: "deduction" },
  { value: "work_related_travel", label: "Work Travel", side: "deduction" },
  { value: "tools_equipment", label: "Tools & Equipment", side: "deduction" },
  { value: "union_fees", label: "Union / Professional Fees", side: "deduction" },
  { value: "donations", label: "Donations / Gifts", side: "deduction" },
  { value: "rental_deductions", label: "Rental Property Expenses", side: "deduction" },
  { value: "other_deductions", label: "Other Deductions", side: "deduction" },
];

export default function ManualEntry() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const initialYear = params.get("year") || "FY2024";
  const [form, setForm] = useState({
    tax_year: ["FY2024", "FY2025"].includes(initialYear) ? initialYear : "FY2024",
    income_or_deduction: "deduction",
    section: "other_deductions",
    amount: "",
    description: "",
    notes: "",
  });
  const [busy, setBusy] = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onSideChange = (side) => {
    // Reset section to the first section matching the new side.
    const first = SECTIONS.find((s) => s.side === side);
    setForm((f) => ({ ...f, income_or_deduction: side, section: first ? first.value : f.section }));
  };

  const submit = async (e) => {
    e.preventDefault();
    const amountNum = parseFloat(form.amount);
    if (!isFinite(amountNum) || amountNum <= 0) { toast.error("Amount must be greater than 0"); return; }
    if (!form.description.trim()) { toast.error("Description is required"); return; }
    setBusy(true);
    try {
      await api.post("/tax-return-items", {
        tax_year: form.tax_year,
        section: form.section,
        amount_cents: Math.round(amountNum * 100),
        description: form.description.trim(),
        income_or_deduction: form.income_or_deduction,
        notes: form.notes,
      });
      toast.success("Manual entry added");
      navigate(`/tax-years/${form.tax_year}`);
    } catch (e2) {
      toast.error(e2.response?.data?.detail || "Failed to add entry");
    } finally {
      setBusy(false);
    }
  };

  const availableSections = SECTIONS.filter((s) => s.side === form.income_or_deduction);

  return (
    <div className="p-6 max-w-2xl mx-auto" data-testid="manual-entry-page">
      <div className="mb-5">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Add manual entry</h1>
        <p className="text-sm text-zinc-500 mt-1">Add a tax-return item that AI missed. This sits alongside the auto-extracted figures and is flagged as manual.</p>
      </div>

      <form onSubmit={submit} className="space-y-4 bg-white p-5 border border-zinc-200 rounded-lg">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Tax year</Label>
            <Select value={form.tax_year} onValueChange={(v) => set("tax_year", v)}>
              <SelectTrigger data-testid="manual-year"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="FY2024">FY2024</SelectItem>
                <SelectItem value="FY2025">FY2025</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Type</Label>
            <Select value={form.income_or_deduction} onValueChange={onSideChange}>
              <SelectTrigger data-testid="manual-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="income">Income</SelectItem>
                <SelectItem value="deduction">Deduction</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div>
          <Label>Section</Label>
          <Select value={form.section} onValueChange={(v) => set("section", v)}>
            <SelectTrigger data-testid="manual-section"><SelectValue /></SelectTrigger>
            <SelectContent>
              {availableSections.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label>Amount (AUD)</Label>
          <Input
            type="number"
            step="0.01"
            min="0"
            value={form.amount}
            onChange={(e) => set("amount", e.target.value)}
            placeholder="0.00"
            required
            data-testid="manual-amount"
          />
        </div>

        <div>
          <Label>Description</Label>
          <Input
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
            placeholder="E.g., Laptop for work"
            required
            data-testid="manual-description"
          />
        </div>

        <div>
          <Label>Notes (optional)</Label>
          <Textarea
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
            rows={3}
            placeholder="Additional context for your accountant…"
            data-testid="manual-notes"
          />
        </div>

        <div className="flex gap-2 justify-end pt-2">
          <Button type="button" variant="ghost" onClick={() => navigate(-1)} disabled={busy}>Cancel</Button>
          <Button type="submit" disabled={busy} data-testid="manual-submit">{busy ? "Adding…" : "Add entry"}</Button>
        </div>
      </form>
    </div>
  );
}

function Label({ children }) {
  return <div className="text-xs mono uppercase text-zinc-500 tracking-wide mb-1">{children}</div>;
}
