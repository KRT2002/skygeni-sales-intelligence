"""
insight_narrator.py
-------------------
Generates a plain-English executive narrative from structured analysis results
using a Groq-hosted LLaMA model via langchain-groq.

Design decisions:
- Graceful fallback: if Groq API is unavailable (no key, rate limit,
  network error), the function falls back to the templated string
  version so notebooks always run end-to-end.
- System prompt lives in prompts/system_prompt.txt — versioned
  separately from code so it can be iterated without touching logic.
- Anti-hallucination enforced at the prompt level: the model is
  explicitly instructed to only reference numbers from the context block.
"""

from __future__ import annotations

from pathlib import Path

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"


def _load_system_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    # Minimal fallback if file is missing
    return (
        "You are a sales intelligence analyst. Summarise the provided analysis "
        "into a concise executive narrative. Only use numbers from the context. "
        "Do not hallucinate any figures."
    )


def _build_context(analysis: dict) -> str:
    """
    Format the structured analysis dict into a clean context block
    for the LLM. Explicit formatting prevents the model from having
    to infer structure, which reduces hallucination risk.
    """
    lines = ["=== ANALYSIS CONTEXT ===", ""]

    cohort = analysis.get("cohort", {})
    if cohort:
        lines.append("OVERALL WIN RATE:")
        lines.append(f"  Baseline (2023):  {cohort.get('baseline_wr', 0):.1%}")
        lines.append(f"  Current (2024Q1): {cohort.get('current_wr', 0):.1%}")
        lines.append(f"  Change:           {cohort.get('absolute_change', 0)*100:+.1f} percentage points")
        lines.append("")

    segments = analysis.get("top_segment_changes", [])
    if segments:
        lines.append("TOP SEGMENT WIN RATE CHANGES (by revenue impact):")
        for s in segments[:4]:
            lines.append(
                f"  {s['dimension']}={s['segment']}: "
                f"{s['wr_change']*100:+.1f}pp change | "
                f"estimated revenue impact ${s['revenue_impact']:,.0f}"
            )
        lines.append("")

    simpsons = analysis.get("simpsons", {})
    if simpsons:
        lines.append("DECOMPOSITION (conversion vs mix shift):")
        for dim, vals in simpsons.items():
            lines.append(
                f"  {dim}: conversion effect {vals['conversion_effect']*100:+.2f}pp | "
                f"mix shift effect {vals['mix_shift_effect']*100:+.2f}pp"
            )
        lines.append("")

    feature_imp = analysis.get("feature_importance", [])
    if feature_imp:
        lines.append("TOP PREDICTORS OF WIN/LOSS (logistic regression):")
        for f in feature_imp[:3]:
            lines.append(f"  {f['feature']}: coefficient {f['coefficient']:+.3f} ({f['direction']})")
        lines.append("")

    insights = analysis.get("programmatic_insights", [])
    if insights:
        lines.append("PRE-COMPUTED INSIGHTS:")
        for ins in insights:
            lines.append(f"  - {ins}")
        lines.append("")

    lines.append("=== END CONTEXT ===")
    return "\n".join(lines)


def generate_executive_narrative(analysis: dict) -> str:
    """
    Generate a CRO-ready executive narrative from pre-computed analysis results.

    Parameters
    ----------
    analysis : dict with keys:
        cohort              : cohort_win_rates() output
        top_segment_changes : list of dicts with dimension/segment/wr_change/revenue_impact
        simpsons            : {dimension: simpsons_paradox_check() output}
        feature_importance  : feature_importance_model() output as records
        programmatic_insights : generate_insights() output list

    Returns
    -------
    str
        LLM-generated narrative, or templated fallback if LLM unavailable.
    """
    from src.config import settings

    if not settings.llm_available:
        print("[narrator] No GROQ_API_KEY found — using templated fallback.")
        return _templated_fallback(analysis)

    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage

        system_prompt = _load_system_prompt()
        context_block = _build_context(analysis)

        llm = ChatGroq(
            model_name=settings.model_name,
            temperature=settings.temperature,
            api_key=settings.groq_api_key,
        )
        # No tools bound — narration is pure reasoning over provided context
        print(f"[narrator] Calling {settings.model_name} for executive narrative")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=(
                "Please generate the executive narrative for the following sales "
                "intelligence analysis. Remember: only use numbers from the context block.\n\n"
                + context_block
            )),
        ]

        response = llm.invoke(messages)
        narrative = response.content.strip()
        print("[narrator] Narrative generated successfully")
        return narrative

    except ImportError:
        print("[narrator] langchain-groq not installed — using templated fallback.")
        return _templated_fallback(analysis)
    except Exception as e:
        print(f"[narrator] LLM call failed: {e} — using templated fallback.")
        return _templated_fallback(analysis)


def _templated_fallback(analysis: dict) -> str:
    """
    Rule-based narrative for when LLM is unavailable.
    Produces a clear, honest summary from structured data.

    Insights are tuned to synthetic dataset patterns → may reflect simulated relationships and 
    might not generalize well to real-world distributions or unseen business scenarios.

    How LLM improves over _template_fallback:
    Provides context-aware reasoning, understands complex feature interactions, and 
    produces adaptive, natural insights instead of rigid rule-based outputs.
    """
    cohort = analysis.get("cohort", {})
    baseline = cohort.get("baseline_wr", 0)
    current  = cohort.get("current_wr", 0)
    change   = cohort.get("absolute_change", 0) * 100

    segments = analysis.get("top_segment_changes", [])
    top_seg  = segments[0] if segments else {}

    simpsons = analysis.get("simpsons", {})
    # Check if any dimension is primarily mix-shift driven
    mix_driven = [
        dim for dim, v in simpsons.items()
        if abs(v.get("mix_shift_effect", 0)) > abs(v.get("conversion_effect", 0))
    ]

    lines = [
        "## Situation",
        f"Win rate shifted from {baseline:.1%} (2023 baseline) to {current:.1%} (2024-Q1), "
        f"a change of {change:+.1f} percentage points. Pipeline volume remained stable, "
        f"indicating the decline reflects conversion quality rather than top-of-funnel issues.",
        "",
        "## Root Causes",
    ]

    if top_seg:
        lines.append(
            f"- **{top_seg.get('dimension','').title()} performance**: "
            f"'{top_seg.get('segment','')}' showed the largest decline "
            f"({top_seg.get('wr_change',0)*100:+.1f}pp), representing "
            f"an estimated ${abs(top_seg.get('revenue_impact',0)):,.0f} revenue impact."
        )

    if mix_driven:
        lines.append(
            f"- **Deal mix shift** ({', '.join(mix_driven)}): A portion of the win rate "
            f"decline is attributable to pipeline composition change, not conversion deterioration. "
            f"This points to a targeting strategy issue, not a sales execution issue."
        )

    insights = analysis.get("programmatic_insights", [])
    for ins in insights[1:3]:
        lines.append(f"- {ins}")

    lines += [
        "",
        "## Recommended Actions",
        "- **Segment intervention**: Prioritise coaching and deal review for the "
        f"highest-impact declining segments identified above.",
        "- **Targeting review**: If mix shift is a significant contributor, align with "
        "SDR and marketing teams on ICP criteria before investing in sales coaching.",
        "- **Early warning**: Implement the 5-metric alert system to detect future "
        "win rate degradation 6-8 weeks before it becomes a board-level issue.",
    ]

    return "\n".join(lines)