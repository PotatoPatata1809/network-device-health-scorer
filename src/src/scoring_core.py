"""
NetPulse SCORING CORE — assemble every signal into the ranked priority list.

This is the assembly step. Each feature already built writes to a shared per-device
record; the scoring core reads them all and computes the one number that ranks the
fleet:

    PRIORITY = health_factor  x  urgency_factor  x  impact_factor

Why multiply (not add)? A nearly-dead device with nothing behind it should stay low;
a mildly-degraded CORE switch with 13 devices downstream should jump to the top.
Multiplication lets any one signal dominate — addition would let a big impact hide a
perfect health score. (The brief's weighted-sum formula is kept as a BASELINE column
for comparison, never as the product.)

The three factors (chosen with Aakash):
  health_factor  = (100 - health) / 100      # 0 = perfect, 1 = critical. "how bad"
  urgency_factor = sooner-to-critical scores sharply higher (4h >> 40h). "how soon"
  impact_factor  = raw downstream count (13 devices = 13). "what breaks with it"

  priority = health_factor * urgency_factor * (1 + impact_factor)
  (1 + impact so a leaf device isn't zeroed out; impact AMPLIFIES, doesn't gate.)

Also emits the brief's weighted-sum baseline beside it, and the incident correlation
(suppressed storm) over the whole fleet.

Output: priority_state.json — the exact per-device state the console consumes.
"""
import json, argparse
import numpy as np
import pandas as pd

import health_score as HS
import forecast as FC
import build_topology as TP
import incident as INC
try:
    import explain as EX
    HAVE_EXPLAIN = True
except Exception:
    HAVE_EXPLAIN = False


def urgency_factor(fc: dict) -> float:
    """Sooner-to-critical -> sharply higher urgency. Uses forecast status + eta."""
    s = fc.get("status")
    if s == "critical_now":
        return 1.0
    if s == "degrading" and fc.get("eta_hours") is not None:
        eta = fc["eta_hours"]
        # sharp decay: 1h->~0.95, 4h->~0.8, 12h->~0.5, 40h->~0.2, 72h->~0.1
        return float(np.clip(np.exp(-eta / 18.0), 0.05, 1.0))
    if s in ("declining_unclear", "declining_slow"):
        return 0.3          # declining but no clean ETA -> mild urgency
    # stable / improving / insufficient -> low but nonzero (health still ranks it)
    return 0.1


def weighted_baseline(metrics: dict) -> float:
    """The brief's weighted-sum formula, kept as a comparison column (NOT the product).
    score = 0.4*cpu + 0.3*mem + 0.2*err + 0.1*(1-uptimeproxy). Higher = worse."""
    cpu = metrics.get("hrProcessorLoad", 0)
    mem = metrics.get("hrStorageUsed", 0)
    err = metrics.get("ifInErrors", 0)
    return round(100 * (0.4 * cpu + 0.3 * mem + 0.2 * err), 1)


def score_fleet(topo, mapping, data_dir, roles_want, sample_min=5):
    devices = topo["devices"]
    records = {}
    alerting = set()
    evidence = {}

    for d in devices:
        dev, m = d["id"], d["smd_machine"]
        cols = {}
        for dim, v in mapping[m].items():
            if v["oid_role"] in roles_want and v["oid_role"] not in cols:
                cols[v["oid_role"]] = int(dim) - 1
        live = list(cols.values()); roles = {c: r for r, c in cols.items()}
        df = pd.read_csv(f"{data_dir}/test/{m}.txt", header=None)

        rec = HS.score_device(df, live, roles, dev)          # health, alert, attribution, series, metrics

        # forecast on the PRIMARY DRIVER metric's headroom-health trajectory
        driver = max(rec["attribution"], key=rec["attribution"].get) if rec["attribution"] else None
        if driver and driver in roles.values():
            dcol = [c for c, r in roles.items() if r == driver][0]
            mh = 100 * (1 - np.clip(df[dcol].to_numpy(), 0, 1))
            mh = pd.Series(mh).rolling(12, min_periods=1).mean().to_numpy()
            fc = FC.forecast(mh[-300:], sample_min)
        else:
            fc = {"status": "insufficient_data", "eta_hours": None, "slope_per_hr": None, "confidence": None}

        # impact from topology
        impact, downstream = TP.blast_radius(topo, dev)

        # factors
        hf = (100 - rec["health"]) / 100.0
        uf = urgency_factor(fc)
        priority = round(100 * hf * uf * (1 + impact), 2)

        # explanation
        expl = (EX.explain(rec["health"], rec["attribution"], rec["alert"])
                if HAVE_EXPLAIN else {"explanation": "", "primary_driver": driver})

        records[dev] = {
            "device": dev, "type": d["type"], "site": d["site"],
            "health": rec["health"], "alert": rec["alert"],
            "attribution": rec["attribution"], "metrics": rec["metrics"],
            "forecast": fc,
            "impact": impact, "downstream": downstream,
            "priority": priority,
            "weighted_baseline": weighted_baseline(rec["metrics"]),
            "explanation": expl["explanation"], "primary_driver": expl["primary_driver"],
        }
        if rec["alert"]:
            alerting.add(dev)
            # independent evidence = device has its own health degradation (not just downstream)
            evidence[dev] = rec["health"] < 75

    # fleet-level incident correlation (suppress storms, keep independent faults)
    correlation = INC.correlate_alerts(topo, alerting, independent_evidence=evidence)
    return records, correlation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topo", default="src/topology/topology.json")
    ap.add_argument("--map", default="src/data/smd_oid_mapping.json")
    ap.add_argument("--data", default="data/ServerMachineDataset")
    ap.add_argument("--roles", default="hrProcessorLoad,hrStorageUsed,ifInErrors")
    ap.add_argument("--out", default="priority_state.json")
    a = ap.parse_args()
    topo = json.load(open(a.topo)); mapping = json.load(open(a.map))
    records, correlation = score_fleet(topo, mapping, a.data, a.roles.split(","))

    state = {"devices": list(records.values()), "correlation": correlation}
    json.dump(state, open(a.out, "w"), indent=1)

    ranked = sorted(records.values(), key=lambda r: -r["priority"])
    print("PRIORITY ACTION LIST (ranked by Health x Urgency x Impact)\n")
    print(f"{'device':<13}{'type':<14}{'health':>7}{'forecast':>18}{'impact':>7}{'priority':>9}{'weighted':>9}")
    print("-" * 77)
    for r in ranked[:12]:
        fc = FC.human(r["forecast"])
        print(f"{r['device']:<13}{r['type']:<14}{r['health']:>7.0f}{fc:>18}{r['impact']:>7}"
              f"{r['priority']:>9.1f}{r['weighted_baseline']:>9.1f}")
    print("-" * 77)
    print(f"\nincidents: {correlation['incident_count']} "
          f"(raw alerts {correlation['raw_alert_count']}, suppressed {len(correlation['suppressed'])}, "
          f"linked independent faults {len(correlation['linked_subincidents'])})")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
