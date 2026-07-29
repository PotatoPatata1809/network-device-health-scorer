"""
Sanity-check the SMD bakeoff result: is LOF's win over IForest real, or a budget artifact?

Sweeps a fixed alert budget (1%, 2%, 3%, 5%) across all detectors on every machine,
and records per-machine recall so we can count head-to-head wins, not just totals.

Usage:  PYTHONPATH=src/detector python src/detector/budget_sweep.py machine-1-1
        (loops over machines; appends to sweep_results.jsonl, skips completed)
"""
import sys, os, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import bakeoff as B

BUDGETS = [0.01, 0.02, 0.03, 0.05]

machine = sys.argv[1]
if os.path.exists("sweep_results.jsonl"):
    with open("sweep_results.jsonl") as f:
        if any(json.loads(l)["machine"] == machine for l in f if l.strip()):
            print(f"{machine} already done — skipping"); raise SystemExit(0)

mapping = json.load(open("src/data/smd_oid_mapping.json"))
live = [int(d)-1 for d, v in mapping[machine].items() if v["oid_role"] != "dead"]
df = pd.read_csv(f"data/ServerMachineDataset/test/{machine}.txt", header=None)
lab = np.loadtxt(f"data/ServerMachineDataset/test_label/{machine}.txt", dtype=int)
W = B.WINDOW
n_sc = len(df) - W
feats = df[live].replace([np.inf,-np.inf], np.nan).fillna(0.0)
wins = [(a,b) for a,b in B.smd_windows(lab) if a >= W]

res = {"machine": machine, "windows": len(wins), "rows": n_sc, "sweep": {}}
for cont in BUDGETS:
    det = B.flags_for(feats, cont, ["iforest","lof","ocsvm"])
    r = {}
    for m, sel in det.items():
        s = sel.iloc[W:]
        idx = s[s].index.to_numpy()
        r[m] = {"caught": int(sum(any(a<=i<=b for i in idx) for a,b in wins)),
                "flags": int(s.sum())}
    res["sweep"][f"{cont:.2f}"] = r

with open("sweep_results.jsonl", "a") as f:
    f.write(json.dumps(res) + "\n")

line = " | ".join(f"{c:.0%}: IF {res['sweep'][f'{c:.2f}']['iforest']['caught']}"
                 f"/LOF {res['sweep'][f'{c:.2f}']['lof']['caught']}" for c in BUDGETS)
print(f"{machine} ({len(wins)} wins) · {line}")
