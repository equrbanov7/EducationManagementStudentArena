"""
courses/ai_planner.py — «AI ilə kurs qur» çekməcəsinin backend-i (2026-09-28).

NİYƏ: əvvəlki çekməcə (``course_ai_drawer.js``) yalnız VİTRİN idi — istənilən
prompt-a eyni hazır «Veb texnologiyaları» planını göstərir, «Təsdiqlə» heç nə
yaratmırdı. İndi:

1. :func:`generate_course_plan` — müəllimin təsvirindən Gemini ilə mövzu +
   (hər mövzu üçün) link resurslarından ibarət plan qurur. Plan normallaşdırılır
   (sayı, uzunluq, yalnız ``http(s)`` linklər) və heç nə YAZILMIR.
2. :func:`apply_course_plan` — müəllimin TƏSDİQLƏDİYİ elementləri atomik şəkildə
   ``CourseTopic`` + ``CourseResource(resource_type="link")`` kimi yaradır.

AI yalnız mövzu və resurs təklif edir: tapşırıq/lab/imtahan/qrup kimi elementlər
tarix, bal, tələbə seçimi tələb edir — onları müəllim öz modalında qurur.
"""

from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Max
from django.utils.translation import get_language

from apps.courses.models import CourseResource, CourseTopic

MAX_TOPICS = 16
MAX_RESOURCES_PER_TOPIC = 3
MAX_PROMPT_CHARS = 1500
_TITLE_MAX = 255
_DESC_MAX = 1200

_LANGUAGE_NAMES = {"az": "Azerbaijani", "en": "English", "ru": "Russian", "tr": "Turkish"}
_url_validator = URLValidator(schemes=["http", "https"])


def _clean_text(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].strip()


def _clean_url(value) -> str:
    url = str(value or "").strip()
    if not url or len(url) > 500:
        return ""
    try:
        _url_validator(url)
    except ValidationError:
        return ""
    return url


def normalise_plan(payload) -> dict:
    """Model cavabını (və ya müəllimin göndərdiyi seçimi) təhlükəsiz plana çevirir."""
    raw_topics = payload.get("topics") if isinstance(payload, dict) else payload
    topics = []
    for raw in raw_topics if isinstance(raw_topics, list) else []:
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title"), _TITLE_MAX)
        if not title:
            continue
        resources = []
        for res in raw.get("resources") if isinstance(raw.get("resources"), list) else []:
            if not isinstance(res, dict):
                continue
            res_title = _clean_text(res.get("title"), _TITLE_MAX)
            url = _clean_url(res.get("url"))
            if res_title and url:
                resources.append(
                    {"title": res_title, "url": url, "description": _clean_text(res.get("description"), 400)}
                )
            if len(resources) >= MAX_RESOURCES_PER_TOPIC:
                break
        topics.append(
            {
                "title": title,
                "description": _clean_text(raw.get("description"), _DESC_MAX),
                "resources": resources,
            }
        )
        if len(topics) >= MAX_TOPICS:
            break
    return {"topics": topics}


def _build_prompt(*, course, request_text: str, language_code: str) -> str:
    lang = _LANGUAGE_NAMES.get((language_code or "az")[:2], "Azerbaijani")
    existing = list(course.topics.order_by("order").values_list("title", flat=True)[:40])
    schema = {
        "topics": [
            {
                "title": "string (<= 120 chars, numbered by week if the teacher asked for weeks)",
                "description": "string (1-2 sentences: what students learn)",
                "resources": [{"title": "string", "url": "https://… (well-known, stable public page)"}],
            }
        ]
    }
    return (
        "You are an experienced university curriculum designer. Build a course outline for a teacher.\n"
        f"Write ALL text in {lang}.\n"
        f"Course title: {course.title}\n"
        f"Course description: {course.description or '-'}\n"
        f"Teacher's request: {request_text}\n"
        f"Topics that already exist in the course (do not repeat them): {json.dumps(existing, ensure_ascii=False)}\n"
        f"Return between 4 and {MAX_TOPICS} topics in logical teaching order. For each topic suggest 0 to "
        f"{MAX_RESOURCES_PER_TOPIC} learning resources that are REAL, stable public URLs (official documentation, "
        "university open courseware, Wikipedia, well-known tutorials). Never invent URLs; if unsure, omit the "
        "resource.\n"
        f"Respond ONLY with JSON matching this shape: {json.dumps(schema, ensure_ascii=False)}"
    )


def generate_course_plan(*, course, request_text: str, user_id: int | None, language_code: str | None = None) -> dict:
    """Plan yaradır (heç nə yazmır). Uğur: ``{"ok": True, "plan": {...}, "remaining": ...}``."""
    from apps.exams.public import generate_ai_json

    request_text = (request_text or "").strip()[:MAX_PROMPT_CHARS]
    result = generate_ai_json(
        prompt=(
            _build_prompt(
                course=course,
                request_text=request_text,
                language_code=language_code or get_language() or "az",
            )
            if request_text
            else ""
        ),
        user_id=user_id,
    )
    if not result.get("ok"):
        return {"ok": False, "code": result.get("code", ""), "error": result.get("error", "")}
    plan = normalise_plan(result.get("payload") or {})
    if not plan["topics"]:
        return {"ok": False, "error": "empty_plan"}
    extras = {key: result[key] for key in ("limit", "remaining", "window") if key in result}
    return {"ok": True, "plan": plan, **extras}


def apply_course_plan(*, course, plan) -> dict:
    """Təsdiqlənmiş planı kursa yazır — hamısı və ya heç biri."""
    clean = normalise_plan(plan)
    created_topics = created_resources = 0
    with transaction.atomic():
        order = CourseTopic.objects.filter(course=course).aggregate(Max("order"))["order__max"] or 0
        for item in clean["topics"]:
            order += 1
            topic = CourseTopic.objects.create(
                course=course, title=item["title"], description=item["description"], order=order
            )
            created_topics += 1
            for res in item["resources"]:
                CourseResource.objects.create(
                    course=course,
                    topic=topic,
                    title=res["title"],
                    description=res["description"],
                    resource_type="link",
                    url=res["url"],
                )
                created_resources += 1
    return {"topics": created_topics, "resources": created_resources}
