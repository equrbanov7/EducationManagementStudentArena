"""Giriş sətirlərinin saxlanması — sessiyalar və OTP-lər (fon işi tutumu 2026-10-07).

* ``django_session`` — ``SESSION_ENGINE=cached_db`` hər girişdə DB sətri yazır
  (prod ``SESSION_COOKIE_AGE`` = 1 gün), amma vaxtı keçmiş sətirləri heç nə
  silmirdi (``clearsessions`` cədvəldə yox idi): cədvəl giriş sayı qədər, sonsuz
  böyüyürdü (1 M sətir ≈ 454 MB sandbox-da). Gecəlik ``accounts.purge_expired_sessions``
  vaxtı keçmiş sətirləri ``expire_date`` indeksi ilə hissə-hissə silir.
* ``accounts_emailotp`` — OTP yalnız ``expires_at``-a qədər + 1 saatlıq göndərmə
  limiti pəncərəsində lazımdır; sətirlər (e-poçt ünvanı ilə) əbədi qalırdı.
  ``ACCOUNTS_OTP_RETENTION_DAYS`` (defolt 30, ``0`` → söndürülür) keçmiş OTP-lər silinir.
"""

from __future__ import annotations

from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.utils import timezone

from core.batch_purge import purge_in_batches

DEFAULT_OTP_RETENTION_DAYS = 30


def otp_retention_days() -> int:
    try:
        value = int(getattr(settings, "ACCOUNTS_OTP_RETENTION_DAYS", DEFAULT_OTP_RETENTION_DAYS))
    except (TypeError, ValueError):
        value = DEFAULT_OTP_RETENTION_DAYS
    return max(value, 0)


def session_model():
    """DB-yə yazan sessiya mühərrikinin modeli; yalnız-cache mühərrikində ``None``."""
    store = getattr(import_module(settings.SESSION_ENGINE), "SessionStore", None)
    getter = getattr(store, "get_model_class", None)
    return getter() if getter is not None else None


def purge_expired_sessions(*, now=None, batch_size=5000, time_budget=180.0, scope=None) -> int:
    """Vaxtı keçmiş sessiya sətirlərini hissə-hissə sil → silinən say.

    ``scope`` — hər hissəni saran kontekst (Celery task-ı ``rls_worker_atomic() + bypass_rls()`` ötürür).
    """
    model = session_model()
    if model is None:
        return 0
    expired = model.objects.filter(expire_date__lt=now or timezone.now())
    return purge_in_batches(
        expired, batch_size=batch_size, time_budget=time_budget, scope=scope, label="django_session"
    )


def purge_stale_otps(*, now=None, batch_size=5000, time_budget=180.0, scope=None) -> int:
    """``ACCOUNTS_OTP_RETENTION_DAYS``-dən əvvəl vaxtı bitmiş OTP sətirlərini sil → silinən say."""
    from .models import EmailOTP

    days = otp_retention_days()
    if days <= 0:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    return purge_in_batches(
        EmailOTP.objects.filter(expires_at__lt=cutoff),
        batch_size=batch_size,
        time_budget=time_budget,
        scope=scope,
        label="accounts_emailotp",
    )


__all__ = [
    "DEFAULT_OTP_RETENTION_DAYS",
    "otp_retention_days",
    "purge_expired_sessions",
    "purge_stale_otps",
    "session_model",
]
