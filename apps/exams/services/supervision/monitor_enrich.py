"""İM monitorunun tələbə sətirlərini proktorinq məlumatı ilə zənginləşdirir.

Zal (``room_monitor_snapshot``) və oturum (``session_monitor_snapshot``)
snapshot-larının HƏR İKİSİ eyni funksiyadan keçir ki, iki ekran heç vaxt
ayrılmasın. Əlavə olunan sahələr (yalnız nəzarətçi view-larında qaytarılır):

* kimlik: ``photo_url`` · ``initials`` · ``group`` · ``student_number``;
* risk: ``risk_score`` · ``risk_threshold`` · ``flagged`` · ``signal_count`` ·
  ``max_severity``;
* canlılıq: ``supervised`` · ``heartbeat`` ({"status", "age", …}).

Sorğu büdcəsi sabitdir (sətir sayından asılı deyil): profil + qrup + imtahan
seçimləri + nəzarət konfiqi + 2 risk aqreqatı + 1 cache ``get_many``.
"""

from __future__ import annotations

from django.utils.dateparse import parse_datetime

from apps.exams.features import exam_supervision_enabled

from ._shared import get_supervision_config
from .heartbeat import heartbeat_map, heartbeat_state
from .identity import attach_identity, student_identity
from .proctoring_options import DEFAULT_FLAG_THRESHOLD, proctoring_options, proctoring_options_for_exams
from .risk import attempt_risk, attempt_timeline, attempts_risk, timeline_as_json


def _supervised_exam_ids(exam_ids) -> set:
    if not exam_ids or not exam_supervision_enabled():
        return set()
    from apps.exams.models import ExamSupervisionConfig

    return set(
        ExamSupervisionConfig.objects.filter(exam_id__in=exam_ids, enabled=True).values_list("exam_id", flat=True)
    )


def enrich_monitor_rows(rows, organization, users_by_id) -> list:
    rows = list(rows)
    if not rows:
        return rows
    attach_identity(rows, organization, users_by_id)

    exam_ids = {row.get("exam_id") for row in rows if row.get("exam_id")}
    options = proctoring_options_for_exams(exam_ids)
    supervised = _supervised_exam_ids(exam_ids)

    thresholds = {}
    attempt_ids = []
    live_attempt_ids = []
    for row in rows:
        attempt_id = row.get("attempt_id")
        if not attempt_id:
            continue
        attempt_ids.append(attempt_id)
        thresholds[attempt_id] = (options.get(row.get("exam_id")) or {}).get("flag_threshold", DEFAULT_FLAG_THRESHOLD)
        if row.get("status") == "active" and row.get("exam_id") in supervised:
            live_attempt_ids.append(attempt_id)

    risk = attempts_risk(attempt_ids, thresholds)
    beats = heartbeat_map(live_attempt_ids)
    live = set(live_attempt_ids)

    for row in rows:
        attempt_id = row.get("attempt_id")
        info = risk.get(attempt_id) or {}
        row["supervised"] = row.get("exam_id") in supervised
        row["risk_score"] = info.get("score", 0)
        row["risk_threshold"] = info.get("threshold", thresholds.get(attempt_id, DEFAULT_FLAG_THRESHOLD))
        row["flagged"] = bool(info.get("flagged"))
        row["signal_count"] = info.get("signals", 0)
        row["max_severity"] = info.get("max_severity", "")
        if attempt_id in live:
            started = parse_datetime(row.get("started_at") or "") if row.get("started_at") else None
            row["heartbeat"] = heartbeat_state(beats.get(attempt_id), started_at=started)
        else:
            row["heartbeat"] = None
    return rows


def attempt_proctor_detail(attempt, organization_id, *, timeline_limit: int = 100) -> dict:
    """Bir cəhdin nəzarətçi detalı: kimlik + risk + xronologiya + heartbeat.

    Çağıran (view) obyekt səviyyəli icazəni ÖZÜ yoxlamalıdır (zal/oturum skopu).
    """
    options = proctoring_options(attempt.exam)
    supervised = get_supervision_config(attempt.exam) is not None
    heartbeat = None
    if supervised and not attempt.is_finished:
        heartbeat = heartbeat_state(heartbeat_map([attempt.pk]).get(attempt.pk), started_at=attempt.started_at)
    return {
        "identity": student_identity(organization_id, attempt.user),
        "supervised": supervised,
        "risk": attempt_risk(attempt, options["flag_threshold"]),
        "timeline": timeline_as_json(attempt_timeline(attempt, limit=timeline_limit)),
        "heartbeat": heartbeat,
    }


__all__ = ["attempt_proctor_detail", "enrich_monitor_rows"]
