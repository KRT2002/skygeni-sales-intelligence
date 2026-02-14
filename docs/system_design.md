# Part 4 – Sales Insight & Alert System Design

> **Purpose**: How SkyGeni would productise this analysis into a continuously running intelligence system.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  CRM (SFDC / │  │  Marketing   │  │  Product Usage /         │  │
│  │  HubSpot)    │  │  Automation  │  │  Engagement Data         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
└─────────┼─────────────────┼──────────────────────-─┼────────────────┘
          │                 │                         │
          ▼                 ▼                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      INGESTION LAYER                                 │
│  • Daily CRM delta sync (changed/new deals)                          │
│  • Schema validation + data quality checks                           │
│  • Null handling, stage normalisation                                │
│  • Deduplication via deal_id                                         │
│  Storage: Append-only deal event log (immutable history)             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FEATURE STORE                                   │
│  • Engineered features computed daily                                │
│  • Cached aggregates: rep_win_rate, segment_win_rate, etc.           │
│  • Rolling metrics: momentum scores, velocity scores                 │
│  • Baseline snapshots (weekly, monthly, quarterly)                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                      ┌────────┴────────┐
                      │                 │
                      ▼                 ▼
        ┌─────────────────────┐  ┌──────────────────────┐
        │  DRIVER ANALYSIS    │  │  RISK SCORING        │
        │  ENGINE             │  │  ENGINE              │
        │                     │  │                      │
        │  • Cohort compare   │  │  • Score open deals  │
        │  • Segment decomp   │  │  • P(loss) per deal  │
        │  • Simpson's check  │  │  • Explain top risk  │
        │  • Feature import   │  │    factors           │
        │  • Stat signif test │  │  • Rep priority list │
        └──────────┬──────────┘  └──────────┬───────────┘
                   │                         │
                   └────────────┬────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ALERT ENGINE                                    │
