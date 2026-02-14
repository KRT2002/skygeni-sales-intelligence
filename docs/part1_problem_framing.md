# Part 1 – Problem Framing

> **Audience**: CRO, VP Sales, Revenue Operations  
> **Date**: 2024

---

## 1. What Is the Real Business Problem?

The CRO's complaint surfaces as *"win rate dropped"*, but that is a symptom, not the problem. The real issue has three layers:

**Layer 1 — Symptom**: Win rate declined while pipeline volume remained healthy. Revenue is being left on the table.

**Layer 2 — Structural Gap**: There is no systematic framework for attributing win rate changes to specific causes. Without decomposition, any intervention is a guess. The CRO cannot tell whether this is a *people problem* (rep performance), a *market problem* (industry headwinds, competitive pressure), a *targeting problem* (pursuing harder deals or wrong segments), or a *process problem* (stage stalling, long cycles).

**Layer 3 — Root Cause**: The organisation is making strategic decisions — coaching investments, territory adjustments, product positioning changes — based on the aggregate win rate number rather than its components. This means the right fix may be being applied to the wrong problem.

**The real business problem**: The CRO lacks a diagnostic framework to decompose performance changes into actionable, attributable root causes. Fixing win rate without this framework is like treating symptoms without a diagnosis.

---

## 2. Key Questions an AI System Must Answer

Framed as questions the CRO would ask on a Monday morning:

**Diagnostic (Understanding the past)**
1. Where exactly is win rate declining — which region, industry, product tier, or lead source?
2. Is the overall decline caused by *converting worse in the same segments*, or by *shifting the pipeline mix toward harder-to-win deals*? (These require different fixes.)
3. Which individual reps are driving the decline, and is it concentrated or spread across the team?
4. Has the sales cycle lengthened in specific stages, indicating where the process is breaking?
5. Have certain lead sources lost their quality premium over time?

**Predictive (Understanding the present)**
6. Which currently open deals are most likely to follow the same losing patterns?
7. How much revenue is at risk in the current pipeline right now?

**Prescriptive (Deciding what to do)**
8. If we fix only one dimension (e.g., APAC performance), how much of the overall win rate decline is recovered?
9. Should the intervention be coaching-led (conversion problem) or targeting-led (mix shift problem)?
10. Which deals should reps prioritise this week to maximise close probability?

---

## 3. Metrics That Matter Most for Diagnosing Win Rate Issues

Metrics are listed in order of diagnostic priority:

### Primary Diagnostic Metrics

**Win Rate by Segment and Period**  
The fundamental decomposition. Win rate must be computed for every combination of time period × dimension (region, industry, product type, lead source) to isolate *where* the decline is happening. A single aggregate win rate hides more than it reveals.

**Win Rate Decomposition (Conversion vs Mix Shift)**  
Uses the Kitagawa-Oaxaca-Blinder method to split total win rate change into (a) pure conversion deterioration and (b) pipeline composition change. This is the most important single metric because it determines *what kind of intervention is needed*. Coaching fixes conversion. ICP/targeting changes fix mix shift.

**Statistical Significance of Segment Changes**  
Win rate changes in small segments can be noise. Chi-square testing on win/loss counts per segment filters spurious signals from real ones.

### Secondary Performance Metrics

**Sales Cycle Length by Stage and Segment**  
Longer cycles correlate with lower win rates. Stage-specific stalling reveals *where* in the sales process deals are losing momentum.

**Rep Performance Distribution (IQR spread)**  
Not just average rep performance, but the gap between top and bottom quartile. A widening gap suggests a coaching or enablement problem. A narrowing gap may indicate top performers are declining.

**Lead Source Quality Premium Over Time**  
The difference between each source's win rate and the overall win rate, tracked quarterly. Decay in the Referral premium is a different problem from decay in all sources simultaneously.

### Custom Metrics (Novel)

**Win Rate Momentum Score**: The rate of change (acceleration/deceleration) of win rate normalised by its historical volatility. A momentum score below −1.5 standard deviations is an early warning signal, even before the absolute level drops below threshold.

**Deal Mix Shift Index**: Quantifies how much the pipeline composition changed versus baseline. Captures Simpson's Paradox risk — the case where win rate can decline even if every individual segment improves, simply because the mix shifted toward harder segments.

**Rep Performance Divergence Index**: The quarterly IQR spread of rep win rates. Tracks whether the performance gap between top and bottom reps is widening (coaching problem) or narrowing (top performer decline).

**Stage Velocity Degradation Score**: Current average days-per-stage vs historical baseline, weighted by that stage's impact on overall win rate. Surfaces where the sales process is slowing down with business-impact context.

**Lead Source Quality Decay**: Channel-specific win rate premium (channel win rate minus overall win rate) tracked over time. Distinguishes channel-specific deterioration from systemic product/market issues.

---

## 4. Assumptions

Being explicit about assumptions is important because false assumptions lead to wrong interventions.

**Data assumptions**
- Deal outcomes are accurately recorded. If reps mark deals as "Lost" late or prematurely, win rates for recent periods will be understated or overstated (survivorship / recency bias).
- `sales_rep_id` is a stable identifier. If reps change territories, regions, or industries, their historical win rates will be misleading signals — a rep with 60% win rate in India who moved to APAC will appear to "underperform" in APAC even if they're performing normally for that market.
- `closed_date` reflects when the deal actually closed, not when it was entered in the CRM. Lagged CRM updates would distort period-based analysis.
- The `deal_stage` column represents the *last* stage reached before close, not the stage at which the deal is currently sitting. This affects how we interpret stage-based risk signals.

**Business assumptions**
- The win rate decline is real and not a data quality artifact (e.g., a recent batch of "Lost" deals being entered that were actually lost in prior periods).
- Deal mix changes are potentially *intentional* (e.g., a sales push into a new vertical) or potentially *accidental* (e.g., less lead volume from quality channels). The analysis surfaces the shift; the business must explain the cause.
- Revenue impact calculations use ACV (annual contract value) as a proxy for closed revenue. Multi-year contracts, expansions, and churn are not captured.
- 25 sales reps with ~200 deals each provides reasonable statistical power for per-rep analysis, but per-rep per-segment estimates will have high variance and should be treated as directional.

**Modelling assumptions**
- The logistic regression feature importance model assumes a log-linear relationship between features and win probability. Non-linear interactions (e.g., large deal × long cycle = much worse than either alone) are captured approximately but not perfectly.
- The risk scoring model trained on 2023 data is applied to 2024-Q1 open deals. If the market or product changed significantly, the model's calibration may drift.
- Statistical significance tests (chi-square) assume independent observations. If the same rep handles many deals in the same segment, observations within that rep-segment bucket are correlated, potentially inflating significance.
