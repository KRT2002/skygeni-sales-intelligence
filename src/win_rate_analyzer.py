"""
win_rate_analyzer.py
--------------------
Core Option B engine: Win Rate Driver Analysis.

Provides:
  - Cohort comparison (before vs after)
  - Segment-level decomposition
  - Simpson's Paradox test
  - Statistical significance testing
  - Feature importance via logistic regression
  - Plain-language insight generation
"""

import pandas as pd
import numpy as np
from scipy.stats import chi2_contingency
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import warnings

warnings.filterwarnings("ignore")

DIMENSIONS = ["region", "industry", "product_type", "lead_source"]
BASELINE = "2023"
CURRENT = "2024Q1"


# ─────────────────────────────────────────────
# 1. Cohort Win Rate Comparison
# ─────────────────────────────────────────────


def cohort_win_rates(df: pd.DataFrame) -> dict[str, float]:
    """Return overall win rate for baseline and current periods."""
    base = df[df["period"] == BASELINE]["won"].mean()
    curr = df[df["period"] == CURRENT]["won"].mean()
    return {
        "baseline_wr": round(base, 4),
        "current_wr": round(curr, 4),
        "absolute_change": round(curr - base, 4),
        "relative_change": round((curr - base) / base, 4),
    }


# ─────────────────────────────────────────────
# 2. Segment Decomposition
# ─────────────────────────────────────────────


def segment_decomposition(
    df: pd.DataFrame,
    dimension: str,
) -> pd.DataFrame:
    """
    For a given dimension, compute win rate + volume for both periods,
    rank by business impact (volume × wr_delta × avg_deal_amount).
    """
    base = df[df["period"] == BASELINE]
    curr = df[df["period"] == CURRENT]

    def agg(frame):
        return frame.groupby(dimension).agg(
            deals=("won", "count"),
            win_rate=("won", "mean"),
            avg_deal=("deal_amount", "mean"),
        )

    base_agg = agg(base).add_suffix("_base")
    curr_agg = agg(curr).add_suffix("_curr")

    result = base_agg.join(curr_agg, how="outer").fillna(0)
    result["wr_change"] = result["win_rate_curr"] - result["win_rate_base"]
    result["volume_change"] = result["deals_curr"] - result["deals_base"]

    # Revenue impact: how much revenue was lost/gained due to wr change?
    result["revenue_impact"] = (
        result["wr_change"] * result["deals_curr"] * result["avg_deal_curr"]
    )

    result["business_impact_score"] = (
        result["wr_change"].abs()
        * result["deals_curr"]
        * (result["avg_deal_curr"] / 1000)
    )

    return (
        result.reset_index()
        .rename(columns={dimension: "segment"})
        .sort_values("business_impact_score", ascending=False)
    )


# ─────────────────────────────────────────────
# 3. Statistical Significance
# ─────────────────────────────────────────────


