"""İşləmələr — yaratma, icra (Celery / sinxron fallback), qaralamanın yazılması, status.

İcra sırası: növbə (``queued``) → ``running`` (atomik CAS iddiası — worker və
brauzer fallback-i eyni anda işləməsin) → nümunənin qurulması (YALNIZ OXU) →
mühərrik → qaralama slotları + KPI → ``done`` (xətada ``failed`` + səbəb).
Bazaya yazılan yeganə şey işləmənin öz sətirləridir; canlı cədvəl dərcə qədər
toxunulmaz qalır.
"""

from __future__ import annotations

import logging
import time
from contextlib import nullcontext

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from ..constants import (
    ACTIVE_STATUSES,
    DEFAULT_PARAMS,
    SYNC_TIME_LIMIT,
    TIME_LIMIT_MAX,
    TIME_LIMIT_MIN,
    TUNABLE_WEIGHTS,
    RunStatus,
    StreamPolicy,
)
from ..engine import WEEK_CODES, WEEK_FROM_CODE, Params, Weights, solve
from ..sources import build_problem, normalize_scope, normalize_weekdays, scope_groups, scope_label

logger = logging.getLogger(__name__)

_CTX = "timetable.run"

#: İşləmə bu qədər saniyə ürək döyüntüsüz qalsa «ilişib» sayılır.
STALE_AFTER = 90


def _model(name):
    return django_apps.get_model("timetable", name)


