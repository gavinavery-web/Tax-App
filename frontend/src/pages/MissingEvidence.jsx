import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { API } from "../lib/api";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import UploadQueue from "../components/UploadQueue";
import { toast } from "sonner";
import {
  CheckCircle2, AlertOctagon, AlertTriangle, Inbox, ShieldCheck,
  RotateCcw, Star, Upload, FolderUp, Files, Download,
} from "lucide-react";

const STATUS = ["Outstanding", "Possible Match", "Received", "Not applicable", "Accountant Review"];
const PRIORITY_ORDER = ["Critical", "Important", "Later"];
const ACCEPTED = ".pdf,.png,.jpg,.jpeg,.webp,.heic,.heif,.xls,.xlsx,.csv,.doc,.docx,.txt";

const STATUS_PALETTE = {
  Outstanding:        { bg: "#FEF2F2", fg: "#991B1B", border: "#FECACA" },
  "Possible Match":   { bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  Received:           { bg: "#F0FDF4", fg: "#166534", border: "#BBF7D0" },
  "Not applicable":   { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" },
  "Accountant Review":{ bg: "#EFF6FF", fg: "#1E40AF", border: "#BFDBFE" },
};

const PRIORITY_PALETTE = {
  Critical:  { bg: "#FEF2F2", fg: "#991B1B", border: "#FECACA" },
  Important: { bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  Later:     { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" },
};

// ----------- Upload helper (chunked, identical pattern to EvidenceRegister) -----------
async function uploadFilesChunked(files) {
  const arr = Array.from(files || []).filter((f) => f && f.size != null);
  if (!arr.length) return false;
  const oversize = arr.filter((f) => f.size > 50 * 1024 * 1024);
  if (oversize.length) toast.warning(`${oversize.length} file(s) over 50MB will still upload but may be slow.`);
  toast.success(`Queuing ${arr.length} file(s)…`);
  const CHUNK = 25;
  for (let i = 0; i < arr.length; i += CHUNK) {
    const fd = new FormData();
    arr.slice(i, i + CHUNK).forEach((f) => fd.append("files", f));
    try {
      await api.post("/uploads/bulk", fd, { headers: { "Content-Type": "multipart/form-data" } });
    } catch (e) {
      toast.error(`Upload batch failed: ${e.response?.data?.detail || e.message}`);
      return false;
    }
  }
  return true;
}

// ----------- Per-row inline upload button -----------
function RowUploadButton({ itemId, onUploaded }) {
  const ref = useRef(null);
  return (
    <>
      <input
        ref={ref}
        type="file"
        hidden
        multiple
        accept={ACCEPTED}
        onChange={async (e) => {
          const ok = await uploadFilesChunked(e.target.files);
          e.target.value = "";
          if (ok) onUploaded?.();
        }}
        data-testid={`row-upload-input-${itemId}`}
      />
      <Button
        size="sm"
        variant="outline"
        onClick={() => ref.current?.click()}
        className="rounded-sm h-7 px-2 text-[11px]"
        data-testid={`btn-upload-for-${itemId}`}
        title="Upload document(s) — the AI will auto-match to this item if appropriate"
      >
        <Upload className="w-3 h-3 mr-1" /> Upload
      </Button>
    </>
  );
}

// ----------- Top quick-upload bar (file + folder) -----------
function QuickUploadBar({ onUploaded }) {
  const fileRef = useRef(null);
  const folderRef = useRef(null);
  const handle = async (fl) => {
    const ok = await uploadFilesChunked(fl);
    if (ok) onUploaded?.();
  };
  return (
    <div className="bg-white border border-zinc-200 rounded-sm px-4 py-3 mb-4 flex items-center justify-between" data-testid="quick-upload-bar">
      <div>
        <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>Have documents ready?</div>
        <div className="text-[11px] text-zinc-500 mt-0.5">
          Upload here — the AI auto-matches each file to an outstanding item where safe. Tip: press <span className="mono">Ctrl/⌘+U</span>.
        </div>
      </div>
      <div className="flex gap-2">
        <input ref={fileRef} type="file" hidden multiple accept={ACCEPTED} onChange={(e) => { handle(e.target.files); e.target.value = ""; }} data-testid="quick-upload-files-input" />
        <input ref={folderRef} type="file" hidden multiple webkitdirectory="" directory="" onChange={(e) => { handle(e.target.files); e.target.value = ""; }} data-testid="quick-upload-folder-input" />
        <Button variant="outline" onClick={() => fileRef.current?.click()} className="rounded-sm" data-testid="quick-upload-files-btn">
          <Files className="w-4 h-4 mr-2" /> Upload files
        </Button>
        <Button variant="outline" onClick={() => folderRef.current?.click()} className="rounded-sm" data-testid="quick-upload-folder-btn">
          <FolderUp className="w-4 h-4 mr-2" /> Upload folder
        </Button>
      </div>
    </div>
  );
}

const Section = ({ title, items, icon: Icon, onChange, onUpdate, onNotes, onUploaded, allowUpload }) => (
  <div className="bg-white border border-zinc-200 rounded-sm mb-4">
    <div className="px-4 py-2 border-b border-zinc-200 flex items-center justify-between">
      <div className="flex items-center gap-2">
        {Icon && <Icon className="w-4 h-4 text-zinc-700" />}
        <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>{title}</div>
      </div>
      <div className="text-[11px] text-zinc-500 mono">{items.length} items</div>
    </div>
    {items.length === 0 ? (
      <div className="text-xs text-zinc-400 px-4 py-3">No items.</div>
    ) : (
      <table className="w-full dense-table text-sm">
        <thead>
          <tr>
            <th style={{ width: "12%" }}>Priority / FY</th>
            <th style={{ width: "30%" }}>Item</th>
            <th>Match info</th>
            <th>Notes</th>
            <th style={{ width: "18%" }}>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const pp = PRIORITY_PALETTE[it.priority] || PRIORITY_PALETTE.Later;
            return (
              <tr key={it.id} data-testid={`missing-row-${it.id}`}>
                <td>
                  <span className="pill" style={{ background: pp.bg, color: pp.fg, borderColor: pp.border }}>{it.priority}</span>
                  <div className="text-[11px] mono text-zinc-500 mt-1">{it.tax_year}</div>
                </td>
                <td>
                  <div className="font-medium">{it.item_description || it.item_needed}</div>
                  <div className="text-[11px] text-zinc-500 mt-0.5">{it.category}</div>
                  {it.notes && (
                    <div className="text-[11px] text-zinc-600 mt-1 leading-snug italic" data-testid={`need-helper-${it.id}`}>
                      Need: {it.notes}
                    </div>
                  )}
                </td>
                <td className="text-xs">
                  {it.matched_document_name ? (
                    <div>
                      <span className="font-medium mono text-xs">{it.matched_document_name}</span>
                      {it.match_confidence && <span className="ml-2 text-[11px] text-zinc-500">({it.match_confidence})</span>}
                      {it.match_reason && <div className="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">{it.match_reason}</div>}
                    </div>
                  ) : <span className="text-zinc-400">—</span>}
                </td>
                <td className="text-xs text-zinc-600 max-w-[260px]">
                  <Textarea
                    defaultValue={it.notes_user || ""}
                    placeholder="Your notes…"
                    onBlur={(e) => onNotes(it.id, e.target.value)}
                    className="rounded-sm text-xs min-h-[40px]"
                    data-testid={`missing-notes-${it.id}`}
                  />
                </td>
                <td>
                  <Select value={it.status} onValueChange={(v) => onChange(it.id, v)}>
                    <SelectTrigger className="rounded-sm h-7 w-40 text-xs" data-testid={`missing-status-${it.id}`}><SelectValue /></SelectTrigger>
                    <SelectContent>{STATUS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </td>
                <td className="text-right">
                  <div className="flex flex-wrap gap-1 justify-end">
                    {allowUpload && <RowUploadButton itemId={it.id} onUploaded={onUploaded} />}
                    <Button size="sm" variant="outline" onClick={() => onChange(it.id, "Received")} className="rounded-sm h-7 px-2 text-[11px]" data-testid={`btn-received-${it.id}`}>Received</Button>
                    <Button size="sm" variant="outline" onClick={() => onChange(it.id, "Not applicable")} className="rounded-sm h-7 px-2 text-[11px]">N/A</Button>
                    <Button size="sm" variant="outline" onClick={() => onChange(it.id, "Accountant Review")} className="rounded-sm h-7 px-2 text-[11px]">Accountant</Button>
                    <Button size="sm" variant="outline" onClick={() => onChange(it.id, "Outstanding")} className="rounded-sm h-7 px-2 text-[11px]" data-testid={`btn-reset-${it.id}`}><RotateCcw className="w-3 h-3" /></Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    )}
  </div>
);

export default function MissingEvidence() {
  const [items, setItems] = useState([]);
  const [next, setNext] = useState(null);
  const quickFileRef = useRef(null);

  const load = useCallback(async () => {
    const [m, nx] = await Promise.all([api.get("/missing-evidence"), api.get("/missing-evidence/next")]);
    setItems(m.data);
    setNext(nx.data?.item || null);
  }, []);
  useEffect(() => { load(); }, [load]);

  // Ctrl/Cmd + U keyboard shortcut → open file picker
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "u" || e.key === "U")) {
        e.preventDefault();
        document.querySelector('[data-testid="quick-upload-files-input"]')?.click();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const updateStatus = async (id, status) => {
    const patch = { status };
    if (status === "Outstanding") {
      patch.matched_document_id = null;
      patch.matched_document_name = null;
      patch.match_confidence = null;
      patch.match_reason = null;
    }
    await api.patch(`/missing-evidence/${id}`, patch);
    toast.success(`Marked: ${status}`);
    load();
  };
  const updateNotes = async (id, notes_user) => { await api.patch(`/missing-evidence/${id}`, { notes_user }); };
  const reseed = async () => { const r = await api.post("/missing-evidence/seed"); toast.success(`Seed: +${r.data.inserted} new, ${r.data.refreshed} refreshed`); load(); };

  const buckets = useMemo(() => {
    const sortKey = (a, b) => (PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority)) || (a.created_at || "").localeCompare(b.created_at || "");
    return {
      Outstanding: items.filter((i) => i.status === "Outstanding").sort(sortKey),
      "Possible Match": items.filter((i) => i.status === "Possible Match").sort(sortKey),
      Received: items.filter((i) => i.status === "Received").sort(sortKey),
      "Accountant Review": items.filter((i) => i.status === "Accountant Review").sort(sortKey),
      "Not applicable": items.filter((i) => i.status === "Not applicable").sort(sortKey),
    };
  }, [items]);

  const totals = {
    out: buckets.Outstanding.length,
    poss: buckets["Possible Match"].length,
    rec: buckets.Received.length,
    na: buckets["Not applicable"].length,
    ar: buckets["Accountant Review"].length,
  };

  return (
    <div className="p-6" data-testid="missing-evidence-page">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Missing Evidence</h1>
          <div className="text-sm text-zinc-500 mt-1" data-testid="counts-summary">
            <span className="mono">{totals.out}</span> outstanding · <span className="mono">{totals.poss}</span> possible match · <span className="mono">{totals.rec}</span> received · <span className="mono">{totals.ar}</span> accountant · <span className="mono">{totals.na}</span> N/A
          </div>
        </div>
        <div className="flex gap-2">
          <a
            href={`${API}/reports/missing-evidence.csv`}
            className="inline-flex items-center gap-1 rounded-sm border border-zinc-200 bg-white hover:bg-zinc-50 text-sm px-3 py-1.5"
            data-testid="export-csv-link"
          >
            <Download className="w-4 h-4" /> Export CSV
          </a>
          <Button variant="outline" onClick={reseed} className="rounded-sm" data-testid="missing-reseed-btn">Re-seed checklist</Button>
        </div>
      </div>

      <QuickUploadBar onUploaded={load} />
      <UploadQueue onChanged={load} />

      {next ? (
        <div className="bg-zinc-950 text-white rounded-sm p-4 mb-5 flex items-start gap-3" data-testid="next-best-card">
          <Star className="w-5 h-5 mt-0.5 text-amber-300" />
          <div className="flex-1">
            <div className="text-[11px] uppercase tracking-wider text-zinc-300">Next best document to find</div>
            <div className="text-base font-semibold mt-0.5" style={{ fontFamily: "Chivo" }}>{next.item_description}</div>
            <div className="text-xs text-zinc-300 mt-1">
              {next.priority} · {next.category} · {next.tax_year}
            </div>
            {next.notes && <div className="text-xs text-zinc-300 mt-1 leading-relaxed">Need: {next.notes}</div>}
          </div>
          <RowUploadButton itemId={`next-${next.id}`} onUploaded={load} />
          <Button onClick={() => updateStatus(next.id, "Not applicable")} variant="outline" className="rounded-sm bg-transparent text-white border-zinc-600 hover:bg-zinc-800 text-xs">Skip</Button>
        </div>
      ) : (
        <div className="bg-green-50 border border-green-200 rounded-sm p-3 mb-5 text-sm text-green-900 flex items-center gap-2" data-testid="all-clear">
          <CheckCircle2 className="w-4 h-4" /> No outstanding items — checklist complete.
        </div>
      )}

      <Section title="Outstanding" items={buckets.Outstanding} icon={AlertOctagon} onChange={updateStatus} onNotes={updateNotes} onUploaded={load} allowUpload />
      <Section title="Possible Match (review required)" items={buckets["Possible Match"]} icon={AlertTriangle} onChange={updateStatus} onNotes={updateNotes} onUploaded={load} allowUpload />
      <Section title="Received" items={buckets.Received} icon={CheckCircle2} onChange={updateStatus} onNotes={updateNotes} />
      <Section title="Accountant Review" items={buckets["Accountant Review"]} icon={ShieldCheck} onChange={updateStatus} onNotes={updateNotes} onUploaded={load} allowUpload />
      <Section title="Not applicable" items={buckets["Not applicable"]} icon={Inbox} onChange={updateStatus} onNotes={updateNotes} />
    </div>
  );
}
