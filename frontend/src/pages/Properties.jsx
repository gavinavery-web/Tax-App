import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Plus, X, Home } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";

const USE_TYPES = [
  { value: "main_residence", label: "Main residence" },
  { value: "rental", label: "Rental" },
  { value: "airbnb", label: "Airbnb" },
  { value: "renovation", label: "Renovation" },
  { value: "vacant", label: "Vacant" },
  { value: "mixed", label: "Mixed use" },
];

const USE_TONE = {
  main_residence: "bg-zinc-100 text-zinc-800 border-zinc-300",
  rental: "bg-blue-50 text-blue-800 border-blue-200",
  airbnb: "bg-pink-50 text-pink-800 border-pink-200",
  renovation: "bg-amber-50 text-amber-800 border-amber-200",
  vacant: "bg-zinc-50 text-zinc-600 border-zinc-200",
  mixed: "bg-violet-50 text-violet-800 border-violet-200",
};

export default function Properties() {
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addingTo, setAddingTo] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/properties");
      setProperties(data);
    } catch (e) {
      toast.error(`Failed to load properties: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const removePeriod = async (propId, periodId) => {
    if (!window.confirm("Remove this use period?")) return;
    try {
      await api.delete(`/properties/${propId}/periods/${periodId}`);
      toast.success("Period removed");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to remove period");
    }
  };

  return (
    <div className="p-6 max-w-[1200px] mx-auto" data-testid="properties-page">
      <div className="mb-5">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }}>Properties</h1>
        <p className="text-sm text-zinc-500 mt-1">Define how each property was used over time. Bank transactions auto-classify against these periods (rental vs main residence vs Airbnb).</p>
      </div>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading…</div>
      ) : (
        <div className="space-y-4">
          {properties.map((p) => (
            <div key={p.id} className="p-4 bg-white border border-zinc-200 rounded-lg" data-testid={`property-card-${p.id}`}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                  <Home className="w-4 h-4 text-zinc-500" />
                  <div>
                    <div className="text-lg font-semibold tracking-tight" style={{ fontFamily: "Chivo" }}>{p.property_name}</div>
                    <div className="text-xs text-zinc-500 mono">{p.address}</div>
                  </div>
                </div>
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAddingTo(addingTo === p.id ? null : p.id)} data-testid={`add-period-btn-${p.id}`}>
                  <Plus className="w-3.5 h-3.5" /> Add period
                </Button>
              </div>

              {addingTo === p.id && (
                <AddPeriodForm propertyId={p.id} onDone={() => { setAddingTo(null); load(); }} onCancel={() => setAddingTo(null)} />
              )}

              <div className="space-y-1.5 mt-2">
                {(p.use_periods || []).length === 0 ? (
                  <div className="text-xs text-zinc-500 italic px-1">No use periods defined yet.</div>
                ) : (
                  p.use_periods.map((pr) => (
                    <div key={pr.period_id} className="p-2.5 bg-zinc-50 border border-zinc-200 rounded flex items-center justify-between" data-testid={`period-${pr.period_id}`}>
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-medium border ${USE_TONE[pr.use_type] || ""}`}>
                          {pr.use_type.replace(/_/g, " ")}
                        </span>
                        <span className="text-xs mono text-zinc-700">
                          {pr.date_from} → {pr.date_to || "Current"}
                        </span>
                        {pr.notes && <span className="text-xs text-zinc-500 truncate">· {pr.notes}</span>}
                      </div>
                      <button
                        onClick={() => removePeriod(p.id, pr.period_id)}
                        className="text-zinc-400 hover:text-red-600"
                        data-testid={`remove-period-${pr.period_id}`}
                        title="Remove period"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AddPeriodForm({ propertyId, onDone, onCancel }) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [useType, setUseType] = useState("rental");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!dateFrom) { toast.error("Start date is required"); return; }
    setBusy(true);
    try {
      await api.post(`/properties/${propertyId}/periods`, {
        date_from: dateFrom,
        date_to: dateTo || null,
        use_type: useType,
        notes,
      });
      toast.success("Period added");
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to add period");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-3 p-3 bg-zinc-50 border border-zinc-200 rounded-lg" data-testid="add-period-form">
      <div className="grid grid-cols-3 gap-2 mb-2">
        <div>
          <label className="text-xs mono uppercase text-zinc-500 tracking-wide">From</label>
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="period-date-from" />
        </div>
        <div>
          <label className="text-xs mono uppercase text-zinc-500 tracking-wide">To (blank = current)</label>
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="period-date-to" />
        </div>
        <div>
          <label className="text-xs mono uppercase text-zinc-500 tracking-wide">Use type</label>
          <Select value={useType} onValueChange={setUseType}>
            <SelectTrigger data-testid="period-use-type"><SelectValue /></SelectTrigger>
            <SelectContent>
              {USE_TYPES.map((u) => <SelectItem key={u.value} value={u.value}>{u.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)" rows={2} className="text-sm" data-testid="period-notes" />
      <div className="flex gap-2 mt-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button size="sm" onClick={submit} disabled={busy} data-testid="save-period-btn">{busy ? "Saving…" : "Save period"}</Button>
      </div>
    </div>
  );
}
