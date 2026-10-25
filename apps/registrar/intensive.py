"""İntensiv kurs — qrupsuz qısa açılış, adla seçilmiş 1–2 tələbə (sahib 2026-10-25).

Sahib: «İntensiv … dərs saatı az olur, 1-2 nəfər üçün açılır, müəllim təyin olunur, tez bitir … müəllim 10
saatlıq dərsi 5 günə də keçə bilər — orada sərbəstlikdir». Rəsmi ad tək: «İntensiv».

YENİ YAZI YOLU İCAD OLUNMUR
──────────────────────────
* Açılış — adi :class:`CourseOffering` (``course_format="intensive"``, ``group=None``, öz tarix aralığı,
  ``lesson_hours`` = kursun saatı). Bax :mod:`apps.registrar.models.offering_format`.
* Tələbə — «alt qrupdan əlavə» RƏSMİ servisi :func:`guest_roster.add_guest_student`: ``source_group`` =
  tələbənin öz qrupu (jurnalda qrup çipi), siyahı qapısı (yalnız cari aktiv semestr), audit.

İKİQAT QİYMƏT OLMASIN (toqquşma qaydası)
────────────────────────────────────────
Tələbə HƏMİN fənn + HƏMİN semestr üzrə başqa jurnalda aktivdirsə (adətən öz qrupunun jurnalı):

* ``release_source=False`` → tələbə YAZILMIR (ön baxışda «Adi jurnalda aktivdir» görünür);
* ``release_source=True`` → «alt qrup birləşməsi» (:mod:`guest_merge`): köhnə qeydiyyat ``dropped`` +
  ``superseded_by`` → intensiv qeydiyyat; qayıb saatı köçür, bal mənbədə QALIR (göstərilir), transkriptdə
  fənn BİR dəfə sayılır. Mənbədə yekun qiymət varsa və ya mənbə jurnal bağlıdırsa birləşmə qadağandır.

Keçmiş semestrdə kəsilmiş fənn → qeydiyyat ``kind=retake`` (yenidən tədris). Fənni artıq KEÇİB və ya fəndən
AZAD edilibsə tələbə yazılmır.

JURNAL QAYDALARI (:func:`lesson_date_error`, ``gradebook_lessons.create_lesson``)
────────────────────────────────────────────────────────────────────────────────
Cədvəl slotu yoxdur → «cədvəldən kənar səbəb» soruşulmur; bir gündə bir neçə dərs (fərqli saatlarda) olar;
dərs tarixi kursun ``starts_on``–``ends_on`` aralığında olmalıdır; saat cəmi ``lesson_hours``-u keçə bilməz
(mövcud #6 həddi) və çatanda jurnal başlığında «Kurs tamamlandı» görünür. Qiymətləndirmə adi fənnin qaydasıdır.
"""

from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import guest_merge, guest_roster
from . import subgroup_placement_query as placement_query
from . import subject_exempt
from .models import (
    AcademicStatus,
    CourseFormat,
    CourseOffering,
    Enrollment,
    EnrollmentKind,
    Lesson,
    StudentAcademicRecord,
)

_CTX = "registrar.intensive"

MIN_HOURS = 1
MAX_HOURS = 120
MAX_STUDENTS = 30
MIN_NOTE_LENGTH = 3
#: ``accounts.UserProfile.AccessState.ARCHIVED`` (məzun/xaric; qeyd hələ «oxuyur» qala bilər) — modul sərhədi: dəyər.
ARCHIVED_ACCESS = "archived"

#: Tələbə yoxlamasının nəticə kodları (UI ön baxışı eyni kodları göstərir).
OK = "ok"
CONFLICT = "conflict"  # başqa jurnalda aktivdir — «adi jurnaldan köçür» lazımdır
BLOCKED = "blocked"  # yazıla bilməz (keçib / azad / qeyd yoxdur / birləşmə qadağan)


