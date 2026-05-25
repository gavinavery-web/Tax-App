import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Cloud, CloudOff, FolderPlus, Loader2, CheckCircle2, AlertCircle, ExternalLink, Unplug, Copy, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { hasPendingUpload } from "../lib/pendingUpload";

const Row = ({ label, value, mono = true, testid }) => (
  <div className="flex items-start gap-3 py-1.5 border-b border-zinc-100 last:border-b-0">
    <div className="text-[11px] uppercase tracking-wider text-zinc-500 w-44 shrink-0 pt-0.5">{label}</div>
    <div className={`flex-1 text-xs break-all ${mono ? "mono" : ""}`} data-testid={testid}>{value ?? "—"}</div>
    {value && typeof value === "string" && (
      <button
        onClick={() => { navigator.clipboard.writeText(value); toast.success("Copied"); }}
        className="text-zinc-400 hover:text-zinc-700 mt-0.5"
        title="Copy"
        data-testid={testid ? `${testid}-copy` : undefined}
      >
        <Copy className="w-3.5 h-3.5" />
      </button>
    )}
  </div>
);

export default function Settings() {
  const [status, setStatus] = useState(null);
  const [diag, setDiag] = useState(null);
  const [aiStats, setAiStats] = useState(null);
  const [busy, setBusy] = useState(false);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const load = async () => {
    const [s, d, ai] = await Promise.all([api.get("/drive/status"), api.get("/diagnostics"), api.get("/ai/stats")]);
    setStatus(s.data); setDiag(d.data); setAiStats(ai.data);
  };

  useEffect(() => {
    load();
    const flag = params.get("drive");
    if (flag === "connected") {
      toast.success("Google Drive connected — folders ready.");
      params.delete("drive"); setParams(params, { replace: true });
      if (hasPendingUpload()) {
        setTimeout(() => navigate("/?retry=1", { replace: true }), 300);
      }
    }
    if (flag === "error") {
      const code = params.get("code") || "error";
      const msg = params.get("msg") || "";
      toast.error(`Drive connection failed (${code}): ${msg}`);
      params.delete("drive"); params.delete("code"); params.delete("msg");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line
  }, []);

  const connect = async () => {
    setBusy(true);
    try {
      const r = await api.get("/drive/connect");
      window.location.href = r.data.authorization_url;
    } catch (e) {
      toast.error("Could not start OAuth: " + (e.response?.data?.detail || e.message));
      setBusy(false);
    }
  };

  const initFolders = async () => {
    setBusy(true);
    try {
      await api.post("/drive/initialize");
      toast.success("Folder structure created in Google Drive.");
      await load();
    } catch (e) {
      toast.error("Failed: " + (e.response?.data?.detail || e.message));
    } finally { setBusy(false); }
  };

  const disconnect = async () => {
    if (!window.confirm("Disconnect Drive? This only removes stored credentials; existing Drive files remain.")) return;
    setBusy(true);
    try { await api.post("/drive/disconnect"); toast.success("Disconnected."); await load(); }
    finally { setBusy(false); }
  };

  const clearError = async () => {
    await api.delete("/diagnostics/last-error");
    await load();
    toast.success("Cleared last error.");
  };

  return (
    <div className="p-6 max-w-3xl" data-testid="settings-page">
      <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Settings</h1>
      <div className="text-sm text-zinc-500 mt-1 mb-4">Google Drive connection, diagnostics, and folder initialisation.</div>

      {/* Diagnostics */}
      <div className="bg-white border border-zinc-200 rounded-sm mb-4">
        <div className="px-4 py-2.5 border-b border-zinc-200 flex items-center justify-between">
          <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>OAuth diagnostics</div>
          <button onClick={load} className="text-xs text-zinc-500 hover:text-zinc-900 flex items-center gap-1" data-testid="diag-refresh">
            <RefreshCw className="w-3 h-3" /> refresh
          </button>
        </div>
        <div className="px-4 py-2">
          <Row label="OAuth client ID" value={diag?.oauth_client_id} testid="diag-client-id" />
          <Row label="Redirect URI" value={diag?.redirect_uri} testid="diag-redirect-uri" />
          <Row label="App origin" value={diag?.frontend_url} testid="diag-frontend-url" />
          <Row label="Browser origin" value={typeof window !== "undefined" ? window.location.origin : ""} testid="diag-browser-origin" />
          <Row label="Requested scope" value={(diag?.requested_scopes || []).join(", ")} testid="diag-requested-scope" />
          <Row label="Granted scopes" value={(diag?.granted_scopes || []).join(", ") || "—"} testid="diag-granted-scope" mono />
          <Row label="Drive connected" value={diag?.drive_connected ? "yes" : "no"} testid="diag-connected" mono />
          <Row label="Folders initialised" value={diag?.drive_initialized ? "yes" : "no"} testid="diag-initialized" mono />
          <Row label="Credentials updated" value={diag?.credentials_updated_at} testid="diag-creds-time" />
          <Row label="Last connect attempt" value={diag?.last_attempt?.started_at || "—"} testid="diag-attempt-time" />
          <Row label="Callback received from Google" value={diag?.last_attempt ? (diag.last_attempt.callback_received ? `yes (${diag.last_attempt.callback_result})` : "NO — Google never redirected back") : "—"} testid="diag-callback-received" />
        </div>
        {diag?.last_attempt && !diag.last_attempt.callback_received && !diag.drive_connected && (
          <div className="px-4 py-3 bg-amber-50 border-t border-amber-200" data-testid="diag-silent-block">
            <div className="text-xs uppercase tracking-wider text-amber-800 font-semibold">Silent failure detected</div>
            <div className="text-sm font-semibold text-amber-900 mt-1">Google blocked the OAuth request at its own consent page</div>
            <div className="text-xs text-amber-900 mt-1 leading-relaxed">
              Backend generated the OAuth URL and you went to Google, but Google never redirected back to the callback. That means the 403 came from <span className="font-semibold">accounts.google.com</span> itself, and Google does not pass us an error code in that case. The fix lives in your Google Cloud Console — see the checklist below.
            </div>
          </div>
        )}
        {diag?.last_error && (
          <div className="px-4 py-3 bg-red-50 border-t border-red-200" data-testid="diag-last-error">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-wider text-red-700 font-semibold">Last OAuth error · {diag.last_error.source}</div>
                <div className="text-sm font-semibold text-red-900 mt-0.5 mono">{diag.last_error.error}</div>
                <div className="text-xs text-red-800 mt-1 leading-relaxed break-all whitespace-pre-wrap">{diag.last_error.error_description}</div>
                <div className="text-[11px] text-red-700 mono mt-1">at {diag.last_error.timestamp}</div>
              </div>
              <button onClick={clearError} className="text-xs text-red-700 hover:text-red-900 underline shrink-0" data-testid="diag-clear-error">
                clear
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Connection */}
      <div className="bg-white border border-zinc-200 rounded-sm">
        <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status?.connected ? <Cloud className="w-4 h-4 text-green-700" /> : <CloudOff className="w-4 h-4 text-zinc-500" />}
            <div>
              <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>Google Drive</div>
              <div className="text-xs text-zinc-500 mono">
                {status?.connected ? "Connected" : "Not connected"} · {status?.initialized ? "folders initialised" : "folders not initialised"}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            {!status?.connected && (
              <Button onClick={connect} disabled={busy} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="drive-connect-btn">
                {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Cloud className="w-4 h-4 mr-2" />}
                Connect Google Drive
              </Button>
            )}
            {status?.connected && !status?.initialized && (
              <Button onClick={initFolders} disabled={busy} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid="drive-init-btn">
                {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FolderPlus className="w-4 h-4 mr-2" />}
                Create folder structure
              </Button>
            )}
            {status?.connected && (
              <Button variant="outline" onClick={disconnect} disabled={busy} className="rounded-sm" data-testid="drive-disconnect-btn">
                <Unplug className="w-4 h-4 mr-2" /> Disconnect
              </Button>
            )}
          </div>
        </div>

        {status?.connected && status?.initialized && (
          <div className="px-4 py-3">
            <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2 flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-green-700" /> Folder structure
            </div>
            <div className="text-xs text-zinc-700 mb-2 mono">
              {status.parent_folder_name}
              {status.parent_folder_id && (
                <a href={`https://drive.google.com/drive/folders/${status.parent_folder_id}`} target="_blank" rel="noreferrer" className="text-blue-700 ml-2 inline-flex items-center gap-1 hover:underline" data-testid="drive-open-folder-link">
                  open <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
            <ul className="text-xs mono text-zinc-700 leading-relaxed">
              {Object.entries(status.subfolders || {}).map(([name, id]) => (
                <li key={id} className="flex items-center justify-between border-t border-zinc-100 py-1">
                  <span>├ {name}</span>
                  <a href={`https://drive.google.com/drive/folders/${id}`} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">open</a>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!status?.connected && (
          <div className="px-4 py-4 text-sm text-zinc-700 bg-amber-50 border-t border-amber-200">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
              <div>
                <div className="font-medium text-amber-900">Drive not connected — fallback mode active</div>
                <div className="text-xs text-amber-800 mt-1 leading-relaxed">
                  Uploads will still work and be stored on the app server. You can paste a manual Google Drive folder name and link for each document so the Evidence Register stays accurate. Connect Drive whenever you're ready and new uploads will go straight to your Drive.
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-white border border-zinc-200 rounded-sm mt-4 p-4 text-xs leading-relaxed text-zinc-700">
        <div className="font-semibold mb-1 text-sm" style={{ fontFamily: "Chivo" }}>If Google returns 403</div>
        <ol className="list-decimal ml-5 space-y-1">
          <li>Confirm the OAuth client → <span className="mono">Authorized redirect URIs</span> contains the redirect URI shown above.</li>
          <li>If the OAuth consent screen is in <span className="font-semibold">Testing</span>, add your account under <span className="mono">Test users</span>.</li>
          <li>The exact Google error appears under <span className="font-semibold">Last OAuth error</span>.</li>
        </ol>
      </div>

      <div className="bg-white border border-zinc-200 rounded-sm mt-4" data-testid="ai-status-card">
        <div className="px-4 py-2.5 border-b border-zinc-200">
          <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>AI Classifier (Hybrid)</div>
          <div className="text-[11px] text-zinc-500 mono mt-0.5">Gemini Flash → Claude Sonnet escalation</div>
        </div>
        <div className="px-4 py-2">
          <Row label="Mode" value={aiStats?.mode || "Hybrid"} testid="ai-mode" />
          <Row label="Primary model" value={aiStats?.primary_model || "—"} testid="ai-primary-model" />
          <Row label="Escalation model" value={aiStats?.escalation_model || "—"} testid="ai-escalation-model" />
          <Row label="Documents processed" value={aiStats ? String(aiStats.totalDocs ?? aiStats.documents_processed) : "—"} testid="ai-docs" />
          <Row label="Gemini-only runs" value={aiStats ? String(aiStats.geminiOnly ?? 0) : "—"} testid="ai-gemini-only" />
          <Row label="Claude escalations" value={aiStats ? String(aiStats.claudeEscalations ?? 0) : "—"} testid="ai-claude-escalations" />
          <Row
            label="Escalation rate"
            value={aiStats && aiStats.totalDocs > 0
              ? `${Math.round((aiStats.claudeEscalations / aiStats.totalDocs) * 100)}%`
              : "—"}
            testid="ai-escalation-rate"
          />
          <Row label="Gemini cost" value={aiStats ? `$${(aiStats.geminiCost || 0).toFixed(4)}` : "—"} testid="ai-gemini-cost" />
          <Row label="Claude cost" value={aiStats ? `$${(aiStats.claudeCost || 0).toFixed(4)}` : "—"} testid="ai-claude-cost" />
          <Row label="Total AI cost" value={aiStats ? `$${(aiStats.totalCost || 0).toFixed(4)}` : "—"} testid="ai-cost" />
          <Row label="Last AI error" value={aiStats?.last_error?.message || "None"} testid="ai-last-error" />
        </div>
      </div>
    </div>
  );
}
