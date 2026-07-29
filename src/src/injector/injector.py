"""
NetPulse failure injector — engineered failure scenarios for the LIVE DEMO and
for testing forecast / blast-radius / suppression features.

HONESTY BOUNDARY: injected failures are NOT real anomalies. They are engineered
scenarios used to (a) trigger the pipeline live on demo day and (b) test features
that need a controllable degrading trend. Detection ACCURACY is validated
separately against real human-labelled anomalies (NAB/SMD) — never against
injected data. Keep those two claims apart.

Scenarios ride on a device's REAL replayed SMD column so the pipeline sees a real
schema and a plausible signal. The `realism` dial controls how much the injected
shape blends with the real underlying data:
    realism = 1.0  -> leak grows ON TOP of the real column (jittery, believable)
    realism = 0.0  -> leak REPLACES the column with a clean synthetic ramp (crisp on screen)
    0 < realism < 1 -> blend of the two

Modes:
    stream  -> yields (row_index, value, injected_flag) at a watchable pace for the demo
    offline -> returns the full modified column as a numpy array for testing/CSV output
"""

import time
import numpy as np
import pandas as pd


# ---------------------------------------------------------------- scenarios ---
def _memory_leak(base: np.ndarray, start: int, realism: float,
                 climb_to: float = 1.0, ramp_frac: float = 0.6,
                 ramp_samples: int = None) -> np.ndarray:
    """Monotonic climb from onset to `climb_to`. Ramp length = ramp_samples if given
    (watchable demo window), else ramp_frac of the remaining stream. This is the demo
    hero: green -> amber -> red as memory creeps up with no plateau."""
    out = base.astype(float).copy()
    n = len(base)
    ramp_len = ramp_samples if ramp_samples else max(1, int((n - start) * ramp_frac))
    onset_level = float(np.median(base[max(0, start - 50):start + 1])) if start > 0 else float(base[0])

    for i in range(start, n):
        prog = min(1.0, (i - start) / ramp_len)          # 0 -> 1 across the ramp
        # smootherstep for an organic accelerating-then-easing climb
        s = prog * prog * prog * (prog * (prog * 6 - 15) + 10)
        synth = onset_level + (climb_to - onset_level) * s
        # blend: realism=1 -> keep real wiggle and add the climb delta on top;
        #        realism=0 -> pure synthetic ramp
        climbed_on_real = base[i] + (synth - onset_level)
        out[i] = realism * climbed_on_real + (1.0 - realism) * synth
    return np.clip(out, 0.0, 1.0)


def _error_creep(base, start, realism, peak=0.8, ramp_frac=0.6, ramp_samples=None):
    """Interface errors rising from ~0: rare spikes that grow more frequent/large."""
    out = base.astype(float).copy()
    n = len(base)
    ramp_len = ramp_samples if ramp_samples else max(1, int((n - start) * ramp_frac))
    rng = np.random.default_rng(42)
    for i in range(start, n):
        prog = min(1.0, (i - start) / ramp_len)
        rate = prog                                       # spike probability grows
        spike = rng.random() < (0.05 + 0.4 * rate)
        synth = (peak * rate * rng.random()) if spike else base[i]
        out[i] = realism * (base[i] + synth) + (1.0 - realism) * synth
    return np.clip(out, 0.0, 1.0)


def _cpu_spike(base, start, realism, level=0.95, width=40, ramp_samples=None):
    width = ramp_samples or width
    """Sudden sustained CPU jump — the fast failure. One frame to high, holds."""
    out = base.astype(float).copy()
    end = min(len(base), start + width)
    for i in range(start, end):
        synth = level
        out[i] = realism * max(base[i], level * 0.9) + (1.0 - realism) * synth
    return np.clip(out, 0.0, 1.0)


def _reboot_loop(base, start, realism, period=60, cycles=6):
    """Uptime-style sawtooth: climbs then drops to zero, repeatedly."""
    out = base.astype(float).copy()
    for c in range(cycles):
        s = start + c * period
        e = min(len(base), s + period)
        if s >= len(base):
            break
        for i in range(s, e):
            synth = (i - s) / period                      # ramp 0..1 then reset
            out[i] = realism * synth + (1.0 - realism) * synth
    return np.clip(out, 0.0, 1.0)


