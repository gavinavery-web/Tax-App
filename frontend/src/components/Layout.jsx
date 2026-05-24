import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Table2, AlertTriangle, FileBarChart2, Settings as SettingsIcon, ShieldCheck } from "lucide-react";

const links = [
  { to: "/", end: true, label: "Dashboard", icon: LayoutDashboard, testid: "nav-dashboard" },
  { to: "/register", label: "Evidence Register", icon: Table2, testid: "nav-register" },
  { to: "/missing", label: "Missing Evidence", icon: AlertTriangle, testid: "nav-missing" },
  { to: "/reports", label: "Reports", icon: FileBarChart2, testid: "nav-reports" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, testid: "nav-settings" },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#F4F4F5] text-zinc-950 flex">
      <aside className="w-60 shrink-0 bg-white border-r border-zinc-200 flex flex-col" data-testid="app-sidebar">
        <div className="px-4 py-5 border-b border-zinc-200">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-zinc-900" strokeWidth={2.2} />
            <div>
              <div className="text-sm font-semibold tracking-tight" style={{ fontFamily: "Chivo" }}>Tax Evidence Vault</div>
              <div className="text-[11px] text-zinc-500 mono">FY2024 · FY2025 · Stage 1</div>
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
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-zinc-200 text-[11px] text-zinc-500 mono leading-relaxed">
          Private · Single user<br />
          Figures: manual only<br />
          Stage 1 · No AI extraction
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
