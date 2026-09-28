"""JSON endpoint-lər — hamısı FAIL-CLOSED: ``schedule.manage`` + struktur əhatəsi.

* ``availability`` — müəllim əlçatanlığının yazılması;
* ``policy``       — pillə defoltu / qrup istisnası;
* ``precheck``     — «Məlumatı yoxla» (heç nə yazmır);
* ``run``          — işləmənin yaradılması və növbəyə qoyulması;
* ``status``       — işləmənin irəliləyişi (poll);
* ``action``       — kilid / köçürmə / sinxron işlətmə / ləğv / dərc.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.registrar.public import schedule_grid
from core.http_ids import parse_uuid

from ..constants import ACTIVE_STATUSES, RunStatus
from ..services import access, availability, draft_edit, policy, precheck, publish, runs
from ..sources import build_problem, scope_groups
from .common import api_organization, json_error, payload

_CTX = "timetable.api"

#: Bir istifadəçinin eyni anda aktiv (növbədə/işləyən) işləmə həddi.
MAX_ACTIVE_RUNS = 2

#: Audit 2026-09-28 TT-5: ağır (heavy növbə / tam nümunə qurulması) endpoint-lərin
#: istifadəçi başına tezlik həddi — ``core.rate_limit`` formatı («N/pəncərə»).
RATE_LIMITS = {
    "timetable.run_start": "6/1m",
    "timetable.precheck": "20/1m",
    "timetable.run_action": "60/1m",
}


def _rate_limited(request, scope):
    """Hədd aşılıbsa 429 JSON cavabı, yoxsa ``None`` (``core.rate_limit`` vedrəsi)."""
    from django.conf import settings

    from core.rate_limit import record_rate_limit_hit

    rate = getattr(settings, "TIMETABLE_RATE_LIMITS", {}).get(scope, RATE_LIMITS[scope])
    limited, retry_after = record_rate_limit_hit(scope, rate, getattr(request.user, "pk", None))
    if not limited:
        return None
    response = json_error(
        "rate_limited",
        pgettext(_CTX, "Çox tez-tez sorğu göndərilir — bir az sonra yenidən cəhd edin."),
        status=429,
        retry_after=retry_after,
    )
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


def _counts_toward_cap(run) -> bool:
    """Audit 2026-09-28 TT-5: növbədəki işləmə «köhnə» olsa da növbəni tutur — sayılır.

    Yalnız ürək döyüntüsü kəsilmiş İŞLƏYƏN (ölü worker) işləmə hədddən çıxır.
    """
    return run.status == RunStatus.QUEUED or not runs.is_stale(run)


def _period(organization, data):
    period = access.period_or_default(organization, data.get("period"))
    if period is None:
        raise Http404
    return period


@login_required
@require_POST
@never_cache
def availability_save(request):
    organization, denied = api_organization(request)
    if denied:
        return denied
    data = payload(request)
    period = _period(organization, data)
    teacher = access.teacher_or_404(request.user, organization, period, data.get("teacher"))
    try:
        row = availability.save(
            actor=request.user, organization=organization, period=period, teacher=teacher, data=data, request=request
        )
    except availability.AvailabilityError as exc:
        return json_error("invalid", exc.message, errors=exc.errors)
    return JsonResponse(
        {
            "ok": True,
            "message": pgettext(_CTX, "Əlçatanlıq yadda saxlanıldı."),
            "summary": availability.summary(row, len(schedule_grid.lesson_periods(organization))),
        }
    )


@login_required
@require_POST
@never_cache
def policy_save(request):
    organization, denied = api_organization(request)
    if denied:
        return denied
    data = payload(request)
    try:
        if data.get("group"):
            # Audit 2026-09-28 TT-3: pozuq UUID 500 yox, 400.
            group_pk = parse_uuid(data.get("group"))
            if group_pk is None:
                return json_error("invalid", pgettext(_CTX, "Qrup identifikatoru düzgün deyil."))
            group = access.scoped_groups(request.user, organization).filter(pk=group_pk).first()
            if group is None:
                raise Http404
            policy.save_group(actor=request.user, organization=organization, group=group, data=data, request=request)
        else:
            policy.save_level(
                actor=request.user,
                organization=organization,
                level=str(data.get("level") or ""),
                data=data,
                request=request,
            )
    except policy.PolicyDenied as exc:
        return json_error("permission_denied", exc.message, status=403)
    except policy.PolicyError as exc:
        return json_error("invalid", exc.message, errors=exc.errors)
    return JsonResponse({"ok": True, "message": pgettext(_CTX, "Növbə siyasəti yadda saxlanıldı.")})


@login_required
@require_POST
@never_cache
def precheck_view(request):
    organization, denied = api_organization(request)
    if denied:
        return denied
    limited = _rate_limited(request, "timetable.precheck")
    if limited:
        return limited
    data = payload(request)
    period = _period(organization, data)
    groups = scope_groups(request.user, organization, data.get("scope") or {})
    if not groups:
        return json_error("empty_scope", pgettext(_CTX, "Seçilmiş əhatədə sizin idarə etdiyiniz qrup yoxdur."))
    params = runs.clean_params(data.get("params") or {})
    problem = build_problem(organization=organization, period=period, groups=groups, params=params)
    report = precheck.run_precheck(problem)
    load: dict = {}
    for event in problem.instance.events:
        if event.teacher is not None:
            load[event.teacher] = load.get(event.teacher, 0) + (0.5 if event.biweekly else 1.0)
    teachers = [
        {"id": teacher_id, "name": problem.teacher_names.get(teacher_id, str(teacher_id)), "load": load.get(index, 0)}
        for index, teacher_id in enumerate(problem.teacher_ids)
    ]
    teachers.sort(key=lambda row: (-row["load"], row["name"].casefold()))
    return JsonResponse({"ok": True, "report": report, "teachers": teachers})


@login_required
@require_POST
@never_cache
def run_start(request):
    organization, denied = api_organization(request)
    if denied:
        return denied
    limited = _rate_limited(request, "timetable.run_start")
    if limited:
        return limited
    data = payload(request)
    period = _period(organization, data)
    Run = django_apps.get_model("timetable", "TimetableRun")
    active = Run.objects.filter(organization=organization, created_by=request.user, status__in=ACTIVE_STATUSES)
    if sum(1 for run in active if _counts_toward_cap(run)) >= MAX_ACTIVE_RUNS:
        return json_error(
            "busy", pgettext(_CTX, "Sizin artıq işləyən cədvəl işləmələriniz var — bitməsini gözləyin."), status=429
        )
    if not scope_groups(request.user, organization, data.get("scope") or {}):
        return json_error("empty_scope", pgettext(_CTX, "Seçilmiş əhatədə sizin idarə etdiyiniz qrup yoxdur."))
    source = None
    if data.get("source_run"):
        source = access.run_or_404(request, organization, data.get("source_run"))
    run = runs.create_run(
        actor=request.user,
        organization=organization,
        period=period,
        scope=data.get("scope") or {},
        params=data.get("params") or {},
        priorities=data.get("priorities") or {},
        seed=data.get("seed") or 1,
        source_run=source,
    )
    run = runs.start(run)
    return JsonResponse(
        {
            "ok": True,
            "run_id": str(run.pk),
            "url": reverse("timetable:run_detail", args=[run.pk]),
            **runs.status_payload(run),
        }
    )


@login_required
@require_GET
@never_cache
def run_status(request, run_id):
    organization, denied = api_organization(request)
    if denied:
        return denied
    run = access.run_or_404(request, organization, run_id)
    return JsonResponse(runs.status_payload(run))


def _action_sync(run):
    """İlişmiş (worker cavab vermir) işləməni brauzerdə qısa limitlə işlət."""
    Run = type(run)
    if run.status == RunStatus.RUNNING and runs.is_stale(run):
        Run.objects.filter(pk=run.pk, status=RunStatus.RUNNING).update(status=RunStatus.QUEUED)
        run.refresh_from_db()
    if run.status != RunStatus.QUEUED:
        return json_error("invalid", pgettext(_CTX, "Bu işləmə növbədə deyil."), status=409)
    run = runs.start(run, force_sync=True)
    return JsonResponse(runs.status_payload(run))


@login_required
@require_POST
@never_cache
def run_action(request, run_id):
    organization, denied = api_organization(request)
    if denied:
        return denied
    limited = _rate_limited(request, "timetable.run_action")
    if limited:
        return limited
    run = access.run_or_404(request, organization, run_id)
    if not access.run_mutable(request.user, organization, run):
        # Audit 2026-09-28 TT-2: ortaq qrup başqasının işləməsini dəyişmək hüququ vermir.
        return json_error(
            "permission_denied",
            pgettext(_CTX, "Bu işləməni yalnız onu yaradan və ya universitet səviyyəli idarəçi dəyişə bilər."),
            status=403,
        )
    data = payload(request)
    action = str(data.get("action") or "")
    if action == "sync":
        return _action_sync(run)
    if action == "discard":
        runs.discard(run, actor=request.user, request=request)
        return JsonResponse({"ok": True, "message": pgettext(_CTX, "İşləmə ləğv edildi.")})
    if action == "publish":
        try:
            result = publish.publish(
                run, actor=request.user, request=request, reason=str(data.get("reason") or "")[:500]
            )
        except publish.PublishError as exc:
            return json_error(exc.code, exc.message, status=exc.status, **exc.errors)
        message = (
            pgettext(_CTX, "Cədvəl dərc edildi: %(created)s dərs yazıldı, %(removed)s köhnə slot əvəz olundu.") % result
        )
        return JsonResponse({"ok": True, "message": message, **result})
    if run.status != RunStatus.DONE:
        return json_error("readonly", pgettext(_CTX, "Yalnız hazır qaralama redaktə edilə bilər."), status=409)
    key = str(data.get("key") or "")[:160]
    try:
        if action in ("lock", "unlock"):
            draft_edit.set_lock(run, key, action == "lock")
            return JsonResponse({"ok": True})
        if action == "move":
            moved = draft_edit.move(
                run, key, weekday=data.get("weekday"), pair=data.get("pair"), week_type=data.get("week_type")
            )
            return JsonResponse({"ok": True, "message": pgettext(_CTX, "Dərs köçürüldü."), **moved})
    except draft_edit.EditError as exc:
        return json_error(exc.code, exc.message, status=exc.status, conflicts=exc.conflicts)
    return json_error("unknown_action", pgettext(_CTX, "Naməlum əməliyyat."))


__all__ = ["availability_save", "policy_save", "precheck_view", "run_action", "run_start", "run_status"]
