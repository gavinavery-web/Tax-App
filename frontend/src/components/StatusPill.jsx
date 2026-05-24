import React from "react";
import { STATUS_COLORS, PRIORITY_COLORS } from "../lib/constants";

export const StatusPill = ({ value, kind = "status", testid }) => {
  const palette = kind === "priority" ? PRIORITY_COLORS : STATUS_COLORS;
  const c = palette[value] || { bg: "#FAFAFA", fg: "#52525B", border: "#E4E4E7" };
  return (
    <span
      className="pill"
      data-testid={testid}
      style={{ background: c.bg, color: c.fg, borderColor: c.border }}
    >
      {value || "—"}
    </span>
  );
};
