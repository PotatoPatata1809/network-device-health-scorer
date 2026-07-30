"use client";
import { useEffect, useRef, useState } from "react";
import type { State, DemoFrame, Device, Correlation, TopoDevice } from "./types";

export type DemoKind = "leak" | "creep" | "spike" | "discover" | null;

const DEMO_FILES: Record<string, string> = {
  leak: "/demo_leak.json", creep: "/demo_creep.json", spike: "/demo_spike.json",
};
export const DEMO_DEVICE: Record<string, string> = {
  leak: "core-sw-01", creep: "acc-sw-01", spike: "fw-01",
};
const TICK_MS = 750;          // slow enough to follow
const DISCOVER_MS = 480;      // one device found per beat

export function useDeviceState() {
  const [state, setState] = useState<State | null>(null);
  const [base, setBase] = useState<State | null>(null);
  const [topoOrder, setTopoOrder] = useState<string[]>([]);
  const [demo, setDemo] = useState<DemoKind>(null);
  const [booted, setBooted] = useState(false);          // fleet visible only after discovery
  const [paused, setPaused] = useState(false);
  const ambient = useRef<ReturnType<typeof setInterval> | null>(null);
  const [discovered, setDiscovered] = useState<Set<string> | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" &&
        new URLSearchParams(window.location.search).get("loaded") === "1") {
      setBooted(true);                                   // safety hatch: ?loaded=1
    }
    fetch("/priority_state.json").then((r) => r.json())
      .then((s: State) => { setState(s); setBase(s); });
    fetch("/topology.json").then((r) => r.json()).then((t) => {
      const devs: TopoDevice[] = t.devices;
      const byId = Object.fromEntries(devs.map((d) => [d.id, d]));
      const depth: Record<string, number> = {};
      const dfor = (id: string): number =>
        depth[id] ?? (depth[id] = byId[id].parent ? dfor(byId[id].parent!) + 1 : 0);
      devs.forEach((d) => dfor(d.id));
      setTopoOrder([...devs].sort((a, b) =>
        depth[a.id] - depth[b.id] || a.id.localeCompare(b.id)).map((d) => d.id));
    });
  }, []);

  const clear = () => { if (timer.current) clearInterval(timer.current); timer.current = null; };

  // ambient live loop: gentle jitter around each device's baseline so the console
  // reads as live telemetry, not a static snapshot. Suspended during demos/pause.
  useEffect(() => {
    if (ambient.current) clearInterval(ambient.current);
    if (!base || paused || demo || !booted) return;
    ambient.current = setInterval(() => {
      setState((prev) => {
        if (!prev || !base) return prev;
        return {
          ...prev,
          devices: prev.devices.map((d, i) => {
            const b = base.devices[i];
            const jh = Math.max(0, Math.min(100,
              b.health + (Math.random() - 0.5) * 1.6));
            const metrics = Object.fromEntries(Object.entries(b.metrics).map(
              ([k, v]) => [k, Math.max(0, +(Number(v) * (1 + (Math.random() - 0.5) * 0.06)).toFixed(3))]));
            const last = d.series?.[d.series.length - 1];
            const series = d.series
              ? [...d.series.slice(-199),
                 { row: (last?.row ?? 0) + 1, health: +jh.toFixed(1), alert: d.alert }]
              : d.series;
            return { ...d, health: +jh.toFixed(1), metrics, series };
          }),
        };
      });
    }, 2200);
    return () => { if (ambient.current) clearInterval(ambient.current); };
  }, [base, paused, demo, booted]);
  const stopDemo = () => { clear(); setDemo(null); setDiscovered(null); if (base) setState(base); };

  const applyFrame = (s: State, f: DemoFrame): State => ({
    devices: s.devices.map((d) => {
      const u = f.updates[d.device];
      if (!u) return d;
      // append the new health point so the graph draws the decline live
      const last = d.series?.[d.series.length - 1];
      const series = u.health != null && d.series
        ? [...d.series.slice(-199), { row: (last?.row ?? 0) + 1,
            health: u.health as number, alert: !!u.alert }]
        : d.series;
      return { ...d, ...u, series } as Device;
    }),
    correlation: (f.correlation as Correlation) ?? s.correlation,
  });

  const startScenario = async (kind: "leak" | "creep" | "spike") => {
    if (!base) return;
    stopDemo(); setBooted(true); setDemo(kind); setState(base);
    const frames: DemoFrame[] = (await (await fetch(DEMO_FILES[kind])).json()).frames;
    let i = 0;
    timer.current = setInterval(() => {
      i += 1;                                   // slow, followable
      if (!frames[i]) { clear(); return; }
      setState((prev) => (prev ? applyFrame(prev, frames[i]) : prev));
    }, TICK_MS);
  };

  // combined demo: devices are DISCOVERED (map builds) and their data arrives with them
  const startDiscover = (order?: string[]) => {
    const seq = order && order.length ? order : topoOrder;
    if (!seq.length) return;
    stopDemo(); setDemo("discover"); setDiscovered(new Set());
    let n = 0;
    timer.current = setInterval(() => {
      n += 1;
      setDiscovered(new Set(seq.slice(0, n)));
      if (n >= seq.length) {
        clear();
        setTimeout(() => { setBooted(true); setDemo(null); setDiscovered(null); }, 1200);
      }
    }, DISCOVER_MS);
  };

  return { state, demo, discovered, booted, paused, setPaused,
           startScenario, startDiscover, stopDemo };
}
