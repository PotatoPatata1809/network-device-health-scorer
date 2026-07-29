"""
Forecast — time to critical. The "when" in "what fails, when, and what breaks."

Fits a trend to a device's recent health decline and extends it to the critical
line. Honest about its limits:

  - GRADUAL failure (leak, error creep): health trends down -> we extrapolate to
    critical and report "~4h". This is the win: warning before the device fails.
  - SUDDEN failure (spike, reboot): no meaningful trend -> no forecast. We say
    "no clear trend" rather than invent a number. You cannot forecast an instant.
  - IMPROVING / flat: health rising or steady -> "stable", no forecast.

Method (deliberately simple + explainable — linear regression on recent health):
  1. take the last LOOKBACK health points.
  2. fit a straight line (slope = health points lost per sample).
  3. if slope is meaningfully negative AND the fit is clean (R^2 high enough),
     project to CRITICAL and convert samples -> time.
  4. otherwise report stable / sudden / no-trend.

Sample spacing assumed 5 min (SMD/NAB). Configurable for real poll rates.

Adds to the shared record:
  "forecast": {"status": "degrading", "eta_hours": 4.2, "slope_per_hr": -3.1,
               "confidence": 0.88}
"""
import numpy as np

LOOKBACK = 60          # recent samples to fit (~5h at 5-min)
SAMPLE_MIN = 5         # minutes per sample
CRITICAL = 20          # health level treated as "failed"
MIN_SLOPE = 0.05       # health pts/sample; below this = effectively flat
MIN_R2 = 0.5           # fit must be at least this clean to trust the trend
MAX_ETA_HRS = 72       # don't forecast absurdly far out


def forecast(health_series, sample_min=SAMPLE_MIN):
    """health_series: list/array of recent health values (oldest->newest).
    Returns forecast dict."""
    h = np.asarray(health_series, float)
    h = h[~np.isnan(h)]
    if len(h) < 10:
        return {"status": "insufficient_data", "eta_hours": None,
                "slope_per_hr": None, "confidence": None}

    recent = h[-LOOKBACK:]
    x = np.arange(len(recent))
    # linear fit
    slope, intercept = np.polyfit(x, recent, 1)
    pred = slope * x + intercept
    ss_res = np.sum((recent - pred) ** 2)
    ss_tot = np.sum((recent - recent.mean()) ** 2) or 1e-9
    r2 = 1 - ss_res / ss_tot

    per_hr = slope * (60 / sample_min)      # health pts lost per hour
    now = recent[-1]

    # improving or flat
    if slope >= -MIN_SLOPE:
        status = "improving" if slope > MIN_SLOPE else "stable"
        return {"status": status, "eta_hours": None,
                "slope_per_hr": round(per_hr, 2), "confidence": round(max(r2, 0), 2)}

    # declining but noisy -> can't trust a straight-line ETA
    if r2 < MIN_R2:
        return {"status": "declining_unclear", "eta_hours": None,
                "slope_per_hr": round(per_hr, 2), "confidence": round(max(r2, 0), 2)}

    # clean decline -> project to critical
    if now <= CRITICAL:
        return {"status": "critical_now", "eta_hours": 0.0,
                "slope_per_hr": round(per_hr, 2), "confidence": round(r2, 2)}
    samples_to_crit = (now - CRITICAL) / (-slope)
    eta_hrs = samples_to_crit * sample_min / 60
    if eta_hrs > MAX_ETA_HRS:
        return {"status": "declining_slow", "eta_hours": None,
                "slope_per_hr": round(per_hr, 2), "confidence": round(r2, 2)}
    return {"status": "degrading", "eta_hours": round(eta_hrs, 1),
            "slope_per_hr": round(per_hr, 2), "confidence": round(r2, 2)}


def forecast_device(metric_health_series, sample_min=SAMPLE_MIN):
    """Forecast on the PRIMARY DRIVER metric's own health trajectory (headroom to its
    ceiling), not the blunt worst-metric composite. This surfaces a gradual leak in
    one metric even when another metric dominates the composite 'worst'. The driver
    is chosen upstream by the health engine's attribution; feed that metric's
    per-sample headroom-health here.
    """
    return forecast(metric_health_series, sample_min)


def human(fc):
    s = fc["status"]
    if s == "degrading":
        return f"~{fc['eta_hours']}h to critical"
    return {"improving": "Recovering", "stable": "Stable",
            "declining_unclear": "Declining (no clear ETA)",
            "declining_slow": "Slowly declining",
            "critical_now": "Critical now",
            "insufficient_data": "—"}.get(s, s)


if __name__ == "__main__":
    # test scenarios
    def line(start, slope, n=60, noise=0.0):
        x = np.arange(n)
        return np.clip(start + slope * x + np.random.normal(0, noise, n), 0, 100)
    np.random.seed(1)
    tests = {
        "clean leak (steady decline)": line(85, -1.1, noise=1.5),
        "steep decline":              line(70, -2.5, noise=1.0),
        "healthy stable":             line(90, 0.0, noise=1.0),
        "recovering":                 line(50, 1.2, noise=1.0),
        "noisy no-trend":             line(60, -0.2, noise=15),
        "already critical":           line(25, -1.0, noise=1.0),
    }
    for name, series in tests.items():
        fc = forecast(series)
        print(f"{name:<32} -> {human(fc):<24} {fc}")
