"""Slotu APARAN müəllim — kim seçilə bilər və seçim necə yoxlanılır (bölünmüş tədris, 2026-09-25).

Mühazirəni jurnal sahibi (``CourseOffering.instructor``), seminarı/laboratoriyanı isə çox vaxt
assistent aparır. ``ScheduleSlot.instructor`` bu faktı saxlayır; NULL = jurnal sahibi (bütün köhnə
sətirlər). Effektiv müəllim qaydası: :func:`apps.registrar.schedule.effective_instructor_id`.

KİM SEÇİLƏ BİLƏR (SERVER AVTORİTETDİR — ixtiyari müəllim YOX)
-------------------------------------------------------------
1. açılışın jurnal sahibi — seçicidə «Jurnal sahibi» (saxlananda NULL, bax ``stored_instructor_id``);
2. bu açılışın jurnalında dərs aparmış müəllimlər (``Lesson.instructor``);
3. kafedra dərs yükü BÖLGÜSÜNDƏ açılışı əhatə edən sətirlərin müəllimləri — eyni fənn + semestr +
   sətrin qrupları arasında açılışın qrupu, ləğv edilmiş tapşırıqlar xaric
   (``apps.workload.public.teachers_for_offering`` ilə EYNİ mənbə). Model ``get_model`` ilə oxunur:
   registrar → workload Python import kənarı yaranmır (modul-sərhəd qapısı; workload registrar-ı oxuyur).

Hamısı həm də AKTİV müəllim üzvlüyü (``grade.input``) tələb edir — ``Lesson.instructor``-un PostgreSQL
qoruyucusu ilə eyni qayda (0041; slot üçün 0082): «Dərsi aktivləşdir» slotun müəllimini dərsə köçürür.

Sorğu profili: seçici siyahısı 3–4 sorğu (dərs müəllimləri, bölgü, üzvlük, adlar); yoxlama eynisi.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

#: ``workload.constants.TaskStatus.CANCELLED`` / ``Activity`` dəyərləri (import YOX — bax modul şərhi).
_CANCELLED_TASK = "cancelled"
_TEACHING_ACTIVITIES = ("lecture", "seminar", "lab")


def user_pk(value):
    """Xam dəyər (JSON-dan ``"12"``, bazadan ``12``) → istifadəçi pk-sı; yararsızdırsa ``None``."""
    if value in (None, ""):
        return None
    try:
        return get_user_model()._meta.pk.to_python(str(value).strip())
    except (TypeError, ValueError, ValidationError):
        return None


def _person_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def _lesson_teacher_ids(offering) -> set:
    if offering is None or offering._state.adding:
        return set()
    rows = offering.lessons.filter(instructor__isnull=False).order_by()
    return set(rows.values_list("instructor_id", flat=True).distinct())


def _workload_teacher_ids(offering) -> set:
    if offering is None or not (offering.subject_id and offering.period_id and offering.group_id):
        return set()
    try:
        Assignment = django_apps.get_model("workload", "TeacherAssignment")
    except LookupError:  # pragma: no cover — workload modulu həmişə quraşdırılıb
        return set()
    rows = Assignment.objects.filter(
        organization_id=offering.organization_id,
        row__subject_id=offering.subject_id,
        row__period_id=offering.period_id,
        row__groups=offering.group_id,
        teacher__isnull=False,
        activity__in=_TEACHING_ACTIVITIES,
    ).exclude(row__task__status=_CANCELLED_TASK)
    return set(rows.order_by().values_list("teacher_id", flat=True).distinct())


def authorized_teacher_ids(organization, user_ids) -> set:
    """``user_ids``-dən bu təşkilatda AKTİV ``grade.input`` üzvlüyü olanlar (TƏK sorğu).

    ``integrity.is_authorized_instructor``-un toplu, namizədlərlə məhdud forması (bütün təşkilatın
    üzvlüklərini oxuyan ``eligible_instructor_user_ids`` redaktor dialoqu üçün ağırdır).
    ``organization`` — obyekt və ya id."""
    from core.permissions import has_permission

    from .integrity import INSTRUCTOR_PERMISSION

    organization_id = getattr(organization, "pk", organization)
    ids = {pk for pk in (user_pk(value) for value in user_ids) if pk is not None}
    if organization_id is None or not ids:
        return set()
    Membership = django_apps.get_model("organizations", "Membership")
    memberships = Membership.objects.filter(
        organization_id=organization_id,
        organization__is_active=True,
        user_id__in=ids,
        user__is_active=True,
        is_active=True,
        role__is_active=True,
        role__organization_id=organization_id,
    ).select_related("role")
    return {
        membership.user_id
        for membership in memberships
        if has_permission(list(membership.role.permissions or []), INSTRUCTOR_PERMISSION)
    }


def allowed_teacher_ids(offering) -> set:
    """Bu açılışın slotuna təyin oluna bilən müəllimlər (jurnal sahibi DAXİL; bax modul şərhi).

    ``offering`` yaddaşda saxlanmamış (quru yoxlama) nüsxə də ola bilər — onda jurnal dərsi yoxdur,
    bölgü isə fənn + semestr + qrup ilə tapılır."""
    if offering is None:
        return set()
    candidates = _lesson_teacher_ids(offering) | _workload_teacher_ids(offering)
    if offering.instructor_id:
        candidates.add(offering.instructor_id)
    return authorized_teacher_ids(offering.organization_id, candidates)


def choices(offering) -> list[dict]:
    """«Dərsi aparan müəllim» seçicisinin sətirləri — jurnal sahibi XARİC (o, «Jurnal sahibi» seçimidir)."""
    ids = allowed_teacher_ids(offering) - {offering.instructor_id if offering is not None else None}
    if not ids:
        return []
    users = get_user_model().objects.filter(pk__in=ids)
    rows = [{"id": str(user.pk), "name": _person_name(user)} for user in users]
    return sorted(rows, key=lambda row: row["name"].lower())


def is_allowed(offering, teacher_id) -> bool:
    """``teacher_id`` bu açılışın slotunu apara bilərmi (server yoxlaması)."""
    pk = user_pk(teacher_id)
    return pk is not None and pk in allowed_teacher_ids(offering)


def is_current_override(offering, slot_id, teacher_id) -> bool:
    """Redaktə olunan slotun DƏYİŞMƏYƏN müəllimidirmi (hələ də aktiv ``grade.input`` üzvü olmaq şərtilə).

    Generatorun dərc etdiyi axın mühazirəsi (məs. başqa qrupun jurnalına yazılmış mühazirəçi) seçici
    mənbələrində olmaya bilər — onu köçürmək / redaktə etmək bloklanmamalıdır. YENİ seçim isə yalnız
    :func:`allowed_teacher_ids`-dəndir. Sorğu: slot 1 + üzvlük 1 (yalnız siyahıda olmayan seçimdə)."""
    from core.http_ids import parse_uuid

    from .models import ScheduleSlot

    slot_pk, pk = parse_uuid(slot_id), user_pk(teacher_id)
    if offering is None or offering._state.adding or slot_pk is None or pk is None:
        return False
    current = (
        ScheduleSlot.objects.filter(pk=slot_pk, offering_id=offering.pk).values_list("instructor_id", flat=True).first()
    )
    return current == pk and pk in authorized_teacher_ids(offering.organization_id, {pk})


__all__ = [
    "allowed_teacher_ids",
    "authorized_teacher_ids",
    "choices",
    "is_allowed",
    "is_current_override",
    "user_pk",
]
