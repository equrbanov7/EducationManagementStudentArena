"""«Data bərpası» rejimi — müəllimin keçmiş tarixli jurnalı səbəb ilə tam redaktəsi (sahib 2026-10-27).

Sahib: «Bütün müəllimlərə access ver … köhnə tarixdə dəyişiklik etmək olsun: əlavə etmək, hər şey etmək, gün
silmək, mövzunu edit etmək. Dəyişikliyin səbəbi soruşulsun sadəcə, heç bir təqdimat və s. olmadan … Dərsin olduğu
xananı da silə bilər — yeni sistemdə data bərpası üçün … Sistem tənzimləməsində bunu söndürüb-yandırmaq olsun.»

AÇAR: ``journal.teacher_full_edit`` (RİM «Sistem tənzimləmələri», defolt SÖNÜLÜ) — oxu nöqtəsi
:func:`apps.registrar.journal_policy.teacher_full_edit_enabled`. Söndürülüdə bu modul heç nəyi dəyişmir.

KİMƏ (:func:`active_for`): yalnız jurnala YAZMA hüququ olan aktor (``journal_access.is_direct_editor`` — açılışın
müəllimi, sahib, bölünmüş jurnalın pay sahibi; RİM rəhbəri/superadmin də). Bölünmüş jurnalın əhatəsi
(``journal_share_guard``), tenant/RLS və ləğv olunmuş açılış qapısı əvvəlki kimi işləyir — başqa müəllimin jurnalı
açılmır.

NƏ AÇILIR (yalnız səbəb ilə — ``full_edit_reason``, ən azı :data:`REASON_MIN_LENGTH` simvol):

* istənilən keçmiş tarixə (semestr / intensiv kurs aralığında, gələcək yox — :func:`date_error`) dərs əlavə etmək
  (yazma pəncərəsi, «Rəsmi sənəd», kafedra təsdiqi yoxdur);
* dərs sətrini (tarix, növ, mövzu, saat, otaq, müəllim) redaktə etmək və dərsi XANALARI İLƏ silmək — redaktə
  pəncərəsi bitsə də;
* q/b, i/e, balı dəyişmək və xananı TƏMİZLƏMƏK (``att__…=clear``) — 15 dəqiqəlik kilid, köçürülmüş xana və yazma
  müddəti keçilir (DB trigger-i ``journal_unlock`` ilə — rəsmi yol);
* hamısı bağlanmış («Jurnal bağlama» / yekunlaşdırılmış) jurnalda da.

QORUNUR: RİM-in sənədli düzəlişi olan xana və üzrlü qayıb (yalnız rəsmi axın), imtahandan gələn ballar (Midterm /
yekun / aralıq qiymətləndirmə — öz axınları; bu modul yalnız dərs sətrinə və ``LessonMark``-a toxunur), fənnin
saat həddi, dublikat saat, sillabus qapısı. Adi pəncərə daxilindəki yazı səbəbsiz, əvvəlki kimi gedir — səbəb
YALNIZ qapını keçən əməl üçün soruşulur və :func:`log` ilə ``AuditLog``-a (``registrar.grade.full-edit``, köhnə →
yeni dəyər + səbəb, fail-closed) yazılır; RİM onu jurnalın «Tarixçə» panelində və audit jurnalında görür.
"""

from __future__ import annotations

import datetime as _dt

from django.utils import timezone
from django.utils.translation import pgettext

_CTX = "registrar.journal_full_edit"

#: Formada / avtomatik yadda saxlamada səbəb sahəsi.
REASON_FIELD = "full_edit_reason"
REASON_MIN_LENGTH = 3
REASON_MAX_LENGTH = 500
#: Grid xanasının «təmizlə» dəyəri (``att__<dərs>__<qeydiyyat>=clear``) — yalnız bu rejimdə qəbul olunur.
CLEAR = "clear"
#: ``AuditLog.resource_type`` = ``registrar.grade.full-edit`` (jurnal «Tarixçə»si eyni prefiksi oxuyur).
AUDIT_KIND = "full-edit"
#: Avtomatik yadda saxlamanın 409 kodu — klient səbəb dialoqunu açır (journal_full_edit.js).
REASON_REQUIRED_CODE = "reason_required"


def enabled(organization=None) -> bool:
    from .journal_policy import teacher_full_edit_enabled

    return teacher_full_edit_enabled(organization)


def active_for(user, offering) -> bool:
    """Rejim açıqdır VƏ aktor bu jurnalın birbaşa redaktorudur (müşahidəçi / korrektor yox)."""
    if not getattr(user, "is_authenticated", False) or not enabled(getattr(offering, "organization", None)):
        return False
    from .journal_access import is_direct_editor

    return is_direct_editor(user, offering)


