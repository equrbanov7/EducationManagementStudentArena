"""Final/midterm imtahanları yalnız universitet şəbəkəsindən (2026-10-13, gecə).

Sahibin tələbi: «ancaq universitet şəbəkəsinə qoşulu olarkən o hissəyə tələbə keçid edib
final və midterm imtahanını verə bilər». Qayda SERVER tərəfindədir və imtahanı vermə
zəncirinin HƏR addımında tətbiq olunur — UI-da düymənin gizlədilməsi sərhəd deyil:

* ``/exams/final/`` giriş səhifəsi + gözləmə otağı + ``begin`` (view: ``final_center.py``);
* ``start_exam`` və kabinet PIN yolu ``exam_code_check`` (midterm);
* cəhd endpoint-ləri — take səhifəsi, autosave/finish, ``question-seen``, kodlaşdırma
  (``ensure_active_attempt_access`` + kilidli POST yolu);
* nəzarət API-ləri — heartbeat, siqnal, hadisə, status.

Zona ``core.network_zone``-dan gəlir (nginx ``X-EMS-Zone`` yalnız
``NETWORK_ZONE_TRUST_HEADER`` olanda, əks halda ``INTERNAL_NETWORKS`` CIDR-i). Qayda
``EXAM_FINAL_INTERNAL_ONLY`` ayarı ilə idarə olunur və ``NETWORK_ZONE_ENFORCED``-dən
ASILI DEYİL (o yalnız jurnal/inzibati qaydalar üçündür). Müəllifin «Sınaq keç» cəhdi
(``is_trial``) və imtahan müəllifinin özü azaddır — onlar nəticəyə sayılmır.

Qiymət: DB sorğusu YOXDUR — zona middleware-in sorğuya yazdığı dəyərdir.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.utils.translation import pgettext

from core.network_zone import ZONE_INTERNAL, request_network_zone
from core.utils import get_client_ip

logger = logging.getLogger("exams.network")

#: Yalnız daxili şəbəkədən verilə bilən imtahan kateqoriyaları.
INTERNAL_ONLY_EXAM_KINDS = frozenset({"final", "midterm"})
#: Eyni (istifadəçi, imtahan) üçün «kənar şəbəkə» audit sətirləri arasında minimum interval.
DENY_AUDIT_THROTTLE_SECONDS = 60

_CTX = "exams.network"


class ExamNetworkDenied(PermissionDenied):
    """Final/midterm kənar şəbəkədən. ``PermissionDenied`` — tutulmasa belə 403 (fail-closed)."""

    def __init__(self, exam=None):
        super().__init__(exam_network_denied_message())
        self.exam = exam


def exam_network_denied_message() -> str:
    return pgettext(
        _CTX,
        "Final və midterm imtahanları yalnız universitet şəbəkəsindən verilir. "
        "Universitetin daxili şəbəkəsinə (imtahan zalı kompüterinə) qoşulun və səhifəni yeniləyin.",
    )


def internal_only_enabled() -> bool:
    return bool(getattr(settings, "EXAM_FINAL_INTERNAL_ONLY", False))


def exam_requires_internal_network(exam) -> bool:
    return internal_only_enabled() and getattr(exam, "exam_type_extended", None) in INTERNAL_ONLY_EXAM_KINDS


def request_on_internal_network(request) -> bool:
    return request is not None and request_network_zone(request) == ZONE_INTERNAL


def final_entry_network_allowed(request) -> bool:
    """``/exams/final/`` səhifələri yalnız final/midterm üçündür — ayar açıqdırsa daxili zona şərtdir."""
    return not internal_only_enabled() or request_on_internal_network(request)


def _is_author(exam, user_pk) -> bool:
    return user_pk is not None and user_pk == getattr(exam, "author_id", None)


def exam_network_allowed(request, exam, user=None) -> bool:
    """YENİ cəhd / giriş üçün: bu sorğu ``exam``-a daxil ola bilərmi (müəllif azaddır)."""
    if not exam_requires_internal_network(exam):
        return True
    if _is_author(exam, getattr(user if user is not None else getattr(request, "user", None), "pk", None)):
        return True
    return request_on_internal_network(request)


def attempt_network_allowed(request, attempt) -> bool:
    """Davam edən cəhdin endpoint-ləri üçün (sınaq cəhdi azaddır).

    Perf: yalnız ``attempt.user_id`` — ``attempt.user`` obyekti yüklənmir (autosave sorğu büdcəsi).
    """
    if request is None or getattr(attempt, "is_trial", False):
        return True
    exam = attempt.exam
    if not exam_requires_internal_network(exam) or _is_author(exam, getattr(attempt, "user_id", None)):
        return True
    return request_on_internal_network(request)


def record_network_denial(request, exam, *, where: str) -> None:
    """Rəddin logu + audit sətri (istifadəçi×imtahan üzrə dəqiqədə bir — autosave dövrəsi selləməsin)."""
    user = getattr(request, "user", None)
    user_pk = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
    client_ip = get_client_ip(request) or ""
    logger.warning(
        "exam_network: kənar zona rədd edildi — %s exam=%s user=%s ip=%s",
        where,
        getattr(exam, "pk", None),
        user_pk,
        client_ip,
    )
    try:
        first = bool(
            cache.add(
                f"exam_network_deny:{user_pk or client_ip}:{getattr(exam, 'pk', '-')}", 1, DENY_AUDIT_THROTTLE_SECONDS
            )
        )
    except Exception:  # noqa: BLE001 — keş yoxdursa audit yazılır
        first = True
    if not first:
        return
    from core.audit import log_action
    from core.constants import AuditAction
    from core.rls import bypass_rls

    try:
        with bypass_rls():
            log_action(
                AuditAction.DENY,
                user=user if user_pk else None,
                organization=getattr(exam, "organization", None),
                obj=exam,
                reason=f"exam_network_external: {where}"[:200],
                request=request,
                resource_type="exam_network_deny",
                resource_id=str(getattr(exam, "pk", "")),
            )
    except Exception:  # noqa: BLE001 — audit xətası cavabı sındırmasın
        logger.exception("exam_network: audit yazılmadı")


def enforce_attempt_network(request, attempt, *, where: str = "attempt") -> None:
    """Kənar zonadan gələn final/midterm cəhd sorğusu → ``ExamNetworkDenied`` (audit view qatında)."""
    if not attempt_network_allowed(request, attempt):
        raise ExamNetworkDenied(attempt.exam)


__all__ = [
    "DENY_AUDIT_THROTTLE_SECONDS",
    "INTERNAL_ONLY_EXAM_KINDS",
    "ExamNetworkDenied",
    "attempt_network_allowed",
    "enforce_attempt_network",
    "exam_network_allowed",
    "exam_network_denied_message",
    "exam_requires_internal_network",
    "final_entry_network_allowed",
    "internal_only_enabled",
    "record_network_denial",
    "request_on_internal_network",
]
