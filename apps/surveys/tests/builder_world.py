"""Sorğu qurucusu testləri üçün köməkçilər (2026-09-30) — ``factories.build_world`` üzərində."""

from __future__ import annotations

import datetime

from django.utils import timezone

from apps.surveys.constants import QuestionKind
from apps.surveys.models import SurveyQuestion
from apps.surveys.services import questions as editor
from apps.surveys.services import survey_builder as builder
from core.rls import bypass_rls

from .factories import member

TODAY = timezone.localdate


def manager(world, suffix="qch"):
    with bypass_rls():
        return member(world["org"], f"{world['org'].slug}_{suffix}", "quality_control_head")


ALL_KINDS = (
    (QuestionKind.LIKERT5, "Xidmətdən razıyam"),
    (QuestionKind.SINGLE, "Ən çox hansı kitabxananı istifadə edirsiniz?"),
    (QuestionKind.MULTI, "Hansı xidmətlərdən istifadə edirsiniz?"),
    (QuestionKind.NPS, "Bizi dostunuza tövsiyə edərdinizmi?"),
    (QuestionKind.YESNO, "Oxu zalı kifayətdirmi?"),
    (QuestionKind.SHORT_TEXT, "Bir sözlə təəssüratınız"),
    (QuestionKind.TEXT, "Nə təklif edərdiniz?"),
)


def make_survey(
    world,
    *,
    title="Kitabxana sorğusu",
    kind="general",
    audience="students",
    anonymous=True,
    mandatory=False,
    policy="defer_days",
    defer_days=3,
    audience_filter=None,
    kinds=ALL_KINDS,
    required=True,
    publish=True,
    opens_on=None,
    closes_on=None,
    k=3,
):
    """Qaralama yaradır, ayarları yazır, sualları əlavə edir və (istəyə görə) dərc edir."""
    with bypass_rls():
        survey = builder.create_survey(world["org"], kind=kind, title=title)
        values = {
            "anonymous": anonymous,
            "audience": audience,
            "audience_filter": audience_filter or {},
            "opens_on": opens_on,
            "closes_on": closes_on or (TODAY() + datetime.timedelta(days=14)),
            "mandatory": mandatory,
            "gate_policy": policy,
            "defer_days": defer_days,
            "min_group_size": k,
        }
        builder.update_settings(survey, values)
        survey.refresh_from_db()
        for question_kind, text in kinds:
            data = {"kind": question_kind, "text": text, "required": "1" if required else "0"}
            if question_kind in (QuestionKind.SINGLE, QuestionKind.MULTI):
                data["choices_text"] = "Mərkəzi\nFakültə\nOnlayn"
            if question_kind == QuestionKind.MULTI:
                data["min_choices"], data["max_choices"] = "1", "2"
            editor.add_question(survey, data)
        if publish:
            builder.publish(survey)
        survey.refresh_from_db()
    return survey


def questions_of(survey):
    return list(SurveyQuestion.objects.filter(template_id=survey.template_id).order_by("order", "code"))


def answer_payload(survey, *, likert="4", nps="9", yes="1", text="Yaxşıdır", pick=0):
    """Bütün suallara etibarlı cavab (POST lüğəti)."""
    data = {}
    for question in questions_of(survey):
        name = f"q_{question.code}"
        choices = [item["key"] for item in (question.options or {}).get("choices", [])]
        if question.kind == QuestionKind.LIKERT5:
            data[name] = likert
        elif question.kind == QuestionKind.NPS:
            data[name] = nps
        elif question.kind == QuestionKind.YESNO:
            data[name] = yes
        elif question.kind == QuestionKind.SINGLE:
            data[name] = choices[pick]
        elif question.kind == QuestionKind.MULTI:
            data[name] = [choices[pick]]
        elif question.kind in (QuestionKind.SHORT_TEXT, QuestionKind.TEXT):
            data[name] = text
    return data
