import json, pandas as pd
from sklearn.ensemble import IsolationForest

DATA = "data/realAWSCloudwatch"
dmap = json.load(open("scripts/device_map.json"))
labels = json.load(open("data/combined_windows.json"))

tot = c = 0
print(f"{'DEVICE':<14}{'ROWS':>6}{'ANOM':>7}{'LABELED':>9}{'CAUGHT':>8}")
print("-" * 44)

for dev, f in dmap.items():
    df = pd.read_csv(f"{DATA}/{f}", parse_dates=["timestamp"])
    m = IsolationForest(contamination=0.02, random_state=42)
    df["flag"] = m.fit_predict(df[["value"]])
    hits = df[df.flag == -1]

    wins = labels.get(f"realAWSCloudwatch/{f}", [])
    caught = sum(any(pd.Timestamp(a) <= t <= pd.Timestamp(b) for t in hits.timestamp)
                 for a, b in wins)
    tot += len(wins); c += caught

    print(f"{dev:<14}{len(df):>6}{len(hits):>7}{len(wins):>9}{caught:>8}")

print("-" * 44)
print(f"TOTAL: {c}/{tot} real labeled anomaly windows detected ({c/tot:.0%} recall)")