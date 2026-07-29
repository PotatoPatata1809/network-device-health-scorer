"""Aggregate sweep_results.jsonl -> budget sensitivity + per-machine head-to-head."""
import json
from collections import defaultdict

seen, rows = set(), []
for line in open("sweep_results.jsonl"):
    line = line.strip()
    if not line: continue
    r = json.loads(line)
    if r["machine"] in seen: continue
    seen.add(r["machine"]); rows.append(r)

budgets = sorted(rows[0]["sweep"].keys(), key=float)
methods = ["iforest","lof","ocsvm","ensemble"]
tot_win = sum(r["windows"] for r in rows)
tot_row = sum(r["rows"] for r in rows)

print(f"machines: {len(rows)} · windows: {tot_win} · rows: {tot_row}\n")
print("=== BUDGET SENSITIVITY (does the winner change with budget?) ===")
print(f"{'budget':<9}" + "".join(f"{m:>12}" for m in methods))
for b in budgets:
    cells = []
    for m in methods:
        c = sum(r["sweep"][b][m]["caught"] for r in rows)
        cells.append(f"{c/tot_win:>11.0%}")
    print(f"{float(b):<9.0%}" + "".join(cells))

print("\n=== HEAD-TO-HEAD per machine (LOF vs IForest) ===")
for b in budgets:
    lof_w = ifo_w = tie = 0
    for r in rows:
        l = r["sweep"][b]["lof"]["caught"]; i = r["sweep"][b]["iforest"]["caught"]
        if l > i: lof_w += 1
        elif i > l: ifo_w += 1
        else: tie += 1
    print(f"  budget {float(b):.0%}:  LOF wins {lof_w:>2} · IForest wins {ifo_w:>2} · tie {tie:>2}")

print("\n=== actual flag rate achieved (sanity: budgets honoured?) ===")
for b in budgets:
    f = sum(r["sweep"][b]["lof"]["flags"] for r in rows)
    print(f"  target {float(b):.0%} -> actual {f/tot_row:.1%}")
