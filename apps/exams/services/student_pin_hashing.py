"""Fərdi imtahan PIN-lərinin hash-i — request-dən kənarda (tutum testi 2026-10-06).

Problem: qrup final/midterm imtahanına təyin olunanda ``provision_exam_student_pins``
hər tələbə üçün request daxilində ``make_password`` (PBKDF2, ~0.1 s) çağırırdı —
300 tələbə ≈ 30 s → müəllimin sorğusu timeout.

Həll («şifrə əvvəl, hash sonra»):

* provizion sətri yalnız Fernet şifrəli nüsxə ilə dərhal yaradır, ``pin_hash`` boş
  qalır (``PIN_HASH_PENDING`` — «hash hazırlanır»). Şifrələmə mikrosaniyələrdir,
  ona görə PIN kabinetdə/imtahan mərkəzində DƏRHAL görünür;
* commit-dən sonra ``exams.hash_pending_student_pins`` Celery task-ı (``heavy``
  növbə) hash-ləri hissə-hissə, imtahanın təşkilatının RLS kontekstində yazır;
* worker gecikərsə/düşərsə giriş yenə işləyir: ilk yoxlama HƏMİN tək sətrin
  şifrəsini sabit-vaxt müqayisə edib hash-ini yerində yazır (düz bir hash) —
  sonrakı bütün yoxlamalar adi hash yoludur. Hasher/iterasiya dəyişmir.
"""

import logging

from django.contrib.auth.hashers import make_password
from django.db import connection, transaction
from django.utils import timezone

from cryptography.fernet import InvalidToken

from apps.exams.models import ExamStudentPin
from apps.exams.services.final_center.pins import (
    _fernet,
    check_pin_hash,
    equalize_verification_timing,
    generate_pin_value,
    pin_cipher_matches,
    remember_verified_pin,
)
from core.rls import bypass_rls

logger = logging.getLogger("exams.student_pin.hashing")

#: ``pin_hash`` bu dəyərdədirsə sətrin hash-i hələ worker-də hazırlanır.
PIN_HASH_PENDING = ""

#: Bir tranzaksiyada hash olunan sətir sayı — sətir kilidi ~1 s-dən çox tutulmur.
HASH_CHUNK_SIZE = 10

_TASK_MARKER = "exams.hash_pending_student_pins"


def has_pending_student_pin_hashes(exam) -> bool:
    return ExamStudentPin.objects.filter(exam=exam, pin_hash=PIN_HASH_PENDING).exclude(pin_cipher="").exists()


def _already_scheduled(marker) -> bool:
    """Bu tranzaksiyada hələ işə düşməmiş eyni callback varmı (commit-də hamısını görəcək)."""
    if not connection.in_atomic_block:
        return False
    return any(
        getattr(entry[1], "ems_marker", None) == marker and not getattr(entry[1], "ems_fired", False)
        for entry in connection.run_on_commit
    )


def schedule_student_pin_hashing(exam) -> None:
    """Commit-dən sonra hash task-ını növbəyə qoy — eyni tranzaksiyada imtahan başına BİR dəfə.

    İmtahan formu bir saxlanışda 3–5 m2m siqnalı + açıq provizion çağırışı edir;
    marker hamısını bir task-a endirir. Növbə əlçatan olmasa sətirlər gözləmədə
    qalır və ilk girişdə tək-tək hash olunur (request-də toplu hash YOX).
    """
    marker = (_TASK_MARKER, exam.pk)
    if _already_scheduled(marker):
        return
    exam_id, organization_id = exam.pk, exam.organization_id

    def _enqueue():
        from apps.exams.tasks import hash_pending_student_pins as hash_task

        _enqueue.ems_fired = True
        try:
            hash_task.delay(exam_id, organization_id)
        except Exception:
            logger.warning(
                "student PIN hash task növbəyə qoyulmadı (exam=%s) — PIN-lər ilk girişdə tək-tək hash olunacaq",
                exam_id,
                exc_info=True,
            )

    _enqueue.ems_marker = marker
    transaction.on_commit(_enqueue)


