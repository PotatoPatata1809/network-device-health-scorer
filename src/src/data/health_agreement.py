"""
AGREEMENT CHECK — does the health BAR agree with the LOF DETECTOR?

Design: LOF (92%) decides sick/not; the health bar (deviation-based) shows how
sick + which metric. For the console to tell one coherent story, when LOF fires
the bar should be LOW, and when LOF is quiet the bar should be HIGH.

This measures that overlap:
  - bar health on rows where LOF FIRED   (want LOW)
  - bar health on rows where LOF QUIET   (want HIGH)
  - agreement %: rows where (LOF fired & bar low) or (LOF quiet & bar high)
  - correlation between LOF badness and (100 - bar health)

Run from repo root:
    python src/data/health_agreement.py --machines all
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


def lof_flags(feats, cont):
    """LOF flags exactly k top-anomalous per chunk (matched budget), like the bakeoff."""
    n = len(feats); out = np.zeros(n, bool)
    for s in range(WINDOW, n, REFIT):
        tr = feats.iloc[s - WINDOW:s].to_numpy()
        ch = feats.iloc[s:s + REFIT].to_numpy()
        if len(ch) == 0:
            continue
        sc = StandardScaler().fit(tr)
        m = LocalOutlierFactor(n_neighbors=min(20, len(tr) - 1), novelty=True).fit(sc.transform(tr))
        score = -m.score_samples(sc.transform(ch))
        k = min(max(1, int(round(cont * len(ch)))), len(ch))
        idx = np.argsort(-score, kind="stable")[:k]
        sel = np.zeros(len(ch), bool); sel[idx] = True
        out[s:s + len(ch)] = sel
    return out


def health_bar(df, live_cols):
    """deviation-based bar health (0-100), worst-metric-leads, smoothed."""
    bads = []
    for c in live_cols:
        mu = df[c].rolling(WINDOW).mean().shift(1)
        sd = df[c].rolling(WINDOW).std().shift(1)
        z = (df[c] - mu).abs() / sd.replace(0, np.nan)
        bads.append((z.fillna(0) / 6.0).clip(0, 1).to_numpy())
    B = np.vstack(bads).T[WINDOW:]
    combined = pd.Series(B.max(axis=1)).rolling(SMOOTH, min_periods=1).mean().to_numpy()
    return np.clip(100 * (1 - combined), 0, 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="src/data/smd_oid_mapping.json")
    ap.add_argument("--data", default="data/ServerMachineDataset")
    ap.add_argument("--roles", default="hrProcessorLoad,hrStorageUsed,ifInErrors")
    ap.add_argument("--machines", default="all")
    args = ap.parse_args()

    mapping = json.load(open(args.map))
    machines = (list(mapping) if args.machines == "all"
                else [m for m in mapping if m.startswith("machine-1-")] if args.machines == "group1"
                else args.machines.split(","))
    want = args.roles.split(",")

    fired_h, quiet_h, corrs = [], [], []
    agree_n = agree_tot = 0
    for m in machines:
        chosen = {}
        for dim, v in mapping[m].items():
            if v["oid_role"] in want and v["oid_role"] not in chosen:
                chosen[v["oid_role"]] = int(dim) - 1
        if not chosen:
            continue
        live = list(chosen.values())
        df = pd.read_csv(f"{args.data}/test/{m}.txt", header=None)

        # LOF on the multivariate live columns, budget = 2%
        feats_multi = df[live].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        flags = lof_flags(feats_multi, 0.02)[WINDOW:]
        bar = health_bar(df, live)

        bar_low = bar < np.percentile(bar, 25)          # "low bar" = bottom quartile
        fired_h.append(bar[flags]); quiet_h.append(bar[~flags])
        agree_n += int(((flags & bar_low) | (~flags & ~bar_low)).sum())
        agree_tot += len(flags)
        lof_badness = flags.astype(float)
        corrs.append(np.corrcoef(lof_badness, 100 - bar)[0, 1])
        print(f"  {m} done", flush=True)

    fired = np.concatenate(fired_h); quiet = np.concatenate(quiet_h)
    print(f"\nAGREEMENT CHECK — {len(machines)} machines · metrics {want}\n")
    print(f"  bar health where LOF FIRED : {fired.mean():.1f}   (want LOW)")
    print(f"  bar health where LOF QUIET : {quiet.mean():.1f}   (want HIGH)")
    print(f"  gap (quiet - fired)        : {quiet.mean() - fired.mean():.1f}")
    print(f"  agreement (both tell same story): {100*agree_n/agree_tot:.0f}%")
    print(f"  mean corr(LOF, low-bar)    : {np.nanmean(corrs):.2f}   (want positive)")
    print("\nHigh gap + high agreement = flag and bar tell one coherent story on screen.")
    print("Low gap = bar and detector contradict; bar should lean on LOF instead.")


if __name__ == "__main__":
    main()
