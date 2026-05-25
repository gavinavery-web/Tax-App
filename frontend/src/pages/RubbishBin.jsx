import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Trash2, RotateCcw, Trash, AlertTriangle } from "lucide-react";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Input } from "../components/ui/input";

export default function RubbishBin() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [emptyOpen, setEmptyOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [emptying, setEmptying] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/rubbish-bin");
      setDocs(data);
    } catch (e) {
      toast.error(`Failed to load rubbish bin: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const restore = async (id) => {
    if (!window.confirm("Restore this document?")) return;
    try {
      await api.post(`/documents/${id}/restore`);
      toast.success("Document restored");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to restore");
    }
  };

  const permanentDelete = async (id) => {
    if (!window.confirm("PERMANENTLY delete this document? This cannot be undone. (Drive copy is preserved.)")) return;
    try {
      const { data } = await api.delete(`/documents/${id}/permanent`);
      if (data?.success) {
        toast.success("Permanently deleted");
        load();
      } else {
        toast.error(data?.error || "Delete blocked");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete blocked");
    }
  };

  const emptyBin = async () => {
    if (confirmText.trim() !== "DELETE") { toast.error("Type DELETE exactly to confirm"); return; }
    setEmptying(true);
    try {
      const { data } = await api.post("/rubbish-bin/empty", {});
      let msg = data.message || "Bin emptied.";
      if (data.drive_failed && data.drive_failed.length) {
        msg += ` (${data.drive_failed.length} Drive failure(s) — trash them manually.)`;
      }
      toast.success(msg);
      setEmptyOpen(false);
      setConfirmText("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Empty bin failed");
    } finally {
      setEmptying(false);
    }
  };

  return (
    <div className="p-6 max-w-[1200px] mx-auto" data-testid="rubbish-bin-page">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Rubbish Bin</h1>
          <p className="text-sm text-zinc-500 mt-1">{docs.length} deleted document(s). Drive copies are preserved unless you permanently delete.</p>
        </div>
        {docs.length > 0 && (
          <Button
            variant="destructive"
            className="gap-1.5"
            onClick={() => setEmptyOpen(true)}
            data-testid="empty-bin-btn"
          ><Trash2 className="w-4 h-4" /> Empty Rubbish Bin</Button>
        )}
      </div>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading…</div>
      ) : docs.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-zinc-300 rounded-lg" data-testid="rubbish-bin-empty">
          <Trash className="w-10 h-10 text-zinc-300 mx-auto mb-2" strokeWidth={1.5} />
          <div className="text-sm text-zinc-500">Rubbish bin is empty.</div>
        </div>
      ) : (
        <div className="space-y-2">
          {docs.map((d) => (
            <div key={d.id} className="p-3 bg-red-50 border border-red-200 rounded-lg" data-testid={`bin-doc-${d.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-zinc-900 text-sm truncate">{d.name}</div>
                  <div className="text-xs text-zinc-600 mt-0.5 mono">
                    {d.category} · {d.tax_year} · {d.original_filename || ""}
                  </div>
                  <div className="text-xs text-red-700 mt-1">
                    Deleted {d.deleted_at ? new Date(d.deleted_at).toLocaleString("en-AU") : "—"}
                    {d.deleted_reason && <span> · {d.deleted_reason}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={() => restore(d.id)} data-testid={`restore-doc-${d.id}`}>
                    <RotateCcw className="w-3.5 h-3.5" /> Restore
                  </Button>
                  <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => permanentDelete(d.id)} data-testid={`permanent-delete-doc-${d.id}`}>
                    <Trash2 className="w-3.5 h-3.5" /> Delete forever
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={emptyOpen} onOpenChange={setEmptyOpen}>
        <DialogContent className="max-w-md rounded-sm" data-testid="empty-bin-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base" style={{ fontFamily: "Chivo" }}>
              <AlertTriangle className="w-5 h-5 text-red-600" /> Permanently empty Rubbish Bin?
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p>This will <b>permanently delete</b> all {docs.length} document(s) from the app database and move their Drive copies to Google Drive trash. This action cannot be undone from the app.</p>
            <p className="text-zinc-700">Type <span className="mono px-1.5 py-0.5 bg-red-100 text-red-800 rounded">DELETE</span> to confirm:</p>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="DELETE"
              autoFocus
              data-testid="empty-bin-confirm-input"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEmptyOpen(false); setConfirmText(""); }} disabled={emptying}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={emptyBin}
              disabled={emptying || confirmText.trim() !== "DELETE"}
              data-testid="empty-bin-confirm-btn"
            >{emptying ? "Emptying…" : "Empty bin permanently"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
