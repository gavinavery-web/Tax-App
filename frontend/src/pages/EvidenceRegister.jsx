import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { StatusPill } from "../components/StatusPill";
import UploadDialog from "../components/UploadDialog";
import DocumentDetail from "../components/DocumentDetail";
import { fmtDate } from "../lib/constants";
import { Upload, ExternalLink, Search, Filter } from "lucide-react";

export default function EvidenceRegister() {
  const [docs, setDocs] = useState([]);
  const [reference, setReference] = useState(null);
  const [search, setSearch] = useState("");
  const [params, setParams] = useSearchParams();
  const cat = params.get("category") || "all";
  const ty = params.get("tax_year") || "all";
  const review = params.get("review") || "all";
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedId, setSelectedId] = useState(null);

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

  const filtered = useMemo(() => {
    if (!search.trim()) return docs;
    const s = search.toLowerCase();
    return docs.filter((d) =>
      [d.name, d.notes, d.category, d.tax_year, d.what_it_proves, d.missing_followup]
        .filter(Boolean).join(" ").toLowerCase().includes(s),
    );
  }, [docs, search]);

  return (
    <div className="p-6" data-testid="register-page">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Evidence Register</h1>
          <div className="text-sm text-zinc-500 mt-1">Every uploaded document. Click a row to inspect, edit, and add manual figures.</div>
        </div>
        <Button onClick={() => setUploadOpen(true)} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="register-upload-btn">
          <Upload className="w-4 h-4 mr-2" /> Upload
        </Button>
      </div>

      {/* Filters */}
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
            {(reference?.tax_years || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
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
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search docs…" className="rounded-sm h-9 w-64" data-testid="register-search" />
        </div>
      </div>

      <div className="bg-white border border-zinc-200 rounded-sm overflow-auto">
        <table className="w-full dense-table text-sm" data-testid="register-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Document name</th>
              <th>Type</th>
              <th>Drive folder</th>
              <th>Link</th>
              <th>Tax year</th>
              <th>Category</th>
              <th>Key figures</th>
              <th>Review</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr key={d.id} onClick={() => setSelectedId(d.id)} className="cursor-pointer" data-testid={`row-${d.id}`}>
                <td className="mono text-xs text-zinc-600 whitespace-nowrap">{fmtDate(d.created_at)}</td>
                <td className="font-medium">{d.name}</td>
                <td className="mono text-[11px] text-zinc-500">{(d.file_type || "").split("/").pop()}</td>
                <td className="mono text-xs text-zinc-600">{d.drive_folder_name || "—"}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  {d.drive_link ? (
                    <a href={d.drive_link} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline flex items-center gap-1 text-xs" data-testid={`drive-link-${d.id}`}>
                      drive <ExternalLink className="w-3 h-3" />
                    </a>
                  ) : d.manual_drive_link ? (
                    <a href={d.manual_drive_link} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline flex items-center gap-1 text-xs" data-testid={`manual-link-${d.id}`}>
                      manual <ExternalLink className="w-3 h-3" />
                    </a>
                  ) : d.storage === "local" ? (
                    <a href={`${process.env.REACT_APP_BACKEND_URL}/api/documents/${d.id}/download`} className="text-blue-700 hover:underline text-xs" data-testid={`local-link-${d.id}`}>
                      local
                    </a>
                  ) : <span className="text-zinc-400 text-xs">—</span>}
                </td>
                <td className="mono">{d.tax_year}</td>
                <td className="text-xs">{d.category}</td>
                <td className="text-xs text-zinc-600 max-w-[220px] truncate">{d.key_figures_found || "—"}</td>
                <td className="text-xs">{d.accountant_review}</td>
                <td><StatusPill value={d.status} /></td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={10} className="text-center text-zinc-500 py-10 text-sm">No documents yet. Click "Upload" to add evidence.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} reference={reference} onUploaded={load} />
      <DocumentDetail docId={selectedId} open={!!selectedId} onOpenChange={(v) => !v && setSelectedId(null)} reference={reference} onChanged={load} />
    </div>
  );
}
