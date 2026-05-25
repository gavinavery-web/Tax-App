import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, API } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Label } from "../components/ui/label";
import { StatusPill } from "../components/StatusPill";
import FigureBadge from "../components/FigureBadge";
import UploadQueue from "../components/UploadQueue";
import { HelpTip } from "../components/HelpTip";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { fmtDate, fmtAUD } from "../lib/constants";
import { TAX_YEAR_OPTIONS } from "../utils/taxYear";
import { Upload, ExternalLink, Search, Filter, AlertTriangle, FolderUp, Files, Trash2, Download, FileText } from "lucide-react";
import { toast } from "sonner";

const ACCEPTED = ".pdf,.png,.jpg,.jpeg,.webp,.heic,.heif,.xls,.xlsx,.csv,.doc,.docx,.txt";

function Dropzone({ onFiles }) {
  const fileRef = useRef(null);
  const folderRef = useRef(null);
  const [drag, setDrag] = useState(false);

  const handle = (fileList) => {
    if (!fileList || !fileList.length) return;
    const arr = Array.from(fileList).filter((f) => f && f.size != null);
    const oversize = arr.filter((f) => f.size > 50 * 1024 * 1024);
    if (oversize.length) toast.warning(`${oversize.length} file(s) over 50MB will still upload but may be slow.`);
    onFiles(arr);
  };

  const onDrop = async (e) => {
    e.preventDefault(); e.stopPropagation(); setDrag(false);
    const items = e.dataTransfer.items;
    if (items && items.length && items[0].webkitGetAsEntry) {
      // walk folder structure
      const all = [];
      const walk = (entry) => new Promise((resolve) => {
        if (entry.isFile) {
          entry.file((f) => { all.push(f); resolve(); });
        } else if (entry.isDirectory) {
          const reader = entry.createReader();
          reader.readEntries(async (entries) => {
            for (const ent of entries) { await walk(ent); }
            resolve();
          });
        } else resolve();
      });
      await Promise.all(Array.from(items).map((it) => {
        const ent = it.webkitGetAsEntry && it.webkitGetAsEntry();
        return ent ? walk(ent) : Promise.resolve();
      }));
      if (all.length) return handle(all);
    }
    handle(e.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      className={`border-2 border-dashed rounded-sm bg-white px-6 py-8 text-center transition ${drag ? "border-zinc-900 bg-zinc-50" : "border-zinc-300"}`}
      data-testid="dropzone"
    >
      <div className="flex flex-col items-center gap-2">
        <Upload className="w-6 h-6 text-zinc-500" />
        <div className="text-sm text-zinc-700" style={{ fontFamily: "Chivo" }}>Drag a folder or files here, or click to browse</div>
        <div className="text-[11px] text-zinc-500 mono">PDF · PNG/JPG · DOCX · XLSX · CSV · TXT — no file count limit</div>
        <div className="flex gap-2 mt-2">
          <input ref={fileRef} type="file" multiple accept={ACCEPTED} hidden onChange={(e) => handle(e.target.files)} data-testid="dropzone-files-input" />
          <input ref={folderRef} type="file" hidden webkitdirectory="" directory="" multiple onChange={(e) => handle(e.target.files)} data-testid="dropzone-folder-input" />
          <Button variant="outline" onClick={() => fileRef.current?.click()} className="rounded-sm" data-testid="dz-select-files-btn"><Files className="w-4 h-4 mr-2" /> Select files</Button>
          <Button variant="outline" onClick={() => folderRef.current?.click()} className="rounded-sm" data-testid="dz-select-folder-btn"><FolderUp className="w-4 h-4 mr-2" /> Select folder</Button>
        </div>
      </div>
    </div>
  );
}

function EditRow({ docId, open, onClose, reference, onSaved }) {
  const [doc, setDoc] = useState(null);
  useEffect(() => { if (open && docId) api.get(`/documents/${docId}`).then((r) => setDoc(r.data)); }, [open, docId]);
  if (!open) return null;
  const update = (patch) => api.patch(`/documents/${docId}`, patch).then((r) => { setDoc(r.data); onSaved?.(); });
  const updateFigure = (idx, patch) => {
    const figs = (doc.headline_figures_json || []).map((f, i) => i === idx ? { ...f, ...patch } : f);
    update({}).then(() => api.patch(`/documents/${docId}/figures`, { figures: figs }).then((r) => { setDoc(r.data); onSaved?.(); }));
  };
  const ref = reference || {};
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl rounded-sm max-h-[92vh] overflow-y-auto" data-testid="edit-row-dialog">
        <DialogHeader>
          <DialogTitle className="text-base" style={{ fontFamily: "Chivo" }}>{doc?.name || "…"}</DialogTitle>
          {doc?.drive_link && <a href={doc.drive_link} target="_blank" rel="noreferrer" className="text-xs text-blue-700 underline">open in Drive</a>}
        </DialogHeader>
        {doc && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs uppercase tracking-wider text-zinc-500">Category</Label>
                <Select value={doc.category} onValueChange={(v) => update({ category: v })}>
                  <SelectTrigger className="rounded-sm mt-1" data-testid="edit-category"><SelectValue /></SelectTrigger>
                  <SelectContent>{(ref.categories || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider text-zinc-500">Tax year</Label>
                <Select value={doc.tax_year} onValueChange={(v) => update({ tax_year: v })}>
                  <SelectTrigger className="rounded-sm mt-1" data-testid="edit-taxyear"><SelectValue /></SelectTrigger>
                  <SelectContent>{TAX_YEAR_OPTIONS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider text-zinc-500">Accountant review</Label>
                <Select value={doc.accountant_review} onValueChange={(v) => update({ accountant_review: v })}>
                  <SelectTrigger className="rounded-sm mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Yes">Yes</SelectItem>
                    <SelectItem value="No">No</SelectItem>
                    <SelectItem value="Unsure">Unsure</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="bg-zinc-50 border border-zinc-200 rounded-sm p-2">
                <div className="text-[11px] uppercase tracking-wider text-zinc-500">Category confidence</div>
                <div className="mt-1"><FigureBadge value={doc.category_confidence || "Unsure"} /></div>
              </div>
              <div className="bg-zinc-50 border border-zinc-200 rounded-sm p-2">
                <div className="text-[11px] uppercase tracking-wider text-zinc-500">Tax-year confidence</div>
                <div className="mt-1"><FigureBadge value={doc.tax_year_confidence || "Unsure"} /></div>
              </div>
              <div className="bg-zinc-50 border border-zinc-200 rounded-sm p-2">
                <div className="text-[11px] uppercase tracking-wider text-zinc-500">AI cost · model</div>
                <div className="mt-1 mono text-xs">${(doc.ai_cost_usd || 0).toFixed(4)}{doc.ai_response_cached && " (cached)"}</div>
                <div className="text-[11px] text-zinc-500 mono">{doc.ai_model_used || "—"}</div>
              </div>
            </div>
            {doc.accountant_review_required && doc.accountant_review_reason && (
              <div className="bg-amber-50 border border-amber-200 rounded-sm p-2 text-xs text-amber-900">
                <span className="font-semibold">Accountant review: </span>{doc.accountant_review_reason}
              </div>
            )}
            <div>
              <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Headline figures</div>
              {(doc.headline_figures_json || []).length === 0 && <div className="text-xs text-zinc-400">No figures extracted.</div>}
              <table className="w-full dense-table text-xs">
                <tbody>
                  {(doc.headline_figures_json || []).map((f, i) => (
                    <tr key={i} data-testid={`figure-${i}`}>
                      <td className="font-medium">{f.label}</td>
                      <td className="mono text-right">{fmtAUD(f.amount)}</td>
                      <td><FigureBadge value={f.confidence} /></td>
                      <td className="text-zinc-500 max-w-[260px] truncate" title={f.source_quote}>{f.source_quote}</td>
                      <td>
                        {f.verified === false && <span className="text-red-700 text-[11px] flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> unverified</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-zinc-500">What it proves</Label>
              <Textarea defaultValue={doc.what_it_proves} onBlur={(e) => update({ what_it_proves: e.target.value })} className="rounded-sm mt-1" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-zinc-500">User notes</Label>
              <Textarea defaultValue={doc.user_notes || ""} onBlur={(e) => update({ user_notes: e.target.value })} className="rounded-sm mt-1" />
            </div>
            <div className="text-[11px] text-zinc-500 mono leading-relaxed">
              SHA-256: {doc.sha256 || "—"}<br />
              Stored: {doc.storage || "—"} · {doc.local_path || ""}<br />
              Tax year reason: {doc.tax_year_reason || "—"}<br />
              {doc.drive_error && <span className="text-red-700">Drive error: {doc.drive_error}</span>}
            </div>
          </div>
        )}
        <DialogFooter>
          <Button onClick={onClose} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="edit-close">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function EvidenceRegister() {
  const [docs, setDocs] = useState([]);
  const [reference, setReference] = useState(null);
  const [search, setSearch] = useState("");
  const [params, setParams] = useSearchParams();
  const cat = params.get("category") || "all";
  const ty = params.get("tax_year") || "all";
  const review = params.get("review") || "all";
  const [editId, setEditId] = useState(null);

  const load = async () => {
    const q = {};
    if (cat !== "all") q.category = cat;
    if (ty !== "all") q.tax_year = ty;
    if (review !== "all") q.accountant_review = review;
    const [d, r] = await Promise.all([
      api.get("/documents", { params: q }),
      reference ? Promise.resolve({ data: reference }) : api.get("/reference"),
    ]);
    setDocs(d.data);
    if (!reference) setReference(r.data);
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [cat, ty, review]);

  const setFilter = (key, val) => {
    const next = new URLSearchParams(params);
    if (val === "all") next.delete(key); else next.set(key, val);
    setParams(next, { replace: true });
  };

  const uploadFiles = async (files) => {
    if (!files.length) return;
    toast.success(`Queuing ${files.length} file(s)…`);
    // chunk to avoid huge multipart bodies
    const CHUNK = 25;
    for (let i = 0; i < files.length; i += CHUNK) {
      const fd = new FormData();
      files.slice(i, i + CHUNK).forEach((f) => fd.append("files", f));
      try {
        await api.post("/uploads/bulk", fd, { headers: { "Content-Type": "multipart/form-data" } });
      } catch (e) {
        toast.error(`Upload batch failed: ${e.response?.data?.detail || e.message}`);
        break;
      }
    }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return docs;
    const s = search.toLowerCase();
    return docs.filter((d) =>
      [d.name, d.notes, d.category, d.tax_year, d.one_line_summary, d.counterparty, d.user_notes]
        .filter(Boolean).join(" ").toLowerCase().includes(s),
    );
  }, [docs, search]);

  return (
    <div className="p-6" data-testid="register-page">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Evidence Register</h1>
          <div className="text-sm text-zinc-500 mt-1">Drag files or a folder to bulk-upload. Each document is classified by AI, filed to Google Drive, and stored locally as a vault copy.</div>
        </div>
        <div className="flex gap-2">
          <a
            href={`${API}/reports/evidence-register.csv`}
            className="inline-flex items-center gap-1 rounded-sm border border-zinc-200 bg-white hover:bg-zinc-50 text-sm px-3 py-1.5"
            data-testid="export-register-csv"
            download
          >
            <Download className="w-4 h-4" /> Export CSV
          </a>
          <a
            href={`${API}/reports/accountant-summary.txt`}
            className="inline-flex items-center gap-1 rounded-sm border border-zinc-200 bg-white hover:bg-zinc-50 text-sm px-3 py-1.5"
            data-testid="export-summary-txt"
            download
          >
            <FileText className="w-4 h-4" /> Accountant summary
          </a>
        </div>
      </div>

      <Dropzone onFiles={uploadFiles} />
      <div className="h-3" />
      <UploadQueue onChanged={load} />

      <div className="bg-white border border-zinc-200 rounded-sm p-3 mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 text-xs text-zinc-500 uppercase tracking-wider mr-2">
          <Filter className="w-3.5 h-3.5" /> Filters
        </div>
        <Select value={cat} onValueChange={(v) => setFilter("category", v)}>
          <SelectTrigger className="rounded-sm w-56 h-9" data-testid="filter-category"><SelectValue placeholder="Category" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {(reference?.categories || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={ty} onValueChange={(v) => setFilter("tax_year", v)}>
          <SelectTrigger className="rounded-sm w-40 h-9" data-testid="filter-taxyear"><SelectValue placeholder="Tax year" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All years</SelectItem>
            {TAX_YEAR_OPTIONS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={review} onValueChange={(v) => setFilter("review", v)}>
          <SelectTrigger className="rounded-sm w-44 h-9" data-testid="filter-review"><SelectValue placeholder="Review?" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any review state</SelectItem>
            <SelectItem value="Yes">Review required</SelectItem>
            <SelectItem value="No">Not flagged</SelectItem>
            <SelectItem value="Unsure">Unsure</SelectItem>
          </SelectContent>
        </Select>
        <div className="ml-auto flex items-center gap-2">
          <Search className="w-3.5 h-3.5 text-zinc-400" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search…" className="rounded-sm h-9 w-64" data-testid="register-search" />
        </div>
      </div>

      <div className="bg-white border border-zinc-200 rounded-sm overflow-auto">
        <table className="w-full dense-table text-sm" data-testid="register-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Document</th>
              <th>Folder</th>
              <th>Link</th>
              <th>Tax year</th>
              <th>Category</th>
              <th>Confidence <HelpTip text="How sure the AI is about the category. Confirmed = matched explicit keywords. Likely = strong signal. Unsure = filed to 00 Inbox for manual review." /></th>
              <th>Review <HelpTip text="Items the AI flagged for an accountant or you to look at — typically due to risky claims, missing context, or low text quality." /></th>
              <th>AI $ <HelpTip text="Cost incurred by Gemini + Claude for this document. Cached re-uploads cost $0." /></th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr key={d.id} onClick={() => setEditId(d.id)} className="cursor-pointer" data-testid={`row-${d.id}`}>
                <td className="mono text-xs text-zinc-600 whitespace-nowrap">{fmtDate(d.created_at)}</td>
                <td className="font-medium max-w-[280px] truncate" title={d.one_line_summary || d.name}>{d.name}</td>
                <td className="mono text-xs text-zinc-600">{d.drive_folder_name || "—"}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  {d.drive_link ? (
                    <a href={d.drive_link} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline flex items-center gap-1 text-xs"><span>drive</span> <ExternalLink className="w-3 h-3" /></a>
                  ) : d.local_path ? (
                    <a href={`${process.env.REACT_APP_BACKEND_URL}/api/documents/${d.id}/download`} className="text-blue-700 hover:underline text-xs">local</a>
                  ) : <span className="text-zinc-400 text-xs">—</span>}
                </td>
                <td className="mono">{d.tax_year}</td>
                <td className="text-xs">{d.category}</td>
                <td><FigureBadge value={d.category_confidence || "Unsure"} /></td>
                <td className="text-xs">{d.accountant_review === "Yes" ? <span className="text-red-700 font-semibold">Review</span> : d.accountant_review}</td>
                <td className="mono text-right text-xs">${(d.ai_cost_usd || 0).toFixed(3)}{d.ai_response_cached && <span className="text-zinc-400"> c</span>}</td>
                <td><StatusPill value={d.status} /></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={10} className="text-center text-zinc-500 py-10 text-sm">No documents yet. Drag a folder onto the dropzone above.</td></tr>}
          </tbody>
        </table>
      </div>

      <EditRow docId={editId} open={!!editId} onClose={() => setEditId(null)} reference={reference} onSaved={load} />
    </div>
  );
}