class IntensiveError(Exception):
    """İstifadəçiyə göstərilə bilən imtina (``code`` sabit, ``text`` — mətn)."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.text = str(message)


def period_window(period) -> tuple:
    """Kursun tarixləri bu aralıqda olmalıdır: semestrin başlanğıcı → (sessiya sonu və ya semestrin sonu)."""
    end = max(d for d in (_coerce(period.end_date), _coerce(getattr(period, "exam_session_end", None))) if d)
    return _coerce(period.start_date), end


def _coerce(value):
    if isinstance(value, date) or value is None:
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def validate_course(*, period, hours, starts_on, ends_on, note) -> tuple:
    """``(starts_on, ends_on, hours, note)`` — təmizlənmiş; səhv olsa :class:`IntensiveError`."""
    if period is None or not guest_roster.period_allows_roster(period):
        raise IntensiveError("period_closed", pgettext(_CTX, "İntensiv kurs yalnız cari aktiv semestrdə açılır."))
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        hours = 0
    if not MIN_HOURS <= hours <= MAX_HOURS:
        raise IntensiveError(
            "hours",
            pgettext(_CTX, "Kursun saatı %(lo)s–%(hi)s arasında olmalıdır.") % {"lo": MIN_HOURS, "hi": MAX_HOURS},
        )
    starts_on, ends_on = _coerce(starts_on), _coerce(ends_on)
    if starts_on is None or ends_on is None:
        raise IntensiveError("dates", pgettext(_CTX, "Başlama və bitmə tarixi seçilməlidir."))
    if starts_on > ends_on:
        raise IntensiveError("dates", pgettext(_CTX, "Bitmə tarixi başlama tarixindən əvvəl ola bilməz."))
    low, high = period_window(period)
    if starts_on < low or ends_on > high:
        raise IntensiveError(
            "dates",
            pgettext(_CTX, "Tarixlər semestrin daxilində olmalıdır (%(lo)s – %(hi)s).")
            % {"lo": f"{low:%d.%m.%Y}", "hi": f"{high:%d.%m.%Y}"},
        )
    note = " ".join(str(note or "").split())[:255]
    if len(note) < MIN_NOTE_LENGTH:
        raise IntensiveError("note", pgettext(_CTX, "Kursun açılma səbəbini yazın (məs. yenidən tədris)."))
    return starts_on, ends_on, hours, note


def active_record(organization, student):
    """Tələbənin oxuyan (qrupu olan) ən son akademik qeydi; yoxdursa ``None``."""
    return (
        StudentAcademicRecord.objects.filter(
            organization=organization,
            student=student,
            is_active=True,
            status=AcademicStatus.ENROLLED,
            group__isnull=False,
        )
        .exclude(student__profile__access_state=ARCHIVED_ACCESS)  # məzun/xaric hesab — yazılmır
        .select_related("group", "student")
        .order_by("-created_at")
        .first()
    )


def _name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def check_student(*, organization, period, subject_id, student, offering=None) -> dict:
    """Bir tələbənin intensiv kursa yazıla bilməsi — ``{"status", "message", "retake", "conflict", …}``."""
    record = active_record(organization, student)
    result = {
        "student_id": str(student.pk),
        "name": _name(student),
        "group": getattr(getattr(record, "group", None), "name", "") or "",
        "status": OK,
        "message": "",
        "retake": False,
        "conflict": None,
        "record": record,
    }

    def block(message):
        result.update(status=BLOCKED, message=str(message))
        return result

    if record is None:
        return block(pgettext(_CTX, "Tələbənin aktiv akademik qeydi (qrupu) yoxdur."))
    outcome = placement_query.subject_outcomes(
        student=student, organization=organization, exclude_period_id=period.pk, subject_ids=[subject_id]
    ).get(subject_id)
    if outcome and outcome.get("passed"):
        return block(pgettext(_CTX, "Tələbə bu fənni artıq keçib."))
    result["retake"] = bool(outcome and outcome.get("failed"))
    if subject_exempt.is_exempt_from_subject(record, period, subject_id):
        return block(pgettext(_CTX, "Tələbə bu semestrdə bu fəndən azad edilib."))
    conflicts = Enrollment.objects.filter(
        organization=organization,
        student=student,
        offering__subject_id=subject_id,
        offering__period_id=period.pk,
        status=Enrollment.Status.ENROLLED,
    ).select_related("offering", "offering__group")
    if offering is not None:
        conflicts = conflicts.exclude(offering_id=offering.pk)
    conflicts = list(conflicts)
    if len(conflicts) > 1:
        return block(
            pgettext(_CTX, "Tələbənin bu fənn üzrə birdən çox aktiv jurnalı var — əvvəlcə dekanlıq həll etməlidir.")
        )
    if conflicts:
        source = conflicts[0]
        blocked = guest_merge.release_block_reason(source)
        result["conflict"] = {
            "group": getattr(source.offering.group, "name", "") or pgettext(_CTX, "İntensiv"),
            "intensive": source.offering.course_format == CourseFormat.INTENSIVE,
        }
        if source.offering.course_format == CourseFormat.INTENSIVE:
            return block(pgettext(_CTX, "Tələbə bu fənn üzrə artıq başqa intensiv kursdadır."))
        if blocked:
            return block(blocked)
        result.update(
            status=CONFLICT,
            message=pgettext(
                _CTX,
                "Bu semestrdə «%(group)s» jurnalında aktivdir — «Adi jurnaldan intensivə köçür» seçilməlidir.",
            )
            % {"group": result["conflict"]["group"]},
        )
    return result


def check_students(*, organization, period, subject_id, students) -> list:
    return [
        check_student(organization=organization, period=period, subject_id=subject_id, student=student)
        for student in students
    ]


def public_check(item: dict) -> dict:
    """JSON üçün (``record`` obyekti çıxarılır)."""
    return {key: value for key, value in item.items() if key != "record"}


def _ensure_instructor(organization, instructor):
    from .integrity import eligible_instructor_user_ids

    if instructor is None or instructor.pk not in eligible_instructor_user_ids(organization=organization):
        raise IntensiveError(
            "instructor",
            pgettext(_CTX, "Seçilmiş müəllimin bu təşkilatda bal yazmaq səlahiyyəti (müəllim rolu) yoxdur."),
        )


@transaction.atomic
def open_course(
    *,
    organization,
    subject,
    period,
    instructor,
    hours,
    starts_on,
    ends_on,
    note,
    students,
    by_user,
    release_source=False,
) -> dict:
    """Açılış + qeydiyyatlar BİR tranzaksiyada. Hər tələbə yoxlanır; biri belə yazılmasa heç nə qalmır."""
    starts_on, ends_on, hours, note = validate_course(
        period=period, hours=hours, starts_on=starts_on, ends_on=ends_on, note=note
    )
    students = list({student.pk: student for student in students}.values())
    if not students:
        raise IntensiveError("students", pgettext(_CTX, "Ən azı bir tələbə seçin."))
    if len(students) > MAX_STUDENTS:
        raise IntensiveError(
            "students", pgettext(_CTX, "İntensiv kursa ən çox %(n)s tələbə yazılır.") % {"n": MAX_STUDENTS}
        )
    if subject is None or subject.organization_id != organization.pk:
        raise IntensiveError("subject", pgettext(_CTX, "Fənn tapılmadı."))
    _ensure_instructor(organization, instructor)
    checks = check_students(organization=organization, period=period, subject_id=subject.pk, students=students)
    for item in checks:
        if item["status"] == BLOCKED or (item["status"] == CONFLICT and not release_source):
            raise IntensiveError("student", f"{item['name']}: {item['message']}")

    offering = CourseOffering.objects.create(
        organization=organization,
        subject=subject,
        period=period,
        group=None,
        instructor=instructor,
        lesson_hours=hours,
        course_format=CourseFormat.INTENSIVE,
        starts_on=starts_on,
        ends_on=ends_on,
        format_note=note,
    )
    reason = pgettext(_CTX, "İntensiv kurs: %(note)s") % {"note": note}
    enrollments, released = [], 0
    for student, item in zip(students, checks):
        try:
            enrollment = guest_roster.add_guest_student(
                offering=offering,
                student=student,
                by_user=by_user,
                source_group=item["record"].group,
                reason=reason,
                release_source=item["status"] == CONFLICT,
            )
        except ValidationError as exc:  # siyahı qapısı / birləşmə qaydası — mətn olduğu kimi
            raise IntensiveError("student", f"{item['name']}: {'; '.join(exc.messages)}") from None
        if item["retake"] and enrollment.kind != EnrollmentKind.RETAKE:
            enrollment.kind = EnrollmentKind.RETAKE
            enrollment.save(update_fields=["kind", "updated_at"])
        released += int(item["status"] == CONFLICT)
        enrollments.append(enrollment)
    log_action(
        AuditAction.CREATE,
        user=by_user,
        organization=organization,
        obj=offering,
        new_values={
            "course_format": CourseFormat.INTENSIVE,
            "subject": subject.code,
            "hours": hours,
            "starts_on": starts_on.isoformat(),
            "ends_on": ends_on.isoformat(),
            "instructor": str(instructor.pk),
            "students": [str(student.pk) for student in students],
            "released": released,
        },
        reason=note,
        resource_type="registrar.CourseOffering",
        resource_id=str(offering.pk),
        resource_repr=f"{subject.code} · {pgettext(_CTX, 'İntensiv')}",
    )
    return {"offering": offering, "enrollments": enrollments, "released": released, "checks": checks}


@transaction.atomic
def cancel_course(*, offering, by_user, reason="") -> dict:
    """Səhv açılmış kursu ləğv et — YALNIZ jurnalda dərs yoxdursa. Köçürülmüş qeydiyyatlar geri qayıdır."""
    if offering.course_format != CourseFormat.INTENSIVE:
        raise IntensiveError("not_intensive", pgettext(_CTX, "Bu açılış intensiv kurs deyil."))
    if not offering.is_active:
        return {"removed": 0}
    if Lesson.objects.filter(offering=offering).exists():
        raise IntensiveError("has_lessons", pgettext(_CTX, "Jurnalda dərs yazılıb — intensiv kursu ləğv etmək olmaz."))
    reason = " ".join(str(reason or "").split()) or pgettext(_CTX, "İntensiv kurs ləğv edildi")
    removed = 0
    for enrollment in offering.enrollments.filter(status=Enrollment.Status.ENROLLED):
        guest_roster.remove_guest_student(offering=offering, enrollment=enrollment, by_user=by_user, reason=reason)
        removed += 1
    offering.is_active = False
    offering.save(update_fields=["is_active", "updated_at"])
    log_action(
        AuditAction.DELETE,
        user=by_user,
        organization=offering.organization,
        obj=offering,
        old_values={"is_active": True},
        new_values={"is_active": False, "removed": removed},
        reason=reason,
        resource_type="registrar.CourseOffering",
        resource_id=str(offering.pk),
        resource_repr=f"{offering.subject.code} · {pgettext(_CTX, 'İntensiv')}",
    )
    return {"removed": removed}


def lesson_date_error(offering, day) -> str:
    """İntensiv kursda dərs tarixi kursun aralığından kənardırsa mətn; əks halda boş sətir."""
    if getattr(offering, "course_format", "") != CourseFormat.INTENSIVE or day is None:
        return ""
    starts_on, ends_on = offering.starts_on, offering.ends_on
    if (starts_on and day < starts_on) or (ends_on and day > ends_on):
        return pgettext(_CTX, "İntensiv kursun dərsi %(lo)s – %(hi)s aralığında olmalıdır.") % {
            "lo": f"{starts_on:%d.%m.%Y}" if starts_on else "—",
            "hi": f"{ends_on:%d.%m.%Y}" if ends_on else "—",
        }
    return ""


__all__ = [
    "BLOCKED",
    "CONFLICT",
    "OK",
    "IntensiveError",
    "cancel_course",
    "check_student",
    "check_students",
    "lesson_date_error",
    "open_course",
    "period_window",
    "public_check",
    "validate_course",
]