def test_significance(
    df: pd.DataFrame,
    dimension: str,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """
    Chi-square test per segment: is the win/loss distribution
    significantly different between baseline and current period?

    Returns a DataFrame with p_value and is_significant flag per segment.
    """
    base = df[df["period"] == BASELINE]
    curr = df[df["period"] == CURRENT]

    records = []
    for seg in df[dimension].unique():
        b = base[base[dimension] == seg]
        c = curr[curr[dimension] == seg]
        if len(b) < 10 or len(c) < 10:
            continue
        table = [
            [b["won"].sum(), len(b) - b["won"].sum()],
            [c["won"].sum(), len(c) - c["won"].sum()],
        ]
        try:
            chi2, p, _, _ = chi2_contingency(table)
            records.append(
                {
                    "segment": seg,
                    "chi2": round(chi2, 3),
                    "p_value": round(p, 4),
                    "is_significant": p < alpha,
                    "base_wr": round(b["won"].mean(), 4),
                    "curr_wr": round(c["won"].mean(), 4),
                    "base_n": len(b),
                    "curr_n": len(c),
                }
            )
        except Exception:
            continue

    return pd.DataFrame(records).sort_values("p_value")


# ─────────────────────────────────────────────
# 4. Simpson's Paradox Check
# ─────────────────────────────────────────────


def simpsons_paradox_check(
    df: pd.DataFrame,
    dimension: str,
) -> dict:
    """
    Decompose the overall win rate change into:
      (a) Pure conversion effect: are we converting WORSE on same segments?
      (b) Mix shift effect: are we chasing harder-to-win segments more?

    If mix effect is large relative to total change → Simpson's Paradox risk.

    Method (Kitagawa-Oaxaca-Blinder decomposition):
        Total change = Conversion effect + Mix shift effect

        Conversion effect:
            Σ [comp_share_i × (comp_wr_i - base_wr_i)]

        Mix shift effect:
            Σ [(comp_share_i - base_share_i) × base_wr_i]
    """
    base = df[df["period"] == BASELINE]
    comp = df[df["period"] == CURRENT]

    base_mix = base[dimension].value_counts(normalize=True)
    comp_mix = comp[dimension].value_counts(normalize=True)
    base_wr = base.groupby(dimension)["won"].mean()
    comp_wr = comp.groupby(dimension)["won"].mean()

    segs = base_wr.index.union(comp_wr.index)
    results = []
    for seg in segs:
        bm = base_mix.get(seg, 0)
        cm = comp_mix.get(seg, 0)
        bw = base_wr.get(seg, 0)
        cw = comp_wr.get(seg, 0)
        conv_contrib = cm * (cw - bw)
        mix_contrib = (cm - bm) * bw
        results.append(
            {"segment": seg, "conv_contrib": conv_contrib, "mix_contrib": mix_contrib}
        )

    result_df = pd.DataFrame(results)
    total_conv_effect = result_df["conv_contrib"].sum()
    total_mix_effect = result_df["mix_contrib"].sum()
    total_change = base["won"].mean() - comp["won"].mean()  # note: negative = decline

    return {
        "dimension": dimension,
        "total_wr_change": round(comp["won"].mean() - base["won"].mean(), 4),
        "conversion_effect": round(total_conv_effect, 4),
        "mix_shift_effect": round(total_mix_effect, 4),
        "mix_share_of_change": round(
            abs(total_mix_effect)
            / (abs(total_conv_effect) + abs(total_mix_effect) + 1e-10),
            4,
        ),
        "detail": result_df,
    }


# ─────────────────────────────────────────────
# 5. Feature Importance (Logistic Regression)
# ─────────────────────────────────────────────


def feature_importance_model(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fit a logistic regression on all closed deals to surface which
    features most strongly predict Win (1) vs Loss (0).

    Uses label encoding for categoricals + standard scaling.
    Returns feature importances as odds-ratio-style coefficients.
    """
    features = [
        "region",
        "industry",
        "product_type",
        "lead_source",
        "deal_amount",
        "sales_cycle_days",
    ]

    X = df[features].copy()
    y = df["won"]

    # Encode categoricals
    encoders = {}
    for col in ["region", "industry", "product_type", "lead_source"]:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col].astype(str))
        encoders[col] = le

    # Fit
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    )
    model.fit(X, y)

    coefs = model.named_steps["lr"].coef_[0]
    importance = pd.DataFrame(
        {
            "feature": features,
            "coefficient": coefs,
            "abs_importance": np.abs(coefs),
            "direction": [
                "Increases Win Rate" if c > 0 else "Decreases Win Rate" for c in coefs
            ],
        }
    ).sort_values("abs_importance", ascending=False)

    return importance


# ─────────────────────────────────────────────
# 6. Cross-Segment Heatmap Data
# ─────────────────────────────────────────────


def cross_segment_win_rates(
    df: pd.DataFrame,
    dim1: str = "region",
    dim2: str = "industry",
    min_deals: int = 20,
) -> pd.DataFrame:
    """
    Win rate matrix for two dimensions combined.
    Cells with fewer than min_deals are masked as NaN.
    """
    cross = (
        df.groupby([dim1, dim2])
        .agg(
            win_rate=("won", "mean"),
            deals=("won", "count"),
        )
        .reset_index()
    )
    cross.loc[cross["deals"] < min_deals, "win_rate"] = np.nan
    return cross.pivot(index=dim1, columns=dim2, values="win_rate")


# ─────────────────────────────────────────────
# 7. Plain-Language Insight Generator
# ─────────────────────────────────────────────


def generate_insights(df: pd.DataFrame) -> list[str]:
    """
    Programmatically generate the top business insights as plain-English
    sentences. Designed to populate the executive report automatically.
    """
    insights = []

    cohort = cohort_win_rates(df)
    change_pp = cohort["absolute_change"] * 100
    insights.append(
        f"Overall win rate changed from {cohort['baseline_wr']:.1%} (2023 baseline) "
        f"to {cohort['current_wr']:.1%} (2024-Q1), a shift of {change_pp:+.1f} percentage points."
    )

    # Worst-performing segment per dimension
    for dim in DIMENSIONS:
        seg_df = segment_decomposition(df, dim)
        worst = seg_df.sort_values("wr_change").iloc[0]
        if worst["wr_change"] < -0.03:
            rev_impact = worst["revenue_impact"]
            insights.append(
                f"'{worst['segment']}' ({dim}) showed the largest win-rate decline: "
                f"{worst['wr_change']*100:+.1f}pp, representing an estimated "
                f"${abs(rev_impact):,.0f} revenue impact."
            )

    # Simpson's Paradox warning
    for dim in ["region", "industry"]:
        sp = simpsons_paradox_check(df, dim)
        mix_pct = sp["mix_share_of_change"] * 100
        if mix_pct > 25:
            insights.append(
                f"Simpson's Paradox warning ({dim}): {mix_pct:.0f}% of the overall "
                f"win-rate change is explained by deal MIX SHIFT, not conversion quality. "
                f"Targeting strategy changed, not just sales execution."
            )

    return insights
