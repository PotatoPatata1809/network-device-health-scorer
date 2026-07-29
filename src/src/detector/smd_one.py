"""Run one SMD machine's bakeoff at BOTH budget definitions; append result to jsonl."""
import sys, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import bakeoff as B

machine = sys.argv[1]
# skip if already done (lets the loop resume after sleep/crash without duplicates)
import os
if os.path.exists("smd_results.jsonl"):
    with open("smd_results.jsonl") as _f:
        if any(__import__("json").loads(l)["machine"] == machine for l in _f if l.strip()):
            print(f"{machine} already done — skipping")
            raise SystemExit(0)
mapping = json.load(open("src/data/smd_oid_mapping.json"))
cols = mapping[machine]
live = [int(d)-1 for d, v in cols.items() if v["oid_role"] != "dead"]
df = pd.read_csv(f"data/ServerMachineDataset/test/{machine}.txt", header=None)
lab = np.loadtxt(f"data/ServerMachineDataset/test_label/{machine}.txt", dtype=int)
W = B.WINDOW

# per-column rolling sigma flags
col_rates, union = [], pd.Series(False, index=df.index)
for c in live:
    mu = df[c].rolling(W).mean().shift(1); sd = df[c].rolling(W).std().shift(1)
    f = ((df[c]-mu).abs() > B.SIGMA*sd).fillna(False)
    union |= f
    col_rates.append(f.iloc[W:].mean())
n_sc = len(df) - W
budgets = {
    "median_col": float(np.clip(np.median(col_rates), B.FLOOR, 0.5)),
    "union":     float(np.clip(union.iloc[W:].sum()/max(n_sc,1), B.FLOOR, 0.5)),
}
feats = df[live].replace([np.inf,-np.inf], np.nan).fillna(0.0)
wins = [(a,b) for a,b in B.smd_windows(lab) if a >= W]

res = {"machine": machine, "windows": len(wins), "rows": n_sc,
       "budgets": budgets, "results": {}}
for bname, cont in budgets.items():
    det = B.flags_for(feats, cont, ["iforest","lof","ocsvm"])
    det["sigma_union"] = union
    r = {}
    for m, sel in det.items():
        s = sel.iloc[W:]
        idx = s[s].index.to_numpy()
        r[m] = {"caught": int(sum(any(a<=i<=b for i in idx) for a,b in wins)),
                "flags": int(s.sum())}
    res["results"][bname] = r
with open("smd_results.jsonl", "a") as f:
    f.write(json.dumps(res) + "\n")
print(f"{machine} done · budgets {budgets['median_col']:.3f}/{budgets['union']:.3f} · {len(wins)} wins")