def clean_reason(raw) -> str:
    """Səbəb mətni (boşluqlar sıxılır, ən çox 500 simvol); qısadırsa «»."""
    text = " ".join(str(raw or "").split())[:REASON_MAX_LENGTH]
    return text if len(text) >= REASON_MIN_LENGTH else ""


def posted_reason(request) -> str:
    return clean_reason(request.POST.get(REASON_FIELD))


def reason_required_message() -> str:
    return pgettext(
        _CTX, "Keçmiş tarixli və ya bağlanmış jurnaldakı dəyişiklik üçün səbəbi yazın (ən azı %(n)s simvol)."
    ) % {"n": REASON_MIN_LENGTH}


# ── Tarix sərhədi ─────────────────────────────────────────────────────────────


def _as_date(value):
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def period_bounds(offering) -> tuple:
    """``(başlanğıc, son)`` — açılışın dövrü (biri bilinmirsə ``None``)."""
    period = getattr(offering, "period", None)
    return _as_date(getattr(period, "start_date", None)), _as_date(getattr(period, "end_date", None))


def date_error(offering, parsed, *, today=None) -> str:
    """Bu rejimdə dərs tarixi: gələcək olmaz, semestrin (intensiv kursda kursun) aralığından kənar olmaz."""
    today = today or timezone.localdate()
    if parsed > today:
        return pgettext(_CTX, "Gələcək tarixə dərs əlavə etmək olmaz.")
    from .intensive import lesson_date_error as intensive_date_error

    error = intensive_date_error(offering, parsed)
    if error:
        return error
    start, end = period_bounds(offering)
    if start and parsed < start:
        return pgettext(_CTX, "Dərs tarixi semestrin başlanğıcından (%(date)s) əvvəl ola bilməz.") % {
            "date": start.strftime("%d.%m.%Y")
        }
    if end and parsed > end:
        return pgettext(_CTX, "Dərs tarixi semestrin sonundan (%(date)s) sonra ola bilməz.") % {
            "date": end.strftime("%d.%m.%Y")
        }
    return ""


def lesson_needs_bypass(offering, raw_date, *, allow_past=False) -> bool:
    """Yeni dərs adi qaydalarla açılmırsa (bağlı jurnal / yazma pəncərəsindən kənar tarix) — səbəb lazımdır."""
    from . import gradebook, journal_edit_windows

    if gradebook.journal_is_locked(offering):
        return True
    parsed = _as_date(raw_date)
    if parsed is None or allow_past:
        return False
    return bool(journal_edit_windows.lesson_date_error(parsed))


def lesson_edit_needs_bypass(offering, lesson, raw_date=None, *, allow_past=False) -> bool:
    """Mövcud dərsin redaktəsi/silinməsi adi qaydalarla olmursa (pəncərə bitib / bağlı jurnal / köhnə tarix)."""
    from . import gradebook, journal_edit_windows

    if gradebook.journal_is_locked(offering) or not gradebook.can_edit_lesson(lesson):
        return True
    parsed = _as_date(raw_date) if raw_date else None
    if parsed is None or parsed == lesson.date or allow_past:
        return False
    return bool(journal_edit_windows.lesson_date_error(parsed))


# ── Audit ─────────────────────────────────────────────────────────────────────


def log(*, offering, by_user, reason, action, changes, request=None) -> None:
    """Bir ``AuditLog`` sətri (fail-closed): ``changes`` = ``[{"student", "item", "old", "new"}]`` + səbəb."""
    if not changes:
        return
    from . import grade_audit
    from .audit_write import create_audit_row

    row = grade_audit.grade_change_row(
        offering=offering, by_user=by_user, kind=AUDIT_KIND, changes=changes, request=request
    )
    row.update(
        resource_repr=f"{offering.subject.code} — data bərpası ({len(changes)})",
        new_values={"count": len(changes), "action": action, "reason": reason},
        reason=f"Data bərpası ({action}): {reason}",
    )
    create_audit_row(fail_closed=True, **row)


def lesson_snapshot(lesson) -> dict:
    """Dərs sətrinin audit üçün mətn şəkli (köhnə → yeni müqayisəsi)."""
    times = ""
    if lesson.start_time:
        times = f"{lesson.start_time:%H:%M}" + (f"-{lesson.end_time:%H:%M}" if lesson.end_time else "")
    return {
        "tarix": str(lesson.date),
        "növ": str(lesson.get_kind_display()),
        "mövzu": lesson.topic or "",
        "saat": str(lesson.hours),
        "vaxt": times,
        "otaq": str(lesson.room) if lesson.room_id else "",
        "müəllim": (lesson.instructor.get_full_name() or lesson.instructor.username) if lesson.instructor_id else "",
    }


def lesson_item(lesson) -> str:
    return f"{lesson.date} · {lesson.get_kind_display()}"


