"""
Generate the two data files the NetPulse console needs, from the REAL backend:

1. priority_state.json WITH per-device health series (downsampled ~200 points) for
   the click-through graph. Same scoring core, just keeps a compact series.

2. demo_sequence.json — the LIVE DEMO frames: a real memory leak injected on
   core-sw-01 (injector, ramp_samples=600, realism 0.5), scored frame-by-frame:
   health falls, forecast ETA shrinks, priority climbs; when health crosses the
   alert line the downstream storm fires and correlate_alerts() collapses it to one
   incident. Every frame is computed from the injected data — nothing hand-animated.

Run from repo root:
  PYTHONPATH=src:src/data:src/topology python src/make_console_data.py
Then copy the two JSONs into console/public/.
"""
import json
import numpy as np
import pandas as pd

import health_score as HS
import forecast as FC
import build_topology as TP
import incident as INC
import scoring_core as SC
import injector as INJ
try:
    import explain as EX
except Exception:
    EX = None

TOPO = "src/topology/topology.json"
MAP = "src/data/smd_oid_mapping.json"
DATA = "data/ServerMachineDataset"
ROLES = ["hrProcessorLoad", "hrStorageUsed", "ifInErrors"]
SERIES_POINTS = 200
DEMO_DEVICE = "core-sw-01"
N_FRAMES = 110


def downsample(series, n=SERIES_POINTS):
    if len(series) <= n:
        return series
    idx = np.linspace(0, len(series) - 1, n).astype(int)
    return [series[i] for i in idx]


def main():
    topo = json.load(open(TOPO))
    mapping = json.load(open(MAP))

    # ---------- 1. state with series ----------
    records, correlation = SC.score_fleet(topo, mapping, DATA, ROLES)
    # score_fleet dropped series; recompute compact series per device
    for d in topo["devices"]:
        dev, m = d["id"], d["smd_machine"]
        cols = {}
        for dim, v in mapping[m].items():
            if v["oid_role"] in ROLES and v["oid_role"] not in cols:
                cols[v["oid_role"]] = int(dim) - 1
        live = list(cols.values()); roles = {c: r for r, c in cols.items()}
        df = pd.read_csv(f"{DATA}/test/{m}.txt", header=None)
        rec = HS.score_device(df, live, roles, dev)
        records[dev]["series"] = downsample(rec["series"])
        print(f"  series {dev}", flush=True)

    state = {"devices": list(records.values()), "correlation": correlation}
    json.dump(state, open("priority_state.json", "w"))
    print("wrote priority_state.json (with series)")

    # ---------- 2. demo sequences (three scenarios, three devices) ----------
    def gen_scenario(dev_id, scenario, role, realism, ramp, n_frames, pre=80, post=60):
        d0 = next(d for d in topo["devices"] if d["id"] == dev_id)
        m = d0["smd_machine"]
        cols = {}
        for dim, v in mapping[m].items():
            if v["oid_role"] in ROLES and v["oid_role"] not in cols:
                cols[v["oid_role"]] = int(dim) - 1
        col = cols[role]
        df = pd.read_csv(f"{DATA}/test/{m}.txt", header=None)
        orig = df[col].to_numpy()
        onset = int(len(df) * 0.5)
        mod = INJ.inject(orig, scenario, onset_frac=0.5, realism=realism, ramp_samples=ramp)
        span = ramp
        # health for the injected metric: headroom against a ceiling from NORMAL history
        if role == "ifInErrors":
            p95 = np.percentile(orig, 95)
            ceil = 3 * p95 if p95 > 1e-6 else max(orig.max(), 1e-6)
        else:
            ceil = 1.0
        mh = 100 * (1 - np.clip(mod / ceil, 0, 1))
        mh = pd.Series(mh).rolling(12, min_periods=1).mean().to_numpy()

        impact, downstream = TP.blast_radius(topo, dev_id)
        base = records[dev_id]
        rows = np.linspace(onset - pre, min(len(mh) - 1, onset + span + post), n_frames).astype(int)
        frames = [{"t": 0, "updates": {}}]
        stormed = False
        role_attr = {role: 85, **{r: 8 for r in base["attribution"] if r != role}}
        for t, i in enumerate(rows, start=1):
            h = float(mh[i])
            fc = FC.forecast(mh[max(0, i - 150):i])
            hf = (100 - h) / 100.0
            uf = SC.urgency_factor(fc)
            priority = round(100 * hf * uf * (1 + impact), 1)
            alert = h < 80 or fc["status"] in ("degrading", "critical_now")
            attribution = role_attr if h < 80 else base["attribution"]
            expl = (EX.explain(h, attribution, alert)["explanation"] if EX else "")
            frame = {"t": t, "updates": {dev_id: {
                "health": round(h, 1), "alert": bool(alert), "forecast": fc,
                "priority": priority, "attribution": attribution, "explanation": expl}}}
            if impact > 0 and h < 45:
                stormed = True
            if stormed:
                for c in downstream:
                    frame["updates"][c] = {"alert": True}
                frame["correlation"] = INC.correlate_alerts(
                    topo, set(downstream) | {dev_id}, independent_evidence={dev_id: True})
            frames.append(frame)
        return {"frames": frames}

    json.dump(gen_scenario("core-sw-01", "memory_leak", "hrStorageUsed", 0.5, 600, 110),
              open("demo_leak.json", "w"))
    print("wrote demo_leak.json (memory leak on core-sw-01)")
    json.dump(gen_scenario("acc-sw-01", "error_creep", "ifInErrors", 0.6, 400, 90),
              open("demo_creep.json", "w"))
    print("wrote demo_creep.json (error creep on acc-sw-01)")
    json.dump(gen_scenario("fw-01", "cpu_spike", "hrProcessorLoad", 0.7, 90, 70, pre=30, post=50),
              open("demo_spike.json", "w"))
    print("wrote demo_spike.json (cpu spike on fw-01)")


if __name__ == "__main__":
    main()
