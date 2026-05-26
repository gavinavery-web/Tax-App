// Stage 7 — tax-year options now match the dynamic /api/tax-years/config
// collection. The seeded defaults are FY2024, FY2025, FY2026 (all active).
// `currentFY()` returns the FY containing `date` (Jul–Jun Australian FY).
export const currentFY = (date = new Date()) => {
  const m = date.getMonth() + 1;
  const y = date.getFullYear();
  return m >= 7 ? `FY${y + 1}` : `FY${y}`;
};

const FIXED_FY = ["FY2024", "FY2025", "FY2026"];
export const TAX_YEAR_OPTIONS = [...FIXED_FY, "Both", "Historical", "Unsure"];
