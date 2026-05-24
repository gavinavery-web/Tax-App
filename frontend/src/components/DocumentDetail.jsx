import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { api } from "../lib/api";
import { toast } from "sonner";
import { FIGURE_TYPES, fmtAUD, fmtDate } from "../lib/constants";
import { ExternalLink, Trash2, Plus } from "lucide-react";

export default function DocumentDetail({ docId, open, onOpenChange, reference, onChanged }) {
  const [doc, setDoc] = useState(null);
  const [figures, setFigures] = useState([]);
  const [saving, setSaving] = useState(false);
  const [newFig, setNewFig] = useState({ figure_type: "income", amount: "", description: "", source_document: "" });

  const load = async () => {
    if (!docId) return;
    const [d, f] = await Promise.all([
      api.get(`/documents/${docId}`),
      api.get(`/figures`, { params: { document_id: docId } }),
    ]);
    setDoc(d.data);
    setFigures(f.data);
  };

  useEffect(() => { if (open && docId) load(); /* eslint-disable-next-line */ }, [open, docId]);

  const update = async (patch) => {
    setSaving(true);
    try {
      const res = await api.patch(`/documents/${docId}`, patch);
      setDoc(res.data);
      onChanged?.();
    } finally { setSaving(false); }
  };

  const addFigure = async () => {
    if (!newFig.amount) { toast.error("Amount required"); return; }
    const payload = {
      ...newFig,
      amount: parseFloat(newFig.amount),
      document_id: docId,
      tax_year: doc?.tax_year || "",
      category: doc?.category || "",
    };
    await api.post("/figures", payload);
    setNewFig({ figure_type: "income", amount: "", description: "", source_document: "" });
    await load();
    toast.success("Figure added");
  };

  const removeFigure = async (id) => {
    await api.delete(`/figures/${id}`);
    await load();
  };

  const removeDoc = async () => {
    if (!window.confirm("Delete this document (also removes it from Google Drive)?")) return;
    await api.delete(`/documents/${docId}`);
    toast.success("Document deleted");
    onChanged?.();
    onOpenChange(false);
  };

  if (!doc) return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl rounded-sm">
        <div className="text-sm text-zinc-500 py-8 text-center">Loading…</div>
      </DialogContent>
    </Dialog>
  );

  const ref = reference || {};
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="doc-detail-dialog">
        <DialogHeader>
          <DialogTitle className="text-lg flex items-center gap-2" style={{ fontFamily: "Chivo" }}>
            {doc.name}
            {doc.drive_link && (
              <a href={doc.drive_link} target="_blank" rel="noreferrer" className="text-xs text-blue-700 underline flex items-center gap-1" data-testid="doc-drive-link">
                Drive <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </DialogTitle>
          <div className="text-xs text-zinc-500 mono">
            Uploaded {fmtDate(doc.created_at)} · {doc.original_filename} · {(doc.size_bytes / 1024).toFixed(1)} KB
          </div>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3 mt-1">
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Name</Label>
            <Input value={doc.name} onChange={(e) => setDoc({ ...doc, name: e.target.value })} onBlur={(e) => update({ name: e.target.value })} className="rounded-sm mt-1" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Status</Label>
            <Select value={doc.status} onValueChange={(v) => update({ status: v })}>
              <SelectTrigger className="rounded-sm mt-1" data-testid="doc-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{(ref.status_options || []).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Tax year</Label>
            <Select value={doc.tax_year} onValueChange={(v) => update({ tax_year: v })}>
              <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>{(ref.tax_years || []).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Category</Label>
            <Select value={doc.category} onValueChange={(v) => update({ category: v })}>
              <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>{(ref.categories || []).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Accountant review</Label>
            <Select value={doc.accountant_review} onValueChange={(v) => update({ accountant_review: v })}>
              <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="No">No</SelectItem>
                <SelectItem value="Yes">Yes</SelectItem>
                <SelectItem value="Unsure">Unsure</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Drive folder</Label>
            <Input value={doc.drive_folder_name || "—"} readOnly className="rounded-sm mt-1 mono text-xs" />
          </div>
          <div className="col-span-2">
            <Label className="text-xs uppercase tracking-wider text-zinc-500">What it proves</Label>
            <Textarea defaultValue={doc.what_it_proves} onBlur={(e) => update({ what_it_proves: e.target.value })} className="rounded-sm mt-1" />
          </div>
          <div className="col-span-2">
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Missing follow-up</Label>
            <Textarea defaultValue={doc.missing_followup} onBlur={(e) => update({ missing_followup: e.target.value })} className="rounded-sm mt-1" />
          </div>
          <div className="col-span-2">
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Notes</Label>
            <Textarea defaultValue={doc.notes} onBlur={(e) => update({ notes: e.target.value })} className="rounded-sm mt-1" />
          </div>
        </div>

        {/* Figures */}
        <div className="mt-5 border-t border-zinc-200 pt-4">
          <div className="text-sm font-semibold mb-2" style={{ fontFamily: "Chivo" }}>Key figures (manual entry)</div>
          {figures.length > 0 && (
            <table className="w-full dense-table text-sm mb-3">
              <thead>
                <tr><th>Type</th><th>Amount</th><th>Description</th><th>Source</th><th></th></tr>
              </thead>
              <tbody>
                {figures.map((f) => (
                  <tr key={f.id}>
                    <td className="mono text-xs">{f.figure_type}</td>
                    <td className="mono text-right">{fmtAUD(f.amount)}</td>
                    <td>{f.description}</td>
                    <td className="text-zinc-500">{f.source_document}</td>
                    <td className="text-right">
                      <button onClick={() => removeFigure(f.id)} className="text-zinc-500 hover:text-red-700" data-testid={`fig-delete-${f.id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="grid grid-cols-12 gap-2 items-end">
            <div className="col-span-3">
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Type</Label>
              <Select value={newFig.figure_type} onValueChange={(v) => setNewFig({ ...newFig, figure_type: v })}>
                <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>{FIGURE_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Amount</Label>
              <Input type="number" step="0.01" value={newFig.amount} onChange={(e) => setNewFig({ ...newFig, amount: e.target.value })} className="rounded-sm mt-1 mono" data-testid="fig-amount-input" />
            </div>
            <div className="col-span-4">
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Description</Label>
              <Input value={newFig.description} onChange={(e) => setNewFig({ ...newFig, description: e.target.value })} className="rounded-sm mt-1" />
            </div>
            <div className="col-span-2">
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Source</Label>
              <Input value={newFig.source_document} onChange={(e) => setNewFig({ ...newFig, source_document: e.target.value })} className="rounded-sm mt-1" />
            </div>
            <div className="col-span-1">
              <Button onClick={addFigure} className="rounded-sm w-full bg-zinc-950 hover:bg-zinc-800" data-testid="fig-add-btn">
                <Plus className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={removeDoc} className="rounded-sm border-red-300 text-red-700 hover:bg-red-50" data-testid="doc-delete-btn">
            <Trash2 className="w-4 h-4 mr-2" /> Delete document
          </Button>
          <Button onClick={() => onOpenChange(false)} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="doc-close-btn">Close</Button>
        </DialogFooter>
        {saving && <div className="text-xs text-zinc-500">Saving…</div>}
      </DialogContent>
    </Dialog>
  );
}
