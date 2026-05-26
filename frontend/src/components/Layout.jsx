import React, { useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, Table2, AlertTriangle, FileBarChart2, Settings as SettingsIcon, ShieldCheck, Receipt, Landmark, Building2, Trash2, FilePlus } from "lucide-react";
import { api } from "../lib/api";
import useTaxYears from "../lib/useTaxYears";

const links = [
  { to: "/", end: true, label: "Dashboard", icon: LayoutDashboard, testid: "nav-dashboard", shortcut: "⌘⇧D" },
  { to: "/register", label: "Evidence Register", icon: Table2, testid: "nav-register", shortcut: "⌘U" },
  { to: "/missing-evidence", label: "Missing Evidence", icon: AlertTriangle, testid: "nav-missing", shortcut: "⌘M" },
  { to: "/tax-years", label: "Tax Years", icon: Receipt, testid: "nav-tax-years" },
  { to: "/tax-returns", label: "Tax Returns", icon: FileBarChart2, testid: "nav-tax-returns" },
  { to: "/tax-returns/new", label: "+ New Tax Return", icon: FilePlus, testid: "nav-new-tax-return" },
  { to: "/bank-transactions", label: "Bank Transactions", icon: Landmark, testid: "nav-bank-transactions" },
  { to: "/properties", label: "Assets & Entities", icon: Building2, testid: "nav-properties" },
  { to: "/rubbish-bin", label: "Rubbish Bin", icon: Trash2, testid: "nav-rubbish-bin" },
  { to: "/reports", label: "Reports", icon: FileBarChart2, testid: "nav-reports" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, testid: "nav-settings" },
];

export default function Layout() {
  const navigate = useNavigate();
  const { activeNames } = useTaxYears();

  // Stage 4: on app load, recover any uploads stuck in active state (e.g.
  // backend was restarted mid-batch). Fire-and-forget — safe to ignore failure.
  useEffect(() => {
    api.post("/uploads/recover-stuck").catch(() => {});
  }, []);

  // Stage 5 — global keyboard shortcuts. Ctrl/⌘ + U / M / D.
  // Skip when the user is typing in an input/textarea/contenteditable so we
  // don't hijack normal editing keystrokes.
  useEffect(() => {
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const tag = (e.target?.tagName || "").toLowerCase();
      if (["input", "textarea", "select"].includes(tag) || e.target?.isContentEditable) return;
      const key = (e.key || "").toLowerCase();
      if (key === "u") { e.preventDefault(); navigate("/register"); }
      else if (key === "m") { e.preventDefault(); navigate("/missing-evidence"); }
      // Avoid hijacking Ctrl+D (bookmark). Use Ctrl+Shift+D for Dashboard.
      else if (key === "d" && e.shiftKey) { e.preventDefault(); navigate("/"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  return (
    <div className="min-h-screen bg-[#F4F4F5] text-zinc-950 flex">
      <aside className="w-60 shrink-0 bg-white border-r border-zinc-200 flex flex-col" data-testid="app-sidebar">
        <div className="px-4 py-5 border-b border-zinc-200">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-zinc-900" strokeWidth={2.2} />
            <div>
              <div className="text-sm font-semibold tracking-[0.16em]" style={{ fontFamily: "Chivo" }} data-testid="app-header-title">TAX FINANCES</div>
              <div className="text-[11px] text-zinc-500 mono" data-testid="app-header-years">
                {activeNames.length ? activeNames.join(" · ") : "—"}
              </div>
            </div>
          </div>
        </div>
        <nav className="flex-1 py-2">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              data-testid={l.testid}
              className={({ isActive }) =>
                `flex items-center gap-2 px-4 py-2 text-sm border-l-2 ${
                  isActive
                    ? "border-zinc-950 bg-zinc-50 text-zinc-950 font-medium"
                    : "border-transparent text-zinc-600 hover:text-zinc-950 hover:bg-zinc-50"
                }`
              }
            >
              <l.icon className="w-4 h-4" strokeWidth={2} />
              <span className="flex-1">{l.label}</span>
              {l.shortcut && <kbd className="text-[9px] mono text-zinc-400 px-1 py-0.5 border border-zinc-200 rounded">{l.shortcut}</kbd>}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-zinc-200 text-[11px] text-zinc-500 mono leading-relaxed">
          Private · Single user<br />
          Figures: AI-verified + manual<br />
          Stage 1 + 2 · Hybrid AI
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
