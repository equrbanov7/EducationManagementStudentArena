"""Jurnal düzəlişi servisi — üzrlü qayıb / bal korreksiyası (rəsmi, sənədli).

Axın: superadmin / "journal.correct" icazəli admin müəllimi seçir → onun
jurnalına düzəliş rejimində baxır → xanaya klik → modal: sahə (davamiyyət|bal),
yeni dəyər, səbəb, qeyd və PDF sənəd (üçü də MƏCBURİ) → təsdiq. Düzəldənin adı
avtomatik profildən götürülür və dəyişdirilə bilməz.

Texniki: 2 saatlıq redaktə pəncərəsi və PG trigger-i (``trg_journal_mark_guard``)
``journal_unlock`` ilə rəsmi yoldan keçilir; ``Enrollment.absence_hours`` yenidən
hesablanır (EXCUSED limitə SAYILMIR); dəyişiklik həm :class:`JournalCorrection`
qeydinə, həm ``grade_audit``-ə, həm də ``core.audit``-ə yazılır; tələbəyə
bildiriş gedir. Bütün oxu/annotasiya köməkçiləri də buradadır.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.permissions import request_has_permission
from core.rls import journal_unlock

from . import grade_audit
from .gradebook import LESSON_SCORE_MAX, lesson_allows_score, recompute_absence_hours
from .models import (
    AttendanceStatus,
    CorrectionField,
    CorrectionReason,
    JournalCorrection,
    LessonCorrection,
    LessonKind,
    LessonMark,
)

CORRECT_PERMISSION = "journal.correct"

_ATT_LABELS = {
    AttendanceStatus.PRESENT: "iə",
    AttendanceStatus.ABSENT: "qb",
    AttendanceStatus.EXCUSED: "üq",
}


def can_correct_journal(request) -> bool:
    """Düzəliş icazəsi: superadmin/superuser və ya ``journal.correct`` icazəsi.

    Wildcard (``*``) daşıyan admin-səviyyə rollar (rektor/owner/menecer)
    avtomatik əhatə olunur; gələcəkdə istənilən rola ``journal.correct``
    əlavə etməklə genişlənir (istifadəçi tələbi: hələlik yalnız admin səviyyə)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    return request_has_permission(request, CORRECT_PERMISSION)


