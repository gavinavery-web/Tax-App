// Single source of truth for tax-year configuration in the UI.
// Reads from /api/tax-years/config (the dynamic collection) and exposes
// {all, active} arrays. Components subscribe via useTaxYears() and re-render
// when /tax-years/config changes (other components can call refresh() after
// PATCH/POST). Falls back to the seeded defaults if the API is unreachable.
import { useEffect, useState, useCallback } from "react";
import { api } from "./api";

const FALLBACK = [
  { id: "fy2024", name: "FY2024", start_date: "2023-07-01", end_date: "2024-06-30", active: true,  locked: false, order: 1 },
  { id: "fy2025", name: "FY2025", start_date: "2024-07-01", end_date: "2025-06-30", active: true,  locked: false, order: 2 },
  { id: "fy2026", name: "FY2026", start_date: "2025-07-01", end_date: "2026-06-30", active: true,  locked: false, order: 3 },
];

// Light global cache so all consumers share the same array reference.
let _cache = null;
const _subscribers = new Set();

const notify = () => _subscribers.forEach((fn) => fn(_cache));

export const refreshTaxYears = async () => {
  try {
    const { data } = await api.get("/tax-years/config");
    _cache = Array.isArray(data) && data.length ? data : FALLBACK;
  } catch (e) {
    _cache = FALLBACK;
  }
  notify();
  return _cache;
};

export default function useTaxYears() {
  const [years, setYears] = useState(_cache || FALLBACK);

  useEffect(() => {
    const cb = (next) => setYears(next || FALLBACK);
    _subscribers.add(cb);
    if (!_cache) refreshTaxYears();
    else setYears(_cache);
    return () => { _subscribers.delete(cb); };
  }, []);

  const refresh = useCallback(() => refreshTaxYears(), []);

  return {
    all: years,
    active: years.filter((y) => y.active),
    activeNames: years.filter((y) => y.active).map((y) => y.name),
    refresh,
  };
}
