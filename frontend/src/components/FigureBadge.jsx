import React from "react";

const PALETTE = {
  Confirmed: { bg: "#F0FDF4", fg: "#166534", border: "#BBF7D0" },
  Likely:    { bg: "#FFFBEB", fg: "#92400E", border: "#FDE68A" },
  Unsure:    { bg: "#FEF2F2", fg: "#991B1B", border: "#FECACA" },
};

export default function FigureBadge({ value = "Unsure", testid }) {
  const p = PALETTE[value] || PALETTE.Unsure;
  return (
    <span className="pill" style={{ background: p.bg, color: p.fg, borderColor: p.border }} data-testid={testid}>
      {value}
    </span>
  );
}