def hash_pending_student_pins(exam_id, *, scope=None, chunk_size: int = HASH_CHUNK_SIZE) -> int:
    """İmtahanın hash gözləyən fərdi PIN-lərinin hash-ini yaz (idempotent). Qaytarır: yazılan say.

    * ``scope`` — hər hissənin DB konteksti (tranzaksiya + tenant); default ``transaction.atomic``.
    * Hissə ``FOR UPDATE SKIP LOCKED`` ilə götürülür: paralel iki task eyni sətri iki
      dəfə hash etmir; yazı şərtlidir (hash hələ boş + şifrə dəyişməyib).
    * Hash CPU işi kilid daxilində qısa hissələrlə gedir (``HASH_CHUNK_SIZE``).
    * Şifrəsi oxunmayan gözləmə sətri (açar dəyişib) — PIN heç kimə görünmür; təzə PIN verilir.
    """
    scope = scope or transaction.atomic
    fernet = _fernet()
    hashed = 0
    last_pk = 0
    while True:
        with scope():
            rows = list(
                ExamStudentPin.objects.select_for_update(skip_locked=True)
                .filter(exam_id=exam_id, pin_hash=PIN_HASH_PENDING, pk__gt=last_pk)
                .exclude(pin_cipher="")
                .order_by("pk")
                .values_list("pk", "pin_cipher")[:chunk_size]
            )
            if not rows:
                return hashed
            for pk, cipher in rows:
                last_pk = pk
                try:
                    raw_pin, new_cipher = fernet.decrypt(cipher.encode()).decode(), cipher
                except (InvalidToken, ValueError):
                    raw_pin = generate_pin_value()
                    new_cipher = fernet.encrypt(raw_pin.encode()).decode()
                hashed += ExamStudentPin.objects.filter(pk=pk, pin_hash=PIN_HASH_PENDING, pin_cipher=cipher).update(
                    pin_hash=make_password(raw_pin), pin_cipher=new_cipher, updated_at=timezone.now()
                )


def verify_pending_student_pin(pin, raw_pin: str) -> bool:
    """Hash-i hələ hazır olmayan sətrin yoxlanması — düz BİR tam hash.

    Şifrəli nüsxə ilə sabit-vaxt müqayisə; uyğundursa həmin PIN-in hash-i elə burada
    yazılır (sonrakı yoxlamalar adi hash yolu, təkrar isə memo-dan). Uyğun deyilsə
    vaxt bərabərləşdirmə hash-i. Yarışda (worker/yeni PIN arada yazılıb) saxlanan
    hash hakimdir.
    """
    if not pin_cipher_matches(pin.pin_cipher, raw_pin):
        equalize_verification_timing(raw_pin)
        return False
    encoded = make_password(raw_pin)
    # Credential artıq bu sətrə bağlanıb (pk); public girişdə tenant konteksti yoxdur.
    with bypass_rls():
        sealed = ExamStudentPin.objects.filter(pk=pin.pk, pin_hash=PIN_HASH_PENDING, pin_cipher=pin.pin_cipher).update(
            pin_hash=encoded, updated_at=timezone.now()
        )
        current = "" if sealed else ExamStudentPin.objects.filter(pk=pin.pk).values_list("pin_hash", flat=True).first()
    if sealed:
        pin.pin_hash = encoded
        remember_verified_pin(raw_pin, encoded)
        return True
    return bool(current) and check_pin_hash(raw_pin, current)


__all__ = [
    "HASH_CHUNK_SIZE",
    "PIN_HASH_PENDING",
    "has_pending_student_pin_hashes",
    "hash_pending_student_pins",
    "schedule_student_pin_hashing",
    "verify_pending_student_pin",
]
