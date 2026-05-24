// Auto-compute Australian financial year + tax-year option list.
// Australian FY runs 1 July → 30 June. FY2024 = 1 Jul 2023 → 30 Jun 2024.
export const currentFY = (date = new Date()) => {
  const m = date.getMonth() + 1; // 1-12
  const y = date.getFullYear();
  return m >= 7 ? `FY${y + 1}` : `FY${y}`;
};

export const TAX_YEAR_OPTIONS = (() => {
  const cur = currentFY();
  const num = parseInt(cur.replace("FY", ""), 10);
  const fixed = ["FY2024", "FY2025", "FY2026"];
  const ordered = Array.from(new Set([...fixed, cur, `FY${num + 1}`])).sort();
  return [...ordered, "Both", "Historical", "Unsure"];
})();
