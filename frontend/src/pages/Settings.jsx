import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Cloud, CloudOff, FolderPlus, Loader2, CheckCircle2, AlertCircle, ExternalLink, Unplug } from "lucide-react";
import { toast } from "sonner";

export default function Settings() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [params, setParams] = useSearchParams();

  const load = async () => {
    const r = await api.get("/drive/status");
    setStatus(r.data);
  };

  useEffect(() => {
    load();
    const flag = params.get("drive");
    if (flag === "connected") { toast.success("Google Drive connected!"); params.delete("drive"); setParams(params, { replace: true }); }
    if (flag === "error") { toast.error(`Drive connection failed: ${params.get("msg") || ""}`); params.delete("drive"); params.delete("msg"); setParams(params, { replace: true }); }
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
    if (!window.confirm("Disconnect Drive? Existing uploaded files remain in Drive; this only removes stored credentials.")) return;
    setBusy(true);
    try {
      await api.post("/drive/disconnect");
      toast.success("Disconnected.");
      await load();
    } finally { setBusy(false); }
  };

  return (
    <div className="p-6 max-w-3xl" data-testid="settings-page">
      <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Settings</h1>
      <div className="text-sm text-zinc-500 mt-1 mb-6">Google Drive connection & folder initialisation.</div>

      <div className="bg-white border border-zinc-200 rounded-sm">
        <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status?.connected ? <Cloud className="w-4 h-4 text-green-700" /> : <CloudOff className="w-4 h-4 text-zinc-500" />}
            <div>
              <div className="text-sm font-semibold" style={{ fontFamily: "Chivo" }}>Google Drive</div>
              <div className="text-xs text-zinc-500 mono">
                {status?.connected ? "Connected" : "Not connected"} ·{" "}
                {status?.initialized ? "folders initialised" : "folders not initialised"}
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
                <a
                  href={`https://drive.google.com/drive/folders/${status.parent_folder_id}`}
                  target="_blank" rel="noreferrer"
                  className="text-blue-700 ml-2 inline-flex items-center gap-1 hover:underline"
                  data-testid="drive-open-folder-link"
                >
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
          <div className="px-4 py-4 text-sm text-zinc-700 flex items-start gap-3 bg-amber-50 border-t border-amber-200">
            <AlertCircle className="w-4 h-4 text-amber-700 mt-0.5" />
            <div>
              <div className="font-medium text-amber-900">Drive not connected</div>
              <div className="text-xs text-amber-800 mt-1">
                Files cannot be uploaded until you authorise Google Drive. Click <span className="font-semibold">Connect Google Drive</span> above.
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-white border border-zinc-200 rounded-sm mt-4 p-4 text-sm leading-relaxed text-zinc-700">
        <div className="font-semibold mb-1" style={{ fontFamily: "Chivo" }}>How it works</div>
        <ol className="list-decimal ml-5 space-y-1 text-xs">
          <li>Connect Google Drive (one-time OAuth).</li>
          <li>App creates a parent folder <span className="mono">Tax Evidence Vault</span> with 11 numbered subfolders.</li>
          <li>Each upload is placed in the matching subfolder based on the category you choose.</li>
          <li>The Evidence Register stores a permanent record + a clickable Drive link.</li>
        </ol>
      </div>
    </div>
  );
}
