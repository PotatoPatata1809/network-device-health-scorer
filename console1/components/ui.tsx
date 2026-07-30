"use client";
import { healthColor } from "@/lib/types";

export const Dot = ({ h }: { h: number }) => (
  <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle"
        style={{ background: h < 0 ? "#d8dee4" : healthColor(h) }} />
);

export const HealthBar = ({ h }: { h: number }) => (
  <span className="inline-flex items-center gap-2">
    <span className="inline-block w-[70px] h-[5px] rounded bg-line align-middle">
      <span className="block h-full rounded"
            style={{ width: `${Math.max(2, h)}%`, background: healthColor(h) }} />
    </span>
    <span className="tabular-nums">{Math.round(h)}</span>
  </span>
);

export const Label = ({ children }: { children: React.ReactNode }) => (
  <div className="text-[10px] text-mut uppercase tracking-wider mb-1.5">{children}</div>
);

export const Card = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-panel border border-line rounded-md p-3 mb-2 text-[12.5px] leading-relaxed">
    {children}
  </div>
);

export const Chip = ({ children }: { children: React.ReactNode }) => (
  <span className="inline-block bg-chip rounded px-2 py-0.5 text-[11px] mr-1.5 mb-1.5">{children}</span>
);
