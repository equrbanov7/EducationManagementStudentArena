"""Oxu tərəfi: siyahı + filtr, təsdiq növbəsi, versiya diff-i, audit xronologiyası.

Bütün sorğular AKTORUN əhatəsinə görə daraldılır (fail-closed): müəllim öz
sillabuslarını, kafedra müdiri yalnız öz kafedrasını, org-səviyyəli rol hamısını
görür. Tenant izolyasiyası əlavə olaraq RLS ilə DB səviyyəsində qorunur.
"""

from __future__ import annotations

from django.db.models import Case, IntegerField, Q, When

from ..constants import (
    PERM_REVIEW,
    PERM_VIEW,
    QUEUE_STATUSES,
    SECTION_ORDER,
    STATUS_SORT_INDEX,
    SyllabusStatus,
)
from ..models import Syllabus, SyllabusReview, SyllabusVersion

#: Siyahının icazə verilən sıralama açarları (README §3.1 — 4 variant).
SORT_KEYS = {
    "recent": ("-current_version__updated_at", "-updated_at"),
    "subject": ("subject__name",),
    "completion": ("-current_version__completion_percent",),
    "status": ("_status_rank", "subject__name"),
}


def _status_rank_annotation():
    whens = [When(current_version__status=status, then=rank) for status, rank in STATUS_SORT_INDEX.items()]
    return Case(*whens, default=len(STATUS_SORT_INDEX), output_field=IntegerField())


def _scope_filter(queryset, actor):
    """Aktorun görə bildiyi sillabuslar (fail-closed)."""
    if actor.is_superadmin:
        return queryset
    own = Q(author_id=actor.user_id) | Q(offering__instructor_id=actor.user_id)
    if not actor.has(PERM_VIEW):
        return queryset.filter(own)
    scope = actor.scope_for(PERM_VIEW)
    if scope.is_org_wide:
        return queryset
    if not scope.is_unit_scoped:
        return queryset.filter(own)
    unit_q = scope.unit_subtree_q(path_field="chair_unit__path", id_field="chair_unit__id")
    return queryset.filter(own | unit_q)


def list_syllabi(
    *,
    organization,
    actor,
    period=None,
    academic_year=None,
    chair_unit=None,
    statuses=None,
    search: str = "",
    sort: str = "recent",
):
    """Müəllim/kafedra siyahısı — filtr + sıralama tətbiq olunmuş queryset."""
    queryset = Syllabus.objects.filter(organization=organization, is_active=True).select_related(
        "subject", "period", "program", "offering", "current_version", "approved_version"
    )
    queryset = _scope_filter(queryset, actor)

    if period is not None:
        queryset = queryset.filter(period=period)
    if academic_year:
        queryset = queryset.filter(period__academic_year=academic_year)
    if chair_unit is not None:
        queryset = queryset.filter(chair_unit=chair_unit)
    if statuses:
        queryset = queryset.filter(current_version__status__in=list(statuses))
    if search:
        queryset = queryset.filter(Q(subject__name__icontains=search) | Q(subject__code__icontains=search))

    queryset = queryset.annotate(_status_rank=_status_rank_annotation())
    return queryset.order_by(*SORT_KEYS.get(sort, SORT_KEYS["recent"]))


def status_counts(queryset) -> dict:
    """KPI kartları üçün status sayğacları (+ sillabussuz fənn ayrıca hesablanır)."""
    counts = {status.value: 0 for status in SyllabusStatus}
    for row in queryset.values_list("current_version__status", flat=True):
        if row in counts:
            counts[row] += 1
    counts["total"] = sum(counts[status.value] for status in SyllabusStatus)
    return counts


def review_queue(*, organization, actor, chair_unit=None):
    """Kafedra müdirinin təsdiq növbəsi — ən çox gözləyən başda.

    İcazəsi olmayan və ya struktur əhatəsi tapılmayan aktor üçün BOŞ queryset
    qaytarılır (README §3.3 ``noscope`` vəziyyəti).
    """
    if not actor.is_superadmin and not actor.has(PERM_REVIEW):
        return SyllabusVersion.objects.none()

    queryset = (
        SyllabusVersion.objects.filter(organization=organization, status__in=sorted(QUEUE_STATUSES))
        .select_related("syllabus", "syllabus__subject", "syllabus__author", "submitted_by")
        .order_by("submitted_at")
    )
    if actor.is_superadmin:
        return queryset.filter(syllabus__chair_unit=chair_unit) if chair_unit else queryset

    scope = actor.scope_for(PERM_REVIEW)
    if scope.is_org_wide:
        pass
    elif scope.is_unit_scoped:
        queryset = queryset.filter(
            scope.unit_subtree_q(path_field="syllabus__chair_unit__path", id_field="syllabus__chair_unit__id")
        )
    else:
        return SyllabusVersion.objects.none()

    if chair_unit is not None:
        queryset = queryset.filter(syllabus__chair_unit=chair_unit)
    return queryset


def version_diff(old_version, new_version) -> dict:
    """İki versiyanın bölmə-bölmə fərqi.

    Nəticə: ``{section_id: {"changed": bool, "old": data, "new": data}}`` —
    dizayndakı yanaşı diff kartı bunun üzərində qurulur.
    """
    old_map = {row.section_id: (row.data or {}) for row in old_version.sections.all()} if old_version else {}
    new_map = {row.section_id: (row.data or {}) for row in new_version.sections.all()} if new_version else {}
    result = {}
    for section_id in SECTION_ORDER:
        old_data = old_map.get(section_id, {})
        new_data = new_map.get(section_id, {})
        result[section_id] = {
            "changed": old_data != new_data,
            "old": old_data,
            "new": new_data,
        }
    return result


def version_timeline(syllabus) -> list:
    """Dosyenin xronologiyası: versiyalar + qərar qeydləri (yeni → köhnə)."""
    events: list = []
    versions = list(syllabus.versions.select_related("approved_by", "created_by").all())
    by_id = {version.pk: version for version in versions}
    for version in versions:
        events.append(
            {
                "kind": "version",
                "at": version.created_at,
                "version": version.label,
                "status": version.status,
                "actor": version.created_by,
            }
        )
    reviews = SyllabusReview.objects.filter(version__syllabus=syllabus).select_related("actor")
    for review in reviews:
        version = by_id.get(review.version_id)
        events.append(
            {
                "kind": "review",
                "at": review.created_at,
                "version": version.label if version else "",
                "decision": review.decision,
                "reason": review.reason,
                "actor": review.actor,
            }
        )
    events.sort(key=lambda event: event["at"], reverse=True)
    return events


def audit_entries(syllabus, *, limit: int = 100):
    """Dosyeyə aid MÖVCUD audit jurnalı sətirləri (yeni jurnal icad edilmir)."""
    from django.apps import apps as django_apps
    from django.contrib.contenttypes.models import ContentType

    audit_log = django_apps.get_model("audit", "AuditLog")
    content_type = ContentType.objects.get_for_model(SyllabusVersion)
    version_ids = list(syllabus.versions.values_list("pk", flat=True))
    return (
        audit_log.objects.filter(content_type=content_type, object_id__in=[str(pk) for pk in version_ids])
        .select_related("user")
        .order_by("-created_at")[:limit]
    )


__all__ = [
    "SORT_KEYS",
    "audit_entries",
    "list_syllabi",
    "review_queue",
    "status_counts",
    "version_diff",
    "version_timeline",
]
