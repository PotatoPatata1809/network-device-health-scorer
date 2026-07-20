# REMEDIES — symptom → likely cause → recommended action

NetPulse does not stop at a score. Every flagged device resolves to a plain-language
remedy shown in the **Recommended Action** panel of the console.

This file is the lookup table behind that panel. Each row is keyed by a **detector
signature** — the shape of the anomaly in the metric stream, not a fixed threshold —
so the same rule applies to a device idling at 15% CPU and one that normally sits at 70%.

**Matching order:** rules are evaluated top to bottom; the first signature that matches
wins. R01–R03 are the three failure modes named in our problem framing and are checked
first. If nothing matches, the console falls back to `R99`.

---

## Lookup table

| ID | Symptom (detector signature) | Metric / OID | Likely cause | Recommended action |
|----|------------------------------|--------------|--------------|--------------------|
| **R01** | Memory rising monotonically over 6h+, no plateau, no matching traffic rise | `hrStorageUsed` | Memory leak in a process or a control-plane task; buffers not being freed | Schedule failover to the peer device, then restart the affected process. Verify STP convergence after switchover. Capture the process table before restarting — the leak is lost on reboot. |
| **R02** | Interface error count climbing steadily while the link stays UP | `ifInErrors` | Failing optic/SFP, damaged or dirty fibre, duplex mismatch, cable near its length limit | Check optical light levels and the interface error counters at both ends. Reseat or replace the SFP. If errors are one-directional, suspect the far-end optic first. |
| **R03** | Uptime resets repeatedly; every poll still reports the device as UP | `sysUpTime` | Reboot loop — power instability, failing PSU, thermal shutdown, or a crashing supervisor | Pull the crash/reboot log and the environment sensors. Check PSU redundancy and inlet temperature. Do not clear the log before capture; the reboot reason is the only evidence. |
| **R04** | CPU steps up abruptly and holds at the new level | `hrProcessorLoad` | Routing churn, a broadcast/multicast storm, or a control-plane process spinning | Identify the top process by CPU. Check for a route flap or a loop on the access tier. Apply control-plane policing if the source is broadcast traffic. |
| **R05** | CPU oscillating with a period of minutes, never settling | `hrProcessorLoad` | Route flapping between two paths, or an unstable neighbour adjacency | Check neighbour adjacency and interface flap counters. Damp the flapping link or shut it administratively until the far end is repaired. |
| **R06** | Traffic volume collapses to near zero, link still UP | `ifInOctets` | Upstream path failure, an ACL or policy change, or a half-dead link passing keepalives only | Confirm whether the drop is one-directional. Check for a recent config change on this device and its parent. Test end-to-end reachability, not just link state. |
| **R07** | Traffic sustained near line rate for an extended period | `ifInOctets` | Genuine saturation, a backup or replication job, or a traffic loop | Identify the top talkers. If the volume is a scheduled job, move it off-peak. If it is unexplained and symmetrical, check for a bridging loop. |
| **R08** | Metric variance collapses — the value freezes and stops moving | any | A stuck SNMP agent or counter, not a healthy device | Re-poll the device directly. Restart the SNMP agent if the counter is frozen while the device is otherwise responsive. A frozen counter reads as "healthy" to every threshold-based tool. |
| **R09** | Device deviates sharply from same-role, same-site peers while its own trend looks flat | any (peer comparison) | Config drift, a hardware fault, or a firmware version mismatch | Diff this device's running config against a healthy sibling. Compare firmware versions across the peer group. A device can be stable and still be the odd one out. |
| **R10** | Parent device degrades and multiple children flag within the same window | topology + any | One upstream fault, not many independent faults | Treat as a single incident on the parent. Child alerts are suppressed and rolled into one grouped incident. Do not dispatch on the children until the parent is cleared. |
| **R11** | An interface transitions to DOWN while its peers stay UP | `ifOperStatus` | Cable fault, far-end shutdown, or a port hardware failure | Check the far-end port state and the physical cable. Confirm whether the port was administratively shut before treating it as a fault. |
| **R99** | Anomaly detected, no signature matched | any | Unclassified deviation from this device's learned baseline | Review the per-metric drill-down for this device and compare against its peer group. Log the pattern — unmatched signatures are the input to the next rule added here. |

---

## Design notes

**Why signatures and not thresholds.** A rule like "alert if CPU > 80%" is wrong on both
sides: it is silent on a device whose normal is 15% and screaming on one whose normal is 78%.
Every signature above describes a *shape* — rising, oscillating, collapsing, stepping — which
is what the detector actually produces. The same rule therefore holds across all 20 devices
without per-device tuning.

**Why R10 is different.** R01 through R09 describe one device. R10 is the only rule that reads
the topology graph, and it exists because an operator facing 15 simultaneous alerts has a worse
problem than one facing a single alert. It is the remedy that turns an alert storm into an incident.

**Honest boundary.** These remedies are drawn from standard network operations practice, not
learned from our dataset. NAB gives us labelled *anomaly windows*, not labelled *root causes* —
no public dataset ships those. So the mapping from signature to cause is expert-authored and we
state that openly rather than implying the model diagnoses causes it was never trained to diagnose.
What is validated is the detection; what is engineered is the remedy.

**Extending this file.** Add a row, give it the next `Rnn` id, and place it above `R99`.
The console reads this table by id — no code change is needed to add a remedy.
