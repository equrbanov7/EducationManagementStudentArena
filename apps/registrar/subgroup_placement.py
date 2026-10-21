"""«Alt qrupa tələbə əlavə et» — yerləşdirmə SERVİSİ (sahib 2026-10-18).

Sahib: «alt qrupa tələbə əlavə et yeri olsun — tələbə seçildikdən, ya da verilən qrup seçilir, uyğun olursa
yerləşir». Bu modul «uyğun olursa» hissəsidir: hər yoxlama aydın KOD + mətnlə imtina edir
(:mod:`apps.registrar.subgroup_placement_errors`), uyğundursa tələbə RƏSMİ yol ilə yazılır.

YENİ YAZI YOLU İCAD OLUNMUR
──────────────────────────
Qeydiyyatın özü :func:`guest_roster.add_guest_student` ilə yaranır — jurnal modalındakı «Alt qrupdan tələbə
əlavə et» ilə EYNİ servis: ``source_group`` provenansı, siyahı qapısı (bağlı jurnal / keçmiş dövr), birləşmə
(``release_source`` → öz jurnalındakı qeydiyyat ``dropped`` + ``superseded_by``), audit. Tələbənin QRUPU
DƏYİŞMİR (``StudentAcademicRecord.group`` — rəsmi köçürmə xidmətinin trigger-i toxunulmur); PostgreSQL-in
``registrar_guard_active_member`` qapısı (qeydiyyat yalnız AKTİV üzvlüyü olan tələbəyə) INSERT-də öz işini görür.

YOXLAMALAR (sıra ilə; önbaxış hamısını, yazı ilk imtinanı qaytarır)
──────────────────────────────────────────────────────────────────
açar → təşkilat → aktiv tələbə → əhatə → aktiv jurnal (cari dövr) → siyahı açıqdır → öz qrupu deyil →
artıq jurnalda deyil → başqa jurnalda aktiv deyil (və ya «azad et») → fənni keçməyib (kəsilibsə — təkrar,
``kind=retake``) → tutum → kredit həddi → cədvəl toqquşması (xəbərdarlıq və ya blok — «Sistem
tənzimləmələri») → sənəd (fayl və ya sərəncam) + səbəb.

TARİXÇƏ
───────
Hər əməl append-only :class:`SubgroupPlacementEvent` sətridir (sənəd, səbəb, kredit əvvəl/sonra, toqquşma
xəbərdarlıqları, aktor) + ``core.audit``. Geri götürmə ayrıca ``undo`` sətridir — rəsmi
:func:`guest_roster.remove_guest_student` ilə (qeydiyyat ``dropped``, bal/davamiyyət qalır, birləşmə bərpa
olunur). Bildiriş — tələbəyə və jurnalın müəlliminə (commit-dən sonra).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from core import runtime_settings
from core.audit import log_action
from core.constants import AuditAction

from . import credit_load, guest_merge, guest_roster
from . import subgroup_access as access
from . import subgroup_documents as documents
from . import subgroup_notifications
from . import subgroup_placement_errors as errors
from . import subgroup_placement_query as query
from . import subject_exempt
from .models import (
    CourseOffering,
    Enrollment,
    EnrollmentKind,
    SubgroupPlacementEvent,
    SubgroupPlacementKind,
)
from .subgroup_placement_errors import SubgroupPlacementError

MIN_REASON_LENGTH = 10
MAX_REASON_LENGTH = 2000


def _clean_reason(reason) -> str:
    return " ".join(str(reason or "").split())[:MAX_REASON_LENGTH]


def _error(code, message=None) -> dict:
    return {"code": code, "message": str(message if message is not None else errors.MESSAGES.get(code, code))}


def _credit_message(projection) -> str:
    from django.utils.translation import pgettext

    return pgettext(
        "registrar.subgroup_placement",
        "Semestr kredit həddi keçilir: yerləşdirmədən sonra %(after)s kredit olacaq, hədd %(limit)s.",
    ) % {"after": projection["total_after"], "limit": projection["limit"]}


def evaluate(*, student, offering, actor, release_source=False, record=None, check_actor=True) -> dict:
    """Yazmadan BÜTÜN yoxlamalar — önbaxış və yazı eyni qaydanı işlədir.

    Qaytarır: ``ok``, ``errors`` (``[{code, message}]``, ilk imtina birinci), ``warnings``, ``credit``
    (yük + proyeksiya), ``clashes``, ``retake`` (kəsilmiş fənnin təkrarı), ``conflicts`` (azad ediləcək
    öz jurnal qeydiyyatları), ``record``.
    """
    organization = offering.organization
    found: list = []
    plan = {"ok": False, "errors": found, "warnings": [], "credit": None, "clashes": [], "retake": False}
    plan.update(conflicts=[], record=None, credits=0, release_source=bool(release_source))

    if check_actor and not access.has_placement_key(actor, organization):
        found.append(_error(errors.FORBIDDEN))
        return plan
    if record is None:
        record = credit_load.active_record(student, organization)
    if record is None or record.group_id is None:
        found.append(_error(errors.STUDENT_INACTIVE))
        return plan
    if record.organization_id != offering.organization_id:
        found.append(_error(errors.WRONG_ORGANIZATION))
        return plan
    plan["record"] = record
    if check_actor and not access.group_in_scope(actor, organization, record.group_id):
        found.append(_error(errors.OUT_OF_SCOPE))
        return plan

    period = offering.period
    if not offering.is_active or not guest_roster.period_allows_roster(period):
        found.append(_error(errors.OFFERING_INACTIVE))
    elif offering.pk in query.locked_offering_ids([offering.pk]):
        found.append(_error(errors.ROSTER_CLOSED))
    if offering.group_id is not None and offering.group_id == record.group_id:
        found.append(_error(errors.OWN_GROUP))
    if Enrollment.objects.filter(
        organization=organization, student=student, offering=offering, status=Enrollment.Status.ENROLLED
    ).exists():
        found.append(_error(errors.ALREADY_ENROLLED))

    conflicts = guest_merge.conflicting_enrollments(offering=offering, student=student)
    plan["conflicts"] = conflicts
    if conflicts and not release_source:
        found.append(_error(errors.ACTIVE_ELSEWHERE))

    outcome = query.subject_outcomes(
        student=student,
        organization=organization,
        exclude_period_id=offering.period_id,
        subject_ids=[offering.subject_id],
    ).get(offering.subject_id)
    if outcome and outcome["passed"]:
        found.append(_error(errors.ALREADY_PASSED))
    plan["retake"] = bool(outcome and outcome["failed"])
    if subject_exempt.is_exempt_from_subject(record, offering.period, offering.subject_id):
        found.append(_error(errors.SUBJECT_EXEMPT))

    capacity = runtime_settings.get_int("credits.journal_capacity")
    if capacity and query.enrolled_counts([offering.pk]).get(offering.pk, 0) >= capacity:
        found.append(_error(errors.CAPACITY_FULL))

    load = credit_load.credit_load(student, period, organization=organization, record=record)
    plan_credits = credit_load.plan_credit_map(record.curriculum_id, [offering.subject_id], period=period)
    credits = credit_load.offering_credit(offering, plan_credits)
    released = (
        sum(credit_load.offering_credit(row.offering, plan_credits) for row in conflicts) if release_source else 0
    )
    projection = credit_load.projected(load, add_credits=credits, release_credits=released)
    plan["credits"] = credits
    plan["credit"] = {"load": load, "projection": projection}
    if not projection["fits"]:
        found.append(_error(errors.CREDIT_LIMIT, _credit_message(projection)))

    own_slots = query.own_schedule(
        organization=organization,
        student=student,
        record=record,
        period=period,
        exclude_offering_ids=[row.offering_id for row in conflicts],
    )
    target_slots = query.offering_slots([offering.pk]).get(offering.pk, [])
    plan["clashes"] = query.clashes(target_slots, own_slots)
    if plan["clashes"]:
        if runtime_settings.get_bool("credits.clash_blocks"):
            found.append(_error(errors.SCHEDULE_CLASH))
        else:
            plan["warnings"].append(_error(errors.SCHEDULE_CLASH))
    plan["ok"] = not found
    return plan


def _lock_offering(offering):
    """Açılış sətrini kilidləyir — eyni jurnala paralel yerləşdirmələr tutumu/krediti birlikdə aşmasın."""
    return (
        CourseOffering.objects.select_for_update(of=("self",))
        .select_related("subject", "period", "group", "organization", "instructor")
        .get(pk=offering.pk, organization_id=offering.organization_id)
    )


def _audit(*, event, actor, request, action, verb):
    offering = event.offering
    student = event.student
    log_action(
        action=action,
        user=actor,
        organization=event.organization,
        obj=event,
        request=request,
        resource_type="registrar.subgroup_placement",
        resource_id=str(event.pk),
        resource_repr=f"{(student.get_full_name() or student.username)} → {offering.subject.code}",
        new_values={"kind": event.kind, "credits_before": event.credits_before, "credits_after": event.credits_after},
        changes={
            "verb": verb,
            "student_id": str(student.pk),
            "offering_id": str(offering.pk),
            "enrollment_id": str(event.enrollment_id),
            "source_group": getattr(event.source_group, "name", "") or "",
            "target_group": getattr(event.target_group, "name", "") or "",
            "order_number": event.order_number,
            "order_date": event.order_date.isoformat() if event.order_date else "",
            "document_id": str(event.document_id or ""),
            "credit_limit": event.credit_limit,
        },
        reason=event.reason,
    )


def place_in_subgroup(*, student, offering, document, actor, reason, request=None, release_source=False) -> dict:
    """Tələbəni *offering* jurnalına alt qrupdan yerləşdirir (hamısı bir tranzaksiyada).

    Uğursuzluqda :class:`SubgroupPlacementError` (``code`` sabit). Uğurda:
    ``{"event", "enrollment", "credit", "warnings", "retake", "released"}``.
    ``release_source=True`` — tələbə fənni öz qrupunun jurnalında artıq keçirsə, o qeydiyyat tarixçəyə keçir
    (birləşmə; kredit dəyişmir).
    """
    if actor is None or not getattr(actor, "pk", None):
        raise SubgroupPlacementError(errors.FORBIDDEN)
    if not access.has_placement_key(actor, offering.organization):
        raise SubgroupPlacementError(errors.FORBIDDEN)
    reason = _clean_reason(reason)
    if len(reason) < MIN_REASON_LENGTH:
        raise SubgroupPlacementError(errors.REASON_REQUIRED)
    doc = documents.validate(documents.coerce(document))
    stored_files: list = []
    try:
        return _place(
            student=student,
            offering=offering,
            doc=doc,
            actor=actor,
            reason=reason,
            request=request,
            release_source=release_source,
            stored_files=stored_files,
        )
    except BaseException:
        # Tranzaksiya geri qayıdıbsa, yaddaşa yazılmış fayl yetim qalmasın.
        for field_file in stored_files:
            try:
                field_file.storage.delete(field_file.name)
            except Exception:  # pragma: no cover — silmə xətası əsas imtinanı gizlətməsin
                pass
        raise


def _place(*, student, offering, doc, actor, reason, request, release_source, stored_files) -> dict:
    with transaction.atomic():
        offering = _lock_offering(offering)
        record = credit_load.active_record(student, offering.organization, lock=True)
        plan = evaluate(student=student, offering=offering, actor=actor, release_source=release_source, record=record)
        if plan["errors"]:
            first = plan["errors"][0]
            raise SubgroupPlacementError(first["code"], first["message"], details={"errors": plan["errors"]})
        record = plan["record"]
        try:
            enrollment = guest_roster.add_guest_student(
                offering=offering,
                student=student,
                by_user=actor,
                source_group=record.group,
                reason=reason,
                release_source=bool(release_source and plan["conflicts"]),
            )
        except ValidationError as exc:
            raise SubgroupPlacementError(errors.ENROLL_FAILED, "; ".join(exc.messages))
        if plan["retake"] and enrollment.kind != EnrollmentKind.RETAKE:
            enrollment.kind = EnrollmentKind.RETAKE
            enrollment.save(update_fields=["kind", "updated_at"])
        stored = documents.store(document=doc, enrollment=enrollment, actor=actor, note=doc.number or reason)
        if stored is not None:
            stored_files.append(stored.document)
        projection = plan["credit"]["projection"]
        event = SubgroupPlacementEvent.objects.create(
            organization=offering.organization,
            kind=SubgroupPlacementKind.PLACE,
            enrollment=enrollment,
            student=student,
            offering=offering,
            source_group=record.group,
            target_group=offering.group,
            document=stored,
            order_number=doc.number,
            order_date=doc.date,
            reason=reason,
            credits_before=projection["total_before"],
            credits_after=projection["total_after"],
            credit_limit=projection["limit"],
            details={
                "clashes": plan["clashes"],
                "retake": plan["retake"],
                "released_offering_ids": [str(row.offering_id) for row in plan["conflicts"]] if release_source else [],
                "credits": plan["credits"],
            },
            actor=actor,
        )
        _audit(event=event, actor=actor, request=request, action=AuditAction.CREATE, verb="place")
        transaction.on_commit(lambda: subgroup_notifications.notify(event))
    return {
        "event": event,
        "enrollment": enrollment,
        "credit": plan["credit"],
        "warnings": plan["warnings"],
        "retake": plan["retake"],
        "released": bool(release_source and plan["conflicts"]),
    }


def undo_placement(*, event_id, actor, reason, organization, request=None) -> dict:
    """Yerləşdirməni RƏSMİ yolla geri götürür (``remove_guest_student``) — tarixçə qalır, ``undo`` sətri yazılır."""
    if not access.has_placement_key(actor, organization):
        raise SubgroupPlacementError(errors.FORBIDDEN)
    reason = _clean_reason(reason)
    if len(reason) < MIN_REASON_LENGTH:
        raise SubgroupPlacementError(errors.REASON_REQUIRED)
    with transaction.atomic():
        event = (
            SubgroupPlacementEvent.objects.select_for_update(of=("self",))
            .select_related("offering__subject", "offering__period", "offering__group", "student", "enrollment")
            .filter(organization=organization, pk=event_id, kind=SubgroupPlacementKind.PLACE)
            .first()
        )
        if event is None:
            raise SubgroupPlacementError(errors.NOT_FOUND)
        record = credit_load.active_record(event.student, organization)
        scope_group = getattr(record, "group_id", None) or event.source_group_id
        if not access.group_in_scope(actor, organization, scope_group):
            raise SubgroupPlacementError(errors.NOT_FOUND)
        if SubgroupPlacementEvent.objects.filter(undoes=event).exists():
            raise SubgroupPlacementError(errors.ALREADY_UNDONE)
        if (
            SubgroupPlacementEvent.objects.filter(
                enrollment_id=event.enrollment_id, kind=SubgroupPlacementKind.PLACE, created_at__gt=event.created_at
            )
            .exclude(pk=event.pk)
            .exists()
        ):
            # Qeydiyyat sonradan YENİDƏN yerləşdirilib — köhnə sətrin geri götürülməsi yeni yerləşdirməni silməsin.
            raise SubgroupPlacementError(errors.SUPERSEDED)
        offering = _lock_offering(event.offering)
        before = credit_load.credit_load(event.student, offering.period, organization=organization, record=record)
        try:
            guest_roster.remove_guest_student(
                offering=offering, enrollment=event.enrollment, by_user=actor, reason=reason
            )
        except ValidationError as exc:
            raise SubgroupPlacementError(errors.UNDO_BLOCKED, "; ".join(exc.messages))
        after = credit_load.credit_load(event.student, offering.period, organization=organization, record=record)
        undo = SubgroupPlacementEvent.objects.create(
            organization=organization,
            kind=SubgroupPlacementKind.UNDO,
            enrollment=event.enrollment,
            student=event.student,
            offering=offering,
            source_group=event.source_group,
            target_group=event.target_group,
            undoes=event,
            reason=reason,
            credits_before=before["total"],
            credits_after=after["total"],
            credit_limit=after["limit"],
            details={"undoes": str(event.pk)},
            actor=actor,
        )
        _audit(event=undo, actor=actor, request=request, action=AuditAction.DELETE, verb="undo")
        transaction.on_commit(lambda: subgroup_notifications.notify(undo, undo=True))
    return {"event": undo, "credit": after}


#: Jurnal modalını da bloklayan yoxlamalar — qalanlarını modal öz servisi (``add_guest_student``) yoxlayır.
JOURNAL_MODAL_BLOCKING = (errors.CREDIT_LIMIT, errors.CAPACITY_FULL)


def _modal_reason(reason) -> str:
    from django.utils.translation import pgettext

    return _clean_reason(reason) or pgettext("registrar.subgroup_placement", "Jurnal modalından əlavə")


def journal_modal_check(*, student, offering, release_source=False) -> dict:
    """Jurnal modalı («Alt qrupdan tələbə əlavə et», ``journal.roster``) üçün kredit + tutum qapısı.

    Səlahiyyəti/əhatəni modal özü yoxlayır. Tranzaksiya İÇİNDƏ çağırılır: jurnal və tələbə qeydi kilidlənir ki,
    paralel əlavələr həddi birlikdə aşmasın. Bloklayan xəta varsa :class:`SubgroupPlacementError`.
    """
    offering = _lock_offering(offering)
    record = credit_load.active_record(student, offering.organization, lock=True)
    plan = evaluate(
        student=student,
        offering=offering,
        actor=None,
        release_source=release_source,
        record=record,
        check_actor=False,
    )
    for item in plan["errors"]:
        if item["code"] in JOURNAL_MODAL_BLOCKING:
            raise SubgroupPlacementError(item["code"], item["message"])
    return plan


def record_journal_placement(*, plan, enrollment, document, actor, reason, request=None):
    """Modal yolu ilə edilən yerləşdirməni də tarixçəyə yazır (``place`` sətri) — reyestr çekmecəsində görünsün."""
    if not plan or plan.get("credit") is None or plan.get("record") is None:
        return None
    offering = enrollment.offering
    record = plan["record"]
    projection = plan["credit"]["projection"]
    event = SubgroupPlacementEvent.objects.create(
        organization=offering.organization,
        kind=SubgroupPlacementKind.PLACE,
        enrollment=enrollment,
        student=enrollment.student,
        offering=offering,
        source_group=enrollment.source_group or record.group,
        target_group=offering.group,
        document=document,
        reason=_modal_reason(reason),
        credits_before=projection["total_before"],
        credits_after=projection["total_after"],
        credit_limit=projection["limit"],
        details={
            "via": "journal_modal",
            "clashes": plan["clashes"],
            "retake": plan["retake"],
            "credits": plan["credits"],
        },
        actor=actor,
    )
    _audit(event=event, actor=actor, request=request, action=AuditAction.CREATE, verb="place")
    return event


def record_journal_removal(*, enrollment, actor, reason, request=None):
    """Modaldan çıxarılan qeydiyyatın açıq ``place`` sətri varsa, ``undo`` sətri yazılır (tarixçə ardıcıl qalsın)."""
    event = (
        SubgroupPlacementEvent.objects.select_for_update(of=("self",))
        .filter(enrollment_id=enrollment.pk, kind=SubgroupPlacementKind.PLACE, undone_by__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if event is None:
        return None
    organization = event.organization
    offering = event.offering
    record = credit_load.active_record(event.student, organization)
    after = credit_load.credit_load(event.student, offering.period, organization=organization, record=record)
    undo = SubgroupPlacementEvent.objects.create(
        organization=organization,
        kind=SubgroupPlacementKind.UNDO,
        enrollment=enrollment,
        student=event.student,
        offering=offering,
        source_group=event.source_group,
        target_group=event.target_group,
        undoes=event,
        reason=_modal_reason(reason),
        credits_before=event.credits_after,
        credits_after=after["total"],
        credit_limit=after["limit"],
        details={"undoes": str(event.pk), "via": "journal_modal"},
        actor=actor,
    )
    _audit(event=undo, actor=actor, request=request, action=AuditAction.DELETE, verb="undo")
    return undo


__all__ = [
    "JOURNAL_MODAL_BLOCKING",
    "MIN_REASON_LENGTH",
    "SubgroupPlacementError",
    "evaluate",
    "journal_modal_check",
    "place_in_subgroup",
    "record_journal_placement",
    "record_journal_removal",
    "undo_placement",
]
