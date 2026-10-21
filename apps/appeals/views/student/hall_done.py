"""Zal apellyasiyasından sonra uğur ekranı → giriş səhifəsi (sahib 2026-10-21).

Sahib: «Apellyasiya verəndən sonra giriş səhifəsinə geri qayıtmalı — uğurlu formada olduğunu dedikdən sonra; burda
kabinetə girir. Final və midtermə aiddir.»

Axın (PRG): zal sessiyasında (final/midterm) uğurlu göndəriş → xülasə yaddaşa alınır → zal sessiyası bağlanır
(``clear_entry_session`` + ``logout`` — 5 dəqiqəlik baxışın sonu ilə eyni, ``apps.exams.public.end_hall_session``) →
xülasə YENİ (anonim) sessiyaya yazılır → bu səhifə. Tələbə artıq çıxış edib: səhifə kabinetə heç bir keçid vermir,
«Bitir» və avtomatik yönləndirmə növün giriş səhifəsinə (``/exams/final/`` | ``/exams/midterm/``) aparır.
Xülasədə yalnız imtahan adı / növ / sual sayı var (anonim sessiyada qalır; növbəti giriş sessiyanı yeniləyir).
"""

from __future__ import annotations

from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from apps.exams.public import center_exam_kind, end_hall_session

HALL_DONE_SESSION_KEY = "appeals_hall_done"
#: Uğur ekranından giriş səhifəsinə avtomatik keçid (saniyə).
HALL_DONE_REDIRECT_SECONDS = 15


def finish_hall_appeal(request, *, exam, appeal):
    """Zal apellyasiyası qəbul edildi: sessiyanı bağla, xülasəni yeni sessiyaya yaz, uğur ekranına yönləndir."""
    from django.urls import reverse

    kind = center_exam_kind(exam)
    summary = {
        "exam_title": exam.title,
        "kind": kind,
        "item_count": appeal.items.count() if appeal is not None else 0,
    }
    summary["entry_url"] = end_hall_session(request, kind)
    request.session[HALL_DONE_SESSION_KEY] = summary
    return redirect(reverse("appeals:hall_appeal_done"))


@require_GET
def hall_appeal_done(request):
    # Pop edilmir: eyni səhifədə dil dəyişəndə (``set_language`` → ``next``) ekran itməsin; anonim sessiyadadır.
    summary = request.session.get(HALL_DONE_SESSION_KEY)
    if not isinstance(summary, dict) or not summary.get("entry_url"):
        from apps.exams.public import center_entry_url_for_exam

        return redirect(center_entry_url_for_exam(None))
    return render(
        request,
        "appeals/student/appeal_hall_done.html",
        {
            "summary": summary,
            "entry_url": summary["entry_url"],
            "is_midterm": summary.get("kind") == "midterm",
            "redirect_seconds": HALL_DONE_REDIRECT_SECONDS,
            "hall_exam_title": summary.get("exam_title", ""),
            "hall_frame_exit": False,
        },
    )


__all__ = ["HALL_DONE_SESSION_KEY", "finish_hall_appeal", "hall_appeal_done"]
