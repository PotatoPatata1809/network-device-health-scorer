# NetPulse

**Network Device Health Scorer — Synergy 2026 (HPE), Problem Statement #12**

> We don't just score health — we tell you what will fail, when, and what breaks with it.

Team T009 · TrekTech — Aakash Kushwaha (lead) · Aman Behera · Tamanna Khanna · Kanishka Gupta

---

## What this is

Up/down monitoring reports a device as healthy right up until it dies. A slow memory leak,
an interface error rate creeping upward, a device silently rebooting every few hours — all
three are invisible to a poller that only asks "is it reachable?"

NetPulse scores every device on three independent signals and multiplies them into a single
ranked action list:

| Signal | Question it answers | How |
|---|---|---|
| **Health** | How bad is it? | Isolation Forest learns each device's own baseline; we score deviation from *its* normal, never a shared threshold |
| **Urgency** | How long have I got? | Trend extrapolation on the degrading metric → "crosses critical in ~4h" |
| **Impact** | What breaks with it? | Graph walk over the topology → "15 devices go dark if this fails" |

The output isn't a wall of equal-looking alerts. It's an ordered list of what to touch first.

---

## Result

**96% recall against human-labelled ground truth, at a 1.9% alert budget.**

| Detector | Windows caught | Recall | Flags | Flag rate |
|---|---|---|---|---|
| **Isolation Forest + derived features** | 23 / 24 | **96%** | 1,039 | **1.9%** |
| Classical rolling 3σ threshold | 21 / 24 | 88% | 1,023 | 1.9% |

Reproduce it:

```bash
python scripts/rolling_features_eval.py
```

**Read the flag rate, not just the recall.** The two detectors are held to the same alert
budget — each device's budget is set to that device's own rolling-sigma flag rate, so the
model may raise exactly as many alerts as the classical method and no more. The recall
difference is therefore detection quality, not alert volume.

We enforce this because we learned it the hard way. An earlier run of ours hit 84% recall by
flagging 90% of all rows. Recall alone is gameable. Every number in this repository is
quoted with its flag rate.

---

## Data

Metrics are real. Failures are real. We did not invent a single anomaly.

- **Source:** [Numenta Anomaly Benchmark](https://github.com/numenta/NAB) — `realAWSCloudwatch`
- **Content:** real AWS server telemetry with human-labelled ground-truth anomaly windows
- **Scale:** 15 devices × ~4,000 readings ≈ 60,000 real points · ~14 days per stream · 25 labelled windows
- **Mapping:** `scripts/device_map.json` maps 15 named network devices to 15 real NAB streams
- **Replay:** 1 second of demo time ≈ 30 minutes of real telemetry (30× compression)

### What is synthetic — stated up front

**Topology is synthetic.** No public dataset ships a network graph alongside labelled
telemetry, so `topology.json` is authored by us: 20 devices across 4 tiers, using standard
core / distribution / access naming plus router, firewall and wireless-controller roles.

**15 devices carry independent real NAB streams; 5 leaf devices replay time-offset copies
purely to populate the topology.** Those 5 exist only for blast radius, the what-if map and
alert suppression. They enter no recall number in this repository.

### Why replay and not live SNMP

Live polling of healthy lab devices produces no anomalies to detect and no labels to be
judged against. Replay gives a reproducible failure with a known right answer, which is the
only way to put an honest number on detection accuracy.

Architecturally the source doesn't matter: every metric travels under its real SNMP object
name — `ifInErrors`, `hrProcessorLoad`, `hrStorageUsed`, `sysUpTime`, `ifOperStatus` — through
a pluggable collector. Swapping the replay collector for a live `pysnmp` poller changes one
class and nothing downstream.

---

## How we got to 96%

Six experiments. Every one is still in this repository, including the two the classical
method won.

| # | Script | Method | Result | What it taught us |
|---|---|---|---|---|
| 1 | `poc_anomaly.py` | Isolation Forest, full stream | 88% | Optimistic by construction — trained and scored on the same data |
| 2 | `baseline_threshold.py` | Static mean ± 3σ, full stream | 76% | One global rule is blind on quiet devices, screaming on noisy ones: `acc-sw-01` flagged 0 times, `dist-sw-01` flagged 180 to catch 2 |
| 3 | `split_eval.py` | Temporal split, both detectors | 84% / 84% | A frozen early baseline goes stale over 14 drifting days. Both degenerated into flagging everything. **Recall alone is gameable** |
| 4 | `rolling_eval.py` | Rolling 24h baseline, both | 92% / 88% | Not a clean win — one extra window for 3× the alerts |
| 5 | matched budget, first try | contamination → 0.006 | 83% / 88% | **The model lost.** Fed a single column, there is nothing to isolate with — on univariate data 3σ is near-optimal and correctly won |
| 6 | `rolling_features_eval.py` | Derived features + per-device budget | **96% / 88%** | Give the forest dimensions it can use, hold it to the same budget, and it wins honestly |

**The insight that changed the project:** a static threshold is not one method. It is a
formula plus a hidden choice of what "normal" is measured over. The same three lines of
arithmetic produced 76%, 84% and 88% depending only on that choice. That is precisely the
argument for letting each device learn its own baseline.

**Run 6 features** (all trailing-only, no look-ahead): `value` · `delta` (rate of change) ·
deviation from rolling mean · volatility. The classical baseline stays univariate on `value`
on purpose — improving it would make the comparison meaningless.

Two bugs found and fixed en route, both preserved in the commit history:
`round()` drove `core-sw-01`'s budget to zero flags and silenced it entirely (fixed with a
floor of 1 flag per chunk); and flat stretches produce identical anomaly scores, so flagging
every tie blew the budget — `srv-mon-01` took 542 flags against a budget of 107 (fixed with
exact rank selection).

