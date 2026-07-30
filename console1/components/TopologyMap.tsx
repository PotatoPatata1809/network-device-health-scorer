"use client";
import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Node, Edge, Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import type { Device, TopoDevice } from "@/lib/types";
import { healthColor } from "@/lib/types";

const ICON: Record<string, string> = {
  "core-switch": "⬢", "dist-switch": "⧉", "access-switch": "⇆",
  "router": "🌐", "firewall": "🛡️", "wlc": "📶", "server": "🖥️",
};

export default function TopologyMap({
  devices, selected, onSelect, discovered,
}: { devices: Device[]; selected: string; onSelect: (d: string) => void;
     discovered?: Set<string> | null }) {
  const [topo, setTopo] = useState<TopoDevice[] | null>(null);
  useEffect(() => {
    fetch("/topology.json").then((r) => r.json()).then((t) => setTopo(t.devices));
  }, []);

  const byName = useMemo(() => Object.fromEntries(devices.map((d) => [d.device, d])), [devices]);
  const selDown = new Set(byName[selected]?.downstream ?? []);

  const { nodes, edges } = useMemo(() => {
    if (!topo) return { nodes: [] as Node[], edges: [] as Edge[] };
    const byId = Object.fromEntries(topo.map((d) => [d.id, d]));
    const depth: Record<string, number> = {};
    const dfor = (id: string): number =>
      depth[id] ?? (depth[id] = byId[id].parent ? dfor(byId[id].parent!) + 1 : 0);
    topo.forEach((d) => dfor(d.id));
    const perDepth: Record<number, string[]> = {};
    topo.forEach((d) => { (perDepth[depth[d.id]] ??= []).push(d.id); });
    Object.values(perDepth).forEach((arr) => arr.sort());

    const disc = discovering;
    const visible = (id: string) => !discovered || discovered.has(id);
    const discovering = !!disc;

    const nodes: Node[] = topo.filter((d) => visible(d.id)).map((d) => {
      const sibs = perDepth[depth[d.id]];
      const i = sibs.indexOf(d.id);
      const dev = byName[d.id];
      const h = dev?.health ?? 90;
      const hl = !discovering && (d.id === selected || selDown.has(d.id));
      const col = healthColor(h);
      return {
        id: d.id,
        position: { x: i * 170 - (sibs.length * 170) / 2 + 620, y: depth[d.id] * 150 + 30 },
        data: {
          label: (
            <div style={{ textAlign: "center", lineHeight: 1.3 }}>
              <div style={{ fontSize: 17 }}>{ICON[d.type] ?? "▢"}</div>
              <div style={{ fontSize: 11.5, fontWeight: 600 }}>{d.id}</div>
              <div style={{ fontSize: 10, color: col }}>{
                dev ? `health ${Math.round(h)}` : ""}</div>
            </div>
          ),
        },
        style: {
          background: "#ffffff", color: "#1f2328",
          border: `2px solid ${hl ? "#cf222e" : discovering ? "#1a7f37" : col}`,
          borderRadius: 10, padding: "8px 10px", width: 150,
          boxShadow: hl ? "0 0 0 4px rgba(207,34,46,.15)" : "0 1px 3px rgba(0,0,0,.08)",
          opacity: !discovering && selected && !hl && d.id !== selected ? 0.5 : 1,
          transition: "all .3s",
        },
      };
    });
    const edges: Edge[] = topo
      .filter((d) => d.parent && visible(d.id) && visible(d.parent!))
      .map((d) => ({
        id: `${d.parent}-${d.id}`, source: d.parent!, target: d.id,
        type: "smoothstep", animated: discovering,
        style: {
          stroke: !discovering && selDown.has(d.id) ? "#cf222e" : "#b6c2cf",
          strokeWidth: !discovering && selDown.has(d.id) ? 2 : 1.4,
        },
      }));
    return { nodes, edges };
  }, [topo, byName, selected, discovered]);

  return (
    <div className="h-full w-full relative">
      {discovered && discovered.size > 0 && discovered.size < devices.length && (
        <div className="absolute z-10 top-3 left-4 text-[12.5px] text-green bg-panel border border-line rounded px-3 py-1.5">
          Walking LLDP neighbours… <b>{nodes.length}</b> of {devices.length} devices found
        </div>
      )}
      {discovered && discovered.size === 0 && (
        <div className="absolute z-10 top-3 left-4 text-[12.5px] text-mut bg-panel border border-line rounded px-3 py-1.5">
          No topology yet — run <span className="font-mono">discover</span> to build the map.
        </div>
      )}
      {!discovering && discovered===null && selected && (
        <div className="absolute z-10 top-3 left-4 text-[12.5px] bg-panel border border-line rounded px-3 py-1.5">
          <b>{selected}</b>{selDown.size > 0
            ? <> — if it fails, <b className="text-red">{selDown.size} devices</b> lose their path (shown in red)</>
            : <> — nothing depends on this device</>}
        </div>
      )}
      <ReactFlow nodes={nodes} edges={edges} onNodeClick={(_, n) => onSelect(n.id)}
                 fitView proOptions={{ hideAttribution: true }}
                 nodesDraggable={false} nodesConnectable={false} minZoom={0.3}>
        <Background color="#e3e8ee" gap={26} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
