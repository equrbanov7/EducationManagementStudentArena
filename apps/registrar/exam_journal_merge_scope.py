"""Rəsmi jurnal birləşməsinin sənədli imtahan bağlantısını yenidən doğrula.

Ad bənzərliyi və ya tək M2M bağı sübut deyil. Native merge manifesti, mənbə
fənni, canlı jurnal cütü və geri qaytarılmamış tarixçə birlikdə tələb olunur.
"""

from uuid import UUID

from django.apps import apps as django_apps
from django.db.models import Q

from core.constants import AuditAction

from .models import CourseOffering


def merged_offering_ids(organization, subject_id, offerings, *, exam_id=None) -> set:
    if not exam_id:
        return set()
    Exam = django_apps.get_model("exams", "Exam")
    linked = set(
        Exam.objects.filter(pk=exam_id, organization=organization, subject_id=subject_id).values_list(
            "journal_offerings__pk", flat=True
        )
    )
    targets = {str(row.pk): row for row in offerings if row.is_active and row.pk in linked}
    if not targets:
        return set()
    AuditLog = django_apps.get_model("audit", "AuditLog")
    logs = AuditLog.objects.filter(
        organization=organization,
        action=AuditAction.UPDATE,
        content_type__app_label="registrar",
        content_type__model="courseoffering",
    )
    receipts = logs.filter(object_id__in=targets, changes__kind__in=("twin_merge_scored", "twin_merge_empty")).order_by(
        "-created_at", "-pk"
    )
    accepted = set()
    seen_pairs = set()
    for receipt in receipts:
        manifest = (receipt.changes or {}).get("manifest")
        if not isinstance(manifest, dict):
            continue
        target = targets[receipt.object_id]
        if manifest.get("target") != str(target.pk):
            continue
        try:
            source_id = UUID(str(manifest.get("source")))
        except (ValueError, TypeError, AttributeError):
            continue
        pair = (source_id, target.pk)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        links = manifest.get("exam_links")
        if not isinstance(links, list):
            continue
        if not any(isinstance(link, dict) and link.get("exam") == str(exam_id) for link in links):
            continue
        source = CourseOffering.objects.filter(
            organization=organization,
            pk=source_id,
            subject_id=subject_id,
            period_id=target.period_id,
            group_id=target.group_id,
            is_active=False,
        ).first()
        if source is None or source.pk in linked:
            continue
        # Both native merge families record subject identity in their summary.
        # Scored merges emit that summary via Merger immediately before receipt.
        summary = {
            "source_subject": str(source.subject_id),
            "target_subject": str(target.subject_id),
        }
        identity = logs.filter(object_id=str(target.pk), created_at__lte=receipt.created_at)
        if (receipt.changes or {}).get("kind") == "twin_merge_scored":
            identity = identity.filter(
                Q(new_values__source=str(source.pk), new_values__target=str(target.pk))
                | Q(
                    changes__kind="twin_merge_empty",
                    changes__manifest__source=str(source.pk),
                    changes__manifest__target=str(target.pk),
                )
            )
        else:
            identity = identity.filter(pk=receipt.pk)
        companion = identity.order_by("-created_at", "-pk").first()
        values = getattr(companion, "new_values", None)
        if (
            companion is None
            or companion.user_id != receipt.user_id
            or not isinstance(values, dict)
            or any(values.get(key) != value for key, value in summary.items())
        ):
            continue
        later = logs.filter(object_id=str(source.pk), created_at__gte=companion.created_at)
        if (
            later.filter(changes__kind="twin_merge_empty_restore").exists()
            or later.filter(new_values__is_active=True).exists()
        ):
            continue
        accepted.add(target.pk)
    return accepted
