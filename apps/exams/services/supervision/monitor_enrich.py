"""İM monitorunun tələbə sətirlərini proktorinq məlumatı ilə zənginləşdirir.

Zal (``room_monitor_snapshot``) və oturum (``session_monitor_snapshot``)
snapshot-larının HƏR İKİSİ eyni funksiyadan keçir ki, iki ekran heç vaxt
ayrılmasın. Əlavə olunan sahələr (yalnız nəzarətçi view-larında qaytarılır):

* kimlik: ``photo_url`` · ``initials`` · ``group`` · ``student_number``;
* risk: ``risk_score`` · ``risk_threshold`` · ``flagged`` · ``signal_count`` ·
  ``max_severity``;
* canlılıq: ``supervised`` · ``heartbeat`` ({"status", "age", …});
* «Qayda pozanlar» paneli (2026-10-21): ``vio_types`` — növ üzrə kompakt cəm
  ``[[kod, say, ciddilik], …]`` (ən çox ``VIO_TYPES_LIMIT``, qalanı ``vio_types_more``) ·
  ``last_event_at`` (ən son qayda/siqnal anı). Etiketlər sətirdə təkrarlanmır —
  snapshot-un yuxarı səviyyəsində bir dəfə (``event_labels_for_rows``).

Sorğu büdcəsi sabitdir (sətir sayından asılı deyil): profil + qrup + imtahan
seçimləri + nəzarət konfiqi + 2 risk aqreqatı + 1 cache ``get_many`` + 1 irəliləyiş
aqreqatı (``answered`` / ``question_total``, 2026-10-13).
"""

from __future__ import annotations

from django.utils.dateparse import parse_datetime

from apps.exams.features import exam_supervision_enabled

from ._shared import get_supervision_config
from .heartbeat import heartbeat_map, heartbeat_state
from .identity import attach_identity, student_identity
from .proctoring_options import DEFAULT_FLAG_THRESHOLD, proctoring_options, proctoring_options_for_exams
from .risk import SEVERITY_POINTS, attempt_risk, attempt_timeline, attempts_risk, timeline_as_json
from .signals import SIGNAL_LABELS, signal_label

#: Sətir başına növ cəmi tavanı — payload tələbə × növ ilə böyüməsin (qalanı ``vio_types_more``).
VIO_TYPES_LIMIT = 4


def _compact_types(types: dict) -> tuple[list, int]:
    """{kod: {"n", "severity", "last"}} → ([[kod, say, ciddilik], …] (say↓, ciddilik↓), artıq növ sayı)."""
    ordered = sorted(
        types.items(),
        key=lambda item: (-item[1]["n"], -SEVERITY_POINTS.get(item[1]["severity"], 0), item[0]),
    )
    compact = [[code, entry["n"], entry["severity"]] for code, entry in ordered[:VIO_TYPES_LIMIT]]
    return compact, max(0, len(ordered) - VIO_TYPES_LIMIT)


def event_label(code: str) -> str:
    """Qayda (``SupervisionIncident``) və ya siqnal (``ProctoringLog``) kodunun tərcümə olunmuş adı."""
    from apps.exams.models import ProctoringLog, SupervisionIncident

    rule = dict(SupervisionIncident.EVENT_TYPE_CHOICES).get(code)
    if rule is not None:
        return str(rule)
    if code in SIGNAL_LABELS:
        return signal_label(code)
    legacy = dict(ProctoringLog.EVENT_TYPE_CHOICES).get(code)
    return str(legacy) if legacy is not None else code


def event_labels_for_codes(codes) -> dict:
    return {code: event_label(code) for code in sorted({str(code) for code in codes if code})}


def event_labels_for_rows(rows) -> dict:
    """Snapshot-dakı bütün ``vio_types`` kodları üçün {kod: etiket} (sorğu yoxdur)."""
    return event_labels_for_codes(entry[0] for row in rows for entry in (row.get("vio_types") or []))


def _supervised_exam_ids(exam_ids) -> set:
    if not exam_ids or not exam_supervision_enabled():
        return set()
    from apps.exams.models import ExamSupervisionConfig

    return set(
        ExamSupervisionConfig.objects.filter(exam_id__in=exam_ids, enabled=True).values_list("exam_id", flat=True)
    )


def attempts_progress(attempt_ids) -> dict:
    """{attempt_id: (cavablanmış, cəmi)} — TƏK aqreqat sorğu (2026-10-13, gecə).

    Nəzarətçi zalda kimin «ilişib qaldığını» (uzun müddət 0 cavab) və ya qeyri-adi
    sürətlə irəlilədiyini görsün. «Cavablanmış» = mətn / rəsm / dondurulmuş variant
    seçimi olan cavab (``_answer_writes`` hər yazıda ``selected_option_ids_snapshot``-u
    doldurur). Kodlaşdırma cəhdlərinin ExamAnswer sətri yoxdursa nəticə boş qalır.
    """
    from django.db.models import Count, Q

    from apps.exams.models import ExamAnswer

    ids = [attempt_id for attempt_id in set(attempt_ids) if attempt_id]
    if not ids:
        return {}
    answered_q = (
        ~Q(text_answer="")
        | Q(has_paint=True)
        | (Q(selected_option_ids_snapshot__isnull=False) & ~Q(selected_option_ids_snapshot=[]))
    )
    rows = (
        ExamAnswer.objects.filter(attempt_id__in=ids)
        .values("attempt_id")
        .annotate(total=Count("id"), answered=Count("id", filter=answered_q))
    )
    return {row["attempt_id"]: (row["answered"], row["total"]) for row in rows}


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
    progress = attempts_progress([row.get("attempt_id") for row in rows if row.get("status") == "active"])

    for row in rows:
        attempt_id = row.get("attempt_id")
        info = risk.get(attempt_id) or {}
        row["supervised"] = row.get("exam_id") in supervised
        row["risk_score"] = info.get("score", 0)
        row["risk_threshold"] = info.get("threshold", thresholds.get(attempt_id, DEFAULT_FLAG_THRESHOLD))
        row["flagged"] = bool(info.get("flagged"))
        row["signal_count"] = info.get("signals", 0)
        row["max_severity"] = info.get("max_severity", "")
        row["vio_types"], row["vio_types_more"] = _compact_types(info.get("types") or {})
        last_at = info.get("last_at")
        row["last_event_at"] = last_at.isoformat() if last_at else None
        answered, total = progress.get(attempt_id, (None, None))
        row["answered"] = answered
        row["question_total"] = total
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


__all__ = [
    "VIO_TYPES_LIMIT",
    "attempt_proctor_detail",
    "attempts_progress",
    "enrich_monitor_rows",
    "event_label",
    "event_labels_for_codes",
    "event_labels_for_rows",
]