def _clean_int_score(raw) -> int:
    """Bal TAM ədəddir (float qadağandır) — 0..LESSON_SCORE_MAX aralığında."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValidationError(pgettext("registrar.correction", "Score must be a whole number."))
    if not 0 <= value <= int(LESSON_SCORE_MAX):
        raise ValidationError(
            pgettext("registrar.correction", "Score must be between 0 and %(max)s.") % {"max": int(LESSON_SCORE_MAX)}
        )
    return value


@transaction.atomic
def correction_author_name(by_user, request=None) -> str:
    """Düzəlişdə göstəriləcək «düzəldən» adı.

    View-as (impersonation) altında ``request.user`` HƏDƏFLƏ əvəzlənir, yəni
    ``by_user`` təqlid edilən şəxsdir. Sənəd modulunun bütün zəmanəti
    «düzəldənin adı avtomatik profildən götürülür və dəyişdirilə bilməz»
    prinsipinə söykənir — impersonasiya altında bu, əksinə işləyir və rəsmi
    düzəliş başqasının adına düşür (2026-07-31 auditi).

    Ona görə view-as aktiv olanda ƏSL aktor da ada yazılır. Model sahəsi
    dəyişmir (miqrasiya yoxdur), jurnal UI-da isə sarı xananın «kim» sahəsi
    həqiqəti göstərir.
    """
    base = (by_user.get_full_name() or by_user.username) if by_user else ""
    if request is None or not getattr(request, "is_view_as", False):
        return base
    actor = getattr(request, "real_user", None)
    if actor is None or getattr(actor, "pk", None) == getattr(by_user, "pk", None):
        return base
    actor_name = actor.get_full_name() or actor.username
    return f"{base} ({actor_name})"[:200]


def apply_correction(
    *,
    mark: LessonMark,
    field: str,
    new_status: str | None = None,
    new_score=None,
    reason: str,
    note: str,
    document,
    by_user,
    request=None,
    was_empty: bool = False,
) -> JournalCorrection:
    """Bir jurnal xanasına rəsmi düzəliş tətbiq et (hamısı bir transaksiyada).

    ``was_empty`` — xana boş idi (mark təzə yaradıldı) → köhnə dəyər "—" (yoxdur)."""
    if field not in CorrectionField.values:
        raise ValidationError(pgettext("registrar.correction", "Choose what to correct: attendance or score."))
    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext("registrar.correction", "Choose a correction reason."))
    note = (note or "").strip()
    if not note:
        raise ValidationError(pgettext("registrar.correction", "A note explaining the correction is required."))
    if not document:
        raise ValidationError(pgettext("registrar.correction", "A justification document (PDF) is required."))

    lesson = mark.lesson
    # lesson_mark QƏSDƏN indi təyin edilmir: boş xanada mark hələ saxlanmayıb.
    # Onu validasiyadan SONRA, bu atomik blokda yaradırıq ki, düzəliş rədd olunsa
    # (məs. PDF yox/yanlış) savepoint geri alsın — audit olunmamış iz qalmasın.
    correction = JournalCorrection(
        organization=mark.organization,
        field=field,
        reason=reason,
        note=note,
        document=document,
        created_mark=was_empty,
        corrected_by=by_user,
        corrected_by_name=correction_author_name(by_user, request),
    )

    if field == CorrectionField.ATTENDANCE:
        if new_status not in AttendanceStatus.values:
            raise ValidationError(pgettext("registrar.correction", "Choose the new attendance value."))
        correction.old_status = "" if was_empty else mark.status
        correction.new_status = new_status
        mark.status = new_status
    else:  # SCORE
        if not lesson_allows_score(lesson):
            raise ValidationError(
                pgettext("registrar.correction", "Lecture cells hold no score — only attendance can be corrected.")
            )
        score = _clean_int_score(new_score)
        correction.old_score = None if was_empty else (int(mark.score) if mark.score is not None else None)
        correction.new_score = score
        mark.score = score

    # PDF/ölçü validatorları burada işləyir (lesson_mark hələ boş ola bilər → istisna).
    correction.full_clean(exclude=["lesson_mark"])

    # 2 saatlıq pəncərə + PG trigger rəsmi düzəliş yolunda keçilir. Boş xanada
    # LessonMark məhz burada — validasiyadan sonra — INSERT olunur.
    with journal_unlock():
        if mark.pk is None:
            mark.save()
        else:
            mark.save(update_fields=["status", "score", "updated_at"])
    correction.lesson_mark = mark
    correction.save()

    enrollment = mark.enrollment
    recompute_absence_hours(enrollment=enrollment)

    old_repr = (
        _ATT_LABELS.get(correction.old_status, correction.old_status)
        if field == CorrectionField.ATTENDANCE
        else str(correction.old_score if correction.old_score is not None else "—")
    )
    new_repr = (
        _ATT_LABELS.get(correction.new_status, correction.new_status)
        if field == CorrectionField.ATTENDANCE
        else str(correction.new_score)
    )
    grade_audit.log_grade_changes(
        offering=lesson.offering,
        by_user=by_user,
        kind="correction",
        changes=[
            {
                "student": grade_audit.student_label(enrollment),
                "item": f"{lesson.date} · {lesson.get_kind_display()}",
                "old": old_repr,
                "new": f"{new_repr} ({correction.get_reason_display()})",
            }
        ],
    )
    try:
        log_action(
            action=AuditAction.UPDATE,
            user=by_user,
            organization=mark.organization,
            obj=correction,
            reason=f"journal correction: {reason}",
            request=request,
            changes=[{"field": field, "old": old_repr, "new": new_repr}],
        )
    except Exception:  # audit heç vaxt axını sındırmır
        pass

    from apps.registrar import journal_notifications as jn

    transaction.on_commit(
        lambda: jn.send_journal_events(
            offering=lesson.offering,
            events=[{"enrollment": enrollment, "kind": jn.EVENT_CORRECTED}],
        )
    )
    return correction


def _lesson_time_str(lesson) -> str:
    """Dərsin saat aralığını "HH:MM–HH:MM" mətni kimi (snapshot üçün)."""
    if lesson.start_time and lesson.end_time:
        return f"{lesson.start_time.strftime('%H:%M')}–{lesson.end_time.strftime('%H:%M')}"
    return ""


@transaction.atomic
def apply_lesson_correction(
    *,
    lesson,
    new_date=None,
    new_kind=None,
    new_hours=None,
    new_start_time=None,
    new_end_time=None,
    new_topic=None,
    new_instructor=None,
    reason: str,
    note: str,
    document,
    by_user,
    request=None,
) -> LessonCorrection:
    """Dərs sətrinə (tarix / tip / saat / mövzu / müəllim) rəsmi, sənədli düzəliş.

    Bal düzəlişi ilə eyni müqavilə: səbəb + qeyd + PDF MƏCBURİ; 2 saatlıq
    pəncərə + keçmiş-tarix qadağası keçilir; dəyişiklik audit olunur. Ən azı bir
    sahə dəyişməlidir (əks halda ``ValidationError``)."""
    from .gradebook import update_lesson

    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext("registrar.correction", "Choose a correction reason."))
    note = (note or "").strip()
    if not note:
        raise ValidationError(pgettext("registrar.correction", "A note explaining the correction is required."))
    if not document:
        raise ValidationError(pgettext("registrar.correction", "A justification document (PDF) is required."))

    def _iname(user):
        return (user.get_full_name() or user.username) if user else "—"

    old = {
        "date": lesson.date,
        "kind": lesson.kind,
        "hours": lesson.hours,
        "time": _lesson_time_str(lesson),
        "topic": lesson.topic or "",
        "instr": lesson.instructor_id,
    }
    old_instructor = lesson.instructor
    kind = new_kind if (new_kind in dict(LessonKind.choices)) else None
    ok = update_lesson(
        lesson=lesson,
        date=new_date or None,
        kind=kind,
        topic=new_topic,
        hours=new_hours,
        start_time=new_start_time,
        end_time=new_end_time,
        instructor=new_instructor,
        allow_past=True,
        allow_locked=True,
    )
    if not ok:
        raise ValidationError(
            pgettext("registrar.correction", "The journal is published — the lesson can't be changed.")
        )
    lesson.refresh_from_db()

    new = {
        "date": lesson.date,
        "kind": lesson.kind,
        "hours": lesson.hours,
        "time": _lesson_time_str(lesson),
        "topic": lesson.topic or "",
        "instr": lesson.instructor_id,
    }
    if all(old[k] == new[k] for k in old):
        raise ValidationError(pgettext("registrar.correction", "Nothing changed — adjust a field before saving."))

    correction = LessonCorrection(
        organization=lesson.organization,
        lesson=lesson,
        old_date=old["date"],
        new_date=new["date"],
        old_kind=old["kind"],
        new_kind=new["kind"],
        old_hours=old["hours"],
        new_hours=new["hours"],
        old_time=old["time"],
        new_time=new["time"],
        old_topic=old["topic"],
        new_topic=new["topic"],
        old_instructor=old_instructor,
        new_instructor=lesson.instructor,
        reason=reason,
        note=note,
        document=document,
        corrected_by=by_user,
        corrected_by_name=correction_author_name(by_user, request),
    )
    correction.full_clean()  # PDF validatorları
    correction.save()

    # DİQQƏT: LessonKind label-ları lazy translation proxy-dir → JSONField-ə
    # birbaşa yazılsa DB xətası verib TRANZAKSİYANI zəhərləyir. Hər dəyər str().
    changes = []
    _k = {k: str(v) for k, v in dict(LessonKind.choices).items()}
    if old["date"] != new["date"]:
        changes.append(
            {"item": str(pgettext("registrar.correction", "Date")), "old": str(old["date"]), "new": str(new["date"])}
        )
    if old["kind"] != new["kind"]:
        changes.append(
            {
                "item": str(pgettext("registrar.correction", "Type")),
                "old": _k.get(old["kind"], old["kind"]),
                "new": _k.get(new["kind"], new["kind"]),
            }
        )
    if old["hours"] != new["hours"]:
        changes.append(
            {"item": str(pgettext("registrar.correction", "Hours")), "old": str(old["hours"]), "new": str(new["hours"])}
        )
    if old["time"] != new["time"]:
        changes.append(
            {
                "item": str(pgettext("registrar.correction", "Time")),
                "old": old["time"] or "—",
                "new": new["time"] or "—",
            }
        )
    if old["topic"] != new["topic"]:
        changes.append(
            {
                "item": str(pgettext("registrar.correction", "Topic")),
                "old": old["topic"] or "—",
                "new": new["topic"] or "—",
            }
        )
    if old["instr"] != new["instr"]:
        changes.append(
            {
                "item": str(pgettext("registrar.correction", "Instructor")),
                "old": _iname(old_instructor),
                "new": _iname(lesson.instructor),
            }
        )
    for c in changes:
        c["student"] = f"{lesson.date} · {_k.get(lesson.kind, lesson.kind)}"
    # Audit savepoint-də: xəta olsa yalnız audit geri qayıdır, dərs düzəlişi qalır.
    try:
        with transaction.atomic():
            grade_audit.log_grade_changes(
                offering=lesson.offering, by_user=by_user, kind="lesson-correction", changes=changes
            )
            log_action(
                action=AuditAction.UPDATE,
                user=by_user,
                organization=lesson.organization,
                obj=correction,
                reason=f"lesson correction: {reason}",
                request=request,
                changes=[{"field": c["item"], "old": c["old"], "new": c["new"]} for c in changes],
            )
    except Exception:  # audit heç vaxt axını sındırmır
        pass
    return correction


@transaction.atomic
def apply_lesson_deletion(*, lesson, reason, note, document, by_user, request=None) -> LessonCorrection:
    """Kilidlənmiş dərsi SİL — bal düzəlişi ilə eyni müqavilə: səbəb + qeyd + PDF
    MƏCBURİ. Silmədən əvvəl sənədli qeyd yaradılır (SET_NULL FK → dərs silinsə də
    qeyd + PDF qalır), sonra dərs (və bütün işarələri) silinir; audit yazılır."""
    from .gradebook import delete_lesson

    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext("registrar.correction", "Choose a correction reason."))
    note = (note or "").strip()
    if not note:
        raise ValidationError(pgettext("registrar.correction", "A note explaining the correction is required."))
    if not document:
        raise ValidationError(pgettext("registrar.correction", "A justification document (PDF) is required."))

    _k = {k: str(v) for k, v in dict(LessonKind.choices).items()}
    label = f"{lesson.date} · {_k.get(lesson.kind, lesson.kind)}"
    correction = LessonCorrection(
        organization=lesson.organization,
        lesson=lesson,
        lesson_label=label,
        is_deletion=True,
        old_date=lesson.date,
        new_date=None,
        old_kind=lesson.kind,
        old_hours=lesson.hours,
        old_time=_lesson_time_str(lesson),
        old_topic=lesson.topic or "",
        old_instructor=lesson.instructor,
        reason=reason,
        note=note,
        document=document,
        corrected_by=by_user,
        corrected_by_name=correction_author_name(by_user, request),
    )
    correction.full_clean()
    correction.save()
    offering = lesson.offering
    changes = [
        {"student": label, "item": str(pgettext("registrar.correction", "Lesson deleted")), "old": label, "new": "—"}
    ]
    try:
        with transaction.atomic():
            grade_audit.log_grade_changes(offering=offering, by_user=by_user, kind="lesson-deletion", changes=changes)
            log_action(
                action=AuditAction.DELETE,
                user=by_user,
                organization=offering.organization,
                obj=correction,
                reason=f"lesson deletion: {reason}",
                request=request,
                changes=[{"field": c["item"], "old": c["old"], "new": c["new"]} for c in changes],
            )
    except Exception:  # audit heç vaxt axını sındırmır
        pass
    # Dərsi sil — SET_NULL sayəsində yuxarıdakı correction (PDF ilə) qalır.
    delete_lesson(lesson=lesson, by_user=by_user, allow_locked=True)
    return correction


@transaction.atomic
def revert_last_grade_correction(*, mark, by_user, request=None) -> bool:
    """Bir xananın SON düzəlişini geri al: dəyəri köhnəyə qaytar, qeydi sil.

    Səhvən edilmiş düzəlişi geri qaytarmaq üçün (İKT/korrektor). Zəncirdə başqa
    düzəliş qalsa xana sarı qalır; sonuncu da silinsə əsl (müəllim) dəyər qayıdır
    və sarı işarə itir. Davamiyyət saatları yenidən hesablanır; audit yazılır."""
    correction = mark.corrections.order_by("-created_at").first()
    if correction is None:
        return False
    enrollment = mark.enrollment
    lesson = mark.lesson
    if correction.field == CorrectionField.ATTENDANCE:
        prev, cur = correction.new_status, correction.old_status
        old_repr = _ATT_LABELS.get(prev, prev)
        new_repr = _ATT_LABELS.get(cur, cur) or "—"
    else:
        old_repr = str(correction.new_score)
        new_repr = str(correction.old_score if correction.old_score is not None else "—")
    if correction.created_mark and mark.corrections.count() == 1:
        # Bu düzəliş boş xanaya mark-ı özü yaradıb və zəncirdə tək odur → geri alma
        # saxta sətri tam silir ki, xana yenidən BOŞ ("—") olsun (CASCADE düzəlişi də silir).
        with journal_unlock():
            mark.delete()
    else:
        if correction.field == CorrectionField.ATTENDANCE:
            mark.status = correction.old_status
        else:
            mark.score = correction.old_score
        with journal_unlock():
            mark.save(update_fields=["status", "score", "updated_at"])
        correction.delete()
    recompute_absence_hours(enrollment=enrollment)
    try:
        with transaction.atomic():
            grade_audit.log_grade_changes(
                offering=lesson.offering,
                by_user=by_user,
                kind="correction-revert",
                changes=[
                    {
                        "student": grade_audit.student_label(enrollment),
                        "item": f"{lesson.date} · {str(lesson.get_kind_display())}",
                        "old": old_repr,
                        "new": f"{new_repr} ({str(pgettext('registrar.correction', 'correction reverted'))})",
                    }
                ],
            )
    except Exception:  # audit heç vaxt axını sındırmır
        pass

    from apps.registrar import journal_notifications as jn

    transaction.on_commit(
        lambda: jn.send_journal_events(
            offering=lesson.offering, events=[{"enrollment": enrollment, "kind": jn.EVENT_CORRECTED}]
        )
    )
    return True


@transaction.atomic
def revert_last_lesson_correction(*, lesson, by_user, request=None) -> bool:
    """Dərsin SON sənədli düzəlişini geri al: tarix/tip/saat/mövzu/müəllim köhnəyə qaytar."""
    from .gradebook import update_lesson

    correction = lesson.corrections.order_by("-created_at").first()
    if correction is None:
        return False
    start = end = None
    if correction.old_time and "–" in correction.old_time:
        from apps.registrar import schedule as schedule_service

        start, end = schedule_service.parse_time_slot(correction.old_time.replace("–", "|"))
    update_lesson(
        lesson=lesson,
        date=correction.old_date,
        kind=correction.old_kind or None,
        topic=correction.old_topic,
        hours=correction.old_hours,
        start_time=start or "",
        end_time=end or "",
        instructor=correction.old_instructor,
        allow_past=True,
        allow_locked=True,
    )
    # instructor=None (köhnə per-dərs müəllim yox) update_lesson-da skip olunur → birbaşa təmizlə.
    if correction.old_instructor_id is None and lesson.instructor_id is not None:
        with journal_unlock():
            lesson.instructor = None
            lesson.save(update_fields=["instructor"])
    correction.delete()
    try:
        with transaction.atomic():
            grade_audit.log_grade_changes(
                offering=lesson.offering,
                by_user=by_user,
                kind="lesson-correction-revert",
                changes=[{"student": str(lesson.date), "item": "dərs", "old": "düzəliş", "new": "geri alındı"}],
            )
    except Exception:  # audit heç vaxt axını sındırmır
        pass
    return True


# ── Oxu köməkçiləri (grid/tələbə annotasiyası) ───────────────────────────────


def _entry(c: JournalCorrection, *, include_document: bool) -> dict:
    data = {
        "id": str(c.id),
        "date": c.created_at.strftime("%d.%m.%Y %H:%M"),
        "field": c.field,
        "field_display": c.get_field_display(),
        "old": (
            _ATT_LABELS.get(c.old_status, c.old_status)
            if c.field == CorrectionField.ATTENDANCE
            else (c.old_score if c.old_score is not None else "—")
        ),
        "new": (_ATT_LABELS.get(c.new_status, c.new_status) if c.field == CorrectionField.ATTENDANCE else c.new_score),
        "reason": c.get_reason_display(),
        "note": c.note,
        "by": c.corrected_by_name,
    }
    if include_document and c.document:
        data["document_url"] = c.document.url
    return data


def corrections_map_for_offering(offering, *, include_document: bool = False) -> dict[str, list[dict]]:
    """Grid annotasiyası: {mark_id: [düzəliş qeydləri]} (sarı xana + tarixçə)."""
    result: dict[str, list[dict]] = {}
    qs = JournalCorrection.objects.filter(lesson_mark__lesson__offering=offering).order_by("created_at")
    for c in qs:
        result.setdefault(str(c.lesson_mark_id), []).append(_entry(c, include_document=include_document))
    return result


def corrections_map_for_enrollment(enrollment) -> dict[str, list[dict]]:
    """Tələbə görünüşü üçün: öz xanalarının düzəliş tarixçəsi (sənədsiz)."""
    result: dict[str, list[dict]] = {}
    qs = JournalCorrection.objects.filter(lesson_mark__enrollment=enrollment).order_by("created_at")
    for c in qs:
        result.setdefault(str(c.lesson_mark_id), []).append(_entry(c, include_document=False))
    return result
