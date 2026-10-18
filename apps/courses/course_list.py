"""«Kurslarım» (müəllim) siyahısının sorğu qatı — filtr, sıralama, səhifələmə, kart sayğacları (2026-10-18).

Kabinet bölməsi (``apps/accounts``) yalnız bu modulun ``build_teacher_course_list``-ini çağırır;
kurs/üzv/mövzu/imtahan sorğuları və task modullarının sayğac registry-si burada yaşayır.

SORĞU BÜDCƏSİ (kart sayından ASILI DEYİL):
  1. KPI aqreqatı (status sayları + sillabusa bağlı + unikal tələbə) — tək ``aggregate``;
  2. filtr seçimləri (bağlı sillabusların fənləri + kursların semestrləri; kurs yoxdursa atlanır);
  3. səhifələyicinin ``COUNT``-u — YALNIZ filtr tətbiq olunanda (əks halda 1-dəki ``total``);
  4. görünən səhifənin kartları — mövzu/tələbə/qrup/imtahan/tapşırıq sayları korrelyasiyalı
     alt-sorğularla eyni SELECT-dədir, fənn/sillabus/semestr ``select_related``;
  5. görünən kartların qrup çipləri (bir ``values_list``).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.models import Exam
from apps.exams.public import without_disabled_practical_exams
from core.search_text import tolerant_q
from core.ui import status_catalog

from . import dashboard_sources, presentation
from .models import Course, CourseMembership, CourseTopic

CTX = "courses.list"
PREFIX = "mc_"
PAGE_SIZE = 12
STATUS_KEYS = ("published", "draft", "archived")
SORTS = {
    "newest": ("-created_at", "-id"),
    "updated": ("-updated_at", "-id"),
    "title": ("title", "id"),
    "students": ("-card_student_count", "title", "id"),
}
GROUP_CHIP_LIMIT = 4


def _count_subquery(queryset, field="course_id"):
    rows = queryset.filter(**{field: OuterRef("pk")}).order_by().values(field).annotate(n=Count("pk")).values("n")
    return Coalesce(Subquery(rows, output_field=IntegerField()), Value(0))


def _annotate_cards(queryset):
    students = CourseMembership.objects.filter(role="student")
    groups = (
        CourseMembership.objects.filter(role="student", course_id=OuterRef("pk"))
        .exclude(group_name="")
        .order_by()
        .values("course_id")
        .annotate(n=Count("group_name", distinct=True))
        .values("n")
    )
    return queryset.annotate(
        card_topic_count=_count_subquery(CourseTopic.objects.all()),
        card_student_count=_count_subquery(students),
        card_group_count=Coalesce(Subquery(groups, output_field=IntegerField()), Value(0)),
        # Kurs paneli ilə eyni süzgəc: söndürülmüş imtahan növləri (praktiki) sayılmır.
        card_exam_count=_count_subquery(without_disabled_practical_exams(Exam.objects.filter(is_deleted=False))),
        card_task_count=dashboard_sources.task_count_expression(),
    )


def _clean(params, name, allowed=None, default=""):
    value = (params.get(PREFIX + name) or "").strip()
    if allowed is not None and value not in allowed:
        return default
    return value


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _kpis(base_courses):
    # Tək sorğu: üzvlük JOIN-i sətirləri çoxaldır, ona görə kurs sayları da `distinct=True`-dur.
    stats = base_courses.aggregate(
        total=Count("id", distinct=True),
        published=Count("id", filter=Q(status="published"), distinct=True),
        draft=Count("id", filter=Q(status="draft"), distinct=True),
        archived=Count("id", filter=Q(status="archived"), distinct=True),
        linked=Count("id", filter=Q(syllabus__isnull=False), distinct=True),
        students=Count("memberships__user_id", filter=Q(memberships__role="student"), distinct=True),
    )
    students = stats["students"]
    return stats, [
        {
            "label": pgettext(CTX, "Kurslar"),
            "value": stats["total"],
            "note": pgettext(CTX, "Arxivdə: %(n)s") % {"n": stats["archived"]},
            "tone": "accent-primary",
        },
        {
            "label": pgettext(CTX, "Yayımlanıb"),
            "value": stats["published"],
            "note": pgettext(CTX, "tələbələr görür"),
            "tone": "accent-success",
        },
        {
            "label": pgettext(CTX, "Qaralama"),
            "value": stats["draft"],
            "note": pgettext(CTX, "tələbələrdən gizlidir"),
            "tone": "accent-warning" if stats["draft"] else "",
        },
        {"label": pgettext(CTX, "Tələbələr"), "value": students, "note": pgettext(CTX, "bütün kurslar üzrə unikal")},
        {
            "label": pgettext(CTX, "Sillabusa bağlı"),
            "value": stats["linked"],
            "note": pgettext(CTX, "%(n)s kursdan") % {"n": stats["total"]},
        },
    ]


def _filter_options(base_courses):
    subjects, periods = {}, {}
    rows = (
        base_courses.filter(Q(syllabus__isnull=False) | Q(period__isnull=False))
        .values_list("syllabus__subject_id", "syllabus__subject__name", "period_id", "period__name")
        .distinct()
    )
    for subject_id, subject_name, period_id, period_name in rows:
        if subject_id:
            subjects[subject_id] = subject_name or ""
        if period_id:
            periods[period_id] = period_name or ""
    as_options = lambda mapping: sorted(  # noqa: E731
        ({"value": str(key), "label": label} for key, label in mapping.items()), key=lambda o: o["label"].casefold()
    )
    return as_options(subjects), as_options(periods)


def _filter_fields(state, subject_options, period_options):
    fields = [
        {
            "name": PREFIX + "q",
            "label": pgettext(CTX, "Axtarış"),
            "kind": "search",
            "wide": True,
            "value": state["q"],
            "placeholder": pgettext(CTX, "Kurs adı, təsviri və ya fənn"),
        },
        {
            "name": PREFIX + "status",
            "label": pgettext(CTX, "Status"),
            "kind": "select",
            "value": state["status"],
            "options": [{"value": "", "label": pgettext(CTX, "Bütün statuslar")}]
            + [{"value": key, "label": status_catalog.label("course", key)} for key in STATUS_KEYS],
        },
    ]
    if subject_options:
        fields.append(
            {
                "name": PREFIX + "subject",
                "label": pgettext(CTX, "Fənn"),
                "kind": "select",
                "value": state["subject"],
                "searchable": len(subject_options) > 8,
                "options": [{"value": "", "label": pgettext(CTX, "Bütün fənlər")}] + subject_options,
            }
        )
    if period_options:
        fields.append(
            {
                "name": PREFIX + "period",
                "label": pgettext(CTX, "Semestr"),
                "kind": "select",
                "value": state["period"],
                "options": [{"value": "", "label": pgettext(CTX, "Bütün semestrlər")}] + period_options,
            }
        )
    fields.append(
        {
            "name": PREFIX + "sort",
            "label": pgettext(CTX, "Sıralama"),
            "kind": "select",
            "value": state["sort"],
            "default": "newest",
            "options": [
                {"value": "newest", "label": pgettext(CTX, "Ən yenisi əvvəl")},
                {"value": "updated", "label": pgettext(CTX, "Son yenilənən")},
                {"value": "title", "label": pgettext(CTX, "Ada görə (A–Z)")},
                {"value": "students", "label": pgettext(CTX, "Ən çox tələbə")},
            ],
        }
    )
    return fields


def _apply_filters(queryset, state):
    if state["status"]:
        queryset = queryset.filter(status=state["status"])
    subject_id = _int_or_none(state["subject"])
    if subject_id:
        queryset = queryset.filter(syllabus__subject_id=subject_id)
    period_id = _int_or_none(state["period"])
    if period_id:
        queryset = queryset.filter(period_id=period_id)
    search_q = tolerant_q(
        state["q"], ("title", "description", "syllabus__subject__name"), compact_fields=("syllabus__subject__code",)
    )
    if search_q is not None:
        queryset = queryset.filter(search_q)
    return queryset


def _attach_groups(courses):
    ids = [course.id for course in courses]
    names = {}
    if ids:
        rows = (
            CourseMembership.objects.filter(course_id__in=ids, role="student")
            .exclude(group_name="")
            .values_list("course_id", "group_name")
            .distinct()
            .order_by("course_id", "group_name")
        )
        for course_id, group_name in rows:
            names.setdefault(course_id, []).append(group_name)
    for course in courses:
        course.card_group_names = names.get(course.id, [])[:GROUP_CHIP_LIMIT]
        course.card_group_more = max(0, course.card_group_count - GROUP_CHIP_LIMIT)
        course.card_status = status_catalog.get("course", course.status) or status_catalog.get("course", "draft")
        course.card_syllabus_version = _syllabus_version(course)
    return courses


def _syllabus_version(course):
    syllabus = course.syllabus if course.syllabus_id else None
    if syllabus is None or not syllabus.is_active:
        return None
    return syllabus.approved_version or syllabus.current_version


def _pagination_query(state):
    """``_pagination.html`` üçün səhifə nömrəsindən başqa bütün vəziyyət (bölmə + filtrlər)."""
    return urlencode({"section": "my-courses", **{PREFIX + key: value for key, value in state.items() if value}})


def build_teacher_course_list(*, base_queryset, params, user) -> dict:
    """Müəllimin «Kurslarım» bölməsi üçün tam context (bax modul docstring-i — sorğu büdcəsi)."""
    state = {
        "q": _clean(params, "q")[:120],
        "status": _clean(params, "status", STATUS_KEYS),
        "subject": _clean(params, "subject"),
        "period": _clean(params, "period"),
        "sort": _clean(params, "sort", SORTS, "newest"),
    }
    base_ids = base_queryset.order_by().values("id")
    base_courses = Course.objects.filter(id__in=base_ids)
    stats, kpi_tiles = _kpis(base_courses)
    subject_options, period_options = _filter_options(base_courses) if stats["total"] else ([], [])

    filtered = _apply_filters(base_courses, state)
    filtered = _annotate_cards(filtered.select_related("syllabus__subject", "syllabus__approved_version", "period"))
    filtered = filtered.select_related("syllabus__current_version").order_by(*SORTS[state["sort"]])

    paginator = Paginator(filtered, PAGE_SIZE)
    filtered_flag = bool(state["q"] or state["status"] or state["subject"] or state["period"])
    if not filtered_flag:
        # Filtrsiz siyahının ölçüsü KPI aqreqatındakı `total`-dır — səhifələyicinin ayrıca COUNT-u lazım deyil.
        paginator.__dict__["count"] = stats["total"]
    page_obj = paginator.get_page(params.get(PREFIX + "page"))
    courses = _attach_groups(presentation.decorate(list(page_obj.object_list)))
    for course in courses:
        course.card_is_owner = course.owner_id == getattr(user, "pk", None)

    return {
        "courses": courses,
        "page_obj": page_obj,
        "pagination_query": _pagination_query(state),
        # Kurs panelinin «geri» keçidi: fraqment URL-i DEYİL, kabinet + cari filtrlər/səhifə.
        "return_to": f"{reverse('accounts:profile')}?{_pagination_query(state)}"
        + (f"&{PREFIX}page={page_obj.number}" if page_obj.number > 1 else ""),
        "kpi_tiles": kpi_tiles,
        "filter_fields": _filter_fields(state, subject_options, period_options),
        "filter_count_label": pgettext(CTX, "Nəticə: %(n)s kurs") % {"n": paginator.count},
        "result_count": paginator.count,
        "total": stats["total"],
        "is_filtered": filtered_flag,
        "state": state,
    }


__all__ = ["PAGE_SIZE", "build_teacher_course_list"]