│  • 5 monitored metrics (see below)                                   │
│  • Z-score anomaly detection vs rolling baselines                    │
│  • Alert prioritisation: CRITICAL / WARNING / INFO                   │
│  • Alert deduplication (don't fire same alert twice in 7 days)       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
              ┌────────────────┼──────────────────┐
              │                │                  │
              ▼                ▼                  ▼
     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
     │  DASHBOARD   │  │  SLACK /     │  │  WEEKLY PDF  │
     │  (CRO View)  │  │  EMAIL ALERT │  │  REPORT      │
     └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Data Flow

### Step 1: Ingestion (Daily, 02:00 UTC)
- Pull deal delta from CRM API (new + changed deals since last sync)
- Validate schema: check for required fields, type conformance, date sanity
- Reject and log bad records; do not silently drop them
- Append to immutable deal event log (enables full replay/audit)

### Step 2: Feature Computation (Daily, 03:00 UTC)
- Recompute rolling aggregates: rep win rates, segment win rates, cycle averages
- Compute momentum scores, velocity scores, lead source decay
- Store in Feature Store with timestamps (enables point-in-time queries)

### Step 3: Risk Scoring (Daily, 04:00 UTC)
- Load all open deals from Feature Store
- Apply trained risk model to score each open deal
- Persist risk scores with timestamp to deal_scores table
- Flag deals whose risk score increased by >15pp since last run

### Step 4: Alert Evaluation (Daily, 05:00 UTC)
- Run 5-metric alert checks against rolling baselines
- Filter: only fire alerts that are NEW or have escalated in severity
- Route by severity: CRITICAL → Slack + email + dashboard; WARNING → dashboard only

### Step 5: Weekly Report Generation (Monday, 06:00 UTC)
- Re-run full driver analysis across all dimensions
- Generate executive summary with key findings and recommendations
- Distribute to CRO, VP Sales, Revenue Operations as PDF + Slack summary

---

## Example Alerts

### Alert 1 — CRITICAL: Win Rate Drop
```
🔴 [CRITICAL] Overall Win Rate
Current: 41.2% | Baseline: 47.8% | Z-score: -2.8

Win rate is 6.6pp below rolling baseline (z = -2.8).

Action: Run full driver analysis. Likely causes:
  - APAC region converting 22% below Q3 baseline
  - Outbound lead source quality degrading (down 18pp)
Review dashboard: skygeni.app/driver-analysis/latest
```

### Alert 2 — WARNING: Stage Stalling
```
🟡 [WARNING] Demo Stage Velocity
Current avg: 38 days | Baseline: 22 days | Z-score: +2.1

Deals are stalling in Demo stage — 73% longer than normal.
9 deals have been in Demo for 30+ days this month.

Action: Check: demo quality issues? Reps need demo training?
        Review: skygeni.app/stage-velocity
```

### Alert 3 — WARNING: Rep Performance Divergence
```
🟡 [WARNING] Rep Win Rate Spread (IQR)
Current gap: 31pp | Baseline: 18pp | Z-score: +1.7

The performance gap between top and bottom quartile reps
has widened significantly this quarter.

Action: Schedule 1:1 reviews with bottom-quartile reps.
        Assign top performers as mentors.
        Affected reps: rep_08, rep_14, rep_21
```

### Alert 4 — INFO: Pipeline Mix Shift
```
🔵 [INFO] Deal Mix Shift Detected (industry)
HealthTech share: 38% (was 22% baseline)

Pipeline composition has shifted toward HealthTech.
Note: HealthTech has 14pp lower win rate than SaaS.
This may explain up to 40% of overall win rate decline.

Action: Review with SDR/marketing team — is this intentional?
        If not, adjust ICP targeting to rebalance pipeline.
```

---

## Cadence

| Frequency | Task |
|-----------|------|
| Real-time | Deal stage changes trigger risk score update via CRM webhook |
| Daily | Full feature recomputation + risk scoring for all open deals |
| Daily | Alert evaluation — only new/escalated alerts fire |
| Weekly (Monday) | Full driver analysis report + distribution to leadership |
| Monthly | Model performance review — has AUC drifted? |
| Quarterly | Model retraining with latest 12 months of closed deals |
| Quarterly | Baseline recalibration for alert thresholds |

---

## Failure Cases and Limitations

### Data Quality Failures

**CRM Data Staleness**: Reps often don't update deal stages in real time. A deal may have verbally closed but still appear "Open" for days or weeks. Risk: deals are scored as high-risk when they are actually won. Mitigation: add a "last_crm_update" staleness flag; exclude deals not updated in 14+ days from risk scoring.

**Outcome Label Lag**: "Lost" deals are sometimes only marked after the end of quarter cleanup. This causes recent periods to appear artificially optimistic. Mitigation: build a "mature deal" filter — only include deals closed 45+ days ago in win rate baselines.

**Stage Regression**: Some CRMs allow deals to move backward (Proposal → Demo). Without tracking the full stage history, cycle time calculations will be wrong. Mitigation: use the maximum stage reached, not the current stage.

### Model Limitations

**Distribution Shift**: If the company enters a new market, targets a different company size, or changes its ICP, the risk model trained on historical data will be miscalibrated. Mitigation: monthly AUC monitoring + quarterly retraining trigger.

**Small Sample Sizes**: Per-rep per-segment win rates can have high variance when n < 30. The system should show confidence intervals alongside point estimates and suppress alerts for small-sample segments.

**Intervention Paradox**: If reps successfully save high-risk deals (because the system told them to intervene), the model will appear "wrong" in hindsight — those deals show as Won despite high risk scores. Mitigation: do not use intervened deals to retrain the model without correction.

### System Failures

**Alert Fatigue**: If too many alerts fire simultaneously (e.g., at quarter-end when pipeline is deliberately volatile), users start ignoring them. Mitigation: cap total weekly alerts at 5; use progressive batching (send INFO digest weekly, CRITICAL immediately).

**Single Source of Truth Conflicts**: If the CRM team changes field definitions (e.g., renaming "Qualified" to "Discovery"), all downstream logic breaks silently. Mitigation: schema validation at ingestion with explicit field mapping contracts.

**Baseline Contamination**: If a particularly bad quarter is included in the rolling baseline, it lowers the threshold for future alerts (anomalies become "normal"). Mitigation: allow manual exclusion of known anomalous periods from baseline calculation.

---

## What Gets Built Next (1-Month Roadmap)

1. **Conversation Intelligence Integration** (Week 1-2): Ingest call transcripts via Gong/Chorus API. Extract objections, competitor mentions, and buying signals. Enrich deal risk scores with qualitative signals — a deal where the buyer said "we're evaluating three vendors" is measurably higher risk.

2. **Cohort Benchmarking** (Week 2-3): Compare the company's win rate by segment against SkyGeni's anonymised customer network. "Your APAC Enterprise win rate of 31% is 12pp below the median for your peer group" is a far stronger signal than "it dropped from 43%."

3. **Rep-Level Coaching Recommendations** (Week 3-4): Move from "bottom quartile reps" to "here is the specific objection rep_14 struggles to handle, based on transcript analysis." This requires conversation intelligence but dramatically increases the actionability of rep performance insights.

4. **Forecast Integration** (Week 4): Connect risk scores to the revenue forecast — instead of multiplying pipeline by flat stage conversion rates, use deal-level risk scores to produce a more accurate weighted forecast with confidence intervals.
