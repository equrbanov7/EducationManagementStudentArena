"""Cari yük təyinatlarının növ payı; manual/legacy/səviyyə və təhvil qərarları qorunur.

Çağıran workload fasadı exact (fənn,dövr,fiziki qrup) planını ötürür. Burada canlı
tenant, müəllim səlahiyyəti, journal/period kilidi və təhvil yoxlanır. Yalnız
``source=workload`` payları idarə olunur; tələbə siyahısı və akademik məzmun dəyişmir.
"""

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .handover import closed_offering_ids
from .integrity import eligible_instructor_user_ids
from .models import CourseOffering, JournalShare, JournalShareSource, LessonKind, TeachingHandover


@transaction.atomic
def sync_workload_journal_shares(
    *, organization_id, offering_ids, plans, by_user=None, request=None, retire_orphans=False
):
    """Plan açarları üzrə payları sinxronla; yeni müəllif/qrup/qiymət yaradılmır."""
    counts = dict.fromkeys(("created", "updated", "deactivated", "preserved", "skipped", "ambiguous"), 0)
    offerings = list(
        CourseOffering.objects.select_for_update()
        .filter(organization_id=organization_id, pk__in=offering_ids)
        .select_related("organization", "period")
    )
    if not offerings:
        return counts
    ids = [offering.pk for offering in offerings]
    closed = closed_offering_ids(ids)
    handed = set(
        TeachingHandover.objects.filter(
            organization_id=organization_id, offering_id__in=ids, reverted_at__isnull=True
        ).values_list("offering_id", flat=True)
    )
    eligible = eligible_instructor_user_ids(organization=offerings[0].organization)
    shares_by_offering = defaultdict(dict)
    for share in JournalShare.objects.select_for_update().filter(
        organization_id=organization_id, offering_id__in=ids, is_active=True
    ):
        shares_by_offering[share.offering_id][share.teacher_id] = share
    # Gələcək manual redaktor avtomatik paya tələbə seçibsə, o artıq bütün-roster payı deyil.
    limited = set(
        JournalShare.enrollments.through.objects.filter(
            journalshare__organization_id=organization_id,
            journalshare__offering_id__in=ids,
            journalshare__source=JournalShareSource.WORKLOAD,
            journalshare__is_active=True,
        ).values_list("journalshare_id", flat=True)
    )
    for offering in offerings:
        key = (offering.subject_id, offering.period_id, offering.group_id)
        plan = plans.get(key)
        # Eyni növ iki müəllimə bölünüb, amma enrollment/section xəritəsi verilməyib:
        # bütün tələbələrə avtomatik yazı girişi açmaq həmin bölgünü genişləndirərdi.
        if plan and plan.get("ambiguous"):
            counts["ambiguous"] += 1
            continue
        if (
            (not plan and not retire_orphans)
            or not offering.is_active
            or offering.period.locked_at is not None
            or offering.pk in closed
            or offering.pk in handed
            or (plan and offering.instructor_id != plan["owner_id"])
        ):
            counts["skipped"] += 1
            continue
        desired = {
            teacher: sorted(set(kinds) & set(LessonKind.values))
            for teacher, kinds in (plan or {}).get("teachers", {}).items()
            if teacher in eligible and kinds
        }
        # Tək sahibin əlavə paya ehtiyacı yoxdur. Sahib də ayrıca növ payı alır ki,
        # seminar/lab həmkarının bütün-roster sütunlarını öz payı kimi göstərməsin.
        if len(desired) < 2 or offering.instructor_id not in desired:
            desired = {}
        current = shares_by_offering[offering.pk]
        for teacher_id, share in current.items():
            if share.source != JournalShareSource.WORKLOAD:
                counts["preserved"] += 1
                continue
            kinds = desired.get(teacher_id)
            if kinds is None:
                _change(share, offering, by_user, counts, request, is_active=False)
            elif share.pk in limited:
                counts["preserved"] += 1
            elif share.kinds != kinds:
                _change(share, offering, by_user, counts, request, kinds=kinds)
        for teacher_id, kinds in desired.items():
            if teacher_id in current:
                continue
            share = JournalShare.objects.create(
                organization_id=organization_id,
                offering=offering,
                teacher_id=teacher_id,
                kinds=kinds,
                source=JournalShareSource.WORKLOAD,
                created_by=by_user,
            )
            counts["created"] += 1
            _audit(share, offering, by_user, {}, {"kinds": kinds, "is_active": True}, request)
    return counts


def _change(share, offering, by_user, counts, request, **fields):
    old = {field: getattr(share, field) for field in fields}
    for field, value in fields.items():
        setattr(share, field, value)
    share.updated_at = timezone.now()
    share.save(update_fields=[*fields, "updated_at"])
    counts["deactivated" if fields.get("is_active") is False else "updated"] += 1
    _audit(share, offering, by_user, old, fields, request)


def _audit(share, offering, by_user, old, new, request):
    log_action(
        AuditAction.UPDATE if old else AuditAction.CREATE,
        user=by_user,
        organization=offering.organization,
        obj=share,
        old_values=old,
        new_values=new,
        reason="workload.journal_share_synced",
        request=request,
        resource_type="registrar.JournalShare",
        resource_id=str(share.pk),
    )
