"""İmtahan mərkəzi — apellyasiya statistikası (SPA bölmə backend-i).

Bütün apellyasiyaların analitikası: filtr (fənn, qrup, kafedra/fakültə, imtahan
tipi, status, semestr, il, mətn axtarışı) → sayğaclar + səhifələnən cədvəl +
qrafik aqreqatları + AI xülasə. İcazə: yalnız imtahan mərkəzi (rəhbər + işçi).

Data AJAX ilə gəlir:
* ``appeal_stats_data``     — filtr + summary + səhifələnən cədvəl
* ``appeal_stats_charts``   — bütün filtrlənmiş data üzrə qrafik aqreqatları
* ``appeal_stats_filters``  — filtr metadatası (illər, tiplər, kafedralar, ...)
* ``appeal_stats_ai``       — AI xülasə (data-hash keş + rate limit)
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import get_language, pgettext
from django.views.decorators.http import require_GET

from apps.exams.public import is_exam_center_user
from apps.exams.services.ai_summary import generate_appeal_statistics_summary
from apps.exams.views.exam_center._shared import supervisor_org_or_403

from ...constants import APPEAL_STATUS_CHOICES, APPEAL_STATUS_VALUES
from ...models import Appeal

_PAGE_SIZE = 15

# Tədris ili sentyabrda başlayır (sentyabr–avqust = bir tədris ili).
_ACADEMIC_YEAR_START_MONTH = 9


def _academic_year_start(dt):
    """datetime → tədris ilinin başlanğıc təqvim ili (lokal vaxta görə)."""
    local = timezone.localtime(dt)
    return local.year if local.month >= _ACADEMIC_YEAR_START_MONTH else local.year - 1


# Sütun → DB order ifadəsi (klik-sıralama).
_SORT_MAP = {
    "student": ("student__first_name", "student__last_name", "student__username"),
    "exam": ("exam__title",),
    "subject": ("exam__subject__name",),
    "type": ("exam__exam_type_extended",),
    "status": ("status",),
    "date": ("created_at",),
}

# Semestr → ay dəsti (payız: sen-yan, yaz: fev-iyun, yay: iyul-avqust).
_SEMESTERS = {
    "fall": (9, 10, 11, 12, 1),
    "spring": (2, 3, 4, 5, 6),
    "summer": (7, 8),
}
_SEMESTER_LABELS = {
    "fall": pgettext("appeals.stats.semester", "Payız semestri"),
    "spring": pgettext("appeals.stats.semester", "Yaz semestri"),
    "summer": pgettext("appeals.stats.semester", "Yay semestri"),
}


def _stats_org(request):
    organization = supervisor_org_or_403(request)
    if not is_exam_center_user(request.user):
        raise PermissionDenied(pgettext("appeals.stats.permission", "Bu bölmə yalnız imtahan mərkəzi üçündür."))
    return organization


def _csv_ints(raw):
    return [int(x) for x in (raw or "").split(",") if x.strip().isdigit()]


def _csv_uuids(raw):
    """UUID PK-lı sahələr (Subject, OrgUnit) üçün. `_csv_ints` UUID-ləri
    ATIRDI (isdigit False) → fənn/fakültə/kafedra filtri səssizcə işləməzdi."""
    import uuid as _uuid

    out = []
    for x in (raw or "").split(","):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(str(_uuid.UUID(x)))
        except ValueError:
            continue
    return out


def _unit_ids_with_children(organization, unit_ids):
    if not unit_ids:
        return []
    from apps.organizations.models import OrgUnit

    rows = OrgUnit.objects.filter(organization=organization).filter(Q(id__in=unit_ids) | Q(parent_id__in=unit_ids))
    return list(rows.values_list("id", flat=True))


def _filtered_appeals(request, organization):
    """GET filtrlərinə görə apellyasiyaların queryset-i (imtahan mərkəzinin org-u)."""
    qs = Appeal.objects.filter(organization=organization).select_related(
        "student", "exam", "exam__subject", "exam__author"
    )

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(student__first_name__icontains=q)
            | Q(student__last_name__icontains=q)
            | Q(student__username__icontains=q)
            | Q(exam__title__icontains=q)
        )

    subject_ids = _csv_uuids(request.GET.get("subjects"))
    if subject_ids:
        qs = qs.filter(exam__subject_id__in=subject_ids)

    group_ids = _csv_ints(request.GET.get("groups"))
    if group_ids:
        qs = qs.filter(exam__allowed_groups__id__in=group_ids)

    unit_ids = _csv_uuids(request.GET.get("units"))
    if unit_ids:
        qs = qs.filter(exam__allowed_groups__org_unit_id__in=_unit_ids_with_children(organization, unit_ids))

    # Ayrı fakültə/kafedra/müəllim filtrləri (imtahan statistikası ilə eyni sxem;
    # fakültə seçiləndə onun kafedraları göstərilir — kaskad).
    faculty_ids = _csv_uuids(request.GET.get("faculties"))
    if faculty_ids:
        qs = qs.filter(exam__allowed_groups__org_unit__parent_id__in=faculty_ids)

    department_ids = _csv_uuids(request.GET.get("departments"))
    if department_ids:
        qs = qs.filter(exam__allowed_groups__org_unit_id__in=department_ids)

    teacher_ids = _csv_ints(request.GET.get("teachers"))
    if teacher_ids:
        qs = qs.filter(exam__author_id__in=teacher_ids)

    exam_type = (request.GET.get("type") or "").strip()
    if exam_type:
        qs = qs.filter(exam__exam_type_extended=exam_type)

    exam_format = (request.GET.get("format") or "").strip()
    if exam_format:
        qs = qs.filter(exam__exam_type=exam_format)

    status = (request.GET.get("status") or "").strip()
    if status in APPEAL_STATUS_VALUES:
        qs = qs.filter(status=status)

    # TƏDRİS İLİ filtri: `year` başlanğıc təqvim ili (2025 = 2025/2026).
    year = (request.GET.get("year") or "").strip()
    if year.isdigit():
        from datetime import datetime

        start = int(year)
        lo = timezone.make_aware(datetime(start, _ACADEMIC_YEAR_START_MONTH, 1))
        hi = timezone.make_aware(datetime(start + 1, _ACADEMIC_YEAR_START_MONTH, 1))
        qs = qs.filter(created_at__gte=lo, created_at__lt=hi)

    semester = (request.GET.get("semester") or "").strip()
    if semester in _SEMESTERS:
        qs = qs.filter(created_at__month__in=_SEMESTERS[semester])

    return qs.distinct()


def _sorted(qs, request):
    raw = (request.GET.get("sort") or "").strip()
    key = raw[1:] if raw.startswith("-") else raw
    desc = raw.startswith("-")
    fields = _SORT_MAP.get(key)
    if not fields:
        return qs.order_by("-created_at", "-id")
    prefix = "-" if desc else ""
    return qs.order_by(*[f"{prefix}{f}" for f in fields], "-id")


def _dedup(names):
    seen, out = set(), []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _row(appeal):
    exam = appeal.exam
    subject = getattr(exam, "subject", None)
    groups = list(exam.allowed_groups.all())
    teacher = ""
    if exam.author_id:
        teacher = exam.author.get_full_name() or exam.author.username
    return {
        "appeal_id": appeal.id,
        "student": appeal.student.get_full_name() or appeal.student.username,
        "username": appeal.student.username,
        "group": ", ".join(_dedup(g.name for g in groups)),
        "teacher": teacher,
        "exam": exam.title,
        "subject": (f"{subject.code} — {subject.name}" if subject else ""),
        "type": exam.get_exam_type_extended_display() if exam.exam_type_extended else "",
        "items": appeal.items.count(),
        "status": appeal.get_status_display(),
        "status_code": appeal.status,
        "date": timezone.localtime(appeal.created_at).strftime("%d.%m.%Y %H:%M"),
    }


def _summary(qs):
    # ``.order_by()`` Appeal.Meta.ordering-i təmizləyir — əks halda o, GROUP BY-a
    # sızır və eyni statuslu apellyasiyaları ayrı-ayrı sətirlərə bölür (aztsayma).
    by_status = {
        row["status"]: row["n"] for row in qs.order_by().values("status").annotate(n=Count("id", distinct=True))
    }
    return {
        "total": qs.count(),
        "students": qs.values("student_id").distinct().count(),
        "exams": qs.values("exam_id").distinct().count(),
        "by_status": [
            {"code": code, "label": str(label), "n": by_status.get(code, 0)} for code, label in APPEAL_STATUS_CHOICES
        ],
    }


@login_required
@require_GET
def appeal_stats_data(request):
    organization = _stats_org(request)
    appeals = _filtered_appeals(request, organization)
    page_obj = Paginator(_sorted(appeals, request), _PAGE_SIZE).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "results": [_row(a) for a in page_obj.object_list],
            "summary": _summary(appeals),
            "pagination": {
                "page": page_obj.number,
                "num_pages": page_obj.paginator.num_pages,
                "has_prev": page_obj.has_previous(),
                "has_next": page_obj.has_next(),
                "count": page_obj.paginator.count,
            },
        }
    )


def _breakdown(qs, field, label_map=None, limit=10):
    rows = qs.values(field).annotate(n=Count("id", distinct=True)).order_by("-n")[:limit]
    labels, counts = [], []
    for row in rows:
        raw = row[field]
        labels.append(str(label_map.get(raw, raw)) if label_map else (raw or "—"))
        counts.append(row["n"])
    return {"labels": labels, "counts": counts}


def _by_subject(qs, limit=10):
    rows = (
        qs.exclude(exam__subject__isnull=True)
        .values("exam__subject__code", "exam__subject__name")
        .annotate(n=Count("id", distinct=True))
        .order_by("-n")[:limit]
    )
    return {
        "labels": [f"{r['exam__subject__code']} — {r['exam__subject__name']}" for r in rows],
        "counts": [r["n"] for r in rows],
    }


def _by_teacher(qs, limit=10):
    rows = (
        qs.exclude(exam__author__isnull=True)
        .values("exam__author__first_name", "exam__author__last_name", "exam__author__username")
        .annotate(n=Count("id", distinct=True))
        .order_by("-n")[:limit]
    )
    labels = []
    for r in rows:
        name = f"{r['exam__author__first_name']} {r['exam__author__last_name']}".strip()
        labels.append(name or r["exam__author__username"])
    return {"labels": labels, "counts": [r["n"] for r in rows]}


def _monthly(qs, limit=24):
    rows = list(
        qs.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(n=Count("id", distinct=True))
        .order_by("month")
    )[-limit:]
    return {
        "labels": [r["month"].strftime("%Y-%m") for r in rows if r["month"]],
        "counts": [r["n"] for r in rows if r["month"]],
    }


def _by_status(qs):
    label_map = dict(APPEAL_STATUS_CHOICES)
    rows = qs.values("status").annotate(n=Count("id", distinct=True)).order_by("-n")
    return {
        "labels": [str(label_map.get(r["status"], r["status"])) for r in rows],
        "counts": [r["n"] for r in rows],
    }


def _chart_payload(qs):
    from apps.exams.models import Exam

    type_labels = dict(Exam.EXAM_TYPE_EXTENDED_CHOICES)
    return {
        "by_status": _by_status(qs),
        "monthly": _monthly(qs),
        "by_type": _breakdown(qs, "exam__exam_type_extended", label_map=type_labels),
        "by_subject": _by_subject(qs),
        "by_teacher": _by_teacher(qs),
    }


@login_required
@require_GET
def appeal_stats_charts(request):
    organization = _stats_org(request)
    qs = _filtered_appeals(request, organization)
    return JsonResponse(_chart_payload(qs))


@login_required
@require_GET
def appeal_stats_filters(request):
    organization = _stats_org(request)
    from apps.exams.models import Exam
    from apps.organizations.models import OrgUnit

    # Tədris illəri (2025/2026 formatı) — apellyasiya tarixlərindən sentyabr sərhədi ilə.
    year_starts = sorted(
        {
            _academic_year_start(d)
            for d in Appeal.objects.filter(organization=organization).values_list("created_at", flat=True)
        },
        reverse=True,
    )
    academic_years = [{"value": str(s), "label": f"{s}/{s + 1}"} for s in year_starts]
    units = list(
        OrgUnit.objects.filter(organization=organization, is_active=True)
        .order_by("name")
        .values("id", "name", "unit_type", "parent_id")
    )
    # Fakültə (faculty/deanery) və kafedra (chair/department) ayrı — iki müstəqil
    # filtr + kaskad (imtahan statistikası ilə eyni sxem). Müəllim = Exam.author.
    faculty_types = {"faculty", "deanery"}
    department_types = {"chair", "department"}
    faculties = [{"id": u["id"], "name": u["name"]} for u in units if u["unit_type"] in faculty_types]
    departments = [
        {"id": u["id"], "name": u["name"], "parent_id": u["parent_id"]}
        for u in units
        if u["unit_type"] in department_types
    ]
    teachers = [
        {
            "id": row["author_id"],
            "name": (f"{row['author__first_name']} {row['author__last_name']}".strip() or row["author__username"]),
        }
        for row in (
            Exam.objects.filter(organization=organization, author__isnull=False)
            .values("author_id", "author__first_name", "author__last_name", "author__username")
            .distinct()
            .order_by("author__first_name", "author__last_name")
        )
    ]
    return JsonResponse(
        {
            "academic_years": academic_years,
            "units": units,  # geriyə-uyğunluq
            "faculties": faculties,
            "departments": departments,
            "teachers": teachers,
            "types": [{"value": v, "label": str(lbl)} for v, lbl in Exam.EXAM_TYPE_EXTENDED_CHOICES],
            "formats": [{"value": v, "label": str(lbl)} for v, lbl in Exam.EXAM_TYPE_CHOICES],
            "statuses": [{"value": v, "label": str(lbl)} for v, lbl in APPEAL_STATUS_CHOICES],
            "semesters": [{"value": k, "label": str(_SEMESTER_LABELS[k])} for k in ("fall", "spring", "summer")],
        }
    )


@login_required
@require_GET
def appeal_stats_ai(request):
    """Filtrlənmiş apellyasiyalar üzrə AI xülasə (data-hash keş + rate limit)."""
    organization = _stats_org(request)
    qs = _filtered_appeals(request, organization)
    charts = _chart_payload(qs)
    stats = {"summary": _summary(qs), **charts}
    result = generate_appeal_statistics_summary(
        stats=stats,
        language_code=get_language(),
        user_id=request.user.id,
    )
    return JsonResponse(result)


__all__ = [
    "appeal_stats_data",
    "appeal_stats_charts",
    "appeal_stats_filters",
    "appeal_stats_ai",
]
