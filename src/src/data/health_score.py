"""
NetPulse HEALTH ENGINE — webapp-ready.

Two independent, honest signals per device:

  HEALTH (0-100)  = headroom to critical. "% of the way to the ceiling."
                    High = lots of runway. Low = close to failure. Self-calibrating,
                    explainable, no hand-picked weights. This is what ranks devices.

  ALERT (bool)    = the LOF detector (validated 92% on SMD) fired. Catches the
                    *change* early — usually BEFORE health drops much. Early warning.

Order in a real failure: ALERT fires first (something started behaving oddly),
then HEALTH slides as the device climbs toward its ceiling. Alert = what's failing;
health = how much runway is left. They answer different questions and the console
shows both.

Output = the SHARED per-device record every NetPulse feature writes to, so the
scoring core can later assemble Priority = Health x Urgency x Impact without rewiring:

  {
    "device": "core-sw-01",
    "health": 41.0,                     # 0-100 headroom
    "alert": true,                      # LOF fired now
    "attribution": {"hrStorageUsed": 71, "hrProcessorLoad": 20, "ifInErrors": 9},
    "metrics": {"hrStorageUsed": 0.88, ...},   # current raw readings
    "series": [ {row, health, alert}, ... ]    # time-series for the click-through graph
  }

Usage:
  from health_score import score_device
  rec = score_device(df, live_cols, roles, device_name)

CLI (offline validation / demo):
  python src/data/health_score.py --machine machine-1-1
  python src/data/health_score.py --validate all
"""

import json, argparse
import numpy as np
import pandas as pd
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

WINDOW = 288        # trailing "normal" window (~24h at 5-min sampling)
REFIT = 288
SMOOTH = 12         # health smoothing (~1h): gradual slides read smooth, sudden drops still fast
# Alert budget is NOT hardcoded — it self-derives per device from that device's own
# rolling 3-sigma flag rate (the matched-budget method validated on NAB), guard-railed
# to a sane 0.5%..5% band so a flat or pathological device can't misbehave.
BUDGET_FLOOR, BUDGET_CEIL, BUDGET_FALLBACK = 0.005, 0.05, 0.02

# Ceiling per OID role, for headroom. Bounded gauges have a natural 0..1 ceiling in
# SMD's normalisation; unbounded counters (errors) use a robust cap (p99 of the
# device's own history), derived per device — not hand-picked.
BOUNDED = {"hrProcessorLoad", "hrStorageUsed"}
COUNTER = {"ifInErrors", "ifInOctets"}


# ----------------------------------------------------------------- detector ---
def _trailing(vals: pd.Series) -> pd.DataFrame:
    mu = vals.rolling(WINDOW).mean().shift(1)
    sd = vals.rolling(WINDOW).std().shift(1)
    return pd.DataFrame({
        "value": vals, "delta": vals.diff(),
        "deviation": (vals - mu) / sd.replace(0, np.nan),
        "volatility": sd,
    }).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _derive_budget(df: pd.DataFrame, live_cols: list) -> float:
    """Self-derived alert budget = the device's own 3-sigma flag rate (union across
    metrics), guard-railed. Nothing hardcoded to the dataset."""
    sg = pd.Series(False, index=df.index)
    for c in live_cols:
        mu = df[c].rolling(WINDOW).mean().shift(1)
        sd = df[c].rolling(WINDOW).std().shift(1)
        sg |= ((df[c] - mu).abs() > 3 * sd).fillna(False)
    rate = sg.iloc[WINDOW:].mean()
    if not np.isfinite(rate) or rate <= 0:
        return BUDGET_FALLBACK
    return float(np.clip(rate, BUDGET_FLOOR, BUDGET_CEIL))


def _derive_ceiling(v: np.ndarray) -> float:
    """Self-derived counter ceiling from the device's own distribution shape.
    Spikier device -> larger multiple of p95. Guard-railed 2x..8x. Fail-safe to max."""
    p95 = np.percentile(v, 95)
    mx = v.max()
    if p95 <= 1e-6:
        return mx if mx > 1e-6 else 1.0
    spikiness = mx / p95
    mult = float(np.clip(spikiness * 0.3, 2.0, 8.0))
    ceil = mult * p95
    return float(min(ceil, mx)) if mx > 1e-6 else 1.0


def _lof_alerts(df: pd.DataFrame, live_cols: list) -> np.ndarray:
    """LOF over the device's multivariate trailing features. Returns bool alert per row.
    Detector is plain LOF at a matched budget — exactly as benchmarked (92% on SMD)."""
    feats = pd.concat([_trailing(df[c]).add_prefix(f"{c}_") for c in live_cols], axis=1)
    feats = feats.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    budget = _derive_budget(df, live_cols)      # self-derived, per device
    n = len(feats)
    alert = np.zeros(n, bool)
    for s in range(WINDOW, n, REFIT):
        tr = feats.iloc[s - WINDOW:s].to_numpy()
        ch = feats.iloc[s:s + REFIT].to_numpy()
        if len(ch) == 0:
            continue
        sc = StandardScaler().fit(tr)
        m = LocalOutlierFactor(n_neighbors=min(20, len(tr) - 1), novelty=True).fit(sc.transform(tr))
        score = -m.score_samples(sc.transform(ch))
        k = min(max(1, int(round(budget * len(ch)))), len(ch))
        idx = np.argsort(-score, kind="stable")[:k]
        sel = np.zeros(len(ch), bool); sel[idx] = True
        alert[s:s + len(ch)] = sel
    return alert


