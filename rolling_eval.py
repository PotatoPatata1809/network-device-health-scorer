"""
Rolling baseline + derived features + per-device auto-matched alert budget.

Two changes from rolling_eval.py:

1. FEATURES. Isolation Forest was given a single column (`value`). On one
   dimension there is nothing to isolate with — it can only ask "is this number
   far from the others", which is what 3-sigma already does more directly. Here
   it gets four views of the same stream, all computed from trailing data only:

       value  ·  delta (rate of change)  ·  deviation from rolling mean  ·  volatility

   That is what the forest is actually for: combinations that are abnormal even
   when no single number is.

2. AUTO-MATCHED BUDGET. Instead of one global contamination for 15 devices with
   very different variance, each device's alert budget is set to that
   device's own rolling-sigma flag rate, and the forest flags exactly that many
   of its most anomalous points per chunk. Both detectors then raise the same number of
   alerts on every device by construction, so any difference in recall is a
   difference in detection quality, not in alert volume.


"""

import json
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

DATA = "data/realAWSCloudwatch"
WINDOW = 288          # trailing samples treated as "normal" (~24h at 5-min sampling)
REFIT = 288           # refit cadence
SIGMA = 3
FLOOR = 0.001         # minimum contamination when a device's sigma rate is ~0

dmap = json.load(open("scripts/device_map.json"))
labels = json.load(open("data/combined_windows.json"))

tot = if_c = sg_c = 0
if_flags = sg_flags = scored_rows = 0

print("ROLLING + DERIVED FEATURES  —  alert budget auto-matched per device")
print(f"window = {WINDOW} (~24h) · refit every {REFIT} · sigma={SIGMA} · "
      f"features: value, delta, deviation, volatility\n")
print(f"{'DEVICE':<14}{'SCORED':>7}{'WINS':>6}{'CONT':>7}{'IF_FLG':>8}{'IF':>4}{'SG_FLG':>8}{'SG':>4}")
print("-" * 58)

for dev, f in dmap.items():
    df = pd.read_csv(f"{DATA}/{f}", parse_dates=["timestamp"]).sort_values("timestamp")
    df = df.reset_index(drop=True)

    # ---- trailing-only statistics (never sees the current point or the future) ----
    roll_mu = df["value"].rolling(WINDOW).mean().shift(1)
    roll_sd = df["value"].rolling(WINDOW).std().shift(1)

    # ---- baseline detector: univariate rolling 3-sigma ----
    sg_flag = (df["value"] - roll_mu).abs() > SIGMA * roll_sd
    sg_flag = sg_flag.fillna(False)

    # ---- derived feature matrix for the forest ----
    feats = pd.DataFrame({
        "value": df["value"],
        "delta": df["value"].diff(),
        "deviation": (df["value"] - roll_mu) / roll_sd.replace(0, np.nan),
        "volatility": roll_sd,
    }).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    scored_idx = df.index[WINDOW:]
    n_scored = len(scored_idx)

    # ---- match this device's alert budget to its own sigma flag rate ----
    sg_rate = sg_flag.iloc[WINDOW:].sum() / max(n_scored, 1)
    cont = float(np.clip(sg_rate, FLOOR, 0.5))

    # ---- rolling isolation forest over the derived features ----
    if_flag = pd.Series(False, index=df.index)
    for start in range(WINDOW, len(df), REFIT):
        train = feats.iloc[start - WINDOW:start]
        chunk = feats.iloc[start:start + REFIT]
        if len(chunk) == 0:
            continue
        m = IsolationForest(contamination="auto", random_state=42)
        m.fit(train)
        # rank-based cut: flag exactly the k most anomalous points in this chunk,
        # where k is this device's matched budget. Guarantees equal alert volume
        # instead of hoping the training threshold transfers to new data.
        # at least 1 point per chunk, or a low-budget device can never alert at all
        k = max(1, int(round(cont * len(chunk))))
        k = min(k, len(chunk))
        scores = m.score_samples(chunk)              # lower = more anomalous
        # take exactly k by rank — flagging every tie blows the budget on flat data
        picked = np.argsort(scores, kind="stable")[:k]
        sel = np.zeros(len(chunk), dtype=bool)
        sel[picked] = True
        if_flag.iloc[start:start + REFIT] = sel

    scored = df.iloc[WINDOW:]
    warmup_end = scored["timestamp"].iloc[0]
    if_hits = scored.loc[if_flag.iloc[WINDOW:], "timestamp"]
    sg_hits = scored.loc[sg_flag.iloc[WINDOW:], "timestamp"]

    wins = [(a, b) for a, b in labels.get(f"realAWSCloudwatch/{f}", [])
            if pd.Timestamp(a) >= warmup_end]

    ifc = sum(any(pd.Timestamp(a) <= t <= pd.Timestamp(b) for t in if_hits) for a, b in wins)
    sgc = sum(any(pd.Timestamp(a) <= t <= pd.Timestamp(b) for t in sg_hits) for a, b in wins)

    tot += len(wins); if_c += ifc; sg_c += sgc
    if_flags += len(if_hits); sg_flags += len(sg_hits); scored_rows += n_scored

    print(f"{dev:<14}{n_scored:>7}{len(wins):>6}{cont:>7.3f}"
          f"{len(if_hits):>8}{ifc:>4}{len(sg_hits):>8}{sgc:>4}")

print("-" * 58)
print(f"scoreable windows: {tot}   ·   rows scored: {scored_rows}\n")
print(f"IFOREST + FEATURES : {if_c}/{tot} windows ({if_c/tot:.0%} recall) · "
      f"{if_flags} flags ({if_flags/scored_rows:.1%} of rows)")
print(f"ROLLING SIGMA      : {sg_c}/{tot} windows ({sg_c/tot:.0%} recall) · "
      f"{sg_flags} flags ({sg_flags/scored_rows:.1%} of rows)")
d = if_c - sg_c
print(f"DELTA              : {d:+d} windows at a matched alert budget")
print("\nBudgets are matched per device, so recall differences are detection quality.")