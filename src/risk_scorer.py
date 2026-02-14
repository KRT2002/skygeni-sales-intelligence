"""
risk_scorer.py
--------------
Hybrid Option A extension: applies 2023 win/loss patterns to 2024-Q1 deals.

Design:
  - Train ONLY on 2023 closed deals (historical baseline)
  - Score ALL 2024-Q1 deals (holdout period the model never saw)
  - Validate scores against known 2024-Q1 outcomes to confirm generalisation
  - Risk tiers use absolute score thresholds, not rank-based percentiles

This is a proper temporal train/score split.
2023 = what we learned. 2024-Q1 = what we apply it to.
"""

import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder
import warnings

warnings.filterwarnings("ignore")


RISK_FEATURES = [
    "region",
    "industry",
    "product_type",
    "lead_source",
    "deal_amount",
    "sales_cycle_days",
]

TRAIN_PERIOD = "2023"
SCORE_PERIOD = "2024Q1"


def _encode_features(df, encoders=None):
    """
    Label-encode categorical features.
    If encoders dict provided, transform using existing fit (for scoring).
    If None, fit new encoders (for training).
    """
    X = df[RISK_FEATURES].copy()
    fitted_encoders = {}
    for col in ["region", "industry", "product_type", "lead_source"]:
        if encoders is not None:
            X[col] = encoders[col].transform(X[col].astype(str))
            fitted_encoders[col] = encoders[col]
        else:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
            fitted_encoders[col] = le
    return X, fitted_encoders


def train_risk_model(df):
    """
    Train Gradient Boosting on 2023 deals only.
    Target: P(loss) — 1 = Lost, 0 = Won.

    Cross-validation within 2023 only — no future data leakage.
    Returns: (model, encoders, cv_scores)
    """
    train_df = df[df["period"] == TRAIN_PERIOD].copy()
    train_df["lost"] = 1 - train_df["won"]

    print(f"[risk_scorer] Training on {len(train_df):,} deals from {TRAIN_PERIOD}")
    print(f"  Win rate in training set: {train_df['won'].mean():.1%}")

    X_train, encoders = _encode_features(train_df)
    y_train = train_df["lost"]

    model = GradientBoostingClassifier(
        n_estimators=150,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.8,
        random_state=42,
    )
    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring="roc_auc")
    model.fit(X_train, y_train)

    print(
        f"[risk_scorer] CV AUC (within 2023): {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}"
    )
    return model, encoders, cv_scores


def score_2024q1_deals(df, model, encoders):
    """
    Score all 2024-Q1 deals using the model trained on 2023 data.

    Since 2024-Q1 deals have known outcomes, we can also validate scores.

    Risk tiers use absolute score thresholds:
      Critical : risk_score >= 0.55
      High     : risk_score >= 0.50
      Medium   : risk_score >= 0.45
      Low      : risk_score <  0.45

    NOTE: With CV AUC near 0.50 (synthetic data has weak signal), tiers should
    be read as relative prioritisation, not calibrated probabilities. In
    production with richer features, AUC of 0.65-0.75 would make absolute
    thresholds meaningfully calibrated.
    """
    score_df = df[df["period"] == SCORE_PERIOD].copy()
    print(f"[risk_scorer] Scoring {len(score_df):,} deals from {SCORE_PERIOD}")

    X_score, _ = _encode_features(score_df, encoders=encoders)
    score_df["risk_score"] = model.predict_proba(X_score)[:, 1]
    score_df["risk_score_pct"] = (score_df["risk_score"] * 100).round(1)

    def assign_tier(score):
        if score >= 0.55:
            return "Critical Risk"
        elif score >= 0.50:
            return "High Risk"
        elif score >= 0.45:
            return "Medium Risk"
        else:
            return "Low Risk"

    score_df["risk_tier"] = score_df["risk_score"].apply(assign_tier)
    score_df = score_df.sort_values("risk_score_pct", ascending=False).reset_index(
        drop=True
    )

    fi = pd.Series(model.feature_importances_, index=RISK_FEATURES).sort_values(
        ascending=False
    )
    top_factors = fi.head(3).index.tolist()

    def explain(row):
        explanations = []
        if row["sales_cycle_days"] > 75:
            explanations.append(f"Long cycle: {row['sales_cycle_days']}d")
        if row["deal_amount"] > 60_000:
            explanations.append(f"Large deal: ${row['deal_amount']:,.0f}")
        for f in top_factors:
            if f not in ["sales_cycle_days", "deal_amount"]:
                explanations.append(f"{f.replace('_', ' ').title()}: {row[f]}")
        return " | ".join(explanations[:3])

    score_df["risk_factors"] = score_df.apply(explain, axis=1)

    def recommend(row):
        if row["risk_tier"] == "Critical Risk":
            return "Escalate to senior rep + schedule executive sponsor call"
        elif row["risk_tier"] == "High Risk":
            return "Review deal with manager + offer POC or discount"
        elif row["risk_tier"] == "Medium Risk":
            return "Check in with buyer + clarify timeline and blockers"
        else:
            return "Maintain cadence — deal on track"

    score_df["recommended_action"] = score_df.apply(recommend, axis=1)
    return score_df


def validate_scores(scored_df):
    """
    Since 2024-Q1 deals have known outcomes, validate whether risk scores
    correlate with actual Won/Lost results.

    This is the true out-of-sample test: model trained on 2023, validated
    on 2024-Q1 actuals it never saw during training.
    """
    from sklearn.metrics import roc_auc_score

    holdout_auc = roc_auc_score(1 - scored_df["won"], scored_df["risk_score"])

    tier_val = (
        scored_df.groupby("risk_tier")
        .agg(
            deals=("won", "count"),
            actual_loss_rate=("won", lambda x: round(1 - x.mean(), 3)),
            avg_risk_score=("risk_score_pct", "mean"),
        )
        .sort_values("avg_risk_score", ascending=False)
    )
    return {
        "holdout_auc": round(holdout_auc, 3),
        "tier_validation": tier_val,
    }


def risk_summary(scored_df):
    """Aggregate risk metrics across the scored 2024-Q1 deals."""
    total = scored_df["deal_amount"].sum()
    critical = scored_df[scored_df["risk_tier"] == "Critical Risk"]
    high = scored_df[scored_df["risk_tier"] == "High Risk"]
    at_risk = critical["deal_amount"].sum() + high["deal_amount"].sum()

    return {
        "period_scored": SCORE_PERIOD,
        "total_deals_scored": len(scored_df),
        "critical_risk_deals": len(critical),
        "high_risk_deals": len(high),
        "medium_low_deals": len(scored_df) - len(critical) - len(high),
        "pipeline_at_risk_$": round(at_risk, 0),
        "total_pipeline_$": round(total, 0),
        "pct_pipeline_at_risk": round(at_risk / total * 100, 1) if total > 0 else 0,
    }
