"use client";
import { useEffect, useRef, useState } from "react";

const HELP = [
  "NetPulse SNMP terminal",
  "",
  "  discover                           FULL network sweep: identity + neighbours + metrics,",
  "                                     one command — builds the map & inventory live",
  "  snmpwalk --all lldpRemTable        neighbour walk only → builds the map",
  "  snmpwalk <device> lldpRemTable     one device's LLDP neighbour table",
  "  snmpget  <device> sysName          device identity",
  "  snmpget  <device> hrStorageUsed    memory reading (also: hrProcessorLoad, ifInErrors)",
  "  mode live <host> <community>       switch relay to a real SNMP device (needs live network)",
  "  mode dataset                       back to dataset mode",
  "  clear · help",
  "",
];

export default function Terminal({
  onDiscover,
}: { onDiscover: (order: string[]) => void }) {
  const [lines, setLines] = useState<string[]>([...HELP]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<{ mode: string; host?: string; community?: string }>({ mode: "dataset" });
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [lines]);

  const run = async () => {
    const cmd = input.trim();
    if (!cmd) return;
    setInput("");
    setLines((l) => [...l, `$ ${cmd}`]);
    if (cmd === "clear") { setLines([]); return; }
    if (cmd === "help") { setLines((l) => [...l, ...HELP]); return; }
    const mm = cmd.match(/^mode\s+(live|dataset)(?:\s+(\S+))?(?:\s+(\S+))?/);
    if (mm) {
      const next = mm[1] === "live"
        ? { mode: "live", host: mm[2], community: mm[3] }
        : { mode: "dataset" };
      setMode(next);
      setLines((l) => [...l, `mode set: ${next.mode}${next.host ? ` → ${next.host}` : ""}`]);
      if (next.mode === "dataset") return;
    }
    setBusy(true);
    try {
      const r = await fetch("/api/snmp", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cmd, ...mode }),
      });
      const data = await r.json();
      if (data.lines?.length) setLines((l) => [...l, ...data.lines]);
      if (data.discover) {
        setLines((l) => [...l, "…devices responding — building map & inventory (see Network map / Overview)"]);
        onDiscover(data.discover);
      }
    } catch {
      setLines((l) => [...l, "relay error"]);
    }
    setBusy(false);
  };

  return (
    <div className="h-full flex flex-col bg-[#0d1117] text-[#c9d1d9] font-mono text-[12.5px]">
      <div className="flex-1 overflow-auto px-4 py-3 leading-relaxed">
        {lines.map((l, i) => (
          <div key={i} className={l.startsWith("$") ? "text-[#58a6ff]" : ""}>{l || "\u00A0"}</div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-[#30363d] px-4 py-2.5 flex items-center gap-2">
        <span className="text-[#58a6ff]">$</span>
        <input value={input} onChange={(e) => setInput(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && !busy && run()}
               placeholder="discover"
               className="flex-1 bg-transparent outline-none placeholder-[#484f58]"
               autoFocus spellCheck={false} />
        <span className="text-[10px] text-[#484f58] uppercase">{mode.mode} mode</span>
      </div>
    </div>
  );
}
