import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Upload, Loader2, Cloud, AlertTriangle } from "lucide-react";
import { stashPendingUpload } from "../lib/pendingUpload";
import { useNavigate } from "react-router-dom";

export default function UploadDialog({ open, onOpenChange, reference, onUploaded, initialFile, initialMeta, autoSubmit }) {
  const [file, setFile] = useState(null);
  const [name, setName] = useState("");
  const [taxYear, setTaxYear] = useState("FY2024");
  const [category, setCategory] = useState("ATO");
  const [notes, setNotes] = useState("");
  const [review, setReview] = useState("No");
  const [uploading, setUploading] = useState(false);
  const [driveError, setDriveError] = useState(false);
  const navigate = useNavigate();

  // Hydrate from initialFile/Meta when re-opened after Drive connect
  useEffect(() => {
    if (open && initialFile) {
      setFile(initialFile);
      const m = initialMeta || {};
      setName(m.name || initialFile.name.replace(/\.[^.]+$/, ""));
      setTaxYear(m.tax_year || "FY2024");
      setCategory(m.category || "ATO");
      setNotes(m.notes || "");
      setReview(m.accountant_review || "No");
    }
    if (!open) {
      setFile(null); setName(""); setTaxYear("FY2024"); setCategory("ATO");
      setNotes(""); setReview("No"); setDriveError(false);
    }
  }, [open, initialFile, initialMeta]);

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      if (!name) setName(f.name.replace(/\.[^.]+$/, ""));
    }
  };

  const doUpload = async (fileArg, metaArg) => {
    const f = fileArg || file;
    const m = metaArg || { name, tax_year: taxYear, category, notes, accountant_review: review };
    setUploading(true);
    setDriveError(false);
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("name", (m.name || "").trim());
      fd.append("tax_year", m.tax_year);
      fd.append("category", m.category);
      fd.append("notes", m.notes || "");
      fd.append("accountant_review", m.accountant_review || "No");
      const res = await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Document uploaded to Google Drive.");
      onUploaded?.(res.data);
      onOpenChange(false);
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      const status = e.response?.status;
      if (status === 400 && /not connected/i.test(detail)) {
        setDriveError(true);
        toast.error("Google Drive is not connected. Connect it now to finish this upload.");
      } else {
        toast.error(`Upload failed: ${detail}`);
      }
    } finally {
      setUploading(false);
    }
  };

  // Auto-submit when reopened after OAuth (file + meta restored from sessionStorage)
  useEffect(() => {
    if (open && autoSubmit && initialFile) {
      doUpload(initialFile, initialMeta);
    }
    // eslint-disable-next-line
  }, [open, autoSubmit, initialFile]);

  const submit = async () => {
    if (!file) { toast.error("Choose a file first."); return; }
    if (!name.trim()) { toast.error("Document name is required."); return; }
    await doUpload();
  };

  const connectAndRetry = async () => {
    if (!file) return;
    const meta = { name, tax_year: taxYear, category, notes, accountant_review: review };
    const ok = await stashPendingUpload(file, meta);
    if (!ok) {
      toast.error("File too large to auto-resume (over 4MB). Connect Drive in Settings, then re-upload manually.");
      navigate("/settings");
      return;
    }
    try {
      const r = await api.get("/drive/connect");
      window.location.href = r.data.authorization_url;
    } catch (e) {
      toast.error("Could not start OAuth: " + (e.response?.data?.detail || e.message));
    }
  };

  const cats = reference?.categories || [];
  const tys = reference?.tax_years || ["FY2024", "FY2025", "Both", "Unsure"];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl rounded-sm" data-testid="upload-dialog">
        <DialogHeader>
          <DialogTitle className="text-lg" style={{ fontFamily: "Chivo" }}>
            {autoSubmit ? "Resuming upload…" : "Upload document"}
          </DialogTitle>
        </DialogHeader>

        {driveError && (
          <div className="bg-amber-50 border border-amber-200 rounded-sm p-3 flex items-start gap-2" data-testid="drive-not-connected-banner">
            <AlertTriangle className="w-4 h-4 text-amber-700 mt-0.5" />
            <div className="flex-1">
              <div className="text-sm font-medium text-amber-900">Google Drive isn't connected yet</div>
              <div className="text-xs text-amber-800 mt-1">
                Click <span className="font-semibold">Connect & retry</span> below — we'll save your file, run the OAuth flow, then auto-resume the upload.
              </div>
            </div>
            <Button onClick={connectAndRetry} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="drive-connect-retry-btn">
              <Cloud className="w-4 h-4 mr-2" /> Connect & retry
            </Button>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">File (PDF, image, Excel/CSV, Word)</Label>
            <Input
              type="file"
              onChange={onFile}
              accept=".pdf,.png,.jpg,.jpeg,.webp,.heic,.heif,.xls,.xlsx,.csv,.doc,.docx,.txt"
              className="rounded-sm mt-1"
              data-testid="upload-file-input"
              disabled={!!autoSubmit}
            />
            {file && <div className="text-xs text-zinc-500 mt-1 mono">{file.name} · {(file.size / 1024).toFixed(1)} KB</div>}
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Document name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="rounded-sm mt-1" data-testid="upload-name-input" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Tax year</Label>
              <Select value={taxYear} onValueChange={setTaxYear}>
                <SelectTrigger className="rounded-sm mt-1" data-testid="upload-taxyear-select"><SelectValue /></SelectTrigger>
                <SelectContent>{tys.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-zinc-500">Category</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="rounded-sm mt-1" data-testid="upload-category-select"><SelectValue /></SelectTrigger>
                <SelectContent>{cats.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Notes</Label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="rounded-sm mt-1 min-h-[60px]" data-testid="upload-notes-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">Accountant review required?</Label>
            <Select value={review} onValueChange={setReview}>
              <SelectTrigger className="rounded-sm mt-1" data-testid="upload-review-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="No">No</SelectItem>
                <SelectItem value="Yes">Yes</SelectItem>
                <SelectItem value="Unsure">Unsure</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-sm" data-testid="upload-cancel-btn">Cancel</Button>
          <Button onClick={submit} disabled={uploading} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="upload-submit-btn">
            {uploading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Upload className="w-4 h-4 mr-2" />}
            Upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
