"""
report_builder.py
-----------------
Assembles a self-contained HTML executive report from analysis outputs.

Pulls together:
  - Key metric cards (win rates, revenue impact)
  - LLM-generated narrative
  - Embedded chart images (base64 so the file is self-contained)
  - Risk scoring summary table
  - Alert system output

The report is a single .html file with no external dependencies —
it can be opened in any browser or emailed as an attachment.
"""

from __future__ import annotations

import base64
from pathlib import Path
from datetime import datetime

import pandas as pd

FIGURES_DIR = Path(__file__).parent.parent / "outputs" / "figures"
REPORTS_DIR = Path(__file__).parent.parent / "outputs" / "reports"
REPORT_PATH = REPORTS_DIR / "executive_report.html"


def _img_tag(filename: str, caption: str = "", width: str = "100%") -> str:
    """Embed image as base64 so the HTML file is fully self-contained."""
    path = FIGURES_DIR / filename
    if not path.exists():
        return f'<p class="missing-chart">[Chart not found: {filename}]</p>'
    data = base64.b64encode(path.read_bytes()).decode()
    ext  = path.suffix.lstrip(".")
    tag  = f'<img src="data:image/{ext};base64,{data}" style="width:{width};border-radius:6px;" alt="{caption}">'
    if caption:
        tag += f'<p class="caption">{caption}</p>'
    return tag


def _metric_card(label: str, value: str, delta: str = "", delta_positive: bool = True) -> str:
    delta_color = "#16A34A" if delta_positive else "#DC2626"
    delta_html  = f'<span style="color:{delta_color};font-size:0.9em;">{delta}</span>' if delta else ""
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>"""


def _risk_table(scored_df: pd.DataFrame) -> str:
    """Render top 15 at-risk deals as an HTML table."""
    top = scored_df[scored_df["risk_tier"].isin(["Critical Risk", "High Risk"])].head(15)
    if top.empty:
        return "<p>No high-risk deals identified.</p>"

    tier_colors = {
        "Critical Risk": "#7C0000",
        "High Risk":     "#DC2626",
        "Medium Risk":   "#D97706",
        "Low Risk":      "#16A34A",
    }

    rows = ""
    for _, row in top.iterrows():
        color = tier_colors.get(row["risk_tier"], "#666")
        rows += f"""
        <tr>
            <td>{row['deal_id']}</td>
            <td>{row['deal_stage']}</td>
            <td>${row['deal_amount']:,.0f}</td>
            <td>{row['industry']}</td>
            <td>{row['region']}</td>
            <td>{row['sales_rep_id']}</td>
            <td><span class="tier-badge" style="background:{color}">{row['risk_tier']}</span></td>
            <td>{row['risk_score_pct']}%</td>
            <td style="font-size:0.8em">{row['risk_factors']}</td>
        </tr>"""

    return f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>Deal ID</th><th>Stage</th><th>Amount</th>
                <th>Industry</th><th>Region</th><th>Rep</th>
                <th>Risk Tier</th><th>Score</th><th>Risk Factors</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""


def _alerts_html(alerts_df: pd.DataFrame) -> str:
    """Render alert engine output as styled alert cards."""
    active = alerts_df[alerts_df["severity"] != "OK"]
    if active.empty:
        return '<p style="color:#16A34A">No active alerts — pipeline health normal.</p>'

    severity_styles = {
        "CRITICAL": ("🔴", "#7C0000", "#FEE2E2"),
        "WARNING":  ("🟡", "#92400E", "#FEF3C7"),
        "INFO":     ("🔵", "#1E3A8A", "#DBEAFE"),
    }

    cards = ""
    for _, row in active.iterrows():
        emoji, text_color, bg_color = severity_styles.get(row["severity"], ("⚪", "#333", "#F9FAFB"))
        cards += f"""
        <div class="alert-card" style="background:{bg_color};border-left:4px solid {text_color}">
            <strong style="color:{text_color}">{emoji} [{row['severity']}] {row['metric']}</strong>
            <p style="margin:4px 0 2px 0">{row['message']}</p>
            <p style="margin:0;font-size:0.85em;color:#555">Action: {row['action']}</p>
        </div>"""
    return cards


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #F8FAFC; color: #1E293B; line-height: 1.6; }
.page { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
.header { background: linear-gradient(135deg, #1E3A8A, #2563EB);
          color: white; padding: 32px; border-radius: 12px; margin-bottom: 28px; }
.header h1 { font-size: 1.8em; font-weight: 700; }
.header p  { opacity: 0.85; margin-top: 6px; }
.section   { background: white; border-radius: 10px; padding: 24px;
             margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
.section h2 { font-size: 1.15em; font-weight: 600; color: #1E3A8A;
              border-bottom: 2px solid #E2E8F0; padding-bottom: 10px; margin-bottom: 18px; }
.metrics-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }
.metric-card { background: #F1F5F9; border-radius: 8px; padding: 16px 20px;
               flex: 1; min-width: 160px; }
.metric-label { font-size: 0.78em; color: #64748B; text-transform: uppercase;
                letter-spacing: 0.04em; }
.metric-value { font-size: 1.6em; font-weight: 700; color: #1E293B; margin-top: 2px; }
.narrative    { background: #F8FAFC; border-left: 4px solid #2563EB;
                padding: 16px 20px; border-radius: 0 8px 8px 0;
                white-space: pre-line; font-size: 0.95em; line-height: 1.75; }
.narrative h2 { font-size: 1em; color: #1E3A8A; margin: 14px 0 4px; }
.charts-grid  { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.chart-box    { background: #F8FAFC; border-radius: 8px; padding: 12px; }
.caption      { font-size: 0.78em; color: #64748B; text-align: center; margin-top: 6px; }
.missing-chart { color: #94A3B8; font-style: italic; font-size: 0.85em; }
.data-table   { width: 100%; border-collapse: collapse; font-size: 0.85em; }
.data-table th { background: #1E3A8A; color: white; padding: 8px 10px;
                 text-align: left; font-weight: 500; }
.data-table td { padding: 7px 10px; border-bottom: 1px solid #E2E8F0; }
.data-table tr:hover td { background: #F1F5F9; }
.tier-badge   { color: white; padding: 2px 8px; border-radius: 10px;
                font-size: 0.78em; font-weight: 600; white-space: nowrap; }
.alert-card   { padding: 12px 16px; border-radius: 0 8px 8px 0;
                margin-bottom: 10px; }
.footer       { text-align: center; color: #94A3B8; font-size: 0.8em; margin-top: 32px; }
"""


