"""final_center paketi — davam edən final cəhdinin cihaza bağlanması (təhlükəsizlik dizaynı 2026-10-08).

Problem (audit 2026-10-07 «Dizayn riskləri»): qeydli zal kompüteri olmayan təşkilatda final
cəhdi biletsiz (fərdi PIN) axınla başlayır və giriş sessiyası yoxlaması yalnız bilet olanda
işləyir — tələbə başqa cihazdan (telefon, ev kompüteri) adi login ilə cəhdi davam etdirə
bilirdi.

Qayda — tətbiq olunur: ``exam_type_extended == "final"``, cəhd bitməyib, sınaq deyil:

1. **İlk giriş bağlayır.** Cəhdin ilk açılışı (take səhifəsi, autosave, ``question-seen``)
   brauzerə imzalı, HttpOnly ``ems_final_device`` cookie-si (təsadüfi id) yazır və eyni id-ni
   sessiyada saxlayır; bazada yalnız ``sha256(attempt_id:id)`` (``FinalAttemptDevice``).
   Yerləşdirmə anında davam edən köhnə cəhdlər də növbəti sorğuda — tələbənin indiki
   cihazında — bağlanır (imtahan qırılmır).
2. **Eyni cihaz həmişə keçir:** cookie (brauzer çöküşü, yenidən login, yeni sessiya) və ya
   sessiya (cookie silinib, sessiya qalıb — cookie yenidən yazılır).
3. **Eyni qeydli zal kompüteri** (cəhdin ``room_computer``-i, MAC/IP ilə tanınır) — cookie-ni
   silən kiosk brauzeri üçün; cəhd həmin kompüterdəki yeni brauzerə köçür (audit).
4. **Başqa cihaz** → 403, aydın mesaj; yalnız nəzarətçi / imtahan mərkəzinin «cihaz
   dəyişikliyi» təsdiqi ilə (``approve_device_change`` — audit, ``DEVICE_CHANGE_WINDOW``
   ərzində, birdəfəlik) cəhd yeni cihaza köçür, köhnə cihaz isə dayanır. Bilet axınında
   nəzarətçinin «yenidən giriş» PIN-i özü təsdiq sayılır (mövcud zal proseduru dəyişmir).

Qeydli kompüteri olan təşkilatda da eyni qayda işləyir (defense in depth: zal IP/MAC qapısı
+ PIN + cihaz bağlantısı).

Qiymət: yalnız final cəhdlərində bir PK SELECT; bağlama/köçürmə şərti UPDATE-dir (yarış
halında ikinci sorğu birinci qalibi görür).
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import FinalAttemptDevice
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls

logger = logging.getLogger("exams.final_center.device")

DEVICE_COOKIE_NAME = "ems_final_device"
DEVICE_COOKIE_SALT = "exams.final_center.device"
DEVICE_COOKIE_MAX_AGE = 14 * 24 * 60 * 60
DEVICE_SESSION_KEY = "final_device_id"
#: ``request``-ə qoyulur: cavaba (yenidən) yazılmalı cihaz id-si (``issue_device_cookie``).
REQUEST_ISSUE_ATTR = "_ems_final_device_issue"
DEVICE_CHANGE_WINDOW = timedelta(minutes=15)
#: Eyni cəhd üçün «başqa cihaz» audit sətirləri arasında minimum interval (autosave dövrəsi).
DENY_AUDIT_THROTTLE_SECONDS = 60

SOURCE_PROCTOR = "proctor_approval"
SOURCE_REENTRY_PIN = "reentry_pin"
SOURCE_HALL_COMPUTER = "hall_computer"

_DEVICE_ID_RE = re.compile(r"[A-Za-z0-9_-]{32,64}")
_CTX = "exams.final_center.device"


class FinalDeviceMismatch(PermissionDenied):
    """Cəhd başqa cihaza bağlıdır. ``PermissionDenied`` — tutulmasa belə 403 (fail-closed)."""

    def __init__(self, attempt):
        super().__init__(device_blocked_message())
        self.attempt = attempt


def device_blocked_message() -> str:
    return pgettext(
        _CTX,
        "Bu final imtahanı başqa cihazda davam edir. Cihazı dəyişmək lazımdırsa, nəzarətçidən və ya "
        "imtahan mərkəzindən «cihaz dəyişikliyi» təsdiqi istəyin, sonra səhifəni yeniləyin.",
    )


def device_window_minutes() -> int:
    return int(DEVICE_CHANGE_WINDOW.total_seconds() // 60)


def device_binding_applies(attempt) -> bool:
    exam = getattr(attempt, "exam", None)
    return bool(
        exam is not None
        and getattr(exam, "exam_type_extended", "") == "final"
        and getattr(exam, "organization_id", None)
        and not getattr(attempt, "is_trial", False)
        and not attempt.is_finished
    )


def _token_hash(attempt_pk, device_id: str) -> str:
    return hashlib.sha256(f"{attempt_pk}:{device_id}".encode()).hexdigest()


def _valid_device_id(value) -> str | None:
    value = str(value or "")
    return value if _DEVICE_ID_RE.fullmatch(value) else None


def _request_device_ids(request) -> tuple[str | None, str | None]:
    try:
        cookie_id = request.get_signed_cookie(
            DEVICE_COOKIE_NAME, default=None, salt=DEVICE_COOKIE_SALT, max_age=DEVICE_COOKIE_MAX_AGE
        )
    except Exception:  # noqa: BLE001 — saxta/köhnə imza = cookie yoxdur
        cookie_id = None
    session = getattr(request, "session", None)
    session_id = session.get(DEVICE_SESSION_KEY) if session is not None else None
    return _valid_device_id(cookie_id), _valid_device_id(session_id)


def _session_device_id(request) -> str | None:
    """Cookie-siz ilk sorğu üçün sessiyadan törəmə id: eyni sessiyanın paralel ilk sorğuları
    (səhifə + autosave) eyni id-ni alır, bir-birini «başqa cihaz» saymır."""
    from django.utils.crypto import salted_hmac

    session_key = getattr(getattr(request, "session", None), "session_key", None)
    return salted_hmac(DEVICE_COOKIE_SALT, session_key).hexdigest() if session_key else None


def _remember_device(request, device_id: str, cookie_id: str | None) -> None:
    session = getattr(request, "session", None)
    if session is not None and session.get(DEVICE_SESSION_KEY) != device_id:
        session[DEVICE_SESSION_KEY] = device_id
    if cookie_id != device_id:
        setattr(request, REQUEST_ISSUE_ATTR, device_id)


def issue_device_cookie(request, response) -> None:
    """Bu sorğuda bağlanan/təsdiqlənən cihaz id-si cookie-də yoxdursa cavaba yaz."""
    device_id = getattr(request, REQUEST_ISSUE_ATTR, None)
    if not device_id or response is None or not hasattr(response, "set_signed_cookie"):
        return
    response.set_signed_cookie(
        DEVICE_COOKIE_NAME,
        device_id,
        salt=DEVICE_COOKIE_SALT,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        samesite="Lax",
    )


def _audit(attempt, *, action, reason, request, user=None, changes=None) -> None:
    try:
        log_action(
            action,
            user=user if user is not None else _request_user(request),
            organization=getattr(attempt.exam, "organization", None),
            obj=attempt,
            changes=changes,
            reason=reason,
            request=request,
            resource_type="exam_attempt",
            resource_id=str(attempt.pk),
        )
    except Exception:  # noqa: BLE001 — audit xətası imtahanı dayandırmasın
        logger.exception("final device audit yazılmadı: attempt=%s reason=%s", attempt.pk, reason)


def _request_user(request):
    user = getattr(request, "user", None)
    return user if getattr(user, "is_authenticated", False) else None


def _bind_first(attempt, device_id: str):
    """Cəhdin ilk bağlanması — yarışda qalib sətir qaytarılır (``created`` ilə)."""
    try:
        with transaction.atomic():
            binding = FinalAttemptDevice.objects.create(
                attempt_id=attempt.pk,
                organization_id=attempt.exam.organization_id,
                token_hash=_token_hash(attempt.pk, device_id),
            )
    except IntegrityError:
        return FinalAttemptDevice.objects.filter(attempt_id=attempt.pk).first(), False
    return binding, True


def _same_hall_computer(request, attempt) -> bool:
    computer_id = getattr(attempt, "room_computer_id", None)
    if not computer_id:
        return False
    from apps.exams.services.exam_center_gate import resolve_room_computer

    _room, computer = resolve_room_computer(request, attempt.exam.organization)
    return computer is not None and computer.pk == computer_id


def _approval_open(binding, now) -> bool:
    approved_at = binding.change_approved_at
    return approved_at is not None and now - approved_at <= DEVICE_CHANGE_WINDOW


def _rebind(binding, device_id: str, *, consume_approval: bool) -> bool:
    updates = {
        "token_hash": _token_hash(binding.attempt_id, device_id),
        "bound_at": timezone.now(),
        "rebind_count": F("rebind_count") + 1,
    }
    if consume_approval:
        updates.update(change_approved_at=None, change_approved_by=None)
    # Şərtli UPDATE: eyni anda iki cihaz eyni təsdiqi istifadə edə bilməz.
    return bool(
        FinalAttemptDevice.objects.filter(
            pk=binding.pk, token_hash=binding.token_hash, change_approved_at=binding.change_approved_at
        ).update(**updates)
    )


def enforce_final_device(request, attempt) -> None:
    """Cəhd bu cihaza bağlıdırsa (və ya indi bağlandısa) keçir, əks halda ``FinalDeviceMismatch``."""
    if request is None or not device_binding_applies(attempt):
        return
    cookie_id, session_id = _request_device_ids(request)
    derived_id = _session_device_id(request)
    candidates = [value for value in (cookie_id, session_id, derived_id) if value]
    # Public PIN axınından gələn sorğuda aktiv-org konteksti cəhdin təşkilatı ilə üst-üstə
    # düşməyə bilər — oxu/yazı açıq ``attempt_id`` süzgəcli dar bypass-dadır.
    with bypass_rls():
        binding = FinalAttemptDevice.objects.filter(attempt_id=attempt.pk).first()
        if binding is None:
            device_id = candidates[0] if candidates else secrets.token_urlsafe(32)
            binding, created = _bind_first(attempt, device_id)
            if created:
                _remember_device(request, device_id, cookie_id)
                _audit(attempt, action=AuditAction.CREATE, reason="final_device_bound", request=request)
                return
        for candidate in candidates:
            if secrets.compare_digest(_token_hash(attempt.pk, candidate), binding.token_hash):
                _remember_device(request, candidate, cookie_id)
                return
        source = None
        if _same_hall_computer(request, attempt):
            source = SOURCE_HALL_COMPUTER
        elif _approval_open(binding, timezone.now()):
            source = SOURCE_PROCTOR
        if source is not None:
            device_id = candidates[0] if candidates else secrets.token_urlsafe(32)
            if _rebind(binding, device_id, consume_approval=source == SOURCE_PROCTOR):
                _remember_device(request, device_id, cookie_id)
                _audit(
                    attempt,
                    action=AuditAction.UPDATE,
                    reason="final_device_rebound",
                    request=request,
                    changes={"source": source, "rebind_count": binding.rebind_count + 1},
                )
                return
    raise FinalDeviceMismatch(attempt)


def record_device_mismatch(request, attempt) -> None:
    """«Başqa cihaz» rəddinin audit sətri (tranzaksiyadan KƏNARDA; cəhd üzrə dəqiqədə bir)."""
    try:
        first = bool(cache.add(f"final_device_deny:{attempt.pk}", 1, DENY_AUDIT_THROTTLE_SECONDS))
    except Exception:  # noqa: BLE001 — keş yoxdursa audit yazılır
        first = True
    logger.warning("final_device: başqa cihaz rədd edildi attempt=%s path=%s", attempt.pk, request.path)
    if first:
        with bypass_rls():
            _audit(attempt, action=AuditAction.DENY, reason="final_device_mismatch", request=request)


def approve_device_change(attempt, *, by, request=None, source: str = SOURCE_PROCTOR) -> bool:
    """Nəzarətçi təsdiqi: pəncərə ərzində növbəti YENİ cihaz cəhdi özünə köçürür.

    Qaytarır: ``True`` — təsdiq yazıldı; ``False`` — cəhd hələ heç bir cihaza bağlanmayıb
    (ilk açan cihaz onsuz da bağlanacaq — təsdiqə ehtiyac yoxdur).
    """
    now = timezone.now()
    with bypass_rls():
        updated = FinalAttemptDevice.objects.filter(attempt_id=attempt.pk).update(
            change_approved_at=now, change_approved_by=by
        )
        if updated:
            _audit(
                attempt,
                action=AuditAction.UPDATE,
                reason="final_device_change_approved",
                request=request,
                user=by,
                changes={"source": source, "window_minutes": device_window_minutes(), "student_id": attempt.user_id},
            )
    return bool(updated)


def device_change_states(attempt_ids) -> dict[int, bool]:
    """``{attempt_id: təsdiq_pəncərəsi_açıqdır}`` — yalnız cihaza bağlanmış cəhdlər (UI)."""
    now = timezone.now()
    with bypass_rls():
        rows = FinalAttemptDevice.objects.filter(attempt_id__in=list(attempt_ids)).values_list(
            "attempt_id", "change_approved_at"
        )
        return {
            attempt_id: approved_at is not None and now - approved_at <= DEVICE_CHANGE_WINDOW
            for attempt_id, approved_at in rows
        }


__all__ = [
    "DEVICE_CHANGE_WINDOW",
    "DEVICE_COOKIE_NAME",
    "FinalDeviceMismatch",
    "SOURCE_PROCTOR",
    "SOURCE_REENTRY_PIN",
    "approve_device_change",
    "device_binding_applies",
    "device_blocked_message",
    "device_change_states",
    "device_window_minutes",
    "enforce_final_device",
    "issue_device_cookie",
    "record_device_mismatch",
]