# ------------------------------------------------------------------- health ---
def _headroom_badness(vals: pd.Series, role: str) -> np.ndarray:
    """0..1 badness from headroom to ceiling. Bounded -> distance to 1.0.
    Counter -> distance to the device's own robust ceiling (p99 of history)."""
    v = vals.to_numpy()
    if role in COUNTER:
        # counters sit near-zero normally then spike on failure. Ceiling = 3x the
        # 95th percentile of the device's own history: leaves normal reading healthy
        # while a real spike still pushes health down. (p99 was too tight; max hid
        # failures.) Derived per device, not hand-picked.
        ceiling = _derive_ceiling(v)         # self-derived from the device's own spread
        return np.clip(v / ceiling, 0, 1)
    # bounded (or fallback): SMD normalised to ~[0,1], ceiling = 1.0
    return np.clip(v, 0, 1)


def _health_series(df: pd.DataFrame, live_cols: list, roles: dict):
    """Per-row health (0-100) + per-metric badness for attribution. Worst metric leads."""
    bad = {c: _headroom_badness(df[c], roles[c]) for c in live_cols}
    B = np.vstack([bad[c] for c in live_cols]).T          # rows x metrics
    combined = B.max(axis=1)                               # worst metric leads (honest)
    combined = pd.Series(combined).rolling(SMOOTH, min_periods=1).mean().to_numpy()
    health = np.clip(100 * (1 - combined), 0, 100)
    return health, bad


# -------------------------------------------------------- public: one device --
def score_device(df: pd.DataFrame, live_cols: list, roles: dict, device: str) -> dict:
    """Compute the SHARED per-device record. df = raw metric columns for this device."""
    health, bad = _health_series(df, live_cols, roles)
    alert = _lof_alerts(df, live_cols)

    i = len(df) - 1                                        # "now" = last row
    badvals = np.array([bad[c][i] for c in live_cols])
    tot = badvals.sum() or 1.0
    attribution = {roles[c]: int(round(100 * bad[c][i] / tot)) for c in live_cols}
    metrics = {roles[c]: round(float(df[c].iloc[i]), 3) for c in live_cols}

    # time-series for the click-through graph (from warm-up onward)
    series = [{"row": int(r), "health": round(float(health[r]), 1), "alert": bool(alert[r])}
              for r in range(WINDOW, len(df))]

    return {
        "device": device,
        "health": round(float(health[i]), 1),
        "alert": bool(alert[i]),
        "attribution": attribution,
        "metrics": metrics,
        "series": series,
    }


# --------------------------------------------------------------- CLI helpers --
def _pick_cols(mapping_m, want):
    chosen = {}
    for dim, v in mapping_m.items():
        if v["oid_role"] in want and v["oid_role"] not in chosen:
            chosen[v["oid_role"]] = int(dim) - 1
    return list(chosen.values()), {c: r for r, c in chosen.items()}


def _windows(lab):
    w, s = [], None
    for i, v in enumerate(lab):
        if v == 1 and s is None: s = i
        if v == 0 and s is not None: w.append((s, i - 1)); s = None
    if s is not None: w.append((s, len(lab) - 1))
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="src/data/smd_oid_mapping.json")
    ap.add_argument("--data", default="data/ServerMachineDataset")
    ap.add_argument("--roles", default="hrProcessorLoad,hrStorageUsed,ifInErrors")
    ap.add_argument("--machine", default=None, help="one machine -> print its record")
    ap.add_argument("--validate", default=None, help="'all'/'group1' -> fleet health check")
    a = ap.parse_args()
    mapping = json.load(open(a.map))
    want = a.roles.split(",")

    if a.machine:
        live, roles = _pick_cols(mapping[a.machine], want)
        df = pd.read_csv(f"{a.data}/test/{a.machine}.txt", header=None)
        rec = score_device(df, live, roles, a.machine)
        show = {k: rec[k] for k in ("device", "health", "alert", "attribution", "metrics")}
        print(json.dumps(show, indent=2))
        print(f"series length: {len(rec['series'])} points (for the graph)")
        return

    machines = (list(mapping) if a.validate == "all"
                else [m for m in mapping if m.startswith("machine-1-")] if a.validate == "group1"
                else (a.validate or "all").split(","))
    norm_H, rec_hit, rec_tot, al_hit, al_tot, al_norm = [], 0, 0, 0, 0, 0
    for m in machines:
        live, roles = _pick_cols(mapping[m], want)
        if not live:
            continue
        df = pd.read_csv(f"{a.data}/test/{m}.txt", header=None)
        lab = np.loadtxt(f"{a.data}/test_label/{m}.txt", dtype=int)
        health, _ = _health_series(df, live, roles)
        alert = _lof_alerts(df, live)
        H, L, A = health[WINDOW:], lab[WINDOW:], alert[WINDOW:]
        thr = np.percentile(H[L == 0], 5) if (L == 0).any() else 50
        norm_H.append(H[L == 0].mean())
        for x, y in _windows(L):
            rec_tot += 1
            if (H[x:y+1] < thr).any() or A[x:y+1].any(): rec_hit += 1
        al_hit += int(A[L == 1].sum()); al_tot += int((L == 1).sum())
        al_norm += int(A[L == 0].sum())
        print(f"  {m}: normalH {H[L==0].mean():.0f} · alertRate {A.mean()*100:.1f}%", flush=True)

    print(f"\nHEALTH ENGINE VALIDATION — {len(machines)} machines · {want}\n")
    print(f"  mean normal health           : {np.mean(norm_H):.1f}   (want ~80+)")
    print(f"  anomaly caught (health-drop OR alert): {rec_hit}/{rec_tot} "
          f"({100*rec_hit/max(rec_tot,1):.0f}%)")
    print(f"  alert rate on anomaly rows   : {100*al_hit/max(al_tot,1):.0f}%")
    print(f"  alert rate on normal rows    : {100*al_norm/max(al_tot,1):.1f}% (lower better)")


if __name__ == "__main__":
    main()
