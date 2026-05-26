import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Plus, X, Building2, Pencil } from "lucide-react";
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

const ENTITY_TYPES = [
  { value: "property", label: "Property" },
  { value: "business", label: "Business" },
  { value: "trust", label: "Trust" },
  { value: "super", label: "Super (SMSF)" },
  { value: "other", label: "Other" },
];

const ENTITY_TONE = {
  property: "bg-emerald-50 text-emerald-800 border-emerald-200",
  business: "bg-blue-50 text-blue-800 border-blue-200",
  trust: "bg-violet-50 text-violet-800 border-violet-200",
  super: "bg-amber-50 text-amber-800 border-amber-200",
  other: "bg-zinc-100 text-zinc-700 border-zinc-200",
};

function entityLabel(p) {
  const t = p.entity_type || "property";
  if (t === "other" && p.entity_type_other) return p.entity_type_other;
  return (ENTITY_TYPES.find((x) => x.value === t) || {}).label || t;
}

export default function Properties() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addingTo, setAddingTo] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/properties");
      setItems(data);
    } catch (e) {
      toast.error(`Failed to load assets/entities: ${e.response?.data?.detail || e.message}`);
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
      <div className="mb-5 flex items-start justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }} data-testid="assets-page-title">Assets &amp; Entities</h1>
          <p className="text-sm text-zinc-500 mt-1">Properties, businesses, trusts, super funds and other tax-relevant entities. Bank transactions auto-classify against the use periods defined here.</p>
        </div>
        <Button onClick={() => setShowCreate((v) => !v)} variant="outline" className="gap-2 rounded-sm" data-testid="add-asset-btn">
          <Plus className="w-4 h-4" /> Add asset / entity
        </Button>
      </div>

      {showCreate && (
        <CreateForm onDone={() => { setShowCreate(false); load(); }} onCancel={() => setShowCreate(false)} />
      )}

      {loading ? (
        <div className="text-sm text-zinc-500">Loading…</div>
      ) : (
        <div className="space-y-4">
          {items.map((p) => (
            <div key={p.id} className="p-4 bg-white border border-zinc-200 rounded-lg" data-testid={`property-card-${p.id}`}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2 min-w-0">
                  <Building2 className="w-4 h-4 text-zinc-500 shrink-0" />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="text-lg font-semibold tracking-tight" style={{ fontFamily: "Chivo" }}>{p.property_name}</div>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${ENTITY_TONE[p.entity_type || "property"] || ""}`} data-testid={`entity-type-${p.id}`}>
                        {entityLabel(p)}
                      </span>
                    </div>
                    <div className="text-xs text-zinc-500 mono">{p.address || "—"}</div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button size="sm" variant="ghost" className="gap-1" onClick={() => setEditing(editing?.id === p.id ? null : p)} data-testid={`edit-asset-btn-${p.id}`}>
                    <Pencil className="w-3.5 h-3.5" /> Edit
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAddingTo(addingTo === p.id ? null : p.id)} data-testid={`add-period-btn-${p.id}`}>
                    <Plus className="w-3.5 h-3.5" /> Add period
                  </Button>
                </div>
              </div>

              {editing?.id === p.id && (
                <EditAssetForm asset={p} onDone={() => { setEditing(null); load(); }} onCancel={() => setEditing(null)} />
              )}

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
          {items.length === 0 && (
            <div className="p-8 text-center text-sm text-zinc-500 border border-dashed border-zinc-300 rounded-lg">
              No assets or entities yet. Click <strong>Add asset / entity</strong> above to start.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CreateForm({ onDone, onCancel }) {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [entityType, setEntityType] = useState("property");
  const [entityOther, setEntityOther] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim()) { toast.error("Name is required"); return; }
    if (entityType === "other" && !entityOther.trim()) { toast.error("Please describe the entity type"); return; }
    setBusy(true);
    try {
      await api.post("/properties", {
        property_name: name.trim(),
        address: address.trim(),
        entity_type: entityType,
        entity_type_other: entityType === "other" ? entityOther.trim() : "",
      });
      toast.success(`${name} added`);
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to add asset/entity");
    } finally { setBusy(false); }
  };

  return (
    <div className="mb-4 p-4 bg-zinc-50 border border-zinc-200 rounded-lg" data-testid="create-asset-form">
      <div className="grid grid-cols-2 gap-3 mb-2">
        <div>
          <label className="text-[11px] uppercase tracking-wider text-zinc-500 mono">Name</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Revive Pty Ltd" data-testid="create-asset-name" />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-wider text-zinc-500 mono">Entity type</label>
          <Select value={entityType} onValueChange={setEntityType}>
            <SelectTrigger data-testid="create-asset-type"><SelectValue /></SelectTrigger>
            <SelectContent>
              {ENTITY_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 mb-2">
        <div className="col-span-2">
          <label className="text-[11px] uppercase tracking-wider text-zinc-500 mono">Address / identifier</label>
          <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Address, ABN, or other identifier" data-testid="create-asset-address" />
        </div>
        {entityType === "other" && (
          <div className="col-span-2">
            <label className="text-[11px] uppercase tracking-wider text-zinc-500 mono">Describe the entity type</label>
            <Input value={entityOther} onChange={(e) => setEntityOther(e.target.value)} placeholder="e.g. Partnership, joint venture, sole trader…" data-testid="create-asset-type-other" />
          </div>
        )}
      </div>
      <div className="flex gap-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button size="sm" onClick={submit} disabled={busy} className="bg-zinc-950 hover:bg-zinc-800" data-testid="create-asset-submit">
          {busy ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}

function EditAssetForm({ asset, onDone, onCancel }) {
  const [name, setName] = useState(asset.property_name || "");
  const [address, setAddress] = useState(asset.address || "");
  const [entityType, setEntityType] = useState(asset.entity_type || "property");
  const [entityOther, setEntityOther] = useState(asset.entity_type_other || "");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim()) { toast.error("Name is required"); return; }
    if (entityType === "other" && !entityOther.trim()) { toast.error("Please describe the entity type"); return; }
    setBusy(true);
    try {
      await api.patch(`/properties/${asset.id}`, {
        property_name: name.trim(),
        address: address.trim(),
        entity_type: entityType,
        entity_type_other: entityType === "other" ? entityOther.trim() : "",
      });
      toast.success("Saved");
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to save");
    } finally { setBusy(false); }
  };

  return (
    <div className="mb-3 p-3 bg-blue-50 border border-blue-200 rounded-lg" data-testid={`edit-asset-form-${asset.id}`}>
      <div className="grid grid-cols-2 gap-2 mb-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" data-testid={`edit-asset-name-${asset.id}`} />
        <Select value={entityType} onValueChange={setEntityType}>
          <SelectTrigger data-testid={`edit-asset-type-${asset.id}`}><SelectValue /></SelectTrigger>
          <SelectContent>
            {ENTITY_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Address / identifier" className="col-span-2" data-testid={`edit-asset-address-${asset.id}`} />
        {entityType === "other" && (
          <Input value={entityOther} onChange={(e) => setEntityOther(e.target.value)} placeholder="Describe the entity type" className="col-span-2" data-testid={`edit-asset-type-other-${asset.id}`} />
        )}
      </div>
      <div className="flex gap-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button size="sm" onClick={submit} disabled={busy} className="bg-zinc-950 hover:bg-zinc-800" data-testid={`edit-asset-submit-${asset.id}`}>
          {busy ? "Saving…" : "Save"}
        </Button>
      </div>
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
