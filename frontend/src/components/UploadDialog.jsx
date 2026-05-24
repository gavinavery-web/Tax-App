import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Upload, Loader2 } from "lucide-react";

export default function UploadDialog({ open, onOpenChange, reference, onUploaded }) {
  const [file, setFile] = useState(null);
  const [name, setName] = useState("");
  const [taxYear, setTaxYear] = useState("FY2024");
  const [category, setCategory] = useState("ATO");
  const [notes, setNotes] = useState("");
  const [review, setReview] = useState("No");
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!open) {
      setFile(null); setName(""); setTaxYear("FY2024"); setCategory("ATO"); setNotes(""); setReview("No");
    }
  }, [open]);

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      if (!name) setName(f.name.replace(/\.[^.]+$/, ""));
    }
  };

  const submit = async () => {
    if (!file) { toast.error("Choose a file first."); return; }
    if (!name.trim()) { toast.error("Document name is required."); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", name.trim());
      fd.append("tax_year", taxYear);
      fd.append("category", category);
      fd.append("notes", notes);
      fd.append("accountant_review", review);
      const res = await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Document uploaded.");
      onUploaded?.(res.data);
      onOpenChange(false);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      toast.error(`Upload failed: ${msg}`);
    } finally {
      setUploading(false);
    }
  };

  const cats = reference?.categories || [];
  const tys = reference?.tax_years || ["FY2024", "FY2025", "Both", "Unsure"];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl rounded-sm" data-testid="upload-dialog">
        <DialogHeader>
          <DialogTitle className="text-lg" style={{ fontFamily: "Chivo" }}>Upload document</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs uppercase tracking-wider text-zinc-500">File (PDF, image, Excel/CSV, Word)</Label>
            <Input
              type="file"
              onChange={onFile}
              accept=".pdf,.png,.jpg,.jpeg,.webp,.heic,.heif,.xls,.xlsx,.csv,.doc,.docx,.txt"
              className="rounded-sm mt-1"
              data-testid="upload-file-input"
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
