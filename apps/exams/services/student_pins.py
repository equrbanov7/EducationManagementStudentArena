"""Final/midterm imtahanlarında hər tələbənin fərdi PIN-i.

İmtahan yaradılanda/redaktə olunanda təyin olunmuş hər tələbəyə unikal PIN
verilir. PIN tələbə kabinetində DƏRHAL görünür (imtahan mərkəzindəki
bilet-PIN sistemindən fərqli olaraq zaman-pəncərəsi yoxdur) və imtahana giriş
zamanı doğrulanır. Kriptoqrafik primitivlər (salted hash + Fernet) mövcud
``final_center/pins.py``-dən təkrar istifadə olunur.
"""

import logging

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from cryptography.fernet import InvalidToken

from apps.exams.models import ExamStudentPin
from apps.exams.services.final_center.pins import (
    _DUMMY_HASH,
    PinHashBudget,
    _fernet,
    check_pin_hash,
    final_entry_login_allowed,
    generate_pin_value,
    pin_cipher_matches,
)
from apps.exams.services.student_pin_hashing import (
    PIN_HASH_PENDING,
    has_pending_student_pin_hashes,
    schedule_student_pin_hashing,
    verify_pending_student_pin,
)
from core.rls import bypass_rls

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


def provision_exam_student_pins(exam) -> int:
    """Təyin olunmuş hər tələbəyə PIN təmin et (idempotent).

    * final/midterm deyilsə → mövcud PIN-ləri təmizlə (kateqoriya dəyişibsə);
    * hər yeni tələbə üçün PIN yarat;
    * artıq təyin olunmayan tələbələrin PIN-lərini sil.

    Tutum testi 2026-10-06: request daxilində ARTIQ hash hesablanmır (300 tələbə ×
    ~0.1 s PBKDF2 ≈ 30 s → timeout). Sətir yalnız şifrəli nüsxə ilə yaranır
    (``pin_hash`` boş = «hash hazırlanır»; PIN dərhal görünür), hash-lər commit-dən
    sonra Celery-də yazılır — bax ``student_pin_hashing``. Qaytarır: hash
    gözləyən yeni/yenilənmiş sətir sayı.
    """
    if not exam_requires_student_pins(exam):
        ExamStudentPin.objects.filter(exam=exam).delete()
        return 0

    assigned_ids = _assigned_student_ids(exam)
    existing_ids = set(ExamStudentPin.objects.filter(exam=exam).values_list("student_id", flat=True))
    fernet = _fernet()
    pending = 0

    to_create = assigned_ids - existing_ids
    if to_create:
        new_pins = [
            ExamStudentPin(
                exam=exam,
                student_id=student_id,
                pin_hash=PIN_HASH_PENDING,
                pin_cipher=fernet.encrypt(generate_pin_value().encode()).decode(),
            )
            for student_id in to_create
        ]
        ExamStudentPin.objects.bulk_create(new_pins, ignore_conflicts=True)
        pending += len(new_pins)

    # 2026-07: boş şifrəli / köhnə-revoke olunmuş PIN-ləri BƏRPA et. Əvvəllər
    # imtahan başlayanda ExamStudentPin ləğv olunurdu (pin_cipher=""); indi
    # revoke edilmir, ona görə köhnə imtahanların boş PIN-ləri təzələnir ki,
    # tələbə kabinetdə PIN-ini yenidən görsün (təyin olunmuş tələbələr üçün).
    stale_cipher = list(
        ExamStudentPin.objects.filter(exam=exam, student_id__in=assigned_ids).filter(
            Q(pin_cipher="") | Q(revoked_at__isnull=False)
        )
    )
    if stale_cipher:
        now = timezone.now()
        for pin in stale_cipher:
            pin.pin_hash = PIN_HASH_PENDING
            pin.pin_cipher = fernet.encrypt(generate_pin_value().encode()).decode()
            pin.revoked_at = None
            pin.expires_at = None
            pin.updated_at = now
        ExamStudentPin.objects.bulk_update(
            stale_cipher, ["pin_hash", "pin_cipher", "revoked_at", "expires_at", "updated_at"]
        )
        pending += len(stale_cipher)

    stale_ids = existing_ids - assigned_ids
    if stale_ids:
        ExamStudentPin.objects.filter(exam=exam, student_id__in=stale_ids).delete()

    # Əvvəlki növbə itkisi (broker düşüb) də burada özünü sağaldır.
    if pending or has_pending_student_pin_hashes(exam):
        schedule_student_pin_hashing(exam)
    return pending


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


def verify_student_pin_row(pin, raw_pin: str) -> bool:
    """Bir ``ExamStudentPin`` sətrinin hash yoxlaması — ən çox BİR tam hash (uğurlu təkrar memo-dan).

    Hash hələ worker-də hazırlanırsa (``PIN_HASH_PENDING``) şifrəli nüsxə ilə
    yoxlanıb həmin sətrin hash-i yerində yazılır — yenə düz bir hash.
    """
    if pin.pin_hash:
        return check_pin_hash(raw_pin, pin.pin_hash)
    return verify_pending_student_pin(pin, raw_pin)


def verify_student_pin(exam, user, raw_pin: str) -> bool:
    """İmtahana giriş üçün PIN doğrulaması (sabit-vaxt müqayisə).

    EXAM-P1-08: revoke olunmuş və ya vaxtı keçmiş PIN doğrulanmır — lakin
    sabit-vaxt davranışını qorumaq üçün müqayisə həmişə icra olunur.
    """
    pin = None
    if user is not None and getattr(user, "id", None):
        pin = (
            ExamStudentPin.objects.filter(exam=exam, student=user)
            .only("pin_hash", "pin_cipher", "expires_at", "revoked_at")
            .first()
        )
    matched = verify_student_pin_row(pin, raw_pin) if pin else check_pin_hash(raw_pin, _DUMMY_HASH)
    ok = bool(pin) and pin.is_usable() and matched
    # EXAM-P1-20: PIN giriş nəticəsini SLI kimi qeyd et.
    from apps.exams.metrics import record_pin_attempt

    record_pin_attempt("success" if ok else "failure")
    return ok


