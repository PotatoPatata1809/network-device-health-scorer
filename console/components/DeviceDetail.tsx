"use client";
import type { Device } from "@/lib/types";
import { ROLE_LABEL, fcText, healthColor } from "@/lib/types";
import { Label, Card, Chip } from "./ui";
import HealthGraph from "./HealthGraph";
import { REMEDY } from "@/lib/remedy";


export default function DeviceDetail({ device }: { device: Device }) {
  const attr = Object.entries(device.attribution).sort((a, b) => b[1] - a[1]);
  const shown = device.downstream.slice(0, 8);
  const more = device.downstream.length - shown.length;
  return (
    <div>
      <div className="mb-4">
        <Label>Selected device</Label>
        <div className="text-[26px] font-semibold leading-tight">{device.device}</div>
        <div className="text-mut text-[12px]">{device.type} · {device.site}</div>
      </div>

      <div className="mb-4">
        <Label>Why this score</Label>
        <Card>{device.explanation || "—"}</Card>
      </div>

      <div className="mb-4">
        <Label>Health — history</Label>
        <HealthGraph device={device} />
      </div>

      <div className="mb-4">
        <Label>Current readings</Label>
        <Card>
          <div className="flex gap-5">
            {Object.entries(device.metrics).map(([role, v]) => (
              <div key={role}>
                <div className="text-[10.5px] text-mut">{ROLE_LABEL[role] ?? role}</div>
                <div className="text-[15px] font-semibold tabular-nums">{Number(v).toFixed(3)}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mb-4">
        <Label>Forecast</Label>
        <Card>
          {fcText(device.forecast)}
          {device.forecast?.confidence != null && device.forecast.status === "degrading" && (
            <span className="text-mut"> · confidence {Math.round(device.forecast.confidence * 100)}%</span>
          )}
        </Card>
      </div>

      <div className="mb-4">
        <Label>Blast radius — {device.impact} devices offline if this fails</Label>
        <Card>
          {device.impact === 0 ? <span className="text-mut">No downstream devices.</span> : (
            <>
              {shown.map((d) => <Chip key={d}>{d}</Chip>)}
              {more > 0 && <Chip>+{more} more</Chip>}
            </>
          )}
        </Card>
      </div>

      <div className="mb-4">
        <Label>Attribution</Label>
        <Card>
          {attr.map(([role, pct]) => (
            <div key={role} className="flex items-center gap-2 mb-1.5 last:mb-0">
              <span className="w-14 text-[11px] text-mut">{ROLE_LABEL[role] ?? role}</span>
              <span className="flex-1 h-[5px] bg-line rounded">
                <span className="block h-full rounded"
                      style={{ width: `${pct}%`, background: healthColor(100 - pct) }} />
              </span>
              <span className="w-8 text-right text-[11px] tabular-nums">{pct}%</span>
            </div>
          ))}
        </Card>
      </div>

      <div>
        <Label>Recommended action</Label>
        <Card>{(device.primary_driver && REMEDY[device.primary_driver]) ||
               "No action required — operating within normal parameters."}</Card>
      </div>
    </div>
  );
}
