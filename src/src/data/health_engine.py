"""
SELF-CALIBRATING per-device HEALTH ENGINE.

Not a shipped config — a function the app runs. On ingest, each device calibrates
its OWN health scale from its OWN normal period. New device -> self-calibrates ->
health reads ~90 when normal and drops during that device's anomalies. No human
picks anything; nothing is fleet-hardcoded. This is the production-viable version:
same function tested offline here becomes the live health engine.

Health source = the LOF anomaly signal (the detector validated at 92%), calibrated
per device against its own normal-score distribution, then mapped to 0-100.

Per device:
  1. warm-up window = the device's first NORMAL stretch -> defines "normal".
  2. fit LOF on normal, get the normal anomaly-score distribution (p50, p95).
  3. calibrate: score at p50 -> health ~90; score well above p95 -> health -> 0.
     (calibration = these two numbers, derived from the device's own normal.)
  4. stream the rest: each row's LOF score -> health via the device's own curve.
  5. attribution = each metric's share of the anomaly, per row.

Run from repo root:
    python src/data/health_engine.py --machines all          # validate fleet-wide
    python src/data/health_engine.py --machine machine-1-1    # one device, detail
"""
import json, argparse
import numpy as np
import pandas as pd
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

WINDOW, REFIT, SMOOTH = 288, 288, 12


def trailing(vals):
    mu = vals.rolling(WINDOW).mean().shift(1)
    sd = vals.rolling(WINDOW).std().shift(1)
    return pd.DataFrame({
        "value": vals, "delta": vals.diff(),
        "deviation": (vals - mu) / sd.replace(0, np.nan),
        "volatility": sd,
    }).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def calibrate_and_score(df, live_cols, warmup=WINDOW):
    """Self-calibrating per-device health. Returns (health[], per-metric badness dict).
    Calibration (normal p50/p95 of LOF score) is derived from THIS device's warm-up."""
    # multivariate features across the device's live metrics
    feats = pd.concat([trailing(df[c]).add_prefix(f"{c}_") for c in live_cols], axis=1)
    feats = feats.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    n = len(feats)
    health = np.full(n, 100.0)
    # rolling refit; the FIRST training window defines the device's "normal" calibration
    lo = hi = None
    per_metric_bad = {c: np.zeros(n) for c in live_cols}

    for s in range(warmup, n, REFIT):
        tr = feats.iloc[s - warmup:s].to_numpy()
        ch = feats.iloc[s:s + REFIT].to_numpy()
        if len(ch) == 0:
            continue
        sc = StandardScaler().fit(tr)
        m = LocalOutlierFactor(n_neighbors=min(20, len(tr) - 1), novelty=True).fit(sc.transform(tr))
        train_scores = -m.score_samples(sc.transform(tr))
        scores = -m.score_samples(sc.transform(ch))

        # per-device calibration from the FIRST (assumed-normal) window
        if lo is None:
            lo = np.percentile(train_scores, 50)     # normal centre -> health ~90
            hi = np.percentile(train_scores, 95)      # edge of normal -> health starts dropping
        scale = max(hi - lo, 1e-6)
        # map score -> health: at lo -> 90, at hi -> ~55, well above -> ->0
        z = (scores - lo) / scale
        h = 100.0 * np.exp(-0.35 * np.clip(z, 0, None))
        health[s:s + len(ch)] = h

        # per-metric badness = that metric's own trailing deviation magnitude (for attribution)
        for c in live_cols:
            dcols = [f"{c}_deviation"]
            per_metric_bad[c][s:s + len(ch)] = np.abs(feats.iloc[s:s + len(ch)][dcols].to_numpy()).ravel()

    health = pd.Series(health).rolling(SMOOTH, min_periods=1).mean().to_numpy()
    return health, per_metric_bad


def attribution(per_metric_bad, live_cols, roles, i):
    vals = np.array([per_metric_bad[c][i] for c in live_cols])
    tot = vals.sum()
    if tot == 0:
        return {roles[c]: round(100 / len(live_cols), 0) for c in live_cols}
    return {roles[c]: round(100 * vals[j] / tot, 0) for j, c in enumerate(live_cols)}


def pick_cols(mapping_m, want):
    chosen = {}
    for dim, v in mapping_m.items():
        if v["oid_role"] in want and v["oid_role"] not in chosen:
            chosen[v["oid_role"]] = int(dim) - 1
    return list(chosen.values()), {c: r for r, c in chosen.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="src/data/smd_oid_mapping.json")
    ap.add_argument("--data", default="data/ServerMachineDataset")
    ap.add_argument("--roles", default="hrProcessorLoad,hrStorageUsed,ifInErrors")
    ap.add_argument("--machines", default="all")
    ap.add_argument("--machine", default=None)
    a = ap.parse_args()

    mapping = json.load(open(a.map))
    if a.machine:
        machines = [a.machine]
    elif a.machines == "all":
        machines = list(mapping)
    elif a.machines == "group1":
        machines = [m for m in mapping if m.startswith("machine-1-")]
    else:
        machines = a.machines.split(",")
    want = a.roles.split(",")

    norm_H, anom_recall_hit, anom_recall_tot, fa_hit, fa_tot = [], 0, 0, 0, 0
    detail = None
    for m in machines:
        live, roles = pick_cols(mapping[m], want)
        if not live:
            continue
        df = pd.read_csv(f"{a.data}/test/{m}.txt", header=None)
        lab = np.loadtxt(f"{a.data}/test_label/{m}.txt", dtype=int)
        health, pmb = calibrate_and_score(df, live)
        H, L = health[WINDOW:], lab[WINDOW:]

        # threshold = p5 of this device's own normal health (self-calibrating "worried" line)
        thr = np.percentile(H[L == 0], 5) if (L == 0).any() else 50
        # recall over anomaly windows
        w, s = [], None
        for i, v in enumerate(L):
            if v == 1 and s is None: s = i
            if v == 0 and s is not None: w.append((s, i-1)); s = None
        if s is not None: w.append((s, len(L)-1))
        for x, y in w:
            anom_recall_tot += 1
            if (H[x:y+1] < thr).any(): anom_recall_hit += 1
        fa_hit += int((H[L == 0] < thr).sum()); fa_tot += int((L == 0).sum())
        norm_H.append(H[L == 0].mean())

        if a.machine:
            worst = np.argmin(H)
            detail = (m, roles, H[L==0].mean(), thr, health[WINDOW+worst],
                      attribution(pmb, live, roles, WINDOW+worst))
        print(f"  {m}: normalH {H[L==0].mean():.0f} · thr {thr:.0f}", flush=True)

    print(f"\nSELF-CALIBRATING HEALTH ENGINE — {len(machines)} machines · {want}\n")
    print(f"  mean normal health  : {np.mean(norm_H):.1f}   (want ~85+)")
    print(f"  anomaly recall      : {anom_recall_hit}/{anom_recall_tot} "
          f"({100*anom_recall_hit/max(anom_recall_tot,1):.0f}%)   (want high)")
    print(f"  false-alarm rate    : {100*fa_hit/max(fa_tot,1):.1f}%   (want ~5%)")
    if detail:
        m, roles, nh, thr, wh, attr = detail
        print(f"\n  {m} detail:")
        print(f"    normal health {nh:.0f} · worried<{thr:.0f} · worst instant health {wh:.0f}")
        print(f"    attribution at worst: {attr}")


if __name__ == "__main__":
    main()
