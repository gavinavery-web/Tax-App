import React, { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import FigureBadge from "./FigureBadge";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { toast } from "sonner";
import { Trash2, RefreshCw, FileWarning, RotateCcw, AlertCircle, AlertTriangle, CloudOff, Clock } from "lucide-react";
import { Link } from "react-router-dom";

const STATUS_PALETTE = {
  Queued:      { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" },
  Uploading:   { bg: "#EFF6FF", fg: "#1E40AF", border: "#BFDBFE" },
  Reading:     { bg: "#EFF6FF", fg: "#1E40AF", border: "#BFDBFE" },
  Classifying: { bg: "#EFF6FF", fg: "#1E40AF", border: "#BFDBFE" },
  Filed:       { bg: "#F0FDF4", fg: "#166534", border: "#BBF7D0" },
  Inbox:       { bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  "Duplicate?":{ bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  Error:       { bg: "#FEF2F2", fg: "#991B1B", border: "#FECACA" },
  Cancelled:   { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" },
};

const StatusPill = ({ value }) => {
  const p = STATUS_PALETTE[value] || STATUS_PALETTE.Queued;
  return <span className="pill" style={{ background: p.bg, color: p.fg, borderColor: p.border }}>{value}</span>;
};

// Map error_code → (icon, hint short label)
const ERROR_HINT = {
  FILE_TOO_LARGE:       { icon: AlertCircle,   label: "Too large" },
  FILE_EMPTY:           { icon: AlertCircle,   label: "Empty file" },
  FILE_DUPLICATE:       { icon: AlertTriangle, label: "Duplicate" },
  AI_TIMEOUT:           { icon: Clock,         label: "AI timeout" },
  AI_RATE_LIMIT:        { icon: Clock,         label: "Rate-limited" },
  AI_FAILED:            { icon: AlertTriangle, label: "AI failed" },
  DRIVE_DISCONNECTED:   { icon: CloudOff,      label: "Drive offline" },
  DRIVE_QUOTA_EXCEEDED: { icon: CloudOff,      label: "Drive quota" },
  DRIVE_UPLOAD_FAILED:  { icon: CloudOff,      label: "Drive failed" },
  STAGING_MISSING:      { icon: AlertCircle,   label: "Staging lost" },
  UNEXPECTED_ERROR:     { icon: AlertCircle,   label: "Crash" },
};

export default function UploadQueue({ onChanged }) {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [dup, setDup] = useState(null);
  // Track per-row "cooldown until" ms timestamp for AI_RATE_LIMIT retries.
  const [cooldown, setCooldown] = useState({});

  const load = useCallback(async () => {
    try {
      const r = await api.get("/uploads/queue");
      setItems(r.data.items);
      setCounts(r.data.counts);
      const firstDup = (r.data.items || []).find((it) => it.status === "Duplicate?");
      setDup((cur) => cur && cur.id === firstDup?.id ? cur : firstDup || null);
    } catch (e) {
      // Polling loop — never block the UI on a transient queue read. We
      // surface to dev tools so a real outage is visible, but skip toast
      // (the next poll will retry in <2s).
      // eslint-disable-next-line no-console
      console.warn("UploadQueue poll failed:", e?.message || e);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const hasActive = (items || []).some((it) => ["Uploading", "Reading", "Classifying"].includes(it.status));
    if (!hasActive) onChanged?.();
    // eslint-disable-next-line
  }, [items.length, items.filter((i) => ["Filed", "Inbox"].includes(i.status)).length]);

  // Tick once per second to refresh cooldown countdowns.
  useEffect(() => {
    if (!Object.keys(cooldown).length) return;
    const t = setInterval(() => setCooldown((c) => ({ ...c })), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  const decide = async (qid, action) => {
    try {
      await api.post(`/uploads/queue/${qid}/decision`, { action });
      toast.success(`Duplicate: ${action}`);
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "Action failed";
      toast.error(`Duplicate ${action} failed: ${msg}`);
    } finally {
      setDup(null);
      load();
    }
  };
  const cancelOne = async (qid) => {
    try { await api.delete(`/uploads/queue/${qid}`); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not cancel"); }
    finally { load(); }
  };
  const cancelAll = async () => {
    try { await api.delete(`/uploads/queue`); toast.success("Pending cancelled"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not cancel all"); }
    finally { load(); }
  };
  const clearDone = async () => {
    try { await api.delete(`/uploads/queue/finished/clear`); toast.success("Cleared finished"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not clear finished"); }
    finally { load(); }
  };

  const retryOne = async (qid) => {
    try {
      await api.post(`/uploads/queue/${qid}/retry`);
      toast.success("Re-queued");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Retry failed — please re-upload this file");
    }
  };

  const retryWithCooldown = (qid, seconds) => {
    const until = Date.now() + seconds * 1000;
    setCooldown((c) => ({ ...c, [qid]: until }));
    toast.message(`Will retry in ${seconds}s — please wait`);
    setTimeout(() => {
      setCooldown((c) => { const { [qid]: _, ...rest } = c; return rest; });
      retryOne(qid);
    }, seconds * 1000);
  };

  if (!items.length) return null;

  const renderActions = (it) => {
    if (["Queued", "Duplicate?"].includes(it.status)) {
      return (
        <button onClick={() => cancelOne(it.id)} className="text-zinc-400 hover:text-red-700"
                data-testid={`queue-cancel-${it.id}`} title="cancel">
          <Trash2 className="w-3 h-3" />
        </button>
      );
    }
    if (it.status === "Error" || it.status === "Cancelled") {
      const isRate = it.error_code === "AI_RATE_LIMIT";
      const isDrive = it.error_code === "DRIVE_DISCONNECTED";
      const inCooldown = cooldown[it.id] && cooldown[it.id] > Date.now();
      const secondsLeft = inCooldown ? Math.ceil((cooldown[it.id] - Date.now()) / 1000) : 0;
      return (
        <div className="flex flex-col items-end gap-1">
          {isDrive ? (
            <Link to="/settings" className="text-blue-700 hover:underline text-[11px]"
                  data-testid={`queue-reconnect-${it.id}`}>Reconnect Drive</Link>
          ) : isRate ? (
            <button
              onClick={() => retryWithCooldown(it.id, 60)}
              disabled={inCooldown}
              className="text-blue-700 hover:underline text-[11px] disabled:text-zinc-400 disabled:no-underline"
              data-testid={`queue-retry-${it.id}`}
              title="AI was rate-limited — waits 60s then retries"
            >
              {inCooldown ? `Retry in ${secondsLeft}s` : "Retry (wait 60s)"}
            </button>
          ) : (
            <button onClick={() => retryOne(it.id)} className="text-blue-700 hover:underline text-[11px]"
                    data-testid={`queue-retry-${it.id}`} title="retry">
              <RotateCcw className="w-3 h-3 inline mr-0.5" /> Retry
            </button>
          )}
        </div>
      );
    }
    return null;
  };

  const renderStatusCell = (it) => {
    const hint = ERROR_HINT[it.error_code];
    return (
      <div className="flex items-center gap-1.5">
        <StatusPill value={it.status} />
        {hint && (
          <span className="inline-flex items-center gap-0.5 text-[10px] text-zinc-500" title={it.error || ""}>
            <hint.icon className="w-3 h-3" /> {hint.label}
          </span>
        )}
      </div>
    );
  };

  const errorRows = items.filter((it) => it.error_code && it.status === "Error");

  return (
    <div className="bg-white border border-zinc-200 rounded-sm mb-3" data-testid="upload-queue">
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-200">
        <div className="text-sm font-semibold flex items-center gap-3" style={{ fontFamily: "Chivo" }}>
          Upload Queue
          <span className="text-[11px] text-zinc-500 mono">
            queued {counts.Queued || 0} · processing {(counts.Uploading||0)+(counts.Reading||0)+(counts.Classifying||0)}
            {" · "}filed {counts.Filed || 0} · inbox {counts.Inbox || 0}
            {counts.Error ? ` · errors ${counts.Error}` : ""}
          </span>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} className="rounded-sm h-7 px-2 text-xs"><RefreshCw className="w-3 h-3 mr-1" /> refresh</Button>
          <Button variant="outline" onClick={cancelAll} className="rounded-sm h-7 px-2 text-xs">cancel pending</Button>
          <Button variant="outline" onClick={clearDone} className="rounded-sm h-7 px-2 text-xs">clear finished</Button>
        </div>
      </div>

      {errorRows.length > 0 && (
        <div className="px-3 py-2 bg-red-50 border-b border-red-200 text-[11px] text-red-800" data-testid="queue-error-banner">
          <strong>{errorRows.length} file(s) need attention.</strong> Use the per-row action on the right to retry or reconnect.
        </div>
      )}

      {/* Fix 10: Import summary band — at-a-glance breakdown of the batch */}
      <div className="px-3 py-2 bg-zinc-50 border-b border-zinc-200 text-[11px] flex flex-wrap items-center gap-x-3 gap-y-1" data-testid="upload-summary">
        <span className="font-semibold text-zinc-700">Summary:</span>
        <span><b className="mono">{items.length}</b> total</span>
        {(counts.Filed || 0) > 0 && <span className="text-emerald-700">✓ <b className="mono">{counts.Filed}</b> filed</span>}
        {(counts.Inbox || 0) > 0 && <span className="text-amber-700">⌂ <b className="mono">{counts.Inbox}</b> inbox</span>}
        {(counts["Duplicate?"] || 0) > 0 && <span className="text-blue-700">⊜ <b className="mono">{counts["Duplicate?"]}</b> duplicate</span>}
        {(counts.Error || 0) > 0 && <span className="text-red-700">✕ <b className="mono">{counts.Error}</b> error</span>}
        {(counts.Cancelled || 0) > 0 && <span className="text-zinc-500">⊘ <b className="mono">{counts.Cancelled}</b> cancelled</span>}
        {((counts.Queued || 0) + (counts.Uploading || 0) + (counts.Reading || 0) + (counts.Classifying || 0)) > 0 && (
          <span className="text-zinc-700">⟳ <b className="mono">{(counts.Queued || 0) + (counts.Uploading || 0) + (counts.Reading || 0) + (counts.Classifying || 0)}</b> in progress</span>
        )}
      </div>

      <div className="max-h-72 overflow-y-auto">
        <table className="w-full dense-table text-xs">
          <thead>
            <tr><th>File</th><th>Status</th><th>Category</th><th>Confidence</th><th>Cost</th><th></th></tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} data-testid={`queue-row-${it.id}`}>
                <td className="font-medium truncate max-w-[280px]" title={it.filename}>
                  {it.result_document_id ? (
                    <Link
                      to={`/register?open=${encodeURIComponent(it.result_document_id)}`}
                      className="text-blue-700 hover:underline"
                      data-testid={`queue-filename-link-${it.id}`}
                      title="Open document in Evidence Register"
                    >{it.filename}</Link>
                  ) : (
                    <span data-testid={`queue-filename-${it.id}`}>{it.filename}</span>
                  )}
                </td>
                <td>{renderStatusCell(it)}</td>
                <td className="text-zinc-600">{it.ai_category || (it.status === "Duplicate?" ? `dup of ${it.duplicate_meta?.name || ""}` : "—")}</td>
                <td>{it.ai_confidence ? <FigureBadge value={it.ai_confidence} /> : <span className="text-zinc-400">—</span>}</td>
                <td className="mono text-right">${(it.ai_cost_usd || 0).toFixed(3)}</td>
                <td className="text-right">
                  {renderActions(it)}
                  {it.error && !ERROR_HINT[it.error_code] && (
                    <span title={it.error} className="text-red-700 ml-1"><FileWarning className="w-3 h-3 inline" /></span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!dup} onOpenChange={(v) => !v && setDup(null)}>
        <DialogContent className="max-w-lg rounded-sm" data-testid="duplicate-dialog">
          <DialogHeader>
            <DialogTitle className="text-base" style={{ fontFamily: "Chivo" }}>Possible duplicate</DialogTitle>
          </DialogHeader>
          {dup && (
            <div className="text-sm space-y-2">
              <div>
                This file <span className="font-semibold mono">{dup.filename}</span> matches an existing document
                <span className="font-semibold mono"> {dup.duplicate_meta?.name}</span> uploaded
                {dup.duplicate_meta?.created_at ? ` on ${dup.duplicate_meta.created_at.slice(0,10)}` : ""}
                {dup.duplicate_meta?.category ? ` in ${dup.duplicate_meta.category}` : ""}.
              </div>
              <div className="text-xs text-zinc-500 mono">SHA-256: {dup.sha256}</div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => decide(dup.id, "skip")} className="rounded-sm" data-testid="dup-skip">Skip</Button>
            <Button variant="outline" onClick={() => decide(dup.id, "replace")} className="rounded-sm" data-testid="dup-replace">Replace</Button>
            <Button onClick={() => decide(dup.id, "upload_anyway")} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="dup-upload-anyway">Upload anyway</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
