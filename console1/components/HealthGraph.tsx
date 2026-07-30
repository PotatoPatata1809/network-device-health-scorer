"use client";
import { LineChart, Line, XAxis, YAxis, ReferenceLine, ReferenceArea,
         ResponsiveContainer, Tooltip } from "recharts";
import type { Device } from "@/lib/types";

export default function HealthGraph({ device }: { device: Device }) {
  const s = device.series ?? [];
  if (!s.length)
    return <div className="text-mut text-[12px] py-6">No history series in state file — regenerate with series enabled.</div>;
  const firstAlert = device.alert ? s.find((p) => p.alert)?.row : undefined;
  return (
    <div className="h-[150px] w-full">
      <ResponsiveContainer>
        <LineChart data={s} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
          <XAxis dataKey="row" tick={{ fontSize: 9, fill: "#57606a" }}
                 tickLine={false} axisLine={{ stroke: "#d0d7de" }} minTickGap={40} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#57606a" }}
                 tickLine={false} axisLine={{ stroke: "#d0d7de" }} />
          <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #d8dee4",
                                   fontSize: 11 }} labelStyle={{ color: "#7d8590" }} />
          <ReferenceLine y={20} stroke="#d0d7de" strokeDasharray="3 3"
            label={{ value: "critical", fontSize: 9, fill: "#57606a", position: "insideTopLeft" }} />
          {firstAlert != null && (
            <ReferenceArea x1={firstAlert} x2={s[s.length - 1].row}
                           fill="#cf222e" fillOpacity={0.06} />
          )}
          {firstAlert != null && (
            <ReferenceLine x={firstAlert} stroke="#cf222e" strokeDasharray="3 3"
              label={{ value: "first alert", fontSize: 9, fill: "#cf222e", position: "insideTopRight" }} />
          )}
          <Line type="monotone" dataKey="health" stroke="#1a7f37" strokeWidth={1.6} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
