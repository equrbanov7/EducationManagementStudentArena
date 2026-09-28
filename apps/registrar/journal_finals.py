"""Jurnalın «Yekun» əməli (``action=save_finals``) — imtahan/təkrar balı + bonus/rəy.

2026-09-28: ``views.py``-dan çıxarılıb (modul 600 sətir tavanında idi).

Audit 2026-09-28 J-01: ``exam__`` açarı əvvəl ``finals.set_exam_score``-u
BİRBAŞA çağırırdı — ``ExamScoreEntry`` sübut jurnalından, sənəd tələbindən və
bitmiş dövr kilidindən (sahib 2026-09-26: «köhnə ilin balını dəyişmək yalnız RİM
rəhbəri, təqdimatla») yan keçirdi, zibil («abc») isə balı 0 edirdi. İndi imtahan
balı YALNIZ ``exam_score_entry.save_roster_scores`` → ``record_exam_score``
(``period_policy`` ilə) üzərindən yazılır: ilk daxiletmə açıqdır, yazılmış balın
dəyişdirilməsi səbəb + qeyd + sənəd tələb edir (bu forma onları daşımır → sətir
rədd olunur və İmtahan Mərkəzi səhifəsinə yönləndirilir). Rəqəm olmayan xana
buraxılır və xəta kimi göstərilir — heç vaxt 0-a çevrilmir.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from . import exam_score_entry, finals, journal_scope

_CTX = "registrar.journal_finals"

#: Mesajda göstərilən xəta sətirlərinin tavanı (uzun siyahı flash-ı partlatmasın).
_MAX_ERRORS_SHOWN = 5


def can_write_finals(user, offering) -> bool:
    """Yekun imtahan / təkrar balı — YALNIZ `final_score.entry` daşıyan aktor (İmtahan
    Mərkəzi) və ya superuser.  Müəllim jurnal redaktoru olsa da bu sahəni yazmır
    (UI-da sahə yoxdur; crafted POST ilə yazıla bilirdi — QA 2026-09-05 JOURNAL-TEACHER-08)."""
    if getattr(user, "is_superuser", False):
        return True
    scope = journal_scope.permission_scope_for(user, offering.organization, "final_score.entry")
    return scope.has_structure_access


def _student_label(enrollment) -> str:
    student = enrollment.student
    return student.get_full_name() or student.username


def _collect(post, enrollments, can_write_scores):
    """POST açarlarını növlərə ayır: imtahan sətirləri, təkrar balları, bonus/rəy."""
    exam_rows, resit_rows, extras = [], [], {}
    refused_scores = False
    for key, raw in post.items():
        if key.startswith("exam__") or key.startswith("resit__"):
            if not can_write_scores:
                refused_scores = True
                continue
            prefix, _sep, enrollment_id = key.partition("__")
            enrollment = enrollments.get(enrollment_id)
            if enrollment is None:
                continue
            if prefix == "exam":
                exam_rows.append({"enrollment_id": enrollment_id, "score": raw})
            elif raw.strip() != "":
                resit_rows.append((enrollment, raw))
        elif key.startswith("bonus__"):
            enrollment = enrollments.get(key[len("bonus__") :])
            if enrollment is not None:
                extras.setdefault(enrollment.id, {"enrollment": enrollment})["bonus"] = raw or "0"
        elif key.startswith("fcomment__"):
            enrollment = enrollments.get(key[len("fcomment__") :])
            if enrollment is not None:
                extras.setdefault(enrollment.id, {"enrollment": enrollment})["comment"] = raw
    return exam_rows, resit_rows, extras, refused_scores


@transaction.atomic  # F-07 (2026-09-14): sətir-sətir servis çağırışları BİR tranzaksiyada — yarımçıq toplu yazı olmasın
def handle_save_finals(request, offering):
    """Yekun imtahan/təkrar balı (exam__/resit__) + bonus-rəy (bonus__/fcomment__).

    Bal sahəsi `final_score.entry` tələb edir (İmtahan Mərkəzi); bonus/rəy (U15)
    isə jurnal redaktorunundur. Ona görə icazəsiz aktorda bütün əməl 404 olmur —
    yalnız bal açarları nəzərə alınmır (QA 2026-09-05 JOURNAL-TEACHER-08).
    """
    can_write_scores = can_write_finals(request.user, offering)
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — nəticə redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    enrollments = {str(e.id): e for e in offering.enrollments.select_related("student")}
    exam_rows, resit_rows, extras, refused_scores = _collect(request.POST, enrollments, can_write_scores)
    errors: list[tuple[str, str]] = []
    if exam_rows:
        # J-01: tək yazı yolu — ExamScoreEntry sübutu + bitmiş dövr qaydası + sənəd tələbi.
        result = exam_score_entry.save_roster_scores(
            offering=offering, rows=exam_rows, by_user=request.user, request=request
        )
        errors.extend(result["errors"])
    for enrollment, raw in resit_rows:
        try:
            finals.set_resit_score(enrollment=enrollment, score=raw, by_user=request.user)
        except ValidationError as exc:
            errors.append((_student_label(enrollment), " ".join(exc.messages)))
    # Bonus/cərimə + rəy (U15) — bal daxil edilməsindən SONRA yazılır ki,
    # evaluate_resit yekun vəziyyəti bonuslu total ilə görsün.
    for data in extras.values():
        try:
            finals.set_final_extras(
                enrollment=data["enrollment"],
                bonus=data.get("bonus"),
                comment=data.get("comment"),
                by_user=request.user,
            )
        except ValidationError as exc:
            errors.append((_student_label(data["enrollment"]), " ".join(exc.messages)))
    _report(request, refused_scores=refused_scores, errors=errors)
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _report(request, *, refused_scores, errors):
    if refused_scores:
        messages.warning(request, _("İmtahan/təkrar balını yalnız İmtahan Mərkəzi yaza bilər — bu sahələr yazılmadı."))
    if errors:
        shown = "; ".join(f"{name}: {message}" for name, message in errors[:_MAX_ERRORS_SHOWN])
        if len(errors) > _MAX_ERRORS_SHOWN:
            shown += " …"
        messages.error(
            request,
            pgettext(
                _CTX,
                "%(n)s xana yazılmadı: %(details)s. Yazılmış imtahan balının dəyişdirilməsi "
                "İmtahan Mərkəzinin bal daxiletmə səhifəsindən, təqdimatla aparılır.",
            )
            % {"n": len(errors), "details": shown},
        )
    elif not refused_scores:
        messages.success(request, _("Yekun nəticələr yadda saxlanıldı."))


def warn_rejected_scores(request, rejected) -> None:
    """J-03: rəqəm olmayan / sonsuz bal xanaları yazılmadı — istifadəçiyə xəbər ver."""
    if rejected:
        messages.warning(
            request,
            pgettext(_CTX, "%(n)s xana yazılmadı — bal rəqəm olmalıdır; mövcud bal dəyişdirilmədi.") % {"n": rejected},
        )
