"""Cəhd üzrə proktorinq RİSK xalı + vahid hadisə xronologiyası.

Xal şəffaf və izah olunandır: hər qeydin ciddiliyi bal verir
(``SEVERITY_POINTS``). Qayda pozuntuları (``SupervisionIncident``) və evristik
siqnallar (``ProctoringLog``) birlikdə cəmlənir. Xal imtahanın
``flag_threshold`` həddinə çatanda cəhd «şübhəli» işarələnir — bu YALNIZ
görüntüdür: nəticəyə, statusa, bala toxunulmur (avtomatik kəsilmə yoxdur;
mövcud «pozuntu limiti → kilid/təhvil» axını dəyişməyib).
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from .constants import NON_COUNTING_EVENT_TYPES, VIOLATION_EVENT_TYPES
from .proctoring_options import DEFAULT_FLAG_THRESHOLD
from .signals import signal_label

SEVERITY_POINTS = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")

#: Xala düşən qayda hadisələri: sayğaclı pozuntular + bloklanmış cəhdlər
#: (kopyala/yapışdır, sağ klik …). Nəticə hadisələri (auto_locked, auto_submitted)
#: pozuntunun özünü ikiqat saymasın deyə daxil deyil.
RISK_INCIDENT_TYPES = frozenset(VIOLATION_EVENT_TYPES | NON_COUNTING_EVENT_TYPES)

TIMELINE_LIMIT = 200


def _empty_counts() -> dict:
    return {severity: 0 for severity in SEVERITY_ORDER}


def _score(counts: dict) -> int:
    return sum(SEVERITY_POINTS.get(severity, 0) * number for severity, number in counts.items())


def attempts_risk(attempt_ids, thresholds=None) -> dict:
    """{attempt_id: {"score", "flagged", "threshold", "rules", "signals", "max_severity"}}.

    İki aqreqat sorğu (qayda + siqnal), N+1 yoxdur. ``thresholds`` —
    {attempt_id: flag_threshold}; verilməyən cəhd üçün defolt hədd.
    """
    from apps.exams.models import ProctoringLog, SupervisionIncident

    ids = [attempt_id for attempt_id in set(attempt_ids) if attempt_id]
    thresholds = thresholds or {}
    rules = defaultdict(_empty_counts)
    signals = defaultdict(_empty_counts)
    if ids:
        incident_rows = (
            SupervisionIncident.objects.filter(attempt_id__in=ids, event_type__in=RISK_INCIDENT_TYPES)
            .values("attempt_id", "severity")
            .annotate(n=Count("id"))
        )
        for row in incident_rows:
            severity = row["severity"] if row["severity"] in SEVERITY_POINTS else "medium"
            rules[row["attempt_id"]][severity] += row["n"]
        signal_rows = (
            ProctoringLog.objects.filter(exam_attempt_id__in=ids)
            .values("exam_attempt_id", "details__severity")
            .annotate(n=Count("id"))
        )
        for row in signal_rows:
            severity = row["details__severity"]
            severity = severity if severity in SEVERITY_POINTS else "low"
            signals[row["exam_attempt_id"]][severity] += row["n"]

    result = {}
    for attempt_id in ids:
        rule_counts = rules.get(attempt_id) or _empty_counts()
        signal_counts = signals.get(attempt_id) or _empty_counts()
        score = _score(rule_counts) + _score(signal_counts)
        threshold = thresholds.get(attempt_id) or DEFAULT_FLAG_THRESHOLD
        max_severity = ""
        for severity in SEVERITY_ORDER:
            if rule_counts[severity] or signal_counts[severity]:
                max_severity = severity
                break
        result[attempt_id] = {
            "score": score,
            "threshold": threshold,
            "flagged": score >= threshold,
            "rules": sum(rule_counts.values()),
            "signals": sum(signal_counts.values()),
            "signal_counts": dict(signal_counts),
            "max_severity": max_severity,
        }
    return result


def attempt_risk(attempt, threshold=None) -> dict:
    thresholds = {attempt.pk: threshold} if threshold else None
    return attempts_risk([attempt.pk], thresholds).get(attempt.pk) or {
        "score": 0,
        "threshold": threshold or DEFAULT_FLAG_THRESHOLD,
        "flagged": False,
        "rules": 0,
        "signals": 0,
        "signal_counts": _empty_counts(),
        "max_severity": "",
    }


def attempt_timeline(attempt, *, limit: int = TIMELINE_LIMIT) -> list:
    """Qayda hadisələri + siqnallar vahid xronologiyada (ən yeni əvvəldə).

    Hər sətir: {"source": "rule"|"signal", "code", "label", "severity", "at",
    "counts": bool}. Detallar (metadata) nəzarətçiyə göstərilmir — yalnız
    qısa, server tərəfindən yaradılmış etiket.
    """
    from apps.exams.models import ProctoringLog, SupervisionIncident

    rows = []
    incidents = SupervisionIncident.objects.filter(attempt_id=attempt.pk).order_by("-timestamp", "-id")[:limit]
    for incident in incidents:
        rows.append(
            {
                "source": "rule",
                "code": incident.event_type,
                "label": str(incident.get_event_type_display()),
                "severity": incident.severity,
                "at": incident.timestamp,
                "counts": incident.event_type in VIOLATION_EVENT_TYPES,
            }
        )
    logs = ProctoringLog.objects.filter(exam_attempt_id=attempt.pk).order_by("-timestamp", "-id")[:limit]
    for log in logs:
        details = log.details if isinstance(log.details, dict) else {}
        kind = str(details.get("kind") or log.event_type)
        rows.append(
            {
                "source": "signal",
                "code": kind,
                "label": signal_label(kind) if details.get("kind") else str(log.get_event_type_display()),
                "severity": details.get("severity") if details.get("severity") in SEVERITY_POINTS else "low",
                "at": log.timestamp,
                "counts": False,
            }
        )
    rows.sort(key=lambda row: row["at"], reverse=True)
    return rows[:limit]


def timeline_as_json(rows) -> list:
    return [{**row, "at": row["at"].isoformat() if row.get("at") else None} for row in rows]


__all__ = [
    "RISK_INCIDENT_TYPES",
    "SEVERITY_POINTS",
    "attempt_risk",
    "attempt_timeline",
    "attempts_risk",
    "timeline_as_json",
]
