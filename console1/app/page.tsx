"use client";
import { useEffect, useState } from "react";
import { useDeviceState, DEMO_DEVICE } from "@/lib/useDeviceState";
import PriorityList from "@/components/PriorityList";
import DeviceDetail from "@/components/DeviceDetail";
import IncidentsPanel from "@/components/IncidentsPanel";
import TopologyMap from "@/components/TopologyMap";
import Terminal from "@/components/Terminal";

function UpdatedAt() {
  const [t, setT] = useState(0);
  useEffect(() => { const i = setInterval(() => setT((x) => x + 5), 5000); return () => clearInterval(i); }, []);
  return <span className="text-mut">updated {t === 0 ? "just now" : `${t}s ago`}</span>;
}

const DEMOS = [
  { key: "discover", label: "Discover the network — map & data build live" },
  { key: "leak", label: "Memory leak on core-sw-01 (gradual failure)" },
  { key: "creep", label: "Interface errors on acc-sw-01 (gradual)" },
  { key: "spike", label: "CPU spike on fw-01 (sudden failure)" },
] as const;

type Tab = "overview" | "map" | "incidents" | "terminal";

export default function Page() {
  const { state, demo, discovered, booted, paused, setPaused, startScenario, startDiscover, stopDemo } = useDeviceState();
  const [selected, setSelected] = useState<string>("");
  const [tab, setTab] = useState<Tab>("overview");
  const [menuOpen, setMenuOpen] = useState(false);

  // during a scenario demo, keep the affected device selected + highlighted
  const demoDev = demo && demo !== "discover" ? DEMO_DEVICE[demo] : null;
  useEffect(() => { if (demoDev) setSelected(demoDev); }, [demoDev]);
  useEffect(() => { if (booted && !selected) setSelected("core-sw-01"); }, [booted, selected]);

  if (!state) return <div className="p-8 text-mut text-sm">Loading NetPulse…</div>;

  const visible = booted ? null : (discovered ?? new Set<string>());

  const dev = state.devices.find((d) => d.device === selected) ?? state.devices[0];
  const alerting = state.devices.filter((d) => d.alert).length;

  const run = (key: string) => {
    setMenuOpen(false);
    if (key === "discover") { setTab("map"); startDiscover(); }
    else { setTab("overview"); startScenario(key as "leak" | "creep" | "spike"); }
  };

  const nInc = booted ? (state.correlation?.incident_count ?? 0) : 0;
  const TabBtn = ({ id, label }: { id: Tab; label: string }) => (
    <button onClick={() => setTab(id)}
      className={`px-3.5 py-1.5 rounded-md text-[13px] ${
        tab === id ? "bg-panel border border-line font-medium" : "text-mut hover:text-txt"}`}>
      {label}
      {id === "incidents" && nInc > 0 &&
        <span className="ml-1.5 text-red font-semibold">●{nInc}</span>}
    </button>
  );

  return (
    <main className="h-screen flex flex-col">
      <header className="px-6 py-3.5 border-b border-line bg-panel flex items-center justify-between shrink-0">
        <div className="flex items-center gap-6">
          <div>
            <h1 className="text-[16px] font-semibold m-0 leading-tight">NetPulse</h1>
            <div className="text-[10.5px] text-mut">Device health &amp; impact console</div>
          </div>
          <nav className="flex gap-1 bg-bg rounded-lg p-1">
            <TabBtn id="overview" label="Overview" />
            <TabBtn id="map" label="Network map" />
            <TabBtn id="incidents" label="Incidents" />
            <TabBtn id="terminal" label="Terminal" />
          </nav>
        </div>
        <div className="flex items-center gap-3 text-[12px]">
          <span className={paused ? "text-mut" : booted ? "text-green" : "text-mut"}>
            {booted ? (paused ? "❚❚ paused" : "● live") : "○ awaiting discovery"} ·{" "}
            {booted ? state.devices.length : (discovered?.size ?? 0)} devices</span>
          <UpdatedAt />
          {alerting > 0 && <span className="text-red font-medium">{alerting} alerting</span>}
          <button onClick={() => setPaused((v) => !v)}
                  className="border border-line rounded px-3 py-1.5 bg-panel">
            {paused ? "▶ Resume" : "❚❚ Pause"}
          </button>
          <div className="relative">
            {demo
              ? <button onClick={stopDemo} className="border border-red text-red rounded px-3 py-1.5 bg-panel">■ Stop demo</button>
              : <button onClick={() => setMenuOpen((v) => !v)}
                        className="border border-green text-green rounded px-3 py-1.5 bg-panel">▶ Run demo</button>}
            {menuOpen && !demo && (
              <div className="absolute right-0 mt-1 bg-panel border border-line rounded-md shadow-lg z-20 w-80 py-1">
                {DEMOS.map((d) => (
                  <button key={d.key} onClick={() => run(d.key)}
                          className="block w-full text-left px-3.5 py-2.5 text-[12.5px] hover:bg-sel">
                    {d.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      {demoDev && (() => {
        const dd = state.devices.find((x) => x.device === demoDev);
        return dd ? (
          <div className="px-6 py-2 bg-hl border-b border-line text-[12.5px]">
            <b>{demoDev}</b> — health {Math.round(dd.health)} · {dd.explanation || "monitoring…"}
          </div>
        ) : null;
      })()}

      {tab === "overview" && (
        <div className="flex flex-1 min-h-0">
          <div className="flex-[1.6] overflow-auto px-6 py-5">
            <PriorityList devices={state.devices} selected={selected} onSelect={setSelected}
                          discovered={visible}
                          highlight={demoDev} />
          </div>
          <div className="flex-1 border-l border-line bg-panel overflow-auto px-6 py-5">
            {booted
              ? <DeviceDetail device={dev} />
              : <div className="text-mut text-[13px] mt-8 text-center">
                  Select a device after discovery to see its health, forecast and blast radius.
                </div>}
          </div>
        </div>
      )}

      {tab === "map" && (
        <div className="flex-1 min-h-0">
          <TopologyMap devices={state.devices} selected={selected}
                       onSelect={(d) => { setSelected(d); }}
                       discovered={visible}
                       discovering={demo === "discover"} />
        </div>
      )}

      {tab === "terminal" && (
        <div className="flex-1 min-h-0">
          <Terminal onDiscover={(order) => { startDiscover(order); setTab("map"); }} />
        </div>
      )}

      {tab === "incidents" && (
        <div className="flex-1 overflow-auto px-6 py-5">
          {booted
            ? <IncidentsPanel c={state.correlation} devices={state.devices}
                              onOpenDevice={(d) => { setSelected(d); setTab("overview"); }} />
            : <div className="text-mut text-[13px] pt-8">
                No incidents yet — run <span className="font-mono">discover</span> to begin monitoring.
              </div>}
        </div>
      )}
    </main>
  );
}
