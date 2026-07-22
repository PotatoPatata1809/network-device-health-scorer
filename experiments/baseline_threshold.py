"""
Static-threshold baseline detector.

Classic monitoring approach: flag any sample outside mean +/- 3*std for that device.
Scored against the same NAB ground-truth anomaly windows as scripts/poc_anomaly.py,

"""

import json
import pandas as pd

DATA = "data/realAWSCloudwatch"
NETPULSE_CAUGHT = 22          # Isolation Forest result from scripts/poc_anomaly.py
SIGMA = 3                     # classic 3-sigma control limit

dmap = json.load(open("scripts/device_map.json"))
labels = json.load(open("data/combined_windows.json"))

tot = c = 0
print(f"STATIC THRESHOLD BASELINE  —  mean +/- {SIGMA}*std per device\n")
print(f"{'DEVICE':<14}{'ROWS':>6}{'FLAG':>7}{'LABELED':>9}{'CAUGHT':>8}")
print("-" * 44)

for dev, f in dmap.items():
    df = pd.read_csv(f"{DATA}/{f}", parse_dates=["timestamp"])

    mu, sd = df["value"].mean(), df["value"].std()
    hi, lo = mu + SIGMA * sd, mu - SIGMA * sd
    df["flag"] = (df["value"] > hi) | (df["value"] < lo)
    hits = df[df.flag]

    wins = labels.get(f"realAWSCloudwatch/{f}", [])
    caught = sum(any(pd.Timestamp(a) <= t <= pd.Timestamp(b) for t in hits.timestamp)
                 for a, b in wins)
    tot += len(wins); c += caught

    print(f"{dev:<14}{len(df):>6}{len(hits):>7}{len(wins):>9}{caught:>8}")

print("-" * 44)
print(f"STATIC THRESHOLD : {c}/{tot} labeled anomaly windows detected ({c/tot:.0%} recall)")
print(f"NETPULSE  (IForest): {NETPULSE_CAUGHT}/{tot} labeled anomaly windows detected "
      f"({NETPULSE_CAUGHT/tot:.0%} recall)")
d = NETPULSE_CAUGHT - c
print(f"DELTA              : {d:+d} windows ({d/tot:+.0%} recall) for self-baselining detection")