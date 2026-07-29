"""
HEALTH FORMULATION BAKEOFF — don't pick the health formula by hand, measure it.

Tests several ways to turn "how far from normal" into a 0-100 Health number, and
reports which one best SEPARATES normal rows from labelled-anomaly rows on real
SMD data. Same spirit as the detector bakeoff: the data picks, you can explain
the result ("we tested N health formulations against ground truth").

Formulations (each returns per-row badness 0..1; Health = 100*(1-badness)):

  A  deviation        : |value - rolling_mean| / rolling_std   (z-score, classic)
  B  percentile       : rank of value vs the trailing window   (no bell assumption)
  C  deviation+trend  : worst of {deviation, |delta|, drift, volatility} z-scores
                        (the 4 trailing features that took detection 83->96%)
  D  headroom         : distance to the metric's ceiling (1.0 for SMD-normalised)
  E  B+D blend        : percentile for spiky/unbounded, headroom for bounded,
                        chosen per-metric by the OID role (errors->B, cpu/mem->D)

All trailing-only. Composite across a device's metrics = WORST metric leads
(honest: one dying metric = unhealthy), with attribution = each metric's share.
Separation = mean Health(normal) - mean Health(anomaly). Higher = better.
"""

import json, argparse
import numpy as np
import pandas as pd
from scipy.stats import rankdata

WINDOW = 288
SMOOTH = 12
EPS = 1e-9


def _roll(vals):
    mu = vals.rolling(WINDOW).mean().shift(1)
    sd = vals.rolling(WINDOW).std().shift(1)
    return mu, sd


def badness_A(vals, role):
    mu, sd = _roll(vals)
    z = (vals - mu).abs() / sd.replace(0, np.nan)
    return (z.fillna(0) / 6.0).clip(0, 1)          # 6σ -> fully bad


def badness_B(vals, role):
    # trailing percentile: fraction of last WINDOW below current value
    out = np.zeros(len(vals))
    v = vals.to_numpy()
    for i in range(WINDOW, len(v)):
        w = v[i - WINDOW:i]
        out[i] = (w < v[i]).mean()                 # 0..1, high = unusually high
    # only the upper tail is "bad" for most health metrics
    return pd.Series(np.clip((out - 0.5) * 2, 0, 1), index=vals.index)


def badness_C(vals, role):
    mu, sd = _roll(vals)
    sd = sd.replace(0, np.nan)
    dev = ((vals - mu).abs() / sd).fillna(0)
    delta = (vals.diff().abs() / sd).fillna(0)
    drift = ((vals.rolling(SMOOTH).mean() - mu).abs() / sd).fillna(0)
    vol = (sd / sd.rolling(WINDOW).median().shift(1)).fillna(1)
    z = pd.concat([dev, delta, drift, vol], axis=1).max(axis=1)   # worst of four
    return (z / 6.0).clip(0, 1)


def badness_D(vals, role, ceiling=1.0):
    # headroom to ceiling; SMD is min-max normalised so ceiling ~1.0
    return (vals / ceiling).clip(0, 1)             # closer to ceiling = worse


def badness_E(vals, role):
    # per-metric: spiky/unbounded counters -> percentile; bounded gauges -> headroom
    if role in ("ifInErrors", "ifInOctets"):
        return badness_B(vals, role)
    if role in ("hrProcessorLoad", "hrStorageUsed"):
        return badness_D(vals, role)
    return badness_A(vals, role)                    # fallback


FORMS = {"A_deviation": badness_A, "B_percentile": badness_B,
         "C_dev+trend": badness_C, "D_headroom": badness_D, "E_B+D_blend": badness_E}


def composite(df, live_cols, roles, form_fn):
    """Worst-metric-leads composite + attribution, smoothed."""
    bad = {c: form_fn(df[c], roles[c]).to_numpy() for c in live_cols}
    B = np.vstack([bad[c] for c in live_cols]).T[WINDOW:]     # rows x metrics
    combined = B.max(axis=1)                                   # worst leads
    combined = pd.Series(combined).rolling(SMOOTH, min_periods=1).mean().to_numpy()
    health = np.clip(100 * (1 - combined), 0, 100)
    # attribution = share of badness at each row
    tot = B.sum(axis=1); tot[tot == 0] = 1
    attr = {c: 100 * B[:, j] / tot for j, c in enumerate(live_cols)}
    return health, attr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="src/data/smd_oid_mapping.json")
    ap.add_argument("--data", default="data/ServerMachineDataset")
    ap.add_argument("--roles", default="hrProcessorLoad,hrStorageUsed,ifInErrors")
    ap.add_argument("--machines", default="all",
                    help="comma list or 'all' or 'group1'")
    args = ap.parse_args()

    mapping = json.load(open(args.map))
    if args.machines == "all":
        machines = list(mapping)
    elif args.machines == "group1":
        machines = [m for m in mapping if m.startswith("machine-1-")]
    else:
        machines = args.machines.split(",")

    want = args.roles.split(",")
    agg = {f: {"norm": [], "anom": []} for f in FORMS}

    for m in machines:
        chosen = {}
        for dim, v in mapping[m].items():
            if v["oid_role"] in want and v["oid_role"] not in chosen:
                chosen[v["oid_role"]] = int(dim) - 1
        if not chosen:
            continue
        live = list(chosen.values())
        roles = {col: role for role, col in chosen.items()}
        df = pd.read_csv(f"{args.data}/test/{m}.txt", header=None)
        lab = np.loadtxt(f"{args.data}/test_label/{m}.txt", dtype=int)[WINDOW:]

        for f, fn in FORMS.items():
            health, _ = composite(df, live, roles, fn)
            agg[f]["norm"].append(health[lab == 0])
            agg[f]["anom"].append(health[lab == 1])

    print(f"HEALTH FORMULATION BAKEOFF — {len(machines)} machines · metrics {want}\n")
    print(f"{'formulation':<16}{'health(normal)':>15}{'health(anom)':>14}{'separation':>12}")
    print("-" * 57)
    results = []
    for f in FORMS:
        norm = np.concatenate(agg[f]["norm"]); anom = np.concatenate(agg[f]["anom"])
        sep = norm.mean() - anom.mean()
        results.append((sep, f, norm.mean(), anom.mean()))
        print(f"{f:<16}{norm.mean():>15.1f}{anom.mean():>14.1f}{sep:>12.1f}")
    print("-" * 57)
    best = max(results)
    print(f"\nBEST SEPARATION: {best[1]}  "
          f"(normal {best[2]:.0f} vs anomaly {best[3]:.0f}, gap {best[0]:.1f})")
    print("\nNote: we want HIGH normal health (~85+) AND large separation.")
    print("A formula with big separation but low normal health (e.g. normal=40)")
    print("is miscalibrated — healthy devices must read healthy.")


if __name__ == "__main__":
    main()
