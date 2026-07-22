"""
Temporal-split evaluation — the honest version of poc_anomaly.py.

Both detectors are FIT on a probationary period and SCORED only on data that
comes after it. Neither one ever sees the test period during training, so this
measures what the system would actually do in production: learn from the past,
judge the future.

Split follows NAB's own convention: the first 15% of each stream (capped at 750
samples) is probationary and is not scored. Labeled windows that fall inside the
probationary period are excluded from both detectors equally.


"""

import json
import pandas as pd
from sklearn.ensemble import IsolationForest

DATA = "data/realAWSCloudwatch"
PROBATION_FRAC = 0.15
PROBATION_CAP = 750
CONTAMINATION = 0.02
SIGMA = 3

dmap = json.load(open("scripts/device_map.json"))
labels = json.load(open("data/combined_windows.json"))

tot = if_c = st_c = if_flags = st_flags = 0
skipped = 0

print("TEMPORAL SPLIT EVALUATION  —  train on probation, score the future")
print(f"probation = first {int(PROBATION_FRAC*100)}% of stream (cap {PROBATION_CAP}) · "
      f"contamination={CONTAMINATION} · sigma={SIGMA}\n")
print(f"{'DEVICE':<14}{'TEST':>6}{'WINS':>6}{'IF_FLG':>8}{'IF':>5}{'ST_FLG':>8}{'ST':>5}")
print("-" * 52)

for dev, f in dmap.items():
    df = pd.read_csv(f"{DATA}/{f}", parse_dates=["timestamp"]).sort_values("timestamp")

    n_prob = min(PROBATION_CAP, int(len(df) * PROBATION_FRAC))
    train, test = df.iloc[:n_prob], df.iloc[n_prob:].copy()
    test_start = test.timestamp.iloc[0]

    # detector 1 — self-baselining
    m = IsolationForest(contamination=CONTAMINATION, random_state=42)
    m.fit(train[["value"]])
    test["if_flag"] = m.predict(test[["value"]]) == -1

    # detector 2 — classic static threshold, limits learned from the same train slice
    mu, sd = train["value"].mean(), train["value"].std()
    test["st_flag"] = (test["value"] > mu + SIGMA * sd) | (test["value"] < mu - SIGMA * sd)

    if_hits = test.loc[test.if_flag, "timestamp"]
    st_hits = test.loc[test.st_flag, "timestamp"]

    # only windows that start after the probationary period are scoreable
    all_wins = labels.get(f"realAWSCloudwatch/{f}", [])
    wins = [(a, b) for a, b in all_wins if pd.Timestamp(a) >= test_start]
    skipped += len(all_wins) - len(wins)

    ifc = sum(any(pd.Timestamp(a) <= t <= pd.Timestamp(b) for t in if_hits) for a, b in wins)
    stc = sum(any(pd.Timestamp(a) <= t <= pd.Timestamp(b) for t in st_hits) for a, b in wins)

    tot += len(wins); if_c += ifc; st_c += stc
    if_flags += len(if_hits); st_flags += len(st_hits)

    print(f"{dev:<14}{len(test):>6}{len(wins):>6}{len(if_hits):>8}{ifc:>5}{len(st_hits):>8}{stc:>5}")

print("-" * 52)
print(f"scoreable windows: {tot}   (excluded, inside probation: {skipped})\n")
print(f"NETPULSE (IForest) : {if_c}/{tot} windows ({if_c/tot:.0%} recall) · {if_flags} total flags")
print(f"STATIC THRESHOLD   : {st_c}/{tot} windows ({st_c/tot:.0%} recall) · {st_flags} total flags")
d = if_c - st_c
print(f"DELTA              : {d:+d} windows ({d/tot:+.0%} recall) for self-baselining detection")