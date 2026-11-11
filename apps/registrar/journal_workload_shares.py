"""Cari yük təyinatlarının növ payı; manual/legacy/səviyyə və təhvil qərarları qorunur.

Çağıran workload fasadı exact (fənn,dövr,fiziki qrup) planını ötürür. Burada canlı
tenant, müəllim səlahiyyəti, journal/period kilidi və təhvil yoxlanır. Yalnız
``source=workload`` payları idarə olunur; tələbə siyahısı və akademik məzmun dəyişmir.
"""

from collections import defaultdict

from django.db import models, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .handover import closed_offering_ids
from .integrity import eligible_instructor_user_ids
from .models import CourseOffering, Enrollment, JournalShare, JournalShareSource, LessonKind

#: Sahib 2026-11-09: alt qrup (Lab-1 / Lab-2, seminar alt qrupu) payının tələbə siyahısını BU sinxron yazır —
#: ``batch`` işarəsi onu əl ilə məhdudlaşdırılmış paydan ayırır (o, əvvəlki kimi qorunur).
SECTIONS_BATCH = "wl-sections"
_SECTION_FIELD = {LessonKind.LAB: "lab_group", LessonKind.SEMINAR: "seminar_group"}


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
            # 2026-11-11: açılışda təhvil olub-olmaması artıq payları DONDURMUR (əvvəl seminarçının dəyişməsi
            # jurnala heç çatmırdı). Tam təhvil sahibi yükdən fərqləndirir → aşağıdakı şərt onsuz da ötürür;
            # «Fənn təhvili»nin növ payları isə ``_handover_claims`` ilə qorunur.
            or (plan and offering.instructor_id != plan["owner_id"])
        ):
            counts["skipped"] += 1
            continue
        current = shares_by_offering[offering.pk]
        claims = _handover_claims(current.values())
        desired = {
            teacher: sorted((set(kinds) & set(LessonKind.values)) - _claimed_by_others(claims, teacher))
            for teacher, kinds in (plan or {}).get("teachers", {}).items()
            if teacher in eligible and kinds
        }
        desired = {teacher: kinds for teacher, kinds in desired.items() if kinds}
        # Tək sahibin əlavə paya ehtiyacı yoxdur. Sahib də ayrıca növ payı alır ki,
        # seminar/lab həmkarının bütün-roster sütunlarını öz payı kimi göstərməsin — «Fənn təhvili»nin
        # növ payı (başqa müəllimdə) da həmkar sayılır.
        partners = len(desired) + len({t for teachers in claims.values() for t in teachers} - set(desired))
        if partners < 2 or offering.instructor_id not in desired:
            desired = {}
        sections = {
            teacher: {kind: set(numbers) for kind, numbers in (kinds or {}).items() if numbers}
            for teacher, kinds in ((plan or {}).get("sections") or {}).items()
            if teacher in desired
        }
        for teacher_id, share in current.items():
            if share.source != JournalShareSource.WORKLOAD:
                counts["preserved"] += 1
                continue
            kinds = desired.get(teacher_id)
            if kinds is None:
                _change(share, offering, by_user, counts, request, is_active=False)
            elif share.pk in limited and share.batch != SECTIONS_BATCH and teacher_id not in sections:
                counts["preserved"] += 1
            else:
                changed = {}
                if share.kinds != kinds:
                    changed["kinds"] = kinds
                if changed:
                    _change(share, offering, by_user, counts, request, **changed)
                if _sync_sections(share, offering, sections.get(teacher_id), by_user, request):
                    counts["updated"] += int(not changed)
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
            _sync_sections(share, offering, sections.get(teacher_id), by_user, request)
    return counts


def _handover_claims(shares) -> dict:
    """«Fənn təhvili» ilə verilmiş aktiv növ payları: ``{növ: {müəllim}}`` — yük həmin növü başqasına vermir.

    Kafedranın HƏMİN növdəki açıq dəyişikliyi bu payı əvvəlcə ortaq servislə əvəzləyir
    (``apps.workload.services.offering_transfer`` → :func:`apps.registrar.journal_transfer.transfer`)."""
    from .journal_transfer import is_handover_share

    claims = defaultdict(set)
    for share in shares:
        if is_handover_share(share):
            for kind in (set(share.kinds or ()) & set(LessonKind.values)) or set(LessonKind.values):
                claims[kind].add(share.teacher_id)
    return claims


def _claimed_by_others(claims, teacher_id) -> set:
    return {kind for kind, teachers in claims.items() if teacher_id not in teachers}


def _section_enrollment_ids(offering, kinds_numbers) -> set:
    """Alt qrup paylarının tələbələri: növ üzrə ``Enrollment.lab_group`` / ``seminar_group`` nömrələri (birləşmə)."""
    condition = None
    for kind, numbers in kinds_numbers.items():
        field = _SECTION_FIELD.get(kind)
        if not field or not numbers:
            continue
        part = models.Q(**{f"{field}__in": sorted(numbers)})
        condition = part if condition is None else (condition | part)
    if condition is None:
        return set()
    return set(
        Enrollment.objects.filter(offering_id=offering.pk, status=Enrollment.Status.ENROLLED)
        .filter(condition)
        .values_list("pk", flat=True)
    )


def _sync_sections(share, offering, kinds_numbers, by_user, request) -> bool:
    """Payın tələbə siyahısını alt qrup nömrələrinə uyğunlaşdırır; bölmə yoxdursa BU sinxronun yazdığı siyahı
    boşaldılır (əl ilə məhdudlaşdırılmış paya toxunulmur). Qaytarır: dəyişiklik oldumu."""
    if kinds_numbers:
        wanted = _section_enrollment_ids(offering, kinds_numbers)
        current = set(share.enrollments.values_list("pk", flat=True))
        if wanted == current and share.batch == SECTIONS_BATCH:
            return False
        share.enrollments.set(list(wanted))
        if share.batch != SECTIONS_BATCH:
            share.batch = SECTIONS_BATCH
            share.save(update_fields=["batch", "updated_at"])
        _audit(share, offering, by_user, {"students": len(current)}, {"students": len(wanted)}, request)
        return True
    if share.batch == SECTIONS_BATCH:
        share.enrollments.clear()
        share.batch = ""
        share.save(update_fields=["batch", "updated_at"])
        _audit(share, offering, by_user, {"students": "sections"}, {"students": "all"}, request)
        return True
    return False


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
