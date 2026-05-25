import React from "react";
import { API } from "../lib/api";
import { FileDown, FileText, FolderTree, AlertOctagon, FileType2, Package, HardDrive } from "lucide-react";

const items = [
  {
    key: "final-pack",
    title: "Final Accountant Pack (ZIP)",
    desc: "Single archive: organised document files by FY/category + all CSVs + summary PDF/TXT + disaster-recovery backup. One link to hand to your accountant.",
    url: `${API}/reports/final-accountant-pack.zip`,
    format: "ZIP",
    icon: Package,
  },
  {
    key: "register",
    title: "Evidence Register",
    desc: "All uploaded documents with AI metadata: risk level, headline figures (verified), counterparty, date range, Drive link, status and notes.",
    url: `${API}/reports/evidence-register.csv`,
    format: "CSV",
    icon: FileDown,
  },
  {
    key: "missing",
    title: "Missing Evidence List",
    desc: "Outstanding items grouped by priority — share with accountant or use as todo list.",
    url: `${API}/reports/missing-evidence.csv`,
    format: "CSV",
    icon: AlertOctagon,
  },
  {
    key: "summary-pdf",
    title: "Accountant Summary (PDF)",
    desc: "Polished PDF: documents received, manual figures entered, outstanding evidence and review items.",
    url: `${API}/reports/accountant-summary.pdf`,
    format: "PDF",
    icon: FileText,
  },
  {
    key: "summary-txt",
    title: "Accountant Summary (TXT)",
    desc: "Plain-text snapshot — counts by category, tax year, risk; review items and outstanding evidence. Ideal for pasting into email.",
    url: `${API}/reports/accountant-summary.txt`,
    format: "TXT",
    icon: FileType2,
  },
  {
    key: "bycat",
    title: "Documents by category",
    desc: "Per-category counts across FY2024 / FY2025 / Both / Unsure.",
    url: `${API}/reports/documents-by-category.csv`,
    format: "CSV",
    icon: FolderTree,
  },
  {
    key: "backup",
    title: "Backup (JSON)",
    desc: "Full disaster-recovery snapshot: every document, figure, AI cache, missing-evidence item, and upload-queue row. Critical before relying on the app for real work.",
    url: `${API}/reports/backup.json`,
    format: "JSON",
    icon: HardDrive,
  },
];

export default function Reports() {
  return (
    <div className="p-6 max-w-4xl" data-testid="reports-page">
      <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Reports & Exports</h1>
      <div className="text-sm text-zinc-500 mt-1 mb-6">
        Downloads pull live data from your Evidence Register — AI-verified headline figures plus any manual figures.
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map((it) => (
          <a
            key={it.key}
            href={it.url}
            className="bg-white border border-zinc-200 rounded-sm p-4 flex gap-3 items-start hover:bg-zinc-50 transition"
            data-testid={`report-${it.key}`}
            download
          >
            <div className="w-10 h-10 rounded-sm bg-zinc-100 border border-zinc-200 flex items-center justify-center">
              <it.icon className="w-5 h-5 text-zinc-700" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>{it.title}</div>
                <span className="pill" style={{ background: "#FAFAFA", color: "#52525B", borderColor: "#E4E4E7" }}>{it.format}</span>
              </div>
              <div className="text-xs text-zinc-500 mt-1 leading-relaxed">{it.desc}</div>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
