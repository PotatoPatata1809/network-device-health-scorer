export type Forecast = {
  status: string;
  eta_hours: number | null;
  slope_per_hr: number | null;
  confidence: number | null;
};

export type Device = {
  device: string;
  type: string;
  site: string;
  health: number;
  alert: boolean;
  attribution: Record<string, number>;
  metrics: Record<string, number>;
  forecast: Forecast;
  impact: number;
  downstream: string[];
  priority: number;
  weighted_baseline: number;
  explanation: string;
  primary_driver: string | null;
  series?: { row: number; health: number; alert: boolean }[];
};

export type Incident = {
  root: string;
  type: string | null;
  explains_n: number;
  explained_children: string[];
  blast_radius: number;
  linked_independent_faults: string[];
};

export type Correlation = {
  incidents: Incident[];
  suppressed: string[];
  linked_subincidents?: string[];
  raw_alert_count: number;
  incident_count: number;
};

export type State = { devices: Device[]; correlation: Correlation };

export type TopoDevice = {
  id: string; type: string; site: string;
  parent: string | null; children: string[];
};

export type DemoFrame = {
  t: number;
  updates: Record<string, Partial<Device>>;
  correlation?: Correlation;
};

export const ROLE_LABEL: Record<string, string> = {
  hrProcessorLoad: "CPU", hrStorageUsed: "Memory", ifInErrors: "Errors",
  ifInOctets: "Traffic", sysUpTime: "Uptime",
};

export const healthColor = (h: number) =>
  h < 45 ? "#cf222e" : h < 75 ? "#9a6700" : "#1a7f37";

export const fcText = (f: Forecast) => {
  if (!f) return "—";
  if (f.status === "degrading" && f.eta_hours != null) return `Fails in ~${f.eta_hours}h`;
  const map: Record<string, string> = {
    critical_now: "Failing now", improving: "Recovering", stable: "Stable",
    declining_unclear: "Declining", declining_slow: "Slowly declining",
    insufficient_data: "—",
  };
  return map[f.status] ?? f.status;
};
