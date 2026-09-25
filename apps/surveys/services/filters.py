"""Nəticə filtrləri + əhatəli queryset qurucusu (analitika API-sinin ortaq girişi).

``ResultFilters.from_params(request.GET)`` F2 UI-ı üçün rahatlıqdır: hər dəyər
yoxlanılır (UUID / tam ədəd), yanlış dəyər səssizcə atılır (500 yox).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from django.db.models import Max

from core.search_text import tokens_of, tolerant_regex

from ..constants import DEFAULT_MIN_GROUP_SIZE, Section
from ..models import SurveyCampaign, SurveyResponse
from .access import response_scope_q


def _uuid_or_none(raw):
    try:
        return uuid.UUID(str(raw)) if raw not in (None, "") else None
    except (TypeError, ValueError, AttributeError):
        return None


def _int_or_none(raw):
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ResultFilters:
    """Bütün analitika funksiyalarının ortaq filtr dəsti (hamısı opsional)."""

    campaign_ids: tuple = ()
    faculty_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    teacher_id: int | None = None
    subject_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    course_year: int | None = None
    question_code: str = ""
    text_query: str = ""

    #: Müəllimin/kafedranın ÜMUMİ nəticəsini daraldan filtrlər (tamamlayıcı qayda üçün).
    NARROWING = ("subject_id", "group_id", "program_id", "course_year")

    @classmethod
    def from_params(cls, params) -> "ResultFilters":
        getlist = getattr(params, "getlist", None)
        raw_campaigns = getlist("campaign") if getlist else params.get("campaign") or []
        if isinstance(raw_campaigns, (str, uuid.UUID)):
            raw_campaigns = [raw_campaigns]
        campaigns = tuple(pk for pk in (_uuid_or_none(value) for value in raw_campaigns) if pk)
        return cls(
            campaign_ids=campaigns,
            faculty_id=_uuid_or_none(params.get("faculty")),
            department_id=_uuid_or_none(params.get("department")),
            teacher_id=_int_or_none(params.get("teacher")),
            subject_id=_uuid_or_none(params.get("subject")),
            group_id=_uuid_or_none(params.get("group")),
            program_id=_uuid_or_none(params.get("program")),
            course_year=_int_or_none(params.get("course_year")),
            question_code=str(params.get("question") or "")[:64],
            text_query=str(params.get("q") or "")[:120],
        )

    @property
    def is_narrowed(self) -> bool:
        return any(getattr(self, name) is not None for name in self.NARROWING)

    def without_narrowing(self) -> "ResultFilters":
        return replace(self, **{name: None for name in self.NARROWING})


def campaign_ids_for(organization, filters) -> list:
    """Filtrdəki kampaniyalar (təşkilata aid olanlar); boşdursa bütün kampaniyalar."""
    queryset = SurveyCampaign.objects.filter(organization=organization)
    if filters.campaign_ids:
        queryset = queryset.filter(pk__in=filters.campaign_ids)
    return list(queryset.values_list("pk", flat=True))


def k_threshold(campaign_ids) -> int:
    """Birdən çox kampaniya birləşəndə ən SƏRT (böyük) k tətbiq olunur."""
    value = SurveyCampaign.objects.filter(pk__in=campaign_ids).aggregate(k=Max("min_group_size"))["k"]
    return max(int(value or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE)


def responses(organization, scope, filters, campaign_ids, *, section=Section.TEACHER):
    """Əhatəli + filtrli ``SurveyResponse`` queryset-i (``values``/``aggregate`` üçün baza)."""
    queryset = SurveyResponse.objects.filter(organization=organization, scope=section, campaign_id__in=campaign_ids)
    for field, value in (
        ("faculty_id", filters.faculty_id),
        ("teacher_department_id", filters.department_id),
        ("teacher_id", filters.teacher_id),
        ("subject_id", filters.subject_id),
        ("group_id", filters.group_id),
        ("program_id", filters.program_id),
        ("course_year", filters.course_year),
    ):
        if value is not None:
            queryset = queryset.filter(**{field: value})
    return queryset.filter(response_scope_q(scope))


def text_regex(query) -> list:
    """Dözümlü (az/ing klaviatura) regex tokenləri — ``text__iregex`` üçün."""
    return [tolerant_regex(token) for token in tokens_of(query)]