def _int(value, default, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def clean_params(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    weights = {}
    for key in TUNABLE_WEIGHTS:
        value = (raw.get("weights") or {}).get(key) if isinstance(raw.get("weights"), dict) else None
        if value not in (None, ""):
            weights[key] = _int(value, 0, 0, 1000)
    policy = str(raw.get("stream_policy") or DEFAULT_PARAMS["stream_policy"])
    return {
        "time_limit": _int(raw.get("time_limit"), DEFAULT_PARAMS["time_limit"], TIME_LIMIT_MIN, TIME_LIMIT_MAX),
        "weekdays": normalize_weekdays(raw.get("weekdays") or DEFAULT_PARAMS["weekdays"]),
        "weeks": _int(raw.get("weeks"), DEFAULT_PARAMS["weeks"], 8, 20),
        "stream_policy": policy if policy in dict(StreamPolicy.choices) else StreamPolicy.TASK_ROWS,
        "keep_published": bool(raw.get("keep_published")),
        "include_vacant": raw.get("include_vacant", True) not in (False, "0", "false", "off", ""),
        "weights": weights,
        # İterasiya büdcəsi (0 = yalnız vaxt): eyni seed + büdcə → eyni nəticə (testlər, müqayisə).
        "max_iterations": _int(raw.get("max_iterations"), 0, 0, 5_000_000),
    }


def clean_priorities(raw) -> dict:
    """Müəllim sırası (yuxarıdakı vacib) → çəki: 5, 4, 3, sonra 2 (siyahıda olmayan = 1)."""
    raw = raw if isinstance(raw, dict) else {}
    order = []
    for value in raw.get("teachers") or []:
        try:
            teacher_id = int(value)
        except (TypeError, ValueError):
            continue
        if teacher_id not in order:
            order.append(teacher_id)
    weights = {str(teacher_id): max(2, 5 - position) for position, teacher_id in enumerate(order[:200])}
    return {"teachers": order[:200], "teacher_weights": weights}


def create_run(*, actor, organization, period, scope, params, priorities=None, seed=1, source_run=None):
    scope = normalize_scope(scope)
    run = _model("TimetableRun").objects.create(
        organization=organization,
        period=period,
        title=scope_label(organization, scope),
        scope=scope,
        status=RunStatus.QUEUED,
        seed=_int(seed, 1, 1, 999_999),
        params=clean_params(params),
        priorities=clean_priorities(priorities),
        created_by=actor if getattr(actor, "pk", None) else None,
        source_run=source_run,
        progress={"phase": "queued", "frac": 0.0},
    )
    return run


def _locked_from(run) -> dict:
    """Mənbə işləmənin KİLİDLİ slotları → ``{event_key: (t, week)}`` (yeni şəbəkədə)."""
    from apps.registrar.public import schedule_grid

    source = run.source_run
    if source is None:
        return {}
    weekdays = normalize_weekdays((run.params or {}).get("weekdays"))
    pairs = len(schedule_grid.lesson_periods(run.organization))
    out = {}
    for slot in source.slots.filter(locked=True, weekday__isnull=False).order_by("event_key"):
        if slot.weekday not in weekdays or not 1 <= int(slot.pair or 0) <= pairs:
            continue
        t = weekdays.index(slot.weekday) * pairs + int(slot.pair) - 1
        out.setdefault(slot.event_key, (t, WEEK_FROM_CODE.get(slot.week_type, 0)))
    return out


def build_for_run(run, *, locked=None):
    actor = run.created_by
    groups = scope_groups(actor, run.organization, run.scope) if actor is not None else []
    return build_problem(
        organization=run.organization,
        period=run.period,
        groups=groups,
        params=run.params or {},
        locked=locked,
        priorities=run.priorities or {},
    )


_REASONS = {
    "teacher_busy": pgettext_lazy(_CTX, "Müəllim bütün uyğun xanalarda başqa dərsdədir."),
    "teacher_external": pgettext_lazy(_CTX, "Müəllim uyğun xanalarda başqa fakültənin dərc olunmuş dərsindədir."),
    "group_busy": pgettext_lazy(_CTX, "Qrupun uyğun xanaları başqa dərslərlə doludur."),
    "group_gap": pgettext_lazy(_CTX, "Qrupun gününü boşluqsuz saxlamaq mümkün olmadı."),
    "rooms_full": pgettext_lazy(_CTX, "Korpusda eyni anda boş otaq qalmayıb."),
    "teacher_unavailable": pgettext_lazy(_CTX, "Müəllim qrupun növbəsində heç gələ bilmir."),
    "no_common_band": pgettext_lazy(_CTX, "Axının qruplarının ortaq növbəsi yoxdur."),
    "group_no_slots": pgettext_lazy(_CTX, "Qrup üçün icazəli xana yoxdur (növbə siyasəti)."),
    "empty_domain": pgettext_lazy(_CTX, "Mümkün vaxt yoxdur."),
    "other": pgettext_lazy(_CTX, "Sərt qaydaları pozmadan yer tapılmadı."),
}

_SHORT = {
    "teacher_busy": pgettext_lazy(_CTX, "müəllim məşğul"),
    "teacher_external": pgettext_lazy(_CTX, "müəllimin kənar dərsi"),
    "group_busy": pgettext_lazy(_CTX, "qrup məşğul"),
    "group_gap": pgettext_lazy(_CTX, "boşluq yaranır"),
    "rooms_full": pgettext_lazy(_CTX, "otaq yoxdur"),
    "other": pgettext_lazy(_CTX, "digər"),
}


def reason_text(code, counts) -> str:
    """Səbəb cümləsi + xana sayları: «… (müəllim məşğul 20, boşluq yaranır 16)»."""
    text = str(_REASONS.get(code, _REASONS["other"]))
    if counts:
        parts = ", ".join(f"{_SHORT.get(key, key)} {n}" for key, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        text = f"{text} ({parts})"
    return text


def _write_drafts(run, problem, result):
    Slot = _model("TimetableDraftSlot")
    run.slots.all().delete()
    reasons = {item["event"]: item for item in result.unplaced}
    rows = []
    for i, (event, meta) in enumerate(zip(problem.instance.events, problem.events)):
        value = result.values[i]
        room_index = result.rooms[i] if result.rooms else None
        room = problem.rooms[room_index] if room_index is not None else None
        weekday = pair = None
        week = "odd" if event.biweekly else "all"
        if value is not None:
            weekday, pair = problem.t_to_cell(value[0])
            week = WEEK_CODES[value[1]]
        reason = reasons.get(i)
        for offering_id in meta["offerings"]:
            rows.append(
                Slot(
                    organization_id=run.organization_id,
                    run=run,
                    event_key=meta["key"],
                    offering_id=offering_id,
                    kind=meta["kind"],
                    weekday=weekday,
                    pair=pair,
                    week_type=week,
                    is_biweekly=event.biweekly,
                    teacher_id=meta["teacher_id"],
                    room=(room or {}).get("label", "")[:64],
                    room_ref=(room or {}).get("id", "")[:64],
                    locked=bool(event.fixed),
                    reason_code=reason["code"] if reason else "",
                    reason=reason_text(reason["code"], reason.get("counts")) if reason else "",
                )
            )
    Slot.objects.bulk_create(rows, batch_size=500)
    return len(rows)


def _progress_writer(run_id, db_block):
    state = {"last": 0.0}

    def write(payload):
        now = time.monotonic()
        if now - state["last"] < 2.0 and payload.get("phase") == "search":
            return
        state["last"] = now
        data = {k: v for k, v in payload.items() if k in ("phase", "frac", "iterations", "unplaced")}
        data["heartbeat"] = timezone.now().isoformat()
        with db_block():
            _model("TimetableRun").objects.filter(pk=run_id).update(progress=data)

    return write


def execute(run_id, *, time_cap=None, db_block=nullcontext):
    """İşləməni icra et (Celery task-ı və sinxron fallback eyni yolu çağırır)."""
    Run = _model("TimetableRun")
    now = timezone.now()
    with db_block():
        claimed = Run.objects.filter(pk=run_id, status__in=(RunStatus.QUEUED, RunStatus.DRAFT)).update(
            status=RunStatus.RUNNING,
            started_at=now,
            progress={"phase": "load", "frac": 0.0, "heartbeat": now.isoformat()},
        )
        run = Run.objects.select_related("organization", "period", "created_by", "source_run").get(pk=run_id)
    if not claimed:
        return run
    try:
        with db_block():
            if run.created_by is None:
                raise ValueError(pgettext(_CTX, "İşləməni yaradan istifadəçi tapılmadı."))
            problem = build_for_run(run, locked=_locked_from(run))
        limit = int((run.params or {}).get("time_limit") or DEFAULT_PARAMS["time_limit"])
        if time_cap:
            limit = min(limit, int(time_cap))
        params = Params(
            seed=run.seed,
            time_limit=limit,
            max_iterations=int((run.params or {}).get("max_iterations") or 0),
            weights=Weights.from_dict((run.params or {}).get("weights")),
        )
        result = solve(problem.instance, params, progress=_progress_writer(run.pk, db_block))
        kpis = dict(result.kpis)
        kpis["unplaced_codes"] = {}
        for item in result.unplaced:
            kpis["unplaced_codes"][item["code"]] = kpis["unplaced_codes"].get(item["code"], 0) + 1
        kpis["time_limit"] = limit
        kpis["summary"] = {
            "groups": len(problem.groups),
            "cohorts": len(problem.instance.cohorts),
            "teachers": len(problem.instance.teachers),
            "streams": sum(1 for meta in problem.events if meta["stream"]),
        }
        with db_block(), transaction.atomic():
            written = _write_drafts(run, problem, result)
            Run.objects.filter(pk=run.pk).update(
                status=RunStatus.DONE,
                kpis=kpis,
                log=result.log + [f"drafts={written}"],
                finished_at=timezone.now(),
                progress={"phase": "done", "frac": 1.0, "heartbeat": timezone.now().isoformat()},
                error="",
            )
    except Exception as exc:  # noqa: BLE001 — istifadəçiyə səbəb göstərilməlidir
        logger.exception("timetable run %s failed", run_id)
        with db_block():
            Run.objects.filter(pk=run_id).update(
                status=RunStatus.FAILED,
                error=str(exc)[:2000] or exc.__class__.__name__,
                finished_at=timezone.now(),
                progress={"phase": "failed", "frac": 1.0},
            )
    with db_block():
        return Run.objects.select_related("organization", "period", "created_by").get(pk=run_id)


def start(run, *, force_sync=False):
    """Növbəyə qoy (Celery ``heavy`` növbəsi); broker yoxdursa brauzerdə qısa limitlə işlət."""
    from ..tasks import run_solver

    if not force_sync:
        try:
            run_solver.apply_async(args=[str(run.pk), str(run.organization_id)], queue="heavy")
            run.refresh_from_db()
            return run
        except Exception:  # noqa: BLE001 — broker əlçatan deyil → sinxron fallback
            logger.warning("timetable: növbə əlçatan deyil, sinxron fallback (run %s)", run.pk)
    return execute(run.pk, time_cap=SYNC_TIME_LIMIT)


def is_stale(run) -> bool:
    """Növbədə/işləyir statusunda ürək döyüntüsü ``STALE_AFTER`` saniyədən köhnədirsə."""
    from datetime import datetime

    if run.status == RunStatus.QUEUED:
        return (timezone.now() - run.created_at).total_seconds() > STALE_AFTER
    if run.status != RunStatus.RUNNING:
        return False
    reference = run.started_at or run.created_at
    beat = (run.progress or {}).get("heartbeat")
    if beat:
        try:
            reference = datetime.fromisoformat(beat)
        except ValueError:
            pass
    return (timezone.now() - reference).total_seconds() > STALE_AFTER


def status_payload(run) -> dict:
    progress = dict(run.progress or {})
    return {
        "ok": True,
        "id": str(run.pk),
        "status": run.status,
        "status_label": str(dict(RunStatus.choices).get(run.status, run.status)),
        "phase": progress.get("phase", ""),
        "frac": progress.get("frac", 0),
        "unplaced": progress.get("unplaced"),
        "stale": is_stale(run),
        "error": run.error,
        "is_active": run.status in ACTIVE_STATUSES,
    }


def rerun(run, *, actor, keep_locks=True):
    """Eyni əhatə/parametrlərlə yeni işləmə; kilidlər mənbədən köçür."""
    return create_run(
        actor=actor,
        organization=run.organization,
        period=run.period,
        scope=run.scope,
        params=run.params,
        priorities={"teachers": (run.priorities or {}).get("teachers") or []},
        seed=run.seed,
        source_run=run if keep_locks else None,
    )


def discard(run, *, actor, request=None):
    from core.audit import log_action
    from core.constants import AuditAction

    if run.status == RunStatus.PUBLISHED:
        return run
    _model("TimetableRun").objects.filter(pk=run.pk).update(status=RunStatus.DISCARDED)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=run.organization,
        obj=run,
        new_values={"status": RunStatus.DISCARDED},
        request=request,
        resource_type="timetable.TimetableRun",
        resource_id=str(run.pk),
        resource_repr=run.title,
    )
    run.refresh_from_db()
    return run


__all__ = [
    "STALE_AFTER",
    "build_for_run",
    "clean_params",
    "clean_priorities",
    "create_run",
    "discard",
    "execute",
    "is_stale",
    "reason_text",
    "rerun",
    "start",
    "status_payload",
]
