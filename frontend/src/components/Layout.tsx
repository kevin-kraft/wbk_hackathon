import { NavLink, Outlet } from "react-router-dom";
import { useServiceHealth } from "../hooks/useServiceHealth";
import { RunProvider } from "../hooks/runContext";
import ServiceHealthStrip from "./ServiceHealthStrip";

const TABS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/perception", label: "Perception" },
  { to: "/inspection", label: "Inspection" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  const { health } = useServiceHealth();

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-2 px-4 py-2.5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-sky-500/20 text-sky-300 ring-1 ring-sky-500/40">
                <span className="text-sm">⬡</span>
              </span>
              <span className="text-sm font-semibold tracking-tight text-zinc-100">
                Disassembly Console
              </span>
            </div>
            <nav className="flex items-center gap-1">
              {TABS.map((t) => (
                <NavLink
                  key={t.to}
                  to={t.to}
                  end={t.end}
                  className={({ isActive }) =>
                    `rounded-md px-3 py-1.5 text-sm font-medium transition ${
                      isActive
                        ? "bg-zinc-800 text-zinc-100"
                        : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                    }`
                  }
                >
                  {t.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <ServiceHealthStrip health={health} />
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-4 py-5">
        <RunProvider>
          <Outlet />
        </RunProvider>
      </main>
    </div>
  );
}
