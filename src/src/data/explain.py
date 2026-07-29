"""
Explainability — turn health + attribution into an honest operator sentence.

The health engine already outputs per-metric attribution (which metric drives the
score). This layer turns that into the human line an operator reads, WITH context
so it never over-claims:

  - healthy device        -> "Operating normally." (no false driver call-out)
  - degraded/critical     -> "Memory pressure drives 71% of the degradation."
  - names the metric in plain English (hrStorageUsed -> "memory pressure")
  - only asserts a driver when health is actually degraded AND one metric clearly
    dominates; otherwise stays vague rather than inventing a cause.

Adds to the shared per-device record:
  "explanation": "Memory pressure drives 71% of the degradation. CPU rising."
  "primary_driver": "hrStorageUsed"   (or null when healthy)

No new model — this reads the attribution the health engine already produced.
Detection is validated; this is presentation of the validated signal, not a new claim.
"""

# plain-English names + how each metric "reads" when it's the problem
PHRASE = {
    "hrStorageUsed":  ("memory pressure", "memory usage climbing"),
    "hrProcessorLoad": ("CPU load", "CPU running hot"),
    "ifInErrors":     ("interface errors", "error rate rising"),
    "ifInOctets":     ("traffic volume", "traffic spiking"),
    "sysUpTime":      ("uptime instability", "recent reboot"),
}

# health bands
HEALTHY = 75      # >= this: operating normally, don't call out a driver
DEGRADED = 45     # >= this and < HEALTHY: degraded; < this: critical


def explain(health: float, attribution: dict, alert: bool) -> dict:
    """Return {'explanation': str, 'primary_driver': role|None}."""
    if not attribution:
        return {"explanation": "No metric data.", "primary_driver": None}

    # dominant metric + its share
    driver, share = max(attribution.items(), key=lambda kv: kv[1])
    name, _ = PHRASE.get(driver, (driver, driver))

    # healthy: don't invent a cause
    if health >= HEALTHY and not alert:
        return {"explanation": "Operating normally.", "primary_driver": None}

    # severity word
    if health < DEGRADED:
        sev = "critical"
        word = "of the failure"
    else:
        sev = "degraded"
        word = "of the degradation"

    # only name a single driver if it clearly dominates; else say "multiple metrics"
    others = sorted([(v, k) for k, v in attribution.items() if k != driver], reverse=True)
    second = others[0] if others else (0, None)

    def sent(s):  # sentence-case without lowercasing acronyms like CPU
        return s[0].upper() + s[1:] if s else s
    if share >= 50:
        line = f"{sent(name)} drives {share}% {word}."
        if second[0] >= 25:
            sname = PHRASE.get(second[1], (second[1], ""))[1]
            line += f" {sent(sname)}."
    elif share >= 35:
        line = f"{sent(name)} is the largest factor at {share}%, but multiple metrics contribute."
    else:
        line = f"Multiple metrics contribute; {name} leads at {share}%."

    # alert-but-healthy-looking: early warning phrasing (prepend, keep main line intact)
    if alert and health >= DEGRADED:
        line = f"Early warning: {name} is anomalous before it shows in headroom. " + line

    return {"explanation": line, "primary_driver": driver}


if __name__ == "__main__":
    # demo the phrasing across scenarios
    cases = [
        (93, {"hrProcessorLoad": 68, "hrStorageUsed": 30, "ifInErrors": 2}, False),
        (41, {"hrStorageUsed": 71, "hrProcessorLoad": 20, "ifInErrors": 9}, True),
        (24, {"hrStorageUsed": 52, "ifInErrors": 30, "hrProcessorLoad": 18}, True),
        (58, {"ifInErrors": 40, "hrProcessorLoad": 35, "hrStorageUsed": 25}, False),
        (80, {"hrProcessorLoad": 55, "hrStorageUsed": 25, "ifInErrors": 20}, True),
    ]
    for h, a, al in cases:
        r = explain(h, a, al)
        print(f"health {h:>3} alert={str(al):<5} -> {r['explanation']}")
