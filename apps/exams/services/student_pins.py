"""Final/midterm imtahanlarında hər tələbənin fərdi PIN-i.

İmtahan yaradılanda/redaktə olunanda təyin olunmuş hər tələbəyə unikal PIN
verilir. PIN tələbə kabinetində DƏRHAL görünür (imtahan mərkəzindəki
bilet-PIN sistemindən fərqli olaraq zaman-pəncərəsi yoxdur) və imtahana giriş
zamanı doğrulanır. Kriptoqrafik primitivlər (salted hash + Fernet) mövcud
``final_center/pins.py``-dən təkrar istifadə olunur.
"""

import logging

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache

from cryptography.fernet import InvalidToken

from apps.exams.models import ExamStudentPin
from apps.exams.services.final_center.pins import _DUMMY_HASH, _fernet, generate_pin_value

logger = logging.getLogger("exams.student_pin.entry")

# Fərdi PIN tələb edən imtahan kateqoriyaları.
SECURE_PIN_CATEGORIES = {"final", "midterm"}


def _student_pin_rate_key(username: str) -> str:
    return f"finpin:rl:{(username or '').strip().lower()[:150]}"


def student_pin_login_rate_limited(username: str) -> bool:
    """Per-username (freeze-safe) sliding-window throttle for the ExamStudentPin
    login path (EXAM-SEC-002).

    Keyed ONLY on the submitted username — never on the client IP — so a shared
    exam-hall / localhost IP cannot freeze other students, and one student's
    failed attempts only slow that same student.  The window self-heals every
    ``FINAL_EXAM_STUDENT_PIN_RATE_WINDOW_SECONDS`` (default 60s), throttling
    brute force without a durable account lockout (which would be DoS-able).
    ``FINAL_EXAM_STUDENT_PIN_RATE_PER_MINUTE`` <= 0 disables the throttle.
    """
    limit = int(getattr(settings, "FINAL_EXAM_STUDENT_PIN_RATE_PER_MINUTE", 10))
    username = (username or "").strip()
    if limit <= 0 or not username:
        return False
    window = int(getattr(settings, "FINAL_EXAM_STUDENT_PIN_RATE_WINDOW_SECONDS", 60))
    key = _student_pin_rate_key(username)
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:  # açar TTL-i incr anında bitibsə
        cache.set(key, 1, window)
        count = 1
    return count > limit


def exam_requires_student_pins(exam) -> bool:
    return getattr(exam, "exam_type_extended", None) in SECURE_PIN_CATEGORIES


def _assigned_student_ids(exam) -> set[int]:
    # İmtahana təyin olunmuş bütün tələbələr (fərdi + qrup + kurs üzvləri).
    from apps.notifications.public import get_exam_assigned_user_ids

    return set(get_exam_assigned_user_ids(exam))


def provision_exam_student_pins(exam) -> None:
    """Təyin olunmuş hər tələbəyə PIN təmin et (idempotent).

    * final/midterm deyilsə → mövcud PIN-ləri təmizlə (kateqoriya dəyişibsə);
    * hər yeni tələbə üçün PIN yarat;
    * artıq təyin olunmayan tələbələrin PIN-lərini sil.
    """
    if not exam_requires_student_pins(exam):
        ExamStudentPin.objects.filter(exam=exam).delete()
        return

    assigned_ids = _assigned_student_ids(exam)
    existing_ids = set(ExamStudentPin.objects.filter(exam=exam).values_list("student_id", flat=True))

    to_create = assigned_ids - existing_ids
    if to_create:
        fernet = _fernet()
        new_pins = []
        for student_id in to_create:
            raw_pin = generate_pin_value()
            new_pins.append(
                ExamStudentPin(
                    exam=exam,
                    student_id=student_id,
                    pin_hash=make_password(raw_pin),
                    pin_cipher=fernet.encrypt(raw_pin.encode()).decode(),
                )
            )
        ExamStudentPin.objects.bulk_create(new_pins, ignore_conflicts=True)

    stale_ids = existing_ids - assigned_ids
    if stale_ids:
        ExamStudentPin.objects.filter(exam=exam, student_id__in=stale_ids).delete()


def student_visible_pin(exam, user) -> str | None:
    """Tələbənin öz PIN-i (kabinetdə göstərmək üçün). İcazə view qatında yoxlanır."""
    if user is None or not getattr(user, "id", None):
        return None
    pin = ExamStudentPin.objects.filter(exam=exam, student=user).only("pin_cipher").first()
    if pin is None or not pin.pin_cipher:
        return None
    try:
        return _fernet().decrypt(pin.pin_cipher.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def verify_student_pin(exam, user, raw_pin: str) -> bool:
    """İmtahana giriş üçün PIN doğrulaması (sabit-vaxt müqayisə).

    EXAM-P1-08: revoke olunmuş və ya vaxtı keçmiş PIN doğrulanmır — lakin
    sabit-vaxt davranışını qorumaq üçün müqayisə həmişə icra olunur.
    """
    pin = None
    if user is not None and getattr(user, "id", None):
        pin = (
            ExamStudentPin.objects.filter(exam=exam, student=user).only("pin_hash", "expires_at", "revoked_at").first()
        )
    stored = pin.pin_hash if pin else _DUMMY_HASH
    matched = check_password(raw_pin or "", stored)
    ok = bool(pin) and pin.is_usable() and matched
    # EXAM-P1-20: PIN giriş nəticəsini SLI kimi qeyd et.
    from apps.exams.metrics import record_pin_attempt

    record_pin_attempt("success" if ok else "failure")
    return ok


def resolve_student_pin_login(username: str, raw_pin: str):
    """`/exams/final/` girişi: istifadəçi adı + fərdi PIN → (exam, user).

    Bilet (otaq-oturum) sistemi TƏLƏB OLUNMUR — imtahan yaradılanda təyin
    olunmuş ``ExamStudentPin`` ilə uyğun aktiv final imtahanını və tələbəni
    qaytarır. Uyğunluq yoxdursa ``(None, None)``. İcazə/vaxt yoxlaması çağıran
    tərəfdə (``can_user_start``) aparılır.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    user_model = get_user_model()
    username = (username or "").strip()
    raw_pin = (raw_pin or "").strip()
    if not username or not raw_pin:
        return None, None

    user = user_model.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
    if user is None or not getattr(user, "is_active", False):
        return None, None

    pins = ExamStudentPin.objects.filter(
        student=user,
        exam__is_active=True,
        exam__exam_type_extended="final",
    ).select_related("exam", "exam__organization")
    for pin in pins:
        # EXAM-P1-08: revoke/expiry olunmuş PIN girişi keçirməməlidir.
        if pin.is_usable() and check_password(raw_pin, pin.pin_hash or ""):
            return pin.exam, user
    return None, None
