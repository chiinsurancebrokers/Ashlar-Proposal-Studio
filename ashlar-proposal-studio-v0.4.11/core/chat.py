"""Grounded case chat for Ashlar Proposal Studio.

The chat never re-reads the full document library on each turn. It reasons over the
structured analysis plus deterministic target-plan evidence that was already produced
for the case. If the answer is not supported by that material it must say so.
"""
from __future__ import annotations

import json
import os

import anthropic


SYSTEM_PROMPT = """You are HAL inside Ashlar Proposal Studio, an internal insurance-broker decision-support tool.

You are discussing ONE already-analyzed insurance case with a professional broker.
Use only the case context supplied below. Do not invent policy benefits, premiums,
underwriting terms, exclusions, waiting periods, or eligibility rules.

Rules:
1. Prefer applicant-specific quotation facts over generic brochure facts when both are present.
2. Treat deterministic target-plan rows as strong evidence for multi-plan brochures.
3. Distinguish clearly between INCLUDED, OPTIONAL/AVAILABLE, and CONFIRMED SELECTED.
4. If the available context does not support an answer, say exactly what document or clause is missing.
5. When evidence includes a source file/page, cite it in plain text like: [IMG GPMI brochure, p.6].
6. When comparing plans, explain the practical difference for the client rather than only repeating limits.
7. Apply applicant relevance. Do not raise maternity/pregnancy/newborn benefits for a male applicant. Keep diagnostic imaging (MRI/CT/PET) separate from wellness/preventive benefits.
8. Do not provide a final placement decision as if you were the insurer. Underwriting and final acceptance remain subject to carrier confirmation.
9. Keep answers concise unless the broker asks for a detailed analysis.
"""


def _compact_result(result: dict) -> dict:
    rows = result.get("focused_rows") or []
    # Cap deterministic evidence to keep chat responsive while retaining a useful spread.
    compact_rows = [
        {
            "source_file": r.get("source_file"),
            "page": r.get("page"),
            "section": r.get("section"),
            "benefit": r.get("benefit"),
            "value": r.get("value"),
            "evidence_type": r.get("evidence_type"),
        }
        for r in rows[:120]
    ]
    return {
        "provider": result.get("provider"),
        "target_plan": result.get("target_plan"),
        "plan_selection": result.get("plan_selection"),
        "library_files": result.get("library_files"),
        "analysis": result.get("analysis"),
        "target_plan_evidence": compact_rows,
    }


def build_case_context(
    case_reference: str,
    results: list[dict],
    *,
    client_profile: str = "",
    client_priorities: str = "",
    client_sex: str = "Not specified",
    client_age: int | None = None,
) -> str:
    payload = {
        "case_reference": case_reference or "Unnamed case",
        "client_profile": client_profile or "Not supplied",
        "client_priorities": client_priorities or "Not supplied",
        "client_sex": client_sex or "Not specified",
        "client_age": client_age,
        "providers": [_compact_result(r) for r in results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def ask_case_agent(
    *,
    question: str,
    case_reference: str,
    client_profile: str = "",
    client_priorities: str = "",
    client_sex: str = "Not specified",
    client_age: int | None = None,
    results: list[dict] = None,
    history: list[dict] | None = None,
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return "AI chat is unavailable because ANTHROPIC_API_KEY is not configured."

    model = os.getenv("HAL_CHAT_MODEL", os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"))
    case_context = build_case_context(
        case_reference,
        results or [],
        client_profile=client_profile,
        client_priorities=client_priorities,
        client_sex=client_sex,
        client_age=client_age,
    )

    history = history or []
    recent = history[-8:]
    transcript = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in recent
    )

    user_prompt = f"""=== CASE CONTEXT ===
{case_context}

=== RECENT CHAT ===
{transcript or 'No prior chat.'}

=== BROKER QUESTION ===
{question}

Answer only from the supplied case context. Cite source file/page where available.
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.AuthenticationError:
        return "HAL could not authenticate with Anthropic. Check ANTHROPIC_API_KEY in Railway."
    except anthropic.NotFoundError:
        return f"HAL could not access the configured model '{model}'. Check HAL_CHAT_MODEL / CLAUDE_MODEL in Railway."
    except anthropic.RateLimitError:
        return "HAL is temporarily rate-limited by the model provider. Please try again shortly."
    except anthropic.APIConnectionError as exc:
        return f"HAL could not reach the model provider: {exc}"
    except anthropic.APIError as exc:
        return f"HAL model request failed: {exc}"

    answer = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    return answer or "HAL returned an empty response. Please try again."
