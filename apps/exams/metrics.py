"""İmtahan biznes SLI metrikləri (audit EXAM-P1-20).

Generic HTTP metrikaları imtahan etibarını ölçmür — audit start/submit/
autosave/result-publish/PIN-fail/supervision üçün ayrıca SLI istədi. Bu modul
prometheus_client Counter-ları təyin edir və `record_*` köməkçiləri ilə view
qatından çağırılır. prometheus_client yoxdursa (məs. minimal test mühiti) modul
no-op-a düşür ki, import heç vaxt sınmasın.
"""

import logging

logger = logging.getLogger("exams.metrics")

try:
    from prometheus_client import Counter

    exam_attempt_started_total = Counter(
        "exam_attempt_started_total",
        "İmtahan cəhdinin uğurla başladılması sayı",
        ["exam_type"],
    )
    exam_attempt_submitted_total = Counter(
        "exam_attempt_submitted_total",
        "İmtahan cəhdinin tamamlanması (submit/expire) sayı",
        ["exam_type", "outcome"],
    )
    exam_autosave_total = Counter(
        "exam_autosave_total",
        "Autosave nəticələri",
        ["result"],
    )
    exam_result_published_total = Counter(
        "exam_result_published_total",
        "Nəticə/görünürlük publish əməliyyatları",
        ["action"],
    )
    exam_pin_attempt_total = Counter(
        "exam_pin_attempt_total",
        "Tələbə PIN giriş cəhdləri",
        ["result"],
    )
    exam_supervision_incident_total = Counter(
        "exam_supervision_incident_total",
        "Qeydə alınan supervision incident-ləri",
        ["event_type"],
    )
    _ENABLED = True
except Exception:  # pragma: no cover — prometheus yoxdursa metriklər no-op
    _ENABLED = False


def _safe(fn):
    """Metrik yazısı heç vaxt biznes axınını pozmamalıdır."""
    try:
        if _ENABLED:
            fn()
    except Exception:  # pragma: no cover
        logger.debug("exam metric yazısı alınmadı", exc_info=True)


def record_attempt_started(exam_type: str) -> None:
    _safe(lambda: exam_attempt_started_total.labels(exam_type=exam_type or "unknown").inc())


def record_attempt_submitted(exam_type: str, outcome: str) -> None:
    _safe(lambda: exam_attempt_submitted_total.labels(exam_type=exam_type or "unknown", outcome=outcome).inc())


def record_autosave(result: str) -> None:
    _safe(lambda: exam_autosave_total.labels(result=result).inc())


def record_result_published(action: str) -> None:
    _safe(lambda: exam_result_published_total.labels(action=action).inc())


def record_pin_attempt(result: str) -> None:
    _safe(lambda: exam_pin_attempt_total.labels(result=result).inc())


def record_supervision_incident(event_type: str) -> None:
    _safe(lambda: exam_supervision_incident_total.labels(event_type=event_type or "unknown").inc())


__all__ = [
    "record_attempt_started",
    "record_attempt_submitted",
    "record_autosave",
    "record_result_published",
    "record_pin_attempt",
    "record_supervision_incident",
]
