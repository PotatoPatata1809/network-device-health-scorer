"use client";
import type { Device } from "@/lib/types";
import { fcText, healthColor } from "@/lib/types";
import { Dot, HealthBar, Label } from "./ui";

export default function PriorityList({
  devices, selected, onSelect, discovered, highlight,
}: { devices: Device[]; selected: string; onSelect: (d: string) => void;
     discovered?: Set<string> | null; highlight?: string | null }) {
  let list = [...devices].sort((a, b) => b.priority - a.priority);
  if (discovered) list = list.filter((d) => discovered.has(d.device));
  const healthy = list.filter((d) => d.health >= 75).length;
  const watch = list.filter((d) => d.health >= 45 && d.health < 75).length;
  const critical = list.filter((d) => d.health < 45).length;
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <Label>
          Devices — most important first
          {discovered && <span className="text-green normal-case tracking-normal ml-2">
            · discovering… {list.length}/{devices.length} found</span>}
        </Label>
        <div className="text-[11.5px] flex gap-3">
          <span><span className="inline-block w-2 h-2 rounded-full mr-1" style={{background:"#1a7f37"}}/>{healthy} healthy</span>
          <span><span className="inline-block w-2 h-2 rounded-full mr-1" style={{background:"#9a6700"}}/>{watch} watch</span>
          <span><span className="inline-block w-2 h-2 rounded-full mr-1" style={{background:"#cf222e"}}/>{critical} critical</span>
        </div>
      </div>
      <div className="bg-panel border border-line rounded-md overflow-hidden">
      <table className="w-full text-[13.5px] border-collapse">
        <thead>
          <tr className="text-left text-mut text-[11px] uppercase tracking-wide bg-bg">
            <th className="font-medium py-2.5 px-3 border-b border-line w-10">#</th>
            <th className="font-medium py-2.5 px-3 border-b border-line">Device</th>
            <th className="font-medium py-2.5 px-3 border-b border-line">Health</th>
            <th className="font-medium py-2.5 px-3 border-b border-line">Outlook</th>
            <th className="font-medium py-2.5 px-3 border-b border-line">Affects</th>
          </tr>
        </thead>
        <tbody>
          {list.map((d, i) => (
            <tr key={d.device}
                onClick={() => onSelect(d.device)}
                className={`border-b border-row last:border-0 cursor-pointer hover:bg-sel/50
                  ${selected === d.device ? "bg-sel" : ""}
                  ${highlight === d.device ? "demo-hl" : ""}`}>
              <td className="py-2.5 px-3 text-mut tabular-nums">{i + 1}</td>
              <td className="py-2.5 px-3 whitespace-nowrap">
                <Dot h={d.health} />
                <span className="font-medium">{d.device}</span>
                <span className="text-mut text-[11.5px] ml-2">{d.type}</span>
                {d.alert && <span className="ml-2 text-red text-[10px] font-semibold align-middle">ALERT</span>}
              </td>
              <td className="py-2.5 px-3"><HealthBar h={d.health} /></td>
              <td className="py-2.5 px-3">{fcText(d.forecast)}</td>
              <td className="py-2.5 px-3">{d.impact === 0 ? "—" : `${d.impact} devices`}</td>
            </tr>
          ))}
          {list.length === 0 && (
            <tr><td colSpan={5} className="py-6 px-3 text-mut text-center">
              Walking the network… devices will appear as they respond.
            </td></tr>
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}
