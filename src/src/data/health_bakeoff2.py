"""
HEALTH FORMULATION BAKEOFF v2 — measure what actually matters, not averages.

v1 used mean-health-during-anomaly, which is misleading: it punishes a formula for
correctly showing a device as still-mostly-fine early in a gradual leak. An
operator doesn't act on averages — they act when health crosses a worrying line.

v2 measures three operator-real things per formulation:

  1. DETECTION RECALL on the health signal: for each labelled anomaly window, does
     health drop below a "worried" threshold at any point in it? (caught / total)
  2. FALSE-ALARM RATE: fraction of NORMAL rows where health is below the threshold.
  3. NORMAL HEALTH: mean health on normal rows (must read healthy, ~85+).

The threshold is derived per formulation from the NORMAL distribution (p5 of normal
health) — "worried" = worse than 95% of this fleet's healthy readings. Self-
calibrating and explainable: the healthy data sets the line, we don't hand-pick it.

Good formula = high recall, low false-alarm, high normal health, all at once.

Run from repo root:
    python src/data/health_bakeoff2.py --machines all
"""

import json, argparse
import numpy as np
import pandas as pd

WINDOW, SMOOTH = 288, 12


# ----------------------------------------------------------- badness formulas --
def _roll(vals):
    mu = vals.rolling(WINDOW).mean().shift(1)
    sd = vals.rolling(WINDOW).std().shift(1)
    return mu, sd


def badness_A(vals, role):
    """deviation: |value - mean| / std  (z-score)."""
    mu, sd = _roll(vals)
    z = (vals - mu).abs() / sd.replace(0, np.nan)
    return (z.fillna(0) / 6.0).clip(0, 1)


def badness_B(vals, role):
    """trailing percentile: how high is value vs its own recent window."""
    out = np.zeros(len(vals))
    v = vals.to_numpy()
    for i in range(WINDOW, len(v)):
        w = v[i - WINDOW:i]
        out[i] = (w < v[i]).mean()
    return pd.Series(np.clip((out - 0.5) * 2, 0, 1), index=vals.index)


def badness_C(vals, role):
    """deviation + trend: worst of {deviation, |delta|, drift, volatility}."""
    mu, sd = _roll(vals)
    sd = sd.replace(0, np.nan)
    dev = ((vals - mu).abs() / sd).fillna(0)
    delta = (vals.diff().abs() / sd).fillna(0)
    drift = ((vals.rolling(SMOOTH).mean() - mu).abs() / sd).fillna(0)
    vol = (sd / sd.rolling(WINDOW).median().shift(1)).fillna(1)
    z = pd.concat([dev, delta, drift, vol], axis=1).max(axis=1)
    return (z / 6.0).clip(0, 1)


def badness_D(vals, role, ceiling=1.0):
    """headroom: how close to the metric's ceiling (SMD normalised ~1.0)."""
    return (vals / ceiling).clip(0, 1)


def badness_E(vals, role):
    """blend: percentile for spiky/unbounded counters, headroom for bounded gauges."""
    if role in ("ifInErrors", "ifInOctets"):
        return badness_B(vals, role)
    if role in ("hrProcessorLoad", "hrStorageUsed"):
        return badness_D(vals, role)
    return badness_A(vals, role)


FORMS = {"A_deviation": badness_A, "B_percentile": badness_B,
         "C_dev+trend": badness_C, "D_headroom": badness_D, "E_B+D_blend": badness_E}


# ----------------------------------------------------------------- composite ---
def composite(df, live_cols, roles, form_fn):
    """worst-metric-leads composite + attribution, smoothed. Returns health[]."""
    bad = {c: form_fn(df[c], roles[c]).to_numpy() for c in live_cols}
    B = np.vstack([bad[c] for c in live_cols]).T[WINDOW:]
    combined = B.max(axis=1)
    combined = pd.Series(combined).rolling(SMOOTH, min_periods=1).mean().to_numpy()
    health = np.clip(100 * (1 - combined), 0, 100)
    return health


def anomaly_windows(lab):
    w, s = [], None
    for i, v in enumerate(lab):
        if v == 1 and s is None: s = i
        if v == 0 and s is not None: w.append((s, i - 1)); s = None
    if s is not None: w.append((s, len(lab) - 1))
    return w


# ---------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="src/data/smd_oid_mapping.json")
    ap.add_argument("--data", default="data/ServerMachineDataset")
    ap.add_argument("--roles", default="hrProcessorLoad,hrStorageUsed,ifInErrors")
    ap.add_argument("--machines", default="all", help="'all' | 'group1' | comma list")
    args = ap.parse_args()

    mapping = json.load(open(args.map))
    machines = (list(mapping) if args.machines == "all"
                else [m for m in mapping if m.startswith("machine-1-")] if args.machines == "group1"
                else args.machines.split(","))
    want = args.roles.split(",")

    store = {f: [] for f in FORMS}
    for m in machines:
        chosen = {}
        for dim, v in mapping[m].items():
            if v["oid_role"] in want and v["oid_role"] not in chosen:
                chosen[v["oid_role"]] = int(dim) - 1
        if not chosen:
            continue
        live = list(chosen.values()); roles = {c: r for r, c in chosen.items()}
        df = pd.read_csv(f"{args.data}/test/{m}.txt", header=None)
        lab = np.loadtxt(f"{args.data}/test_label/{m}.txt", dtype=int)[WINDOW:]
        wins = anomaly_windows(lab)
        for f, fn in FORMS.items():
            store[f].append((composite(df, live, roles, fn), lab, wins))
        print(f"  scored {m}", flush=True)

    print(f"\nHEALTH BAKEOFF v2 — {len(machines)} machines · metrics {want}\n")
    print(f"{'formulation':<16}{'normalH':>9}{'threshold':>11}{'recall':>9}{'false-alarm':>13}")
    print("-" * 58)
    rows = []
    for f in FORMS:
        norm_all = np.concatenate([h[l == 0] for h, l, _ in store[f]])
        thr = np.percentile(norm_all, 5)
        caught = total = fa_below = fa_tot = 0
        for health, lab, wins in store[f]:
            for a, b in wins:
                total += 1
                if (health[a:b + 1] < thr).any():
                    caught += 1
            fa_below += int((health[lab == 0] < thr).sum())
            fa_tot += int((lab == 0).sum())
        recall = caught / max(total, 1)
        fa = fa_below / max(fa_tot, 1)
        rows.append((recall, -fa, f, norm_all.mean(), thr))
        print(f"{f:<16}{norm_all.mean():>9.1f}{thr:>11.1f}{recall:>8.0%}{fa:>13.1%}")
    print("-" * 58)
    rows.sort(reverse=True)
    print("\nRanked by recall (then low false-alarm):")
    for rec, negfa, f, nh, thr in rows:
        print(f"  {f:<16} recall {rec:.0%} · false-alarm {-negfa:.1%} · normalH {nh:.0f}")
    print("\nBest = warns during real failures (high recall), rarely cries wolf")
    print("(low false-alarm), keeps healthy devices reading healthy (high normalH).")


if __name__ == "__main__":
    main()
