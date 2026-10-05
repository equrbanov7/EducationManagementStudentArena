"""final_center paketi — PIN təhlükəsizliyi.

Hər tələbəyə imtahan üçün fərdi, kriptoqrafik təsadüfi PIN:

* Doğrulama — salted hash (``check_password``, sabit-vaxt müqayisə).
* İcazəli göstərmə — Fernet ilə şifrələnmiş nüsxə (``pin_cipher``);
  oturum bitdikdə silinir.
* Xam PIN heç vaxt log, audit metadata və URL-lərə yazılmır.
"""

import secrets
import threading
import time
from base64 import urlsafe_b64encode
from collections import OrderedDict
from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from cryptography.fernet import Fernet, InvalidToken

from apps.exams.domain.final_center import (
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_READY,
    TICKET_STATUS_WAITING,
)

_PIN_ALPHABET = "0123456789"

# İstifadəçi tapılmayanda da eyni hesablama aparılır ki, cavab müddətindən
# istifadəçi mövcudluğu sızmasın (user enumeration).
_DUMMY_HASH = make_password("final-exam-dummy-pin")


# Tutum testi 2026-10-05: final girişi eyni PIN-i eyni hash-ə qarşı bir neçə dəfə
# yoxlayırdı (fərdi PIN yolu + ``can_user_start``) — hər biri ~1M PBKDF2 iterasiyası.
# Yalnız UĞURLU nəticə 60 s yadda saxlanır; açar saxlanan hash + xam PIN-in HMAC-ıdır,
# ona görə hash dəyişəndə (yeni PIN) memo avtomatik etibarsızdır. Səhv PIN həmişə
# tam hash ilə yoxlanır — brute-force dəyəri dəyişmir.
_VERIFIED_PIN_TTL = 60.0
_VERIFIED_PIN_MAX = 4096
_verified_pins: "OrderedDict[tuple[str, str], float]" = OrderedDict()
_verified_pins_lock = threading.Lock()


def check_pin_hash(raw_pin: str, encoded: str) -> bool:
    """``check_password`` ilə eyni nəticə; təkrar uğurlu yoxlama hash-siz."""
    raw_pin = raw_pin or ""
    if not encoded:
        return check_password(raw_pin, encoded)
    key = (encoded, salted_hmac("exams.pin-verify-memo", raw_pin).hexdigest())
    now = time.monotonic()
    with _verified_pins_lock:
        expires = _verified_pins.get(key)
        if expires is not None and expires > now:
            return True
    matched = check_password(raw_pin, encoded)
    if matched:
        with _verified_pins_lock:
            _verified_pins[key] = now + _VERIFIED_PIN_TTL
            _verified_pins.move_to_end(key)
            while len(_verified_pins) > _VERIFIED_PIN_MAX:
                _verified_pins.popitem(last=False)
    return matched


def _pin_length() -> int:
    return int(getattr(settings, "FINAL_EXAM_PIN_LENGTH", 8))


def _fernet() -> Fernet:
    key = urlsafe_b64encode(sha256(f"final-exam-pin:{settings.SECRET_KEY}".encode()).digest())
    return Fernet(key)


def generate_pin_value() -> str:
    """Kriptoqrafik təsadüfi, ardıcıl olmayan rəqəm PIN-i."""
    return "".join(secrets.choice(_PIN_ALPHABET) for _ in range(_pin_length()))


def _pin_expiry_for(exam):
    """PIN son istifadə vaxtı İMTAHANIN cədvəlindən (oturum sisteminin ləğvi):
    ``exam.end_datetime`` + grace. Cədvəlsiz imtahanda müddət yoxdur (yalnız
    revoke/başlama ilə ləğv olunur)."""
    end = getattr(exam, "end_datetime", None)
    if not end:
        return None
    grace = int(getattr(settings, "FINAL_EXAM_PIN_EXPIRY_GRACE_MINUTES", 120))
    return end + timedelta(minutes=grace)


def set_ticket_pin(ticket, by_user, *, save=True) -> str:
    """
    Biletə yeni PIN yazır (köhnəni avtomatik keçərsizləşdirir) və XAM PIN-i
    qaytarır. Xam dəyər yalnız çağıran tərəfin cavabında istifadə olunmalıdır.
    """
    raw_pin = generate_pin_value()
    ticket.pin_hash = make_password(raw_pin)
    ticket.pin_cipher = _fernet().encrypt(raw_pin.encode()).decode()
    ticket.pin_issued_at = timezone.now()
    ticket.pin_expires_at = _pin_expiry_for(ticket.exam)
    ticket.pin_revoked_at = None
    ticket.pin_failed_attempts = 0
    ticket.pin_locked_until = None
    ticket.pin_generated_by = by_user
    if save:
        ticket.save(
            update_fields=[
                "pin_hash",
                "pin_cipher",
                "pin_issued_at",
                "pin_expires_at",
                "pin_revoked_at",
                "pin_failed_attempts",
                "pin_locked_until",
                "pin_generated_by",
                "updated_at",
            ]
        )
    return raw_pin


