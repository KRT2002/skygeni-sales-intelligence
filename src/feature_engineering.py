"""
feature_engineering.py
-----------------------
Computes all standard + custom metrics used in analysis and modelling.

Custom Metrics Defined Here:
  1. win_rate_momentum      - Rate of change of win rate (acceleration / deceleration)
  2. deal_mix_shift_index   - How much pipeline composition changed vs baseline
  3. rep_divergence_index   - Gap between top/bottom-quartile rep performance
  4. stage_velocity_score   - How fast/slow deals move vs historical average
  5. lead_source_decay      - Change in quality premium per lead source over time
"""

import pandas as pd
import numpy as np
from src.data_loader import load_raw, add_time_features, PROCESSED_PATH

# ─────────────────────────────────────────────
# Standard derived features
# ─────────────────────────────────────────────


def add_deal_size_band(df: pd.DataFrame) -> pd.DataFrame:
    """Bin deal_amount into Small / Mid / Large / Enterprise tiers."""
    df = df.copy()
    df["deal_size_band"] = pd.cut(
        df["deal_amount"],
        bins=[0, 10_000, 30_000, 60_000, 1_000_000],
        labels=["Small (<10K)", "Mid (10-30K)", "Large (30-60K)", "Enterprise (60K+)"],
    )
    return df


def add_cycle_band(df: pd.DataFrame) -> pd.DataFrame:
    """Bin sales_cycle_days into speed tiers."""
    df = df.copy()
    df["cycle_band"] = pd.cut(
        df["sales_cycle_days"],
        bins=[0, 20, 45, 80, 200],
        labels=["Fast (<20d)", "Normal (20-45d)", "Slow (45-80d)", "Stalled (80d+)"],
    )
    return df


def add_rep_win_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Historical win rate per rep (global, not time-sliced)."""
    df = df.copy()
    rep_wr = df.groupby("sales_rep_id")["won"].mean().rename("rep_win_rate")
    df = df.merge(rep_wr, on="sales_rep_id", how="left")
    return df


def add_rep_quartile(df: pd.DataFrame) -> pd.DataFrame:
    """Assign each rep to performance quartile based on their win rate."""
    df = df.copy()
    if "rep_win_rate" not in df.columns:
        df = add_rep_win_rate(df)
    rep_wr = df[["sales_rep_id", "rep_win_rate"]].drop_duplicates()
    rep_wr["rep_quartile"] = pd.qcut(
        rep_wr["rep_win_rate"], q=4, labels=["Q4 (Bottom)", "Q3", "Q2", "Q1 (Top)"]
    )
    df = df.merge(
        rep_wr[["sales_rep_id", "rep_quartile"]], on="sales_rep_id", how="left"
    )
    return df


# ─────────────────────────────────────────────
# Custom Metric 1 – Win Rate Momentum Score
# ─────────────────────────────────────────────


def compute_win_rate_momentum(df: pd.DataFrame, window: int = 2) -> pd.DataFrame:
    """
    Win Rate Momentum Score
    -----------------------
    Measures the *direction and speed* of win rate change rather than
    the absolute level. A score of -0.12 means win rate has been falling
    at ~12pp per period. Normalised by rolling std to surface unusual swings.

    Formula:
        raw_slope = (wr_t - wr_{t-window}) / window
        momentum  = raw_slope / rolling_std(wr, window+2)   [z-score of slope]

    Returns a per-quarter DataFrame with:
        quarter | win_rate | momentum_raw | momentum_score
    """
    q_wr = (
        df.groupby("created_quarter")["won"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "win_rate", "count": "deals"})
        .sort_index()
    )
    q_wr["momentum_raw"] = q_wr["win_rate"].diff(window)
    rolling_std = q_wr["win_rate"].rolling(window + 2, min_periods=2).std()
    rolling_std = rolling_std.replace(0, np.nan)
    q_wr["momentum_score"] = q_wr["momentum_raw"] / rolling_std
    return q_wr.reset_index()


# ─────────────────────────────────────────────
# Custom Metric 2 – Deal Mix Shift Index
# ─────────────────────────────────────────────


def compute_deal_mix_shift(
    df: pd.DataFrame,
    dimension: str,
    baseline_period: str = "2023",
    comparison_period: str = "2024Q1",
) -> pd.DataFrame:
    """
    Deal Mix Shift Index
    --------------------
    Quantifies how much the *composition* of the pipeline changed between
    two periods. This separates "we converted worse" from "we started
    chasing harder deals" (Simpson's Paradox guard).

    For each segment value:
        shift = weight_comparison - weight_baseline

    Positive = grew as share of pipeline
    Negative = shrunk as share of pipeline

    Also computes `expected_wr_if_mix_unchanged` to show the hypothetical
    win rate under the baseline mix — isolating pure conversion vs mix effect.
    """
    base = df[df["period"] == baseline_period]
    comp = df[df["period"] == comparison_period]

    base_mix = base[dimension].value_counts(normalize=True).rename("base_share")
    comp_mix = comp[dimension].value_counts(normalize=True).rename("comp_share")
    base_wr = base.groupby(dimension)["won"].mean().rename("base_win_rate")
    comp_wr = comp.groupby(dimension)["won"].mean().rename("comp_win_rate")

    mix = pd.concat([base_mix, comp_mix, base_wr, comp_wr], axis=1).fillna(0)
    mix["mix_shift"] = mix["comp_share"] - mix["base_share"]
    mix["wr_change"] = mix["comp_win_rate"] - mix["base_win_rate"]

    # Hypothetical: apply base win rates to new mix
    mix["expected_wr_new_mix"] = (mix["comp_share"] * mix["base_win_rate"]).sum()

    # Decompose: how much of overall wr change is mix vs conversion?
    overall_base_wr = base["won"].mean()
    overall_comp_wr = comp["won"].mean()
    mix_effect = mix["expected_wr_new_mix"].iloc[0] - overall_base_wr
    conversion_effect = overall_comp_wr - mix["expected_wr_new_mix"].iloc[0]

    mix.attrs["mix_effect"] = round(mix_effect, 4)
    mix.attrs["conversion_effect"] = round(conversion_effect, 4)
    mix.attrs["overall_wr_change"] = round(overall_comp_wr - overall_base_wr, 4)

    return mix.reset_index().rename(columns={dimension: "segment"})


# ─────────────────────────────────────────────
# Custom Metric 3 – Rep Performance Divergence Index
# ─────────────────────────────────────────────


def compute_rep_divergence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rep Performance Divergence Index
    ---------------------------------
    Tracks the gap between top-quartile and bottom-quartile rep win rates
    over time. A widening gap signals a coaching / enablement problem;
    a narrowing gap may mean top performers are declining.

    Returns per-quarter:
        quarter | top_q_wr | bottom_q_wr | divergence_index | overall_wr
    """
    if "rep_win_rate" not in df.columns:
        df = add_rep_win_rate(df)

    # Per rep per quarter
    rep_q = (
        df.groupby(["created_quarter", "sales_rep_id"])["won"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "wr", "count": "deals"})
    )
    # Only reps with ≥5 deals in that quarter for stability
    rep_q = rep_q[rep_q["deals"] >= 5]

    def divergence(g):
        top = g["wr"].quantile(0.75)
        bottom = g["wr"].quantile(0.25)
        return pd.Series(
            {
                "top_q_wr": top,
                "bottom_q_wr": bottom,
                "divergence_index": top - bottom,
                "overall_wr": g["wr"].mean(),
                "rep_count": len(g),
            }
        )

    result = rep_q.groupby("created_quarter").apply(divergence).reset_index()
    return result


