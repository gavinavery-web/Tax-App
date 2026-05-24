export const STATUS_COLORS = {
  "Not started": { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" },
  Partial: { bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  Complete: { bg: "#F0FDF4", fg: "#166534", border: "#BBF7D0" },
  "Accountant review": { bg: "#FEF2F2", fg: "#991B1B", border: "#FECACA" },
  "Uploaded only": { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" },
  "Needs analysis": { bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  Analysed: { bg: "#EFF6FF", fg: "#1E40AF", border: "#BFDBFE" },
  "Missing evidence": { bg: "#FEF2F2", fg: "#991B1B", border: "#FECACA" },
};

export const PRIORITY_COLORS = {
  Critical: { bg: "#FEF2F2", fg: "#991B1B", border: "#FECACA" },
  Important: { bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  Later: { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" },
};

export const MISSING_STATUS_OPTIONS = ["Not started", "In progress", "Found", "Skipped"];

export const FIGURE_TYPES = [
  { value: "income", label: "Income" },
  { value: "tax_withheld", label: "Tax withheld" },
  { value: "expense", label: "Expense" },
  { value: "interest", label: "Interest" },
  { value: "liability", label: "Liability" },
  { value: "other", label: "Other" },
];

export const fmtAUD = (n) =>
  new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", minimumFractionDigits: 2 }).format(Number(n) || 0);

export const fmtDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-AU", { day: "2-digit", month: "short", year: "numeric" });
};