SCENARIOS = {
    "memory_leak": _memory_leak,
    "error_creep": _error_creep,
    "cpu_spike": _cpu_spike,
    "reboot_loop": _reboot_loop,
}


# --------------------------------------------------------------- public API ---
def inject(column: np.ndarray, scenario: str = "memory_leak",
           onset_frac: float = 0.45, realism: float = 1.0,
           ramp_samples: int = None) -> np.ndarray:
    """Return a modified copy of `column` with `scenario` injected from onset_frac.
    onset_frac: where the failure begins, as a fraction of the stream length.
    ramp_samples: for memory_leak, absolute ramp length (watchable demo window)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {list(SCENARIOS)}")
    start = int(len(column) * onset_frac)
    if ramp_samples and scenario in ("memory_leak", "error_creep", "cpu_spike"):
        return SCENARIOS[scenario](np.asarray(column, float), start, realism, ramp_samples=ramp_samples)
    return SCENARIOS[scenario](np.asarray(column, float), start, realism)


def stream(column: np.ndarray, scenario: str = "memory_leak",
           onset_frac: float = 0.45, realism: float = 1.0,
           window: int = 300, fps: float = 12.0, tail: int = 200):
    """Generator for the live demo. Emits the last `window` points, advancing one
    row per frame at `fps`, starting `tail` points before onset so the panel sees
    the healthy baseline first, then the failure build. Yields dicts."""
    modified = inject(column, scenario, onset_frac, realism)
    start = int(len(column) * onset_frac)
    begin = max(0, start - tail)
    delay = 1.0 / fps
    for i in range(begin, len(modified)):
        lo = max(0, i - window + 1)
        yield {
            "row": i,
            "value": float(modified[i]),
            "injected": i >= start,
            "onset": start,
            "window": modified[lo:i + 1].tolist(),
        }
        time.sleep(delay)


# ------------------------------------------------------------------- demo -----
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NetPulse failure injector")
    ap.add_argument("--machine", default="machine-1-1")
    ap.add_argument("--dim", type=int, default=1, help="1-indexed column to inject into")
    ap.add_argument("--scenario", default="memory_leak", choices=list(SCENARIOS))
    ap.add_argument("--realism", type=float, default=1.0)
    ap.add_argument("--onset", type=float, default=0.45)
    ap.add_argument("--data", default="data/ServerMachineDataset/test")
    ap.add_argument("--check", action="store_true", help="offline: print before/after stats, no stream")
    args = ap.parse_args()

    df = pd.read_csv(f"{args.data}/{args.machine}.txt", header=None)
    col = df[args.dim - 1].to_numpy()
    mod = inject(col, args.scenario, args.onset, args.realism)
    start = int(len(col) * args.onset)

    if args.check:
        print(f"{args.machine} dim{args.dim} · {args.scenario} · realism={args.realism} · onset row {start}/{len(col)}")
        print(f"  before onset : mean={col[:start].mean():.3f}  max={col[:start].max():.3f}")
        print(f"  after  onset : real mean={col[start:].mean():.3f}  ->  injected mean={mod[start:].mean():.3f}  max={mod[start:].max():.3f}")
        # rough "is it visible" check: how far does it climb past normal
        climb = mod[start:].max() - col[:start].mean()
        print(f"  climb above baseline: {climb:+.3f}  ({'clearly visible' if climb > 0.3 else 'subtle'})")
    else:
        # tiny terminal preview of the live stream (portal will consume stream() directly)
        for frame in stream(col, args.scenario, args.onset, args.realism, fps=30):
            bar = "#" * int(frame["value"] * 40)
            tag = "LEAK" if frame["injected"] else "ok"
            print(f"row {frame['row']:5d} [{tag:4}] {frame['value']:.3f} |{bar}")
