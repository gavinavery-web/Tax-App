import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Label } from "../components/ui/label";
import { StatusPill } from "../components/StatusPill";
import { MISSING_STATUS_OPTIONS } from "../lib/constants";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

const PRIORITIES = ["Critical", "Important", "Later"];

export default function MissingEvidence() {
  const [items, setItems] = useState([]);
  const [reference, setReference] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [draft, setDraft] = useState({ item_needed: "", category: "Other", tax_year: "Both", priority: "Important", where_to_find: "", why_matters: "", status: "Not started", notes: "" });

  const load = async () => {
    const [m, r] = await Promise.all([api.get("/missing-evidence"), api.get("/reference")]);
    setItems(m.data); setReference(r.data);
  };
  useEffect(() => { load(); }, []);

  const update = async (id, patch) => {
    await api.patch(`/missing-evidence/${id}`, patch);
    load();
  };
  const remove = async (id) => {
    if (!window.confirm("Delete this item?")) return;
    await api.delete(`/missing-evidence/${id}`);
    load();
  };
  const create = async () => {
    if (!draft.item_needed.trim()) { toast.error("Item name required"); return; }
    await api.post("/missing-evidence", draft);
    setAddOpen(false);
    setDraft({ ...draft, item_needed: "", where_to_find: "", why_matters: "", notes: "" });
    toast.success("Item added");
    load();
  };

  const grouped = PRIORITIES.map((p) => ({ priority: p, items: items.filter((i) => i.priority === p) }));
  const remaining = items.filter((i) => i.status !== "Found").length;

  return (
    <div className="p-6" data-testid="missing-page">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Missing Evidence Tracker</h1>
          <div className="text-sm text-zinc-500 mt-1">
            <span className="mono font-semibold text-zinc-900">{remaining}</span> outstanding · sourced from preloaded known-missing items
          </div>
        </div>
        <Button onClick={() => setAddOpen(true)} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="missing-add-btn">
          <Plus className="w-4 h-4 mr-2" /> Add item
        </Button>
      </div>

      {grouped.map(({ priority, items: rows }) => (
        <div key={priority} className="bg-white border border-zinc-200 rounded-sm mb-4">
          <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-200">
            <div className="flex items-center gap-2">
              <StatusPill value={priority} kind="priority" />
              <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>{priority}</div>
            </div>
            <div className="text-[11px] text-zinc-500 mono">{rows.filter((r) => r.status !== "Found").length} / {rows.length} outstanding</div>
          </div>
          <table className="w-full dense-table text-sm">
            <thead>
              <tr>
                <th style={{ width: "32%" }}>Item needed</th>
                <th>Category</th>
                <th>FY</th>
                <th>Where to find</th>
                <th>Why it matters</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((it) => (
                <tr key={it.id} data-testid={`missing-row-${it.id}`}>
                  <td className="font-medium">{it.item_needed}</td>
                  <td className="text-xs">{it.category}</td>
                  <td className="mono text-xs">{it.tax_year}</td>
                  <td className="text-xs text-zinc-600">{it.where_to_find}</td>
                  <td className="text-xs text-zinc-600">{it.why_matters}</td>
                  <td>
                    <Select value={it.status} onValueChange={(v) => update(it.id, { status: v })}>
                      <SelectTrigger className="rounded-sm h-7 w-32 text-xs" data-testid={`missing-status-${it.id}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{MISSING_STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="text-right">
                    <button onClick={() => remove(it.id)} className="text-zinc-400 hover:text-red-700"><Trash2 className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} className="text-center text-zinc-400 py-4 text-xs">No items</td></tr>}
            </tbody>
          </table>
        </div>
      ))}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader><DialogTitle style={{ fontFamily: "Chivo" }}>Add missing item</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Item needed</Label>
              <Input value={draft.item_needed} onChange={(e) => setDraft({ ...draft, item_needed: e.target.value })} className="rounded-sm mt-1" data-testid="missing-item-input" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label className="text-xs uppercase tracking-wider text-zinc-500">Category</Label>
                <Select value={draft.category} onValueChange={(v) => setDraft({ ...draft, category: v })}>
                  <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>{(reference?.categories || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider text-zinc-500">FY</Label>
                <Select value={draft.tax_year} onValueChange={(v) => setDraft({ ...draft, tax_year: v })}>
                  <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>{(reference?.tax_years || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider text-zinc-500">Priority</Label>
                <Select value={draft.priority} onValueChange={(v) => setDraft({ ...draft, priority: v })}>
                  <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>{PRIORITIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Where to find</Label>
              <Input value={draft.where_to_find} onChange={(e) => setDraft({ ...draft, where_to_find: e.target.value })} className="rounded-sm mt-1" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Why it matters</Label>
              <Textarea value={draft.why_matters} onChange={(e) => setDraft({ ...draft, why_matters: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)} className="rounded-sm">Cancel</Button>
            <Button onClick={create} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="missing-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