---

## Repository layout

```
topology.json                       20 devices, 4 tiers, parent/child graph
scripts/
  device_map.json                   15 devices → 15 NAB streams
  poc_anomaly.py                    run 1 — first proof of concept
  baseline_threshold.py             run 2 — classical static threshold
  split_eval.py                     run 3 — temporal split, both detectors
  rolling_eval.py                   run 4 — rolling baseline, both detectors
  rolling_features_eval.py          run 6 — FINAL: 96% vs 88% at matched budget
docs/
  mockup.html                       working console mockup
  REMEDIES.md                       12-rule symptom → cause → action table
  architecture.svg                  5-layer system diagram
```

Nothing is deleted. The progression from naive to static baseline to temporal split to
rolling window to derived features is the reasoning, and it is meant to be read in order.

---

## Running it

```bash
python -m venv venv && source venv/bin/activate
pip install pandas scikit-learn networkx

# fetch NAB into data/ — see https://github.com/numenta/NAB
python scripts/rolling_features_eval.py     # the headline result
python scripts/baseline_threshold.py        # the classical comparison
```

Every script prints a per-device table and a totals line. No arguments, no config.

---

## Architecture

```
NAB data  →  replay engine  →  scoring core  →  Supabase  →  Next.js console
             (pluggable        (IsolationForest,  (Postgres +   (Tailwind,
              collector,        trend forecast,    realtime)     Recharts,
              SNMP-native       networkx blast                   React Flow,
              OIDs)             radius)                          Vercel)
```

**Topology is a first-class input.** One graph powers blast radius, the what-if failure map
and correlated alert suppression — three features from one data structure.

**BI export ready.** Scores land in Postgres, so Power BI or Grafana attach with no extra
work. Power BI is not part of the build and we don't claim it is.

---

## Status

| | Capability | Status |
|---|---|---|
| **A** | Self-baseline anomaly detection | **Built and validated** — 96% vs NAB ground truth |
| B | Blast-radius impact scoring | Designed and scheduled — 21–23 Jul |
| C | Time-to-failure forecast | Designed and scheduled — 24–26 Jul |
| D | Peer comparison vs same-role siblings | Designed and scheduled — 21–23 Jul |
| F | Explainability line per score | Designed and scheduled — 24–26 Jul |
| G | What-if failure map | Designed and scheduled — 27–28 Jul |
| H | Correlated alert suppression | Designed and scheduled — 27–28 Jul |

`docs/mockup.html` shows all seven in a working console. It is a mockup, and it is labelled
as one.

---

## Known limitations

We would rather write these down than be asked.

- **One window is missed** (23 of 24). It sits inside a low-variance stretch where the anomaly
  is small relative to the device's own noise floor, and it doesn't rank inside a 1.9% alert
  budget. Widening the budget would catch it — that trade is exactly what we refuse to make silently.
- **Isolation Forest is a validated baseline, not a final answer.** LOF, One-Class SVM and an
  ensemble are benchmarked against the same NAB labels before 31 July.
- **Root causes are expert-authored, not learned.** NAB labels anomaly *windows*, not *causes*;
  no public dataset labels causes. `docs/REMEDIES.md` is a rule table written from standard
  network operations practice. Detection is validated; diagnosis is engineered. We keep the
  two claims separate.
- **Not load-tested.** Detection is per-device and independent, so it parallelises, but we
  scoped 15 devices deliberately in order to validate accuracy properly rather than produce
  a scale number nobody had checked.
- **One metric per device today.** NAB gives one stream per file. Expanding to 3–4 metrics per
  device — so the composite score has real inputs — is the only planned data change before 31 July.

---

## Roadmap to 31 July

| Dates | Work |
|---|---|
| 21–23 Jul | Collector + scoring service live on Supabase; blast radius (B) and peer comparison (D) |
| 24–26 Jul | Next.js console wired to realtime; React Flow map; forecast (C) and explainability (F) |
| 27–28 Jul | Detector bakeoff — LOF · One-Class SVM · ensemble; what-if map (G); alert suppression (H) |
| 29–30 Jul | Freeze, final numbers, demo rehearsal — code complete a day early |
| 31 Jul | Live demonstration to the HPE panel |

---

## Team

| Member | Ownership |
|---|---|
| **Aakash Kushwaha** (lead) | Data pipeline, detection, scoring core |
| **Aman Behera** | Supabase schema, realtime, dashboard UI |
| **Tamanna Khanna** | Solution design, feature decisions, demo narrative |
| **Kanishka Gupta** | Topology modelling, documentation, QA and testing |
