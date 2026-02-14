"""
alert_engine.py
---------------
Lightweight alert engine: the Option D monitoring hook.

Rather than building full anomaly detection, this module defines
the 5 key metrics that — if monitored weekly — would have caught
the win-rate decline 6+ weeks earlier.

Designed as a production-ready foundation for Part 4 system design.
"""

import pandas as pd
from dataclasses import dataclass
from typing import Literal

AlertSeverity = Literal["CRITICAL", "WARNING", "INFO", "OK"]


@dataclass
class Alert:
    metric: str
    severity: AlertSeverity
    current_value: float
    baseline_value: float
    threshold: float
    message: str
    recommended_action: str
    dimension: str = ""
    segment: str = ""


def _z_score(current: float, baseline: float, std: float) -> float:
    if std < 1e-9:
        return 0.0
    return (current - baseline) / std


def _severity(z: float) -> AlertSeverity:
    az = abs(z)
    if az >= 2.5:
        return "CRITICAL"
    elif az >= 1.5:
        return "WARNING"
    elif az >= 1.0:
        return "INFO"
    return "OK"


# ─────────────────────────────────────────────
# The 5 Monitored Metrics
# ─────────────────────────────────────────────


def alert_overall_win_rate(df: pd.DataFrame) -> Alert:
    """Alert 1: Overall quarterly win rate vs rolling baseline."""
    q_wr = df.groupby("created_quarter")["won"].mean().sort_index()
    baseline = q_wr.iloc[:-1].mean()
    std = q_wr.iloc[:-1].std()
    current = q_wr.iloc[-1]
    z = _z_score(current, baseline, std)
    sev = _severity(z)
    return Alert(
        metric="Overall Win Rate",
        severity=sev,
        current_value=round(current, 4),
        baseline_value=round(baseline, 4),
        threshold=round(baseline - 1.5 * std, 4),
        message=(
            f"Win rate is {current:.1%} vs baseline {baseline:.1%} " f"(z={z:.2f})"
        ),
        recommended_action=(
            "Trigger full driver analysis to identify root cause."
            if sev in ("CRITICAL", "WARNING")
            else "No action required."
        ),
    )


def alert_segment_win_rates(
    df: pd.DataFrame,
    dimension: str = "region",
) -> list[Alert]:
    """Alert 2: Per-segment win rate drops vs rolling baseline."""
    alerts = []
    for seg in df[dimension].unique():
        seg_df = df[df[dimension] == seg]
        q_wr = seg_df.groupby("created_quarter")["won"].mean().sort_index()
        if len(q_wr) < 3:
            continue
        baseline = q_wr.iloc[:-1].mean()
        std = max(q_wr.iloc[:-1].std(), 0.02)  # floor at 2pp
        current = q_wr.iloc[-1]
        z = _z_score(current, baseline, std)
        sev = _severity(z)
        if sev != "OK":
            alerts.append(
                Alert(
                    metric=f"Win Rate ({dimension})",
                    severity=sev,
                    current_value=round(current, 4),
                    baseline_value=round(baseline, 4),
                    threshold=round(baseline - 1.5 * std, 4),
                    message=f"{dimension}={seg}: {current:.1%} vs baseline {baseline:.1%}",
                    recommended_action=f"Investigate {dimension} '{seg}' pipeline health.",
                    dimension=dimension,
                    segment=seg,
                )
            )
    return sorted(alerts, key=lambda a: a.current_value - a.baseline_value)


def alert_deal_velocity(df: pd.DataFrame) -> Alert:
    """Alert 3: Average sales cycle days vs baseline."""
    q_cycle = df.groupby("created_quarter")["sales_cycle_days"].mean().sort_index()
    baseline = q_cycle.iloc[:-1].mean()
    std = max(q_cycle.iloc[:-1].std(), 3.0)
    current = q_cycle.iloc[-1]
    z = _z_score(current, baseline, std)
    sev = _severity(z)
    return Alert(
        metric="Average Sales Cycle (days)",
        severity=sev,
        current_value=round(current, 1),
        baseline_value=round(baseline, 1),
        threshold=round(baseline + 1.5 * std, 1),
        message=f"Avg cycle {current:.0f}d vs baseline {baseline:.0f}d (z={z:.2f})",
        recommended_action=(
            "Check for stage stalling — run stage velocity report."
            if sev in ("CRITICAL", "WARNING")
            else "Deal velocity normal."
        ),
    )


