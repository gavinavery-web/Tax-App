import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { StatusPill } from "../components/StatusPill";
import { Cloud, CloudOff, AlertCircle, Banknote, FileStack, ShieldCheck, AlertTriangle as AlertTri, Upload as UploadIcon, CheckCircle2, PackageOpen } from "lucide-react";
import { fmtAUD } from "../lib/constants";
import { Link } from "react-router-dom";
import { API } from "../lib/api";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [drive, setDrive] = useState(null);
  const [paygFigures, setPaygFigures] = useState([]);
  const [stats, setStats] = useState(null);
  const [readiness, setReadiness] = useState(null);

  const load = async () => {
    const [d, ds, pf, st, rd] = await Promise.all([
      api.get("/dashboard"),
      api.get("/drive/status"),
      api.get("/figures", { params: { } }),
      api.get("/dashboard/stats"),
      api.get("/dashboard/readiness"),
    ]);
    setData(d.data); setDrive(ds.data);
    setPaygFigures(pf.data.filter((f) => f.figure_type === "payg_income"));
    setStats(st.data);
    setReadiness(rd.data);
  };

  useEffect(() => {
    load();
    // Live dashboard — refresh every 10s so changes elsewhere in the app
    // (uploads finishing, transactions added to a return, reset, etc.) are
    // reflected without a manual reload.
    const interval = setInterval(() => { load().catch(() => {}); }, 10000);
    return () => clearInterval(interval);
  }, []);

  // Memoise per-year PAYG totals — filter+reduce previously ran on every
  // render and was called once per FY card (so twice per render). Recompute
  // only when `paygFigures` actually changes.
  const paygTotals = useMemo(() => {
    const totals = {};
    for (const f of paygFigures) {
      const y = f.tax_year || "Unsure";
      totals[y] = (totals[y] || 0) + Number(f.amount || 0);
    }
    return totals;
  }, [paygFigures]);
  const totalByYear = (year) => paygTotals[year] || 0;

  return (
    <div className="p-6 max-w-[1400px] mx-auto" data-testid="dashboard-page">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Dashboard</h1>
          <div className="text-sm text-zinc-500 mt-1">Evidence overview for FY2024 & FY2025 returns (overdue).</div>
        </div>
        <div className="flex items-center gap-2">
          {drive && (
            <Link
              to="/register"
              className="pill"
              data-testid="drive-status-pill"
              style={drive.connected
                ? { background: "#F0FDF4", color: "#166534", borderColor: "#BBF7D0" }
                : { background: "#FEF2F2", color: "#991B1B", borderColor: "#FECACA" }}
            >
              {drive.connected ? <Cloud className="w-3 h-3" /> : <CloudOff className="w-3 h-3" />}
              Drive {drive.connected ? "connected" : "not connected"} · go to Register
            </Link>
          )}
        </div>
      </div>

      {/* Stage 5 — at-a-glance stat band */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5" data-testid="stats-band">
          <div className="bg-white border border-zinc-200 border-l-2 border-l-zinc-950 rounded-sm p-3 flex items-start gap-3" data-testid="stat-total">
            <FileStack className="w-5 h-5 text-zinc-700 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">Total documents</div>
              <div className="text-2xl font-bold mono leading-tight">{stats.total}</div>
            </div>
          </div>
          <Link to="/register" className="bg-white border border-zinc-200 border-l-2 border-l-green-600 rounded-sm p-3 flex items-start gap-3 hover:bg-zinc-50 transition" data-testid="stat-classified">
            <ShieldCheck className="w-5 h-5 text-green-700 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">Classified &amp; filed</div>
              <div className="text-2xl font-bold mono leading-tight">{stats.classified}</div>
            </div>
          </Link>
          <Link to="/register?review=Yes" className="bg-white border border-zinc-200 border-l-2 border-l-amber-500 rounded-sm p-3 flex items-start gap-3 hover:bg-zinc-50 transition" data-testid="stat-needs-review">
            <AlertTri className="w-5 h-5 text-amber-600 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">Needs review</div>
              <div className="text-2xl font-bold mono leading-tight">{stats.needs_review}</div>
            </div>
          </Link>
          <Link to="/missing" className="bg-white border border-zinc-200 border-l-2 border-l-red-600 rounded-sm p-3 flex items-start gap-3 hover:bg-zinc-50 transition" data-testid="stat-missing-critical">
            <AlertCircle className="w-5 h-5 text-red-700 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">Critical missing</div>
              <div className="text-2xl font-bold mono leading-tight">{stats.missing_critical}</div>
              <div className="text-[11px] text-zinc-500 mt-0.5">{stats.missing_total} outstanding total</div>
            </div>
          </Link>
        </div>
      )}

      {/* Stage 5 — Ready for Accountant? gate */}
      {readiness && (
        <div
          className={`border rounded-sm p-4 mb-5 ${
            readiness.ready
              ? "bg-green-50 border-green-200"
              : "bg-amber-50 border-amber-200"
          }`}
          data-testid="readiness-card"
        >
          <div className="flex items-start gap-3">
            {readiness.ready ? (
              <CheckCircle2 className="w-5 h-5 text-green-700 mt-0.5 flex-shrink-0" />
            ) : (
              <AlertTri className="w-5 h-5 text-amber-700 mt-0.5 flex-shrink-0" />
            )}
            <div className="flex-1">
              <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }} data-testid="readiness-headline">
                {readiness.ready ? "Ready for accountant" : "Not ready yet — review required"}
              </div>
              <div className="text-[11px] text-zinc-600 mt-0.5">
                {readiness.ready
                  ? "All checks passed. You can hand the Final Accountant Pack to your accountant."
                  : "Resolve each blocker below, then re-check from here."}
              </div>
              {!readiness.ready && readiness.blockers?.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs text-zinc-700" data-testid="readiness-blockers">
                  {readiness.blockers.map((b) => (
                    <li key={b.key} className="flex items-center gap-2">
                      <span className="mono text-[11px] text-amber-700 w-6 text-right">{b.count}</span>
                      <span>·</span>
                      <span>{b.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-3 flex gap-2">
                <a
                  href={`${API}/reports/final-accountant-pack.zip`}
                  className={`inline-flex items-center gap-1 rounded-sm text-xs px-3 py-1.5 border ${
                    readiness.ready
                      ? "bg-zinc-950 text-white border-zinc-950 hover:bg-zinc-800"
                      : "bg-white text-zinc-700 border-zinc-200 hover:bg-zinc-50"
                  }`}
                  data-testid="final-pack-link"
                  download
                >
                  <PackageOpen className="w-3.5 h-3.5" /> Download Final Accountant Pack (ZIP)
                </a>
                <a
                  href={`${API}/reports/backup.json`}
                  className="inline-flex items-center gap-1 rounded-sm text-xs px-3 py-1.5 border bg-white text-zinc-700 border-zinc-200 hover:bg-zinc-50"
                  data-testid="backup-link"
                  download
                >
                  Backup (JSON)
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Empty state — surfaces only when nothing has been uploaded yet */}
      {stats && stats.total === 0 && (
        <div className="bg-white border border-dashed border-zinc-300 rounded-sm p-8 mb-5 text-center" data-testid="dashboard-empty-state">
          <UploadIcon className="w-10 h-10 text-zinc-400 mx-auto mb-3" />
          <div className="text-sm font-semibold mb-1" style={{ fontFamily: "Chivo" }}>No documents yet</div>
          <div className="text-xs text-zinc-500 mb-3">Drag a folder onto the Evidence Register, or press{" "}
            <kbd className="px-1.5 py-0.5 bg-zinc-100 border border-zinc-200 rounded text-[10px] mono">Ctrl/⌘+U</kbd>
            {" "}to jump straight there.
          </div>
          <Link to="/register" className="inline-block px-4 py-1.5 bg-zinc-950 text-white text-xs rounded-sm hover:bg-zinc-800">Go to Evidence Register</Link>
        </div>
      )}

      {/* Tax year status row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-6">
        {["FY2024", "FY2025"].map((yr) => {
          const card = data?.cards.find((c) => c.value === yr);
          const total = totalByYear(yr);
          return (
            <div key={yr} className="bg-white border-l-2 border-l-zinc-950 border border-zinc-200 rounded-sm p-4" data-testid={`fy-summary-${yr}`}>
              <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">{yr} Tax Return · OVERDUE</div>
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-2xl font-bold mono">{card?.documents ?? "—"}</div>
                  <div className="text-xs text-zinc-500">documents uploaded</div>
                </div>
                <div className="text-right">
                  <div className="text-sm mono">{fmtAUD(total)}</div>
                  <div className="text-[11px] text-zinc-500">PAYG income (preloaded)</div>
                </div>
              </div>
              <div className="mt-3"><StatusPill value={card?.status || "Not started"} testid={`fy-status-${yr}`} /></div>
            </div>
          );
        })}
        <div className="bg-white border-l-2 border-l-amber-500 border border-zinc-200 rounded-sm p-4">
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">FY2023 / FY2026</div>
          <div className="text-sm text-zinc-700">FY2023 lodged & assessed.</div>
          <div className="text-sm text-zinc-700">FY2026 current/live — not in scope.</div>
        </div>
      </div>

      {/* Category cards */}
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Categories</div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mb-6">
        {(data?.cards || []).filter((c) => !["fy2024", "fy2025"].includes(c.key)).map((c) => {
          const isMissing = c.key === "missing";
          const isReview = c.key === "review";
          return (
            <Link
              key={c.key}
              to={isMissing ? "/missing" : isReview ? "/register?review=Yes" : `/register?category=${encodeURIComponent(c.value)}`}
              className={`bg-white border border-zinc-200 rounded-sm p-3 hover:bg-zinc-50 transition block ${
                isMissing ? "border-l-2 border-l-red-600" : isReview ? "border-l-2 border-l-amber-500" : ""
              }`}
              data-testid={`card-${c.key}`}
            >
              <div className="flex items-start justify-between">
                <div className="text-sm font-medium text-zinc-900 leading-tight" style={{ fontFamily: "Chivo" }}>{c.title}</div>
                {isMissing && <AlertCircle className="w-4 h-4 text-red-600" />}
              </div>
              <div className="flex items-end justify-between mt-3">
                <div>
                  <div className="text-xl font-bold mono">{c.documents}</div>
                  <div className="text-[11px] text-zinc-500">{isMissing ? "outstanding items" : "documents"}</div>
                </div>
                <StatusPill value={c.status} />
              </div>
            </Link>
          );
        })}
      </div>

      {/* PAYG preloaded */}
      <div className="bg-white border border-zinc-200 rounded-sm">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200">
          <div className="flex items-center gap-2">
            <Banknote className="w-4 h-4 text-zinc-700" />
            <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>Preloaded PAYG income (known facts)</div>
          </div>
          <div className="text-[11px] text-zinc-500">From confirmed PAYG payment summaries</div>
        </div>
        <table className="w-full dense-table text-sm">
          <thead>
            <tr><th>Tax year</th><th>Employer</th><th className="text-right">Amount (AUD)</th></tr>
          </thead>
          <tbody>
            {paygFigures.sort((a, b) => (a.tax_year || "").localeCompare(b.tax_year) || a.description.localeCompare(b.description)).map((f) => (
              <tr key={f.id}>
                <td className="mono">{f.tax_year}</td>
                <td>{f.description}</td>
                <td className="mono text-right">{fmtAUD(f.amount)}</td>
              </tr>
            ))}
            <tr style={{ background: "#FAFAFA" }}>
              <td className="font-semibold">FY2024 total</td>
              <td></td>
              <td className="mono text-right font-semibold">{fmtAUD(totalByYear("FY2024"))}</td>
            </tr>
            <tr style={{ background: "#FAFAFA" }}>
              <td className="font-semibold">FY2025 total</td>
              <td></td>
              <td className="mono text-right font-semibold">{fmtAUD(totalByYear("FY2025"))}</td>
            </tr>
          </tbody>
        </table>
      </div>

    </div>
  );
}
