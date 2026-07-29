"""
Detector bakeoff — LOF, One-Class SVM, ensemble vs Isolation Forest.

Rules (same spine as rolling_features_eval):
  - trailing-only derived features: value, delta, deviation, volatility
  - per-device alert budget matched to that device's rolling 3-sigma flag rate
  - exact rank selection (flag exactly k most anomalous per chunk)
  - recall always quoted with flag rate
  - NAB: 15 devices, single metric, human-labelled windows  (headline defence)
  - SMD: 28 machines, multivariate (all mapped live columns), expert labels (breadth)

Ensemble = mean of per-detector rank-normalised scores, same budget.
"""

import json, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
WINDOW, REFIT, SIGMA, FLOOR, RS = 288, 288, 3, 0.001, 42


def score_chunk(train, chunk, method):
    sc = StandardScaler().fit(train)
    tr, ch = sc.transform(train), sc.transform(chunk)
    if method == "iforest":
        m = IsolationForest(contamination="auto", random_state=RS).fit(tr)
        return -m.score_samples(ch)
    if method == "lof":
        m = LocalOutlierFactor(n_neighbors=min(20, len(tr) - 1), novelty=True).fit(tr)
        return -m.score_samples(ch)
    if method == "ocsvm":
        m = OneClassSVM(nu=0.05, kernel="rbf", gamma="scale").fit(tr)
        return -m.score_samples(ch)
    raise ValueError(method)


def rank01(x):
    return np.argsort(np.argsort(x, kind="stable")) / max(1, len(x) - 1)


def flags_for(feats, cont, methods):
    n = len(feats)
    out = {m: pd.Series(False, index=feats.index) for m in methods + ["ensemble"]}
    for start in range(WINDOW, n, REFIT):
        train = feats.iloc[start - WINDOW:start].to_numpy()
        chunk = feats.iloc[start:start + REFIT].to_numpy()
        if len(chunk) == 0:
            continue
        k = min(max(1, int(round(cont * len(chunk)))), len(chunk))
        ranked = {}
        for m in methods:
            s = score_chunk(train, chunk, m)
            ranked[m] = rank01(s)
            sel = np.zeros(len(chunk), bool)
            sel[np.argsort(-s, kind="stable")[:k]] = True
            out[m].iloc[start:start + len(chunk)] = sel
        ens = np.mean([ranked[m] for m in methods], axis=0)
        sel = np.zeros(len(chunk), bool)
        sel[np.argsort(-ens, kind="stable")[:k]] = True
        out["ensemble"].iloc[start:start + len(chunk)] = sel
    return out


def derived(vals):
    mu = vals.rolling(WINDOW).mean().shift(1)
    sd = vals.rolling(WINDOW).std().shift(1)
    return pd.DataFrame({
        "value": vals, "delta": vals.diff(),
        "deviation": (vals - mu) / sd.replace(0, np.nan),
        "volatility": sd,
    }).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def run_nab(data_dir="data/realAWSCloudwatch", dmap_path="experiments/device_map.json",
            labels_path="data/combined_windows.json"):
    dmap = json.load(open(dmap_path))
    labels = json.load(open(labels_path))
    methods = ["iforest", "lof", "ocsvm"]
    names = methods + ["ensemble", "sigma"]
    caught = {m: 0 for m in names}; flags = {m: 0 for m in names}
    tot = rows = 0
    for dev, f in dmap.items():
        df = pd.read_csv(f"{data_dir}/{f}", parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        vals = df["value"]
        mu = vals.rolling(WINDOW).mean().shift(1)
        sd = vals.rolling(WINDOW).std().shift(1)
        sg = ((vals - mu).abs() > SIGMA * sd).fillna(False)
        feats = derived(vals)
        n_sc = len(df) - WINDOW
        cont = float(np.clip(sg.iloc[WINDOW:].sum() / max(n_sc, 1), FLOOR, 0.5))
        det = flags_for(feats, cont, methods)
        det["sigma"] = sg
        warm = df["timestamp"].iloc[WINDOW]
        wins = [(a, b) for a, b in labels.get(f"realAWSCloudwatch/{f}", [])
                if pd.Timestamp(a) >= warm]
        tot += len(wins); rows += n_sc
        for m in names:
            sel = det[m].iloc[WINDOW:]
            hits = df.loc[sel[sel].index, "timestamp"]
            caught[m] += sum(any(pd.Timestamp(a) <= t <= pd.Timestamp(b) for t in hits) for a, b in wins)
            flags[m] += int(sel.sum())
        print(f"  NAB {dev} done", flush=True)
    print(f"\n=== NAB (15 devices · {tot} windows · {rows} rows) ===")
    print(f"{'method':<10}{'recall':<16}{'flags':>7}{'flag%':>8}")
    for m in names:
        print(f"{m:<10}{f'{caught[m]}/{tot} ({caught[m]/tot:.0%})':<16}{flags[m]:>7}{flags[m]/rows:>8.1%}")


def smd_windows(lab):
    w, s = [], None
    for i, v in enumerate(lab):
        if v == 1 and s is None: s = i
        if v == 0 and s is not None: w.append((s, i - 1)); s = None
    if s is not None: w.append((s, len(lab) - 1))
    return w


def run_smd(data_dir="data/ServerMachineDataset", map_path="src/data/smd_oid_mapping.json"):
    mapping = json.load(open(map_path))
    methods = ["iforest", "lof", "ocsvm"]
    names = methods + ["ensemble", "sigma"]
    caught = {m: 0 for m in names}; flags = {m: 0 for m in names}
    tot = rows = 0
    for machine, cols in mapping.items():
        live = [int(d) - 1 for d, v in cols.items() if v["oid_role"] != "dead"]
        df = pd.read_csv(f"{data_dir}/test/{machine}.txt", header=None)
        lab = np.loadtxt(f"{data_dir}/test_label/{machine}.txt", dtype=int)
        sg = pd.Series(False, index=df.index)
        for c in live:
            mu = df[c].rolling(WINDOW).mean().shift(1)
            sd = df[c].rolling(WINDOW).std().shift(1)
            sg |= ((df[c] - mu).abs() > SIGMA * sd).fillna(False)
        n_sc = len(df) - WINDOW
        cont = float(np.clip(sg.iloc[WINDOW:].sum() / max(n_sc, 1), FLOOR, 0.5))
        feats = df[live].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        det = flags_for(feats, cont, methods)
        det["sigma"] = sg
        wins = [(a, b) for a, b in smd_windows(lab) if a >= WINDOW]
        tot += len(wins); rows += n_sc
        for m in names:
            sel = det[m].iloc[WINDOW:]
            idx = sel[sel].index.to_numpy()
            caught[m] += sum(any(a <= i <= b for i in idx) for a, b in wins)
            flags[m] += int(sel.sum())
        print(f"  SMD {machine} done ({len(wins)} windows)", flush=True)
    print(f"\n=== SMD (28 machines · {tot} windows · {rows} rows · multivariate) ===")
    print(f"{'method':<10}{'recall':<16}{'flags':>7}{'flag%':>8}")
    for m in names:
        print(f"{m:<10}{f'{caught[m]}/{tot} ({caught[m]/tot:.0%})':<16}{flags[m]:>7}{flags[m]/rows:>8.1%}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["nab", "smd", "both"], default="both")
    a = ap.parse_args()
    if a.dataset in ("nab", "both"):
        run_nab()
    if a.dataset in ("smd", "both"):
        run_smd()
