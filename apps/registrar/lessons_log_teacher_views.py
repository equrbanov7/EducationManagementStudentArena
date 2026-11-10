"""«Keçilmiş dərslər» → «Cədvəl formasında bax»: müəllim cədvəlinin ucları (JSON + .xlsx).

ƏHATƏ — bölmə ilə EYNİ qayda (`lessons_log_request.resolve_request`):

* nəzarətçi (``journal.roster`` / ``journal.lessons_unit``) müəllimi ``ll_teacher`` ilə seçir; müəllimin baxanın
  əhatəsində heç bir dərsi yoxdursa **403** ``teacher_out_of_scope`` (boş cədvəl yox — id qəsdən yazılıb);
* adi müəllim YALNIZ öz cədvəlini alır; başqasının id-si → **403** ``teacher_filter_forbidden`` (CSV ilə eyni).

Bütün uclar OXU-ONLYdır (GET), dövr / süzgəc parametrləri bölmənin ``ll_*`` parametrləridir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar import lessons_log_teacher_table as table_service
from apps.registrar.lessons_log_request import parse_user_id, resolve_request, teacher_q
from apps.registrar.lessons_log_teacher_xlsx import XLSX_CONTENT_TYPE, build_xlsx
from core.tenancy import get_request_organization, request_has_active_organization_context


def _deny(code: str, status: int = 403) -> JsonResponse:
    return JsonResponse({"ok": False, "error": code}, status=status)


def _resolve(request):
    """``(ctx, teacher, None)`` və ya ``(None, None, rədd cavabı)``."""
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return None, None, _deny("no_active_organization")
    ctx = resolve_request(request, organization, with_options=False)
    requested = parse_user_id(ctx["teacher_raw"])
    if ctx["supervisor"]:
        if requested is None:
            return None, None, _deny("teacher_required", 400)
        if not table_service.teacher_in_scope(ctx["lessons_all"], requested):
            return None, None, _deny("teacher_out_of_scope")
        teacher_id = requested
    else:
        if ctx["teacher_raw"] and requested != request.user.pk:
            return None, None, _deny("teacher_filter_forbidden")
        teacher_id = request.user.pk
    teacher = get_user_model().objects.filter(pk=teacher_id).only("id", "username", "first_name", "last_name").first()
    if teacher is None:
        return None, None, _deny("teacher_out_of_scope")
    return ctx, teacher, None


def _table(ctx, teacher) -> dict:
    own = teacher_q(teacher.pk)
    events = table_service.load_events(ctx["scoped_window"].filter(own), matched_qs=ctx["lessons"].filter(own))
    return table_service.summarise(events)


def _teacher_name(teacher) -> str:
    return (teacher.get_full_name() or "").strip() or teacher.username


def _head(ctx, teacher) -> dict:
    window = ctx["window"]
    return {
        "teacher": {"id": str(teacher.pk), "name": _teacher_name(teacher)},
        "period": {
            "start": window["start"].isoformat(),
            "end": window["end"].isoformat(),
            "text": "%s — %s" % (window["start"].strftime("%d.%m.%Y"), window["end"].strftime("%d.%m.%Y")),
        },
    }


@never_cache
@login_required
@require_GET
def teacher_table(request):
    """Müəllimin icmal cədvəli: sətirlər (qrup/patok × fənn × növ) + cəmlər."""
    ctx, teacher, denied = _resolve(request)
    if denied is not None:
        return denied
    table = _table(ctx, teacher)
    return JsonResponse(
        {"ok": True, **_head(ctx, teacher), "rows": table_service.public_rows(table), "totals": table["totals"]}
    )


@never_cache
@login_required
@require_GET
def teacher_table_lessons(request):
    """«Ətraflı bax»: bir sətrin dərsləri (tarix, gün, saat, mövzu, otaq, iştirak)."""
    ctx, teacher, denied = _resolve(request)
    if denied is not None:
        return denied
    key = (request.GET.get("row") or "").strip()[:40]
    table = _table(ctx, teacher)
    row = next((item for item in table["rows"] if item["key"] == key), None)
    if row is None:
        return _deny("row_not_found", 404)
    public = {name: value for name, value in row.items() if name != "events"}
    return JsonResponse({"ok": True, **_head(ctx, teacher), "row": public, "lessons": table_service.event_details(row)})


@never_cache
@login_required
@require_GET
def teacher_table_xlsx(request):
    """«Excel kimi yüklə»: «İcmal» + «Dərslər» vərəqləri."""
    ctx, teacher, denied = _resolve(request)
    if denied is not None:
        return denied
    table = _table(ctx, teacher)
    payload = build_xlsx(
        teacher_name=_teacher_name(teacher),
        window=ctx["window"],
        table=table,
        details=table_service.event_details(table["rows"]),
    )
    response = HttpResponse(payload, content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = 'attachment; filename="muellim-dersleri-%s-%s.xlsx"' % (
        teacher.pk,
        timezone.localdate().isoformat(),
    )
    return response


__all__ = ["teacher_table", "teacher_table_lessons", "teacher_table_xlsx"]
