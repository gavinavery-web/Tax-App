// Stage 5 — tax-year options are LOCKED to the in-scope FYs for this trial.
// FY2026 and beyond are deliberately not exposed yet; if/when the user
// enables it later, just extend `FIXED_FY`. We no longer auto-roll forward
// based on `new Date()`.
export const currentFY = (date = new Date()) => {
  const m = date.getMonth() + 1;
  const y = date.getFullYear();
  const computed = m >= 7 ? `FY${y + 1}` : `FY${y}`;
  // Clamp anything beyond FY2025 to "Unsure" until enabled.
  if (["FY2024", "FY2025"].includes(computed)) return computed;
  return "Unsure";
};

const FIXED_FY = ["FY2024", "FY2025"];
export const TAX_YEAR_OPTIONS = [...FIXED_FY, "Both", "Historical", "Unsure"];
