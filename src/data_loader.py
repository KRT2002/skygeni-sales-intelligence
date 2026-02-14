"""
data_loader.py
--------------
Loads, validates, and does light cleaning on the raw deals CSV.
All downstream modules import from here so data contracts are centralised.
"""

import pandas as pd
from pathlib import Path

RAW_PATH = Path(__file__).parent.parent / "data" / "raw" / "deals.csv"
PROCESSED_PATH = (
    Path(__file__).parent.parent / "data" / "processed" / "deals_engineered.csv"
)

EXPECTED_COLUMNS = {
    "deal_id",
    "created_date",
    "closed_date",
    "sales_rep_id",
    "industry",
    "region",
    "product_type",
    "lead_source",
    "deal_stage",
    "deal_amount",
    "sales_cycle_days",
    "outcome",
}

CATEGORICAL_COLUMNS = [
    "industry",
    "region",
    "product_type",
    "lead_source",
    "deal_stage",
    "outcome",
]
DATE_COLUMNS = ["created_date", "closed_date"]


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    """Load raw CSV and do minimal type coercion + validation."""
    df = pd.read_csv(path)

    # --- column check ---
    missing = EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")

    # --- date parsing ---
    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], format="%Y-%m-%d")

    # --- numeric ---
    df["deal_amount"] = pd.to_numeric(df["deal_amount"], errors="coerce")
    df["sales_cycle_days"] = pd.to_numeric(df["sales_cycle_days"], errors="coerce")

    # --- outcome binary ---
    df["won"] = (df["outcome"] == "Won").astype(int)

    # --- strip whitespace from strings ---
    for col in CATEGORICAL_COLUMNS:
        df[col] = df[col].str.strip()

    print(f"[data_loader] Loaded {len(df):,} rows, {df['won'].mean():.1%} win rate")
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add calendar-based features used throughout analysis."""
    df = df.copy()
    df["created_year"] = df["created_date"].dt.year
    df["created_month"] = df["created_date"].dt.month
    df["created_quarter"] = df["created_date"].dt.to_period("Q").astype(str)
    df["closed_quarter"] = df["closed_date"].dt.to_period("Q").astype(str)

    # Period label for before/after comparison (inflection point = 2024Q1)
    df["period"] = df["created_quarter"].apply(
        lambda q: "2024Q1" if "2024" in str(q) else "2023"
    )
    return df


def load_engineered(path: Path = PROCESSED_PATH) -> pd.DataFrame:
    """Load the processed/feature-engineered dataset if it exists."""
    if not path.exists():
        raise FileNotFoundError(
            f"Processed data not found at {path}. " "Run feature_engineering.py first."
        )
    df = pd.read_csv(path, parse_dates=DATE_COLUMNS)
    df["won"] = (df["outcome"] == "Won").astype(int)
    return df