# ─────────────────────────────────────────────
# Custom Metric 4 – Stage Velocity Score
# ─────────────────────────────────────────────


def compute_stage_velocity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage Velocity Degradation Score
    ----------------------------------
    Compares current average sales_cycle_days against the historical
    baseline (2023 average) for each deal stage.

    velocity_score > 0 : deals moving FASTER than baseline (good)
    velocity_score < 0 : deals moving SLOWER (stalling signal)

    Also weights by that stage's impact on win rate to produce a
    business-impact-adjusted score.
    """
    baseline = df[df["period"] == "2023"]
    current = df[df["period"] == "2024Q1"]

    base_cycle = (
        baseline.groupby("deal_stage")["sales_cycle_days"]
        .mean()
        .rename("base_avg_days")
    )
    curr_cycle = (
        current.groupby("deal_stage")["sales_cycle_days"].mean().rename("curr_avg_days")
    )
    stage_wr = baseline.groupby("deal_stage")["won"].mean().rename("stage_win_rate")

    velocity = pd.concat([base_cycle, curr_cycle, stage_wr], axis=1).dropna()
    velocity["days_delta"] = velocity["curr_avg_days"] - velocity["base_avg_days"]
    velocity["velocity_score"] = -velocity["days_delta"]  # negative delta = good
    velocity["weighted_impact"] = (
        velocity["velocity_score"] * velocity["stage_win_rate"]
    )
    return velocity.reset_index().rename(columns={"deal_stage": "stage"})


# ─────────────────────────────────────────────
# Custom Metric 5 – Lead Source Quality Decay
# ─────────────────────────────────────────────


def compute_lead_source_decay(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lead Source Quality Decay
    --------------------------
    Tracks how the win-rate PREMIUM of each lead source (relative to the
    overall win rate) has changed over time.

    premium = lead_source_wr - overall_wr_that_quarter

    A shrinking premium in Referral means the best channel is weakening.
    All channels decaying together → product/market problem.
    Only one channel decaying → channel-specific investigation.
    """
    q_overall = df.groupby("created_quarter")["won"].mean().rename("overall_wr")
    q_source = (
        df.groupby(["created_quarter", "lead_source"])["won"].mean().rename("source_wr")
    )

    decay = q_source.reset_index().merge(q_overall.reset_index(), on="created_quarter")
    decay["premium"] = decay["source_wr"] - decay["overall_wr"]
    return decay


# ─────────────────────────────────────────────
# Master pipeline
# ─────────────────────────────────────────────


def build_engineered_dataset(save: bool = True) -> pd.DataFrame:
    """
    Run the full feature engineering pipeline and optionally persist to disk.
    This is the single entry point used by notebooks.
    """
    df = load_raw()
    df = add_time_features(df)
    df = add_deal_size_band(df)
    df = add_cycle_band(df)
    df = add_rep_win_rate(df)
    df = add_rep_quartile(df)

    if save:
        PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(PROCESSED_PATH, index=False)
        print(f"[feature_engineering] Saved engineered dataset → {PROCESSED_PATH}")

    return df


if __name__ == "__main__":
    build_engineered_dataset()
