"""
AI-powered exam statistics summary generation using Google Gemini.

Reads the API key from the GEMINI_API_KEY environment variable.
Falls back gracefully when the key is not configured.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.utils.translation import get_language
from django.utils.translation import pgettext

logger = logging.getLogger(__name__)


def _get_api_key() -> str | None:
    """Return the Gemini API key from settings, or *None* if unconfigured."""
    key = getattr(settings, "GEMINI_API_KEY", "") or ""
    return key.strip() or None


def _language_name(code: str) -> str:
    mapping = {
        "az": "Azerbaijani",
        "en": "English",
        "ru": "Russian",
        "tr": "Turkish",
    }
    return mapping.get(code, "English")


def generate_exam_statistics_summary(
    *,
    exam_title: str,
    exam_type: str,
    stats: dict,
    language_code: str | None = None,
) -> dict:
    """Generate an AI-powered summary of exam statistics.

    Parameters
    ----------
    exam_title : str
        Human-readable exam title.
    exam_type : str
        "test", "written", or a live-exam identifier.
    stats : dict
        Pre-computed statistics dictionary containing keys such as
        ``total_attempts``, ``avg_score``, ``pass_rate``, ``group_stats``,
        ``question_stats``, etc.
    language_code : str | None
        ISO language code (az/en/ru/tr).  Defaults to the current request
        language.

    Returns
    -------
    dict
        ``{"ok": True, "summary": "<markdown text>"}`` on success, or
        ``{"ok": False, "error": "<reason>"}`` on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "gemini_api_key_missing")}

    lang = language_code or get_language() or "en"
    lang_name = _language_name(lang)

    prompt = _build_prompt(
        exam_title=exam_title,
        exam_type=exam_type,
        stats=stats,
        lang_name=lang_name,
    )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        text = response.text or ""
        return {"ok": True, "summary": text.strip()}
    except Exception:
        logger.exception("Gemini AI summary generation failed")
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "generation_failed")}


def _build_prompt(
    *,
    exam_title: str,
    exam_type: str,
    stats: dict,
    lang_name: str,
) -> str:
    stats_json = json.dumps(stats, ensure_ascii=False, default=str)
    return f"""You are an expert education analytics assistant. Analyze the following exam statistics and provide a professional summary.

**Exam:** {exam_title}
**Type:** {exam_type}
**Language:** Respond ONLY in {lang_name}.

**Statistics data (JSON):**
```json
{stats_json}
```

Please provide:
1. **Performance Summary** — A concise overview of overall performance.
2. **Critical Analysis** — Key strengths and weaknesses observed.
3. **Notable Patterns** — Any anomalies, trends, or outliers.
4. **Group Comparison** (if group data is present) — Compare groups by average score, pass rate, and participation.
5. **Topic/Question Analysis** (if question data is present) — Which topics/questions students struggled with most and which they excelled at.
6. **Recommendations** — Actionable suggestions for teachers to improve outcomes.
7. **Students at Risk** — Identify struggling students or groups that need extra attention.

Format the response in clean Markdown with headers. Be concise but thorough. Do not include the raw data in your response. Focus on insights and actionable information."""
