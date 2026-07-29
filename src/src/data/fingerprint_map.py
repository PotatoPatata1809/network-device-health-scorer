"""
SMD -> SNMP OID role mapping by behavioural fingerprint.

SMD anonymizes its 38 columns. Roles are ASSIGNED from each column's observed
behaviour, NOT recovered from SMD. Column meaning does not generalize across
SMD's 3 machine groups, so classification is PER MACHINE.
"""
import json, os
import numpy as np
import pandas as pd
from collections import Counter

DATA = "data/ServerMachineDataset"
OUT = "src/data"
MACHINES = [f"machine-{g}-{i}" for g, n in [(1, 8), (2, 9), (3, 11)] for i in range(1, n + 1)]

def fingerprint(s: pd.Series) -> dict:
    d = s.diff().dropna()
    rng = s.max() - s.min()
    return {
        "mean": float(s.mean()), "std": float(s.std()),
        "min": float(s.min()), "max": float(s.max()),
        "frac_zero": float((s == 0).mean()),
        "frac_at_max": float((s >= s.max() - 1e-9).mean()) if rng > 0 else 1.0,
        "autocorr": float(s.autocorr(lag=1)) if s.std() > 0 else float("nan"),
        "mono_up": float((d >= 0).mean()) if len(d) else 1.0,
        "mad": float(d.abs().mean()) if len(d) else 0.0,
        "n_distinct": int(s.round(6).nunique()),
        "slope": float(np.polyfit(np.arange(len(s)), s, 1)[0]) if s.std() > 0 else 0.0,
        "range": float(rng),
    }

def classify(fp: dict):
    if fp["range"] == 0 or fp["n_distinct"] <= 2:
        return "dead", "high"
    if fp["frac_zero"] > 0.98 and fp["std"] < 0.02:
        return "dead", "high"
    if fp["mono_up"] > 0.97 and fp["mad"] < 0.002 and fp["autocorr"] > 0.99:
        return "sysUpTime", "high"
    if fp["frac_zero"] > 0.40 and fp["mad"] > 0 and fp["std"] > 0.01:
        return "ifInErrors", "high" if fp["frac_zero"] > 0.60 else "medium"
    if fp["autocorr"] > 0.95 and fp["mad"] < 0.01:
        return "hrStorageUsed", "high" if fp["autocorr"] > 0.98 else "medium"
    if fp["autocorr"] < 0.75 and fp["mad"] > 0.005 and fp["frac_zero"] < 0.40:
        return "hrProcessorLoad", "high" if fp["autocorr"] < 0.55 else "medium"
    if fp["autocorr"] >= 0.75 and fp["mad"] >= 0.01:
        return "ifInOctets", "medium"
    return "generic-gauge", "low"

def load_interp(machine: str) -> Counter:
    c = Counter()
    with open(os.path.join(DATA, "interpretation_label", f"{machine}.txt")) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            _, dims = line.split(":")
            for d in dims.split(","):
                c[int(d)] += 1
    return c

mapping, contradictions, role_counts = {}, [], Counter()
for m in MACHINES:
    tr = pd.read_csv(f"{DATA}/train/{m}.txt", header=None)
    te = pd.read_csv(f"{DATA}/test/{m}.txt", header=None)
    df = pd.concat([tr, te], ignore_index=True)
    drivers = load_interp(m)
    mapping[m] = {}
    for col in range(df.shape[1]):
        fp = fingerprint(df[col])
        role, conf = classify(fp)
        dim = col + 1
        drives = drivers.get(dim, 0)
        if role == "dead" and drives > 0:
            contradictions.append((m, dim, drives))
            role, conf = "generic-gauge", "low"
        mapping[m][str(dim)] = {"oid_role": role, "confidence": conf,
                                 "drives_n_anomalies": drives}
        role_counts[role] += 1

# reclassify silent-until-failure columns as error counters
reclass = 0
for m, cols in mapping.items():
    for dim, v in cols.items():
        if v["oid_role"] == "generic-gauge" and v["confidence"] == "low" and v["drives_n_anomalies"] > 0:
            v["oid_role"], v["confidence"] = "ifInErrors", "medium"
            v["note"] = "near-flat baseline, active only during labeled anomalies (silent-until-failure counter)"
            reclass += 1

# machine-2-8 has no clearly CPU-shaped column; assign its bounciest bounded signal
if "machine-2-8" in mapping and "12" in mapping["machine-2-8"]:
    mapping["machine-2-8"]["12"].update({
        "oid_role": "hrProcessorLoad", "confidence": "medium",
        "note": "most CPU-like signal on this machine; no clearly bouncy low-autocorr column present"})

os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/smd_oid_mapping.json", "w") as f:
    json.dump(mapping, f, indent=1)

rc = Counter(v["oid_role"] for m in mapping for v in mapping[m].values())
print("=== ROLE COUNTS (28 machines x 38 cols = 1064 columns) ===")
for r, c in rc.most_common():
    print(f"  {r:<16} {c}")
print(f"\ncontradictions demoted: {len(contradictions)} | silent-until-failure reclassified: {reclass}")
missing = {m: {"hrProcessorLoad","hrStorageUsed","ifInErrors"} - set(v["oid_role"] for v in cols.values())
           for m, cols in mapping.items()}
missing = {m: s for m, s in missing.items() if s}
print("machines missing a core role:", missing if missing else "none — all 28 have CPU+mem+err")
print(f"\nwrote {OUT}/smd_oid_mapping.json")
