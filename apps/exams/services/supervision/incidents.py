"""supervision paketi — incidents.

2026-11-20 (sahib, QuizPython577E): bir hərəkət bir neçə pozuntu kimi sayılırdı — pəncərədən çıxmaq eyni
saniyədə ``window_blurred`` + ``tab_switched`` (+ ikinci ``blur``) göndərir; 3 limitli imtahanda tələbə BİR
alt-tab ilə 1 saniyədə kilidlənirdi (prod: 2 cəhd belə kilidləndi, biri 10 dəq-lik bərpa pəncərəsi bitib
0 cavabla təhvil verildi). İndi:

* eyni «çıxış epizodu» (``VIOLATION_EPISODE_SECONDS`` daxilində) bir dəfə sayılır, qalanları qeyd olunur,
  amma sayğacı artırmır (``metadata.counted = False``, ciddilik ``info``);
* cəhd kilidli/uzaqlaşdırılmış ikən gələn hadisələr sayılmır — tələbə kilid ekranındadır, yaza bilmir;
  əvvəl sayğac limitdən yuxarı qalxırdı və «əlavə şans» (-1) onu limitin altına endirə bilmirdi.

Qərar cəhd sətrinin ``FOR UPDATE`` kilidi altındadır: eyni anda gələn iki hadisə ikisi də «ilk» sayılmır.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import SupervisionIncident

from ._shared import (
    get_supervision_config,
)
from .constants import (
    EVENT_SEVERITY_MAP,
    VIOLATION_EVENT_TYPES,
)

#: Bu pəncərədə ikinci sayılan pozuntu eyni epizoddur (blur + tab_switched eyni hərəkətdir).
#: ``EXAM_SUPERVISION_VIOLATION_EPISODE_SECONDS`` ilə dəyişdirilə bilər (0 = hər hadisə ayrıca sayılır).
VIOLATION_EPISODE_SECONDS = 3
_NOT_COUNTING_STATUSES = ("locked", "removed")
#: Saxlanan metadata açarlarının tavanı (klient açarları + serverin ``counted`` açarı).
_METADATA_KEY_CAP = 20


def _episode_seconds():
    return max(0, int(getattr(settings, "EXAM_SUPERVISION_VIOLATION_EPISODE_SECONDS", VIOLATION_EPISODE_SECONDS)))


def _server_metadata(metadata, counted):
    client = [(key, value) for key, value in (metadata or {}).items() if key != "counted"]
    return {**dict(client[: _METADATA_KEY_CAP - 1]), "counted": counted}


def _record_violation(attempt, event_type, metadata):
    """Pozuntunu kilid altında yaz; ``(incident, counted)``. Sayılan pozuntu sayğacı +1 edir."""
    now = timezone.now()
    model = attempt.__class__
    with transaction.atomic():
        row = model.objects.select_for_update(of=("self",)).filter(pk=attempt.pk).values("supervision_status").first()
        status = (row or {}).get("supervision_status", attempt.supervision_status)
        recent = SupervisionIncident.objects.filter(
            attempt_id=attempt.pk,
            event_type__in=VIOLATION_EVENT_TYPES,
            metadata__counted=True,
            timestamp__gt=now - timedelta(seconds=_episode_seconds()),
        ).exists()
        counted = status not in _NOT_COUNTING_STATUSES and not recent
        if counted:
            # F() paralel brauzer hadisələrinin eyni köhnə dəyəri yazıb artım itirməsinin qarşısını alır.
            model.objects.filter(pk=attempt.pk).update(supervision_violation_count=F("supervision_violation_count") + 1)
        attempt.refresh_from_db(fields=["supervision_violation_count", "supervision_status"])
        incident = SupervisionIncident.objects.create(
            organization=attempt.exam.organization,
            exam=attempt.exam,
            attempt=attempt,
            student=attempt.user,
            event_type=event_type,
            severity=EVENT_SEVERITY_MAP.get(event_type, "medium") if counted else "info",
            # ``counted`` SERVERİN açarıdır — klientin göndərdiyi eyni adlı açarın üstünə yazılır.
            metadata=_server_metadata(metadata, counted),
            violation_count_at_time=attempt.supervision_violation_count,
        )
    return incident, counted


def log_supervision_incident(attempt, event_type, metadata=None):
    """
    Log a supervision incident and return the result with status info.

    Returns a dict with:
      - incident: the created SupervisionIncident
      - violation_count: current total violations for this attempt
      - limit_exceeded: whether the violation limit has been exceeded
      - action_taken: what action was taken (if any)
      - supervision_status: current supervision status of the attempt
    """
    if not exam_supervision_enabled():
        return None

    exam = attempt.exam
    config = get_supervision_config(exam)

    if config is None:
        return None

    is_violation = event_type in VIOLATION_EVENT_TYPES
    counted = False

    if is_violation:
        incident, counted = _record_violation(attempt, event_type, metadata)
    else:
        incident = SupervisionIncident.objects.create(
            organization=exam.organization,
            exam=exam,
            attempt=attempt,
            student=attempt.user,
            event_type=event_type,
            severity=EVENT_SEVERITY_MAP.get(event_type, "medium"),
            metadata=metadata or {},
            violation_count_at_time=attempt.supervision_violation_count,
        )
    violation_count = attempt.supervision_violation_count

    # EXAM-P1-20: supervision incident-i SLI kimi qeyd et.
    from apps.exams.metrics import record_supervision_incident

    record_supervision_incident(event_type)

    # Check if violation limit exceeded
    max_violations = config.get_max_total_violations()
    limit_exceeded = counted and violation_count >= max_violations
    action_taken = ""

    # Müəllimin "Sınaq keç" cəhdi nəzarət qaydalarını YOXLAMAQ üçündür — orada
    # kilid/uzaqlaşdırma tətbiq olunmur (əks halda sınaq cəhdi "suspended"
    # vəziyyətində ilişib qalır və onu bərpa edəcək müəllim elə özüdür).
    # İncident yenə yazılır, amma cavabda yalnız xəbərdarlıq qaytarılır.
    is_trial_attempt = bool(getattr(attempt, "is_trial", False))

    if limit_exceeded and attempt.supervision_status not in ("locked", "removed"):
        if is_trial_attempt:
            action_taken = "trial_warning"
        else:
            action_taken = _apply_violation_action(attempt, config, violation_count)

    return {
        "incident_id": incident.id,
        "violation_count": violation_count,
        "max_violations": max_violations,
        "limit_exceeded": limit_exceeded,
        "action_taken": action_taken,
        "supervision_status": attempt.supervision_status,
        "is_trial": is_trial_attempt,
        "counted": counted,
    }


def _apply_violation_action(attempt, config, violation_count):
    """Apply the configured violation action when limit is exceeded."""
    action = config.violation_action

    if action == "auto_submit":
        attempt.supervision_status = "removed"
        attempt.mark_finished(status="submitted", extra_update_fields=["supervision_status"])
        _log_system_incident(
            attempt,
            "auto_submitted",
            {
                "reason": "violation_limit_exceeded",
                "violation_count": violation_count,
            },
        )
        return "auto_submitted"

    elif action == "lock_exam":
        attempt.supervision_status = "locked"
        # Start the teacher resume window from this moment.
        attempt.supervision_locked_at = timezone.now()
        attempt.save(update_fields=["supervision_status", "supervision_locked_at"])
        _log_system_incident(
            attempt,
            "auto_locked",
            {
                "reason": "violation_limit_exceeded",
                "violation_count": violation_count,
            },
        )
        return "locked"

    elif action == "remove_student":
        attempt.supervision_status = "removed"
        attempt.save(update_fields=["supervision_status"])
        _log_system_incident(
            attempt,
            "auto_locked",
            {
                "reason": "student_removed",
                "violation_count": violation_count,
            },
        )
        return "removed"

    elif action == "mark_suspicious":
        attempt.supervision_status = "warned"
        attempt.save(update_fields=["supervision_status"])
        _log_system_incident(
            attempt,
            "suspicious_repeated",
            {
                "reason": "marked_suspicious",
                "violation_count": violation_count,
            },
        )
        return "marked_suspicious"

    return ""


def _log_system_incident(attempt, event_type, metadata):
    """Log a system-generated incident (auto-lock, auto-submit, etc.)."""
    SupervisionIncident.objects.create(
        organization=attempt.exam.organization,
        exam=attempt.exam,
        attempt=attempt,
        student=attempt.user,
        event_type=event_type,
        severity=EVENT_SEVERITY_MAP.get(event_type, "critical"),
        metadata=metadata,
        violation_count_at_time=attempt.supervision_violation_count,
    )