def build_report(
    cohort: dict,
    segment_changes: list,
    narrative: str,
    scored_df: pd.DataFrame,
    alerts_df: pd.DataFrame,
    risk_summary_dict: dict,
) -> Path:
    """
    Assemble and write the executive HTML report.

    Parameters
    ----------
    cohort           : cohort_win_rates() output
    segment_changes  : list of top segment decline dicts
    narrative        : string from generate_executive_narrative()
    scored_df        : scored 2024-Q1 deals DataFrame
    alerts_df        : run_all_alerts() output DataFrame
    risk_summary_dict: risk_summary() output dict

    Returns
    -------
    Path to the written HTML file
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    baseline_wr = cohort.get("baseline_wr", 0)
    current_wr  = cohort.get("current_wr", 0)
    change_pp   = cohort.get("absolute_change", 0) * 100
    delta_pos   = change_pp >= 0

    # ── Key metric cards ─────────────────────────────────────
    metrics_html = '<div class="metrics-row">'
    metrics_html += _metric_card("2023 Baseline Win Rate", f"{baseline_wr:.1%}")
    metrics_html += _metric_card(
        "2024-Q1 Win Rate", f"{current_wr:.1%}",
        delta=f"{change_pp:+.1f}pp", delta_positive=delta_pos
    )
    at_risk = risk_summary_dict.get("pipeline_at_risk_$", 0)
    total   = risk_summary_dict.get("total_pipeline_$", 0)
    metrics_html += _metric_card(
        "Pipeline at Risk (2024-Q1)", f"${at_risk:,.0f}",
        delta=f"{risk_summary_dict.get('pct_pipeline_at_risk',0)}% of pipeline",
        delta_positive=False
    )
    critical_n = risk_summary_dict.get("critical_risk_deals", 0)
    metrics_html += _metric_card("Critical Risk Deals", str(critical_n), delta_positive=False)
    metrics_html += "</div>"

    # ── Narrative (markdown-style → simple HTML) ──────────────
    narrative_html = narrative.replace("## ", "<h2>").replace("\n", "<br>")

    # ── Top segment changes as a small summary table ──────────
    seg_rows = ""
    for s in segment_changes[:6]:
        color = "#DC2626" if s["wr_change"] < 0 else "#16A34A"
        seg_rows += f"""
        <tr>
            <td>{s['dimension'].replace('_',' ').title()}</td>
            <td>{s['segment']}</td>
            <td style="color:{color};font-weight:600">{s['wr_change']*100:+.1f}pp</td>
            <td>${s['revenue_impact']:,.0f}</td>
        </tr>"""

    seg_table = f"""
    <table class="data-table">
        <thead><tr>
            <th>Dimension</th><th>Segment</th>
            <th>Win Rate Change</th><th>Revenue Impact</th>
        </tr></thead>
        <tbody>{seg_rows}</tbody>
    </table>"""

    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SkyGeni Sales Intelligence Report</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">

  <div class="header">
    <h1>SkyGeni Sales Intelligence Report</h1>
    <p>Win Rate Driver Analysis &amp; Pipeline Risk Scoring &nbsp;|&nbsp; Generated {generated_at}</p>
  </div>

  <!-- KEY METRICS -->
  <div class="section">
    <h2>Key Metrics</h2>
    {metrics_html}
  </div>

  <!-- EXECUTIVE NARRATIVE -->
  <div class="section">
    <h2>Executive Narrative <span style="font-size:0.75em;color:#64748B;font-weight:400">(AI-generated · LLaMA 3.3 70B via Groq)</span></h2>
    <div class="narrative">{narrative_html}</div>
  </div>

  <!-- WIN RATE TRENDS -->
  <div class="section">
    <h2>Win Rate Analysis</h2>
    <div class="charts-grid">
      <div class="chart-box">
        {_img_tag("01_win_rate_over_time.png", "Win Rate Trend Over Time")}
      </div>
      <div class="chart-box">
        {_img_tag("10_cohort_overview.png", "Baseline vs Current Period")}
      </div>
      <div class="chart-box">
        {_img_tag("11_segment_decomposition.png", "Win Rate Change by Segment")}
      </div>
      <div class="chart-box">
        {_img_tag("12_simpsons_decomposition.png", "Simpson's Paradox Decomposition")}
      </div>
    </div>
  </div>

  <!-- SEGMENT BREAKDOWN -->
  <div class="section">
    <h2>Top Segment Changes</h2>
    {seg_table}
  </div>

  <!-- CUSTOM METRICS -->
  <div class="section">
    <h2>Custom Metrics</h2>
    <div class="charts-grid">
      <div class="chart-box">
        {_img_tag("05_momentum_score.png", "Win Rate Momentum Score")}
      </div>
      <div class="chart-box">
        {_img_tag("06_rep_divergence.png", "Rep Performance Divergence Index")}
      </div>
      <div class="chart-box">
        {_img_tag("07_stage_velocity.png", "Stage Velocity Score")}
      </div>
      <div class="chart-box">
        {_img_tag("08_lead_source_decay.png", "Lead Source Quality Decay")}
      </div>
    </div>
  </div>

  <!-- RISK SCORING -->
  <div class="section">
    <h2>2024-Q1 Pipeline Risk Scoring</h2>
    <div class="charts-grid" style="margin-bottom:20px">
      <div class="chart-box">
        {_img_tag("15_risk_tier_distribution.png", "Risk Tier Distribution")}
      </div>
      <div class="chart-box">
        {_img_tag("16_risk_score_validation.png", "Score Validation vs Actuals")}
      </div>
    </div>
    <h2 style="margin-top:0">High-Priority Intervention List</h2>
    {_risk_table(scored_df)}
  </div>

  <!-- ALERTS -->
  <div class="section">
    <h2>Pipeline Health Alerts</h2>
    {_alerts_html(alerts_df)}
  </div>

  <div class="footer">
    SkyGeni Sales Intelligence System &nbsp;|&nbsp;
    Built with Python, scikit-learn, LLaMA 3.3 70B (Groq) &nbsp;|&nbsp;
    {generated_at}
  </div>

</div>
</body>
</html>"""

    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"[report_builder] Report saved: {REPORT_PATH}")
    return REPORT_PATH