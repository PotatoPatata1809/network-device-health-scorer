"use client";
import type { Correlation, Device } from "@/lib/types";
import { Label, Chip } from "./ui";
import { REMEDY } from "@/lib/remedy";

export default function IncidentsPanel({
  c, devices, onOpenDevice,
}: { c: Correlation; devices: Device[]; onOpenDevice: (d: string) => void }) {
  if (!c) return null;
  const byName = Object.fromEntries(devices.map((d) => [d.device, d]));
  const ranked = [...c.incidents].sort((a, b) => {
    const pa = byName[a.root]?.priority ?? 0, pb = byName[b.root]?.priority ?? 0;
    return pb - pa;
  });
  const collapsed = c.raw_alert_count - c.incident_count;
  return (
    <div className="max-w-3xl">
      <Label>Incidents — what to do, in order</Label>
      <div className="text-[13px] mb-4">
        <b>{c.raw_alert_count}</b> alert{c.raw_alert_count === 1 ? "" : "s"} →{" "}
        <b>{c.incident_count}</b> incident{c.incident_count === 1 ? "" : "s"}
        {collapsed > 0 && <span className="text-mut"> · {collapsed} downstream alarms grouped under their root cause</span>}
      </div>
      {ranked.length === 0 && <div className="text-mut text-[13px]">No active incidents.</div>}
      {ranked.map((inc, i) => {
        const dev = byName[inc.root];
        const action = (dev?.primary_driver && REMEDY[dev.primary_driver]) ||
                       "Investigate the device — no automatic action suggested.";
        return (
          <button key={inc.root} onClick={() => onOpenDevice(inc.root)}
                  className="block w-full text-left bg-panel border border-line rounded-md px-4 py-3 mb-3 text-[13px] hover:bg-sel/40">
            <div className="flex items-baseline gap-2">
              <span className="text-mut tabular-nums">{i + 1}.</span>
              <span className="font-semibold text-red text-[14px]">{inc.root}</span>
              <span className="text-mut text-[12px]">{inc.type ?? "device"}</span>
              {dev && <span className="ml-auto text-[12px] text-mut">health {Math.round(dev.health)}</span>}
            </div>
            <div className="mt-1.5"><b>Do:</b> {action}</div>
            {inc.explains_n > 0 && (
              <div className="text-mut mt-1.5 text-[12.5px]">
                {inc.explains_n} downstream device{inc.explains_n === 1 ? "" : "s"} will recover once this is fixed:
                {" "}{inc.explained_children.slice(0, 8).map((f) => <Chip key={f}>{f}</Chip>)}
                {inc.explained_children.length > 8 && <Chip>+{inc.explained_children.length - 8} more</Chip>}
              </div>
            )}
            {inc.linked_independent_faults.length > 0 && (
              <div className="mt-1.5 text-amber text-[12.5px]">
                ⚠ Also check separately (own fault, won&apos;t recover on its own):{" "}
                {inc.linked_independent_faults.map((f) => <Chip key={f}>{f}</Chip>)}
              </div>
            )}
            <div className="text-mut text-[11px] mt-1.5">Click to open this device →</div>
          </button>
        );
      })}
    </div>
  );
}