def revoke_ticket_pin(ticket, *, save=True) -> None:
    ticket.pin_revoked_at = timezone.now()
    ticket.pin_cipher = ""
    if save:
        ticket.save(update_fields=["pin_revoked_at", "pin_cipher", "updated_at"])


def wipe_ticket_pin_cipher(ticket, *, save=True) -> None:
    """Oturum bitdikdə şifrəli nüsxəni silir (hash qalır — tarixi doğrulama yox)."""
    if not ticket.pin_cipher:
        return
    ticket.pin_cipher = ""
    if save:
        ticket.save(update_fields=["pin_cipher", "updated_at"])


def decrypt_ticket_pin(ticket) -> str | None:
    """İcazəli göstərmə üçün PIN-in açılması. Yalnız view qatı icazəni yoxladıqdan sonra."""
    if not ticket.pin_cipher or not ticket.has_valid_pin:
        return None
    try:
        return _fernet().decrypt(ticket.pin_cipher.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def student_visible_pin(ticket) -> str | None:
    """
    Tələbə panelində PIN-in görünmə qaydası (oturum sisteminin ləğvindən sonra
    İMTAHANIN cədvəlinə əsaslanır — bilet zala yalnız giriş anında qoşulur):

    * yalnız biletin öz sahibi üçün (view qatı yoxlayır);
    * bilet hələ yekun statusda deyilsə;
    * görünmə pəncərəsi daxilində — imtahanın başlanğıcından N dəqiqə əvvəl.
    """
    if not ticket.has_valid_pin:
        return None
    if ticket.status not in (TICKET_STATUS_ASSIGNED, TICKET_STATUS_WAITING, TICKET_STATUS_READY):
        return None
    visibility_minutes = int(getattr(settings, "FINAL_EXAM_PIN_VISIBILITY_MINUTES", 120))
    start = getattr(ticket.exam, "start_datetime", None)
    if visibility_minutes > 0 and start:
        opens_at = start - timedelta(minutes=visibility_minutes)
        if timezone.now() < opens_at:
            return None
    return decrypt_ticket_pin(ticket)


def verify_ticket_pin(ticket, raw_pin: str) -> bool:
    """
    PIN doğrulaması + uğursuz cəhd sayğacı / müvəqqəti kilid.

    Sabit-vaxt müqayisə ``check_password`` daxilindədir. Kilidli və ya
    keçərsiz PIN-li biletdə də hash yoxlaması aparılır ki, cavab vaxtı
    fərqlənməsin.
    """
    now = timezone.now()
    usable = ticket.has_valid_pin and not ticket.is_pin_locked
    matched = check_pin_hash(raw_pin, ticket.pin_hash or _DUMMY_HASH)

    if usable and matched:
        if ticket.pin_failed_attempts or ticket.pin_locked_until:
            ticket.pin_failed_attempts = 0
            ticket.pin_locked_until = None
            ticket.save(update_fields=["pin_failed_attempts", "pin_locked_until", "updated_at"])
        return True

    # 2026-10-03: «Sistem tənzimləmələri» (RİM rəhbəri) dəyəri varsa o, yoxdursa mühitin ayarı.
    from core import runtime_settings

    max_failures = int(
        runtime_settings.override("exam.pin_max_failures") or getattr(settings, "FINAL_EXAM_PIN_MAX_FAILURES", 5)
    )
    lock_minutes = int(
        runtime_settings.override("exam.pin_lock_minutes") or getattr(settings, "FINAL_EXAM_PIN_LOCK_MINUTES", 10)
    )
    # Atomic increment (F()) so parallel wrong-PIN attempts cannot lose counts
    # and slip past the lockout threshold under a race (EXAM-SEC-003).  Re-read
    # the persisted value before deciding whether to arm the lockout window, and
    # arm it with a conditional UPDATE so only one racing request sets it.
    type(ticket).objects.filter(pk=ticket.pk).update(pin_failed_attempts=F("pin_failed_attempts") + 1, updated_at=now)
    ticket.refresh_from_db(fields=["pin_failed_attempts", "pin_locked_until"])
    if ticket.pin_failed_attempts >= max_failures and not ticket.is_pin_locked:
        locked_until = now + timedelta(minutes=lock_minutes)
        type(ticket).objects.filter(pk=ticket.pk, pin_locked_until__isnull=True).update(pin_locked_until=locked_until)
        ticket.pin_locked_until = locked_until
    return False


def equalize_verification_timing(raw_pin: str) -> None:
    """Bilet tapılmayanda çağırılır — user enumeration-a qarşı vaxt bərabərləşdirmə."""
    check_password(raw_pin or "", _DUMMY_HASH)


__all__ = [
    "check_pin_hash",
    "decrypt_ticket_pin",
    "equalize_verification_timing",
    "generate_pin_value",
    "revoke_ticket_pin",
    "set_ticket_pin",
    "student_visible_pin",
    "verify_ticket_pin",
    "wipe_ticket_pin_cipher",
]