def alert_pipeline_volume(df: pd.DataFrame) -> Alert:
    """Alert 4: New deals created per quarter vs baseline."""
    q_vol = df.groupby("created_quarter")["deal_id"].count().sort_index()
    baseline = q_vol.iloc[:-1].mean()
    std = max(q_vol.iloc[:-1].std(), 10.0)
    current = q_vol.iloc[-1]
    z = _z_score(current, baseline, std)
    sev = _severity(z)
    return Alert(
        metric="Pipeline Volume (deals/quarter)",
        severity=sev,
        current_value=int(current),
        baseline_value=round(baseline, 1),
        threshold=round(baseline - 1.5 * std, 1),
        message=f"{current:.0f} deals vs baseline {baseline:.0f} (z={z:.2f})",
        recommended_action=(
            "Check lead source volumes — are inbound/outbound channels declining?"
            if sev in ("CRITICAL", "WARNING")
            else "Pipeline volume stable."
        ),
    )


def alert_rep_performance_spread(df: pd.DataFrame) -> Alert:
    """Alert 5: Rep performance divergence index — is the gap widening?"""
    rep_q = df.groupby(["created_quarter", "sales_rep_id"])["won"].mean().reset_index()
    rep_q.columns = ["quarter", "rep", "wr"]

    def spread(g):
        return g["wr"].quantile(0.75) - g["wr"].quantile(0.25)

    q_spread = rep_q.groupby("quarter").apply(spread).sort_index()
    if len(q_spread) < 3:
        return Alert(
            metric="Rep Performance Spread",
            severity="INFO",
            current_value=0,
            baseline_value=0,
            threshold=0,
            message="Not enough quarters to compute spread trend.",
            recommended_action="Collect more data.",
        )
    baseline = q_spread.iloc[:-1].mean()
    std = max(q_spread.iloc[:-1].std(), 0.02)
    current = q_spread.iloc[-1]
    z = _z_score(current, baseline, std)
    sev = _severity(z)
    return Alert(
        metric="Rep Win Rate Spread (IQR)",
        severity=sev,
        current_value=round(current, 4),
        baseline_value=round(baseline, 4),
        threshold=round(baseline + 1.5 * std, 4),
        message=(
            f"Top-bottom rep gap: {current:.1%} vs baseline {baseline:.1%} (z={z:.2f})"
        ),
        recommended_action=(
            "Widening rep performance gap detected — prioritise coaching for bottom quartile."
            if sev in ("CRITICAL", "WARNING")
            else "Rep performance spread stable."
        ),
    )


# ─────────────────────────────────────────────
# Master Alert Runner
# ─────────────────────────────────────────────


def run_all_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run all 5 alert checks and return a prioritised alert report.
    This is the function the scheduler would call in production.
    """
    alerts: list[Alert] = []

    alerts.append(alert_overall_win_rate(df))
    alerts.extend(alert_segment_win_rates(df, "region"))
    alerts.extend(alert_segment_win_rates(df, "industry"))
    alerts.append(alert_deal_velocity(df))
    alerts.append(alert_pipeline_volume(df))
    alerts.append(alert_rep_performance_spread(df))

    rows = []
    for a in alerts:
        rows.append(
            {
                "severity": a.severity,
                "metric": a.metric,
                "segment": a.segment,
                "current": a.current_value,
                "baseline": a.baseline_value,
                "message": a.message,
                "action": a.recommended_action,
            }
        )

    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2, "OK": 3}
    result = pd.DataFrame(rows)
    result["_order"] = result["severity"].map(severity_order)
    return result.sort_values("_order").drop(columns="_order").reset_index(drop=True)
