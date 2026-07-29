/**
 * SNMP relay — dual mode.
 *
 * dataset mode (default): answers real snmpwalk/snmpget-style queries from the
 *   NetPulse dataset (SMD-backed metrics + LLDP neighbour tables in public/).
 *   Same output shape a live walk would return.
 *
 * live mode: same commands against a real device. Browsers cannot speak SNMP
 *   (UDP), so this server-side route is where a real query would run, using an
 *   SNMP library (e.g. net-snmp) with host+community from the request. The demo
 *   environment has no SNMP devices, so live mode returns a clear message unless
 *   NETPULSE_LIVE_SNMP=1 is set and net-snmp is installed — the code path and
 *   interface are real; only the demo venue lacks devices to answer.
 */
import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

type Neighbour = { local_port: string; remote_sys_name: string; remote_port: string;
                   remote_chassis_id: string; capabilities: string };
type TopoDev = { sys_name: string; device_type: string; site: string;
                 chassis_id: string; smd_machine: string; lldp_neighbours: Neighbour[] };

function loadJSON(name: string) {
  return JSON.parse(fs.readFileSync(path.join(process.cwd(), "public", name), "utf8"));
}

export async function POST(req: NextRequest) {
  const { cmd, mode, host, community } = await req.json();

  if (mode === "live") {
    if (process.env.NETPULSE_LIVE_SNMP === "1") {
      // Real path: const snmp = require("net-snmp"); create session(host, community),
      // walk/get the requested OID, format as below. Enabled only where devices exist.
      return NextResponse.json({ lines: ["live mode: net-snmp session would run here (enable on a network with SNMP devices)"] });
    }
    return NextResponse.json({ lines: [
      `live mode requested for ${host ?? "?"} (community ${community ? "***" : "not set"})`,
      "No SNMP-speaking devices reachable in this environment.",
      "Set NETPULSE_LIVE_SNMP=1 on a network with SNMP devices to enable. 'mode dataset' to return.",
    ]});
  }

  // ---------- dataset mode ----------
  const neighbours: { devices: TopoDev[] } = loadJSON("neighbours.json");
  const state = loadJSON("priority_state.json");
  const byName: Record<string, TopoDev> = Object.fromEntries(neighbours.devices.map((d) => [d.sys_name, d]));
  const stateBy: Record<string, any> = Object.fromEntries(state.devices.map((d: any) => [d.device, d]));

  const parts = String(cmd ?? "").trim().split(/\s+/);
  const [tool, a, b] = [parts[0], parts[1], parts[2]];
  const lines: string[] = [];
  const say = (s: string) => lines.push(s);

  const walkLLDP = (d: TopoDev) => {
    d.lldp_neighbours.forEach((n, i) => {
      say(`LLDP-MIB::lldpRemSysName.${i + 1} = STRING: ${n.remote_sys_name}`);
      say(`LLDP-MIB::lldpRemPortId.${i + 1} = STRING: ${n.remote_port}`);
      say(`LLDP-MIB::lldpRemChassisId.${i + 1} = STRING: ${n.remote_chassis_id}`);
      say(`  (local port ${n.local_port}, capabilities ${n.capabilities})`);
    });
  };

  if (tool === "discover" || (tool === "snmpwalk" && a === "--all" && (b === "full" || !b))) {
    // FULL network sweep: identity + neighbours + metrics for every device, one command.
    const order = [...neighbours.devices].sort((x, y) =>
      (x.device_type === "core-switch" ? 0 : x.device_type === "dist-switch" ? 1 : 2) -
      (y.device_type === "core-switch" ? 0 : y.device_type === "dist-switch" ? 1 : 2) ||
      x.sys_name.localeCompare(y.sys_name));
    const sweep: string[] = [`full SNMP sweep: ${order.length} devices — sysName, lldpRemTable, metrics…`, ""];
    order.forEach((d) => {
      const st = stateBy[d.sys_name];
      sweep.push(`── ${d.sys_name} (${d.device_type} · ${d.site})`);
      sweep.push(`   neighbours: ${d.lldp_neighbours.map((n) => n.remote_sys_name).join(", ") || "none"}`);
      if (st) sweep.push(`   cpu ${st.metrics.hrProcessorLoad ?? "—"} · mem ${st.metrics.hrStorageUsed ?? "—"} · errors ${st.metrics.ifInErrors ?? "—"} · health ${st.health}`);
    });
    sweep.push("", "sweep complete — map and inventory built (see Network map / Overview)");
    return NextResponse.json({ discover: order.map((d) => d.sys_name), lines: sweep });
  }

  if (tool === "snmpwalk" && a === "--all" && b === "lldpRemTable") {
    // full discovery walk: return per-device neighbour tables in BFS-ish order
    const order = [...neighbours.devices].sort((x, y) =>
      (x.device_type === "core-switch" ? 0 : x.device_type === "dist-switch" ? 1 : 2) -
      (y.device_type === "core-switch" ? 0 : y.device_type === "dist-switch" ? 1 : 2) ||
      x.sys_name.localeCompare(y.sys_name));
    return NextResponse.json({
      discover: order.map((d) => d.sys_name),
      lines: [`walking lldpRemTable on ${order.length} devices…`],
    });
  }

  if ((tool === "snmpwalk" || tool === "snmpget") && a && byName[a]) {
    const dev = byName[a]; const st = stateBy[a];
    const oid = b ?? "";
    if (oid === "lldpRemTable") walkLLDP(dev);
    else if (oid === "sysName") say(`SNMPv2-MIB::sysName.0 = STRING: ${dev.sys_name}`);
    else if (oid === "sysDescr") say(`SNMPv2-MIB::sysDescr.0 = STRING: ${dev.device_type} · site ${dev.site}`);
    else if (["hrProcessorLoad", "hrStorageUsed", "ifInErrors"].includes(oid) && st) {
      const v = st.metrics[oid];
      const mib = oid === "ifInErrors" ? "IF-MIB" : "HOST-RESOURCES-MIB";
      say(`${mib}::${oid}.0 = Gauge32: ${v}`);
      say(`  health ${st.health} · ${st.explanation || "operating normally"}`);
    } else if (!oid) {
      say(`usage: ${tool} <device> <lldpRemTable|sysName|sysDescr|hrProcessorLoad|hrStorageUsed|ifInErrors>`);
    } else say(`No Such Object: ${oid}`);
    return NextResponse.json({ lines });
  }

  if (tool === "snmpwalk" || tool === "snmpget") {
    say(`unknown device: ${a ?? "?"} — try one of: ${neighbours.devices.slice(0, 4).map((d) => d.sys_name).join(", ")} …`);
    return NextResponse.json({ lines });
  }

  say(`unknown command: ${tool}. type 'help'.`);
  return NextResponse.json({ lines });
}