def lesson_changes(lesson, before: dict) -> list:
    after = lesson_snapshot(lesson)
    return [
        {
            "student": "—",
            "item": f"{lesson_item(lesson)} · dərs {field}",
            "old": before[field] or "—",
            "new": value or "—",
        }
        for field, value in after.items()
        if before.get(field) != value
    ]


def log_lesson_added(*, offering, lesson, by_user, reason, request=None) -> None:
    log(
        offering=offering,
        by_user=by_user,
        reason=reason,
        action="lesson-add",
        request=request,
        changes=[
            {"student": "—", "item": lesson_item(lesson), "old": "—", "new": f"dərs açıldı — {lesson.topic or '—'}"}
        ],
    )


def delete_lesson(*, offering, lesson, by_user, reason, request=None) -> int:
    """Dərsi xanaları ilə birlikdə sil (səbəb + hər xananın köhnə dəyəri auditə). Silinən xana sayı."""
    from django.db import transaction

    from . import grade_audit, gradebook
    from .models import LessonMark

    with transaction.atomic():
        marks = list(LessonMark.objects.filter(lesson=lesson).select_related("enrollment__student"))
        changes = [{"student": "—", "item": lesson_item(lesson), "old": "dərs sütunu", "new": "silindi"}]
        changes += [
            {
                "student": grade_audit.student_label(mark.enrollment),
                "item": lesson_item(lesson),
                "old": grade_audit.mark_repr(mark.status, mark.score),
                "new": "—",
            }
            for mark in marks
        ]
        log(offering=offering, by_user=by_user, reason=reason, action="lesson-delete", changes=changes, request=request)
        gradebook.delete_lesson(lesson=lesson, by_user=by_user, full_edit=True)
    return len(marks)


# ── Jurnal səhifəsi (GET) ─────────────────────────────────────────────────────


def _unlock_grid(journal, *, journal_locked) -> None:
    """Grid-i redaktəyə aç: hər dərs sütunu redaktə/silinir, hər xana yazılır (sənədli düzəlişli / üzrlü xana
    istisna). ``full_edit_needed`` — adi qayda ilə bağlı idi (JS səbəb sahəsini məcburi edir)."""
    from django.db.models import Count

    from .models import AttendanceStatus, LessonMark

    lesson_ids = [meta["lesson"].id for meta in journal.get("lesson_meta", [])]
    counts = dict(
        LessonMark.objects.filter(lesson_id__in=lesson_ids)
        .values("lesson_id")
        .annotate(n=Count("id"))
        .values_list("lesson_id", "n")
    )
    for meta in journal.get("lesson_meta", []):
        meta["full_edit_needed"] = journal_locked or not meta["editable"]
        meta["full_edit_marks"] = counts.get(meta["lesson"].id, 0)
        meta["editable"] = meta["markable"] = True
    for row in journal.get("rows", []):
        for cell in row["cells"]:
            mark = cell["mark"]
            if cell["corrected"] or (mark is not None and mark.status == AttendanceStatus.EXCUSED):
                continue
            cell.update(locked=False, lock_reason="", writable=True)


def page_context(request, offering, context) -> dict:
    """``journal_detail`` kontekstinə: rejim açıqdırsa banner + səbəb dialoqu + açılmış grid/modal sərhədləri."""
    if context.get("correction_mode") or not active_for(request.user, offering):
        return {"full_edit_active": False}
    today = timezone.localdate()
    journal_locked = bool(context.get("journal_locked"))
    result = {
        "full_edit_active": True,
        "full_edit_reason_min": REASON_MIN_LENGTH,
        "full_edit_reason_max": REASON_MAX_LENGTH,
        "full_edit_normal_min": context.get("lesson_date_min") or today,
    }
    if (context.get("syllabus_gate") or {}).get("locked"):
        return result  # sillabus siyasəti jurnalı yalnız-oxu saxlayır (bu rejim onu dəyişmir)
    grid = context.get("active_tab") == "grid"
    if grid or not journal_locked:
        result["can_edit"] = True  # bağlı jurnalın digər tabları (Midterm, yekun…) yalnız-oxu qalır
    if grid:
        _unlock_grid(context["journal"], journal_locked=journal_locked)
    start, _end = period_bounds(offering)
    result.update(lesson_date_min=start or today - _dt.timedelta(days=365), lesson_date_max=today)
    return result


__all__ = [
    "AUDIT_KIND",
    "CLEAR",
    "REASON_FIELD",
    "REASON_MAX_LENGTH",
    "REASON_MIN_LENGTH",
    "REASON_REQUIRED_CODE",
    "active_for",
    "clean_reason",
    "date_error",
    "delete_lesson",
    "enabled",
    "lesson_changes",
    "lesson_edit_needs_bypass",
    "lesson_needs_bypass",
    "lesson_snapshot",
    "log",
    "log_lesson_added",
    "page_context",
    "period_bounds",
    "posted_reason",
    "reason_required_message",
]