def reissue_student_pin(exam, student) -> bool:
    """Tələbəyə bu imtahan üçün TƏZƏ fərdi PIN ver (ikinci şans axını).

    İmtahan başlayanda köhnə PIN birdəfəlik ləğv olunur (``revoke_student_pin``)
    — yenidən şans veriləndə tələbənin yeni etibarlı PIN-i olmalıdır. Mövcud
    sətir yenilənir (revoked/expired sıfırlanır), yoxdursa yaradılır.
    """
    if not exam_requires_student_pins(exam):
        return False
    raw_pin = generate_pin_value()
    ExamStudentPin.objects.update_or_create(
        exam=exam,
        student=student,
        defaults={
            "pin_hash": make_password(raw_pin),
            "pin_cipher": _fernet().encrypt(raw_pin.encode()).decode(),
            "revoked_at": None,
            "expires_at": None,
        },
    )
    return True


def revoke_student_pin(exam, user) -> bool:
    """İmtahan başlayanda ilkin fərdi PIN-i birdəfəlik ləğv et."""
    if user is None or not getattr(user, "id", None):
        return False
    return bool(
        ExamStudentPin.objects.filter(exam=exam, student=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now(),
            pin_cipher="",
        )
    )


def _pin_candidates_by_cipher(pins, raw_pin: str):
    """Namizədləri hash-SİZ ayır: (hash-lə yoxlanacaqlar, şifrəsi uyğun gəlməyənlər).

    Birinci siyahı: şifrəli nüsxəsi yazılan PIN-ə uyğun olanlar, sonra şifrəsi
    oxunmayanlar (köhnə/silinmiş şifrə — hash yeganə yoldur). Hər qrupda hazırda
    başlana bilən (vaxt pəncərəsi daxilindəki) imtahan öndədir.
    """
    matched, unknown, rest = [], [], []
    for pin in pins:
        hint = pin_cipher_matches(pin.pin_cipher, raw_pin)
        (matched if hint else unknown if hint is None else rest).append(pin)

    def _startable_first(pin):
        return not pin.exam.is_currently_active()

    return sorted(matched, key=_startable_first) + sorted(unknown, key=_startable_first), sorted(
        rest, key=_startable_first
    )


def resolve_student_pin_login(username: str, raw_pin: str, *, budget=None):
    """`/exams/final/` girişi: istifadəçi adı + fərdi PIN → (exam, user).

    Bilet (otaq-oturum) sistemi TƏLƏB OLUNMUR — imtahan yaradılanda təyin
    olunmuş ``ExamStudentPin`` ilə uyğun aktiv final imtahanını və tələbəni
    qaytarır. Uyğunluq yoxdursa ``(None, None)``. İcazə/vaxt yoxlaması çağıran
    tərəfdə (``can_user_start``) aparılır.

    Tutum testi 2026-10-06: əvvəl tələbənin HƏR aktiv final PIN-i tam PBKDF2 ilə
    yoxlanırdı (N final → N hash), istifadəçi tapılmayanda isə heç biri — vaxt
    fərqi PIN mövcudluğunu sızdırırdı. İndi namizəd şifrəli nüsxə ilə hash-siz
    seçilir və hər sonluq (uğur / səhv PIN / PIN-siz / naməlum istifadəçi) düz
    BİR tam hash edir. ``budget`` (``PinHashBudget``) bilet yolu ilə paylaşılır.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    if budget is None:
        budget = PinHashBudget()
    user_model = get_user_model()
    username = (username or "").strip()
    raw_pin = (raw_pin or "").strip()
    if not username or not raw_pin:
        budget.equalize(raw_pin)
        return None, None

    user = user_model.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
    # Auditi 2026-10-07 AUTH-03: ``is_active`` + ``access_state`` (arxiv hesabda is_active True qalır).
    if not final_entry_login_allowed(user):
        budget.equalize(raw_pin)
        return None, None

    # Public girişdə tələbə hələ autentifikasiya/tenant seçimi etməyib, buna
    # görə RLS normal olaraq bütün ExamStudentPin sətirlərini gizlədir. Bypass
    # yalnız username ilə tapılmış istifadəçinin aktiv final PIN-lərini
    # materializasiya edir; xam PIN müqayisəsi və nəticə bypass-dan kənardadır.
    with bypass_rls():
        pins = list(
            ExamStudentPin.objects.filter(
                student=user,
                exam__is_active=True,
                exam__exam_type_extended="final",
            )
            .select_related("exam", "exam__organization")
            .order_by("pk")
        )
    # EXAM-P1-08: revoke/expiry olunmuş PIN girişi keçirməməlidir.
    now = timezone.now()
    to_verify, mismatched = _pin_candidates_by_cipher([p for p in pins if p.is_usable(now=now)], raw_pin)
    for pin in to_verify:
        budget.charge()
        if verify_student_pin_row(pin, raw_pin):
            return pin.exam, user
    if not budget.spent and mismatched:
        # Şifrə heç birinə uyğun deyil — bərabərləşdirmə hash-ini boşa yandırmaq
        # əvəzinə ən uyğun namizədin hash-ini yoxla (hash yenə hakimdir).
        budget.charge()
        if verify_student_pin_row(mismatched[0], raw_pin):
            return mismatched[0].exam, user
    budget.equalize(raw_pin)
    return None, None
