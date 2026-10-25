"""«İntensiv kurs» əməlləri — ``/ders-yuku/emel/`` tək endpoint-inin handler-ləri (sahib 2026-10-25).

* ``intensive_preview`` — seçilmiş tələbələrin yoxlaması (yazmadan): ``ok`` / ``conflict`` / ``blocked``;
* ``intensive_create`` — sətir + bölgü + jurnal + qeydiyyat bir addımda (``services.intensive.create_intensive``);
* ``intensive_cancel`` — dərssiz kursu ləğv.

Qapılar servisdədir (fail-closed); burada yalnız sorğu → arqument çevrilməsi.
"""

from __future__ import annotations

from django.http import JsonResponse

from .services.intensive import cancel_intensive, create_intensive, preview


def _students(request) -> list:
    values = request.POST.getlist("students")
    if len(values) == 1 and "," in values[0]:
        values = values[0].split(",")
    return [value.strip() for value in values if value and value.strip()]


def _preview(request, organization, actor):
    result = preview(
        organization=organization,
        actor=actor,
        chair_id=request.POST.get("chair") or "",
        subject_id=request.POST.get("subject") or "",
        student_ids=_students(request),
    )
    return JsonResponse({"ok": True, **result})


def _create(request, organization, actor):
    result = create_intensive(
        organization=organization,
        actor=actor,
        chair_id=request.POST.get("chair") or "",
        subject_id=request.POST.get("subject") or "",
        teacher_id=request.POST.get("teacher") or "",
        student_ids=_students(request),
        lecture_hours=request.POST.get("lecture_hours") or 0,
        seminar_hours=request.POST.get("seminar_hours") or 0,
        starts_on=request.POST.get("starts_on") or "",
        ends_on=request.POST.get("ends_on") or "",
        note=request.POST.get("note") or "",
        release_source=(request.POST.get("release_source") or "") in ("1", "on", "true"),
        request=request,
    )
    return JsonResponse({"ok": True, **result})


def _cancel(request, organization, actor):
    result = cancel_intensive(
        organization=organization,
        actor=actor,
        row_id=request.POST.get("row") or "",
        reason=request.POST.get("reason") or "",
        request=request,
    )
    return JsonResponse({"ok": True, **result})


INTENSIVE_HANDLERS = {
    "intensive_preview": _preview,
    "intensive_create": _create,
    "intensive_cancel": _cancel,
}

__all__ = ["INTENSIVE_HANDLERS"]
