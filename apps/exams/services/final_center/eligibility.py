"""final_center paketi — qayıb limiti buraxılış qapısı (Audit 2026-09-28 EXA-04).

Qapı əvvəl YALNIZ kabinetdəki ``start_exam`` yolunda idi
(``views/student/attempts.py``). Zal bileti (``begin_attempt_for_ticket``),
fərdi PIN girişi (``/exams/final/``) və kod yolu (``exam_code_check``) onu
keçirdi — qayıb limitini aşmış tələbə finalda zalda otura bilirdi
(``compute_final_result`` sonradan kəssə də, buraxılış qaydası qapıda tətbiq
olunmurdu). Üstəlik mövcud köməkçi (``journal_sync.registrar_block_reason``)
registrar xətasında ``None`` qaytarır — yəni «buraxılır» (fail-open).

Bu köməkçi FAIL-CLOSED-dur: registrar yoxlaması istisna atsa log yazılır və
start RƏDD olunur (aydın mesajla). Yalnız YENİ cəhd yoxlanır — artıq aktiv
cəhdi olan tələbə (kompüter dəyişməsi, texniki fasilə) imtahanın ortasında
kənarlaşdırılmır.
"""

import logging

from django.utils.translation import pgettext

logger = logging.getLogger("exams.final_center")


def _check_failed_message():
    return pgettext(
        "exams.final_center.error",
        "İmtahana buraxılış yoxlanıla bilmədi — nəzarətçiyə və ya imtahan mərkəzinə müraciət edin.",
    )


def _barred_fallback_message():
    return pgettext(
        "exams.final_center.error",
        "Qayıb limiti keçildiyi üçün bu imtahana buraxılmırsınız.",
    )


def admission_block_reason(student, exam):
    """Tələbə bu imtahana (YENİ cəhd) buraxılmırsa səbəb mətni, yoxsa ``None``.

    İmtahan jurnal fənninə bağlı deyilsə qapı tətbiq olunmur (``None``).
    Registrar yoxlaması sınarsa → səbəb mətni (fail-closed)."""
    subject_id = getattr(exam, "subject_id", None)
    organization = getattr(exam, "organization", None)
    if not subject_id or organization is None or student is None:
        return None
    try:
        if exam._user_has_active_attempt(student):
            return None  # davam edən cəhd — imtahanın ortasında kəsilmir
        from apps.registrar.public import exam_eligibility

        eligibility = exam_eligibility(student=student, subject_id=subject_id, organization=organization)
    except Exception:  # noqa: BLE001 — fail-closed: xəta = buraxılmır
        logger.exception(
            "final_center: admission check failed for exam %s student %s — start denied",
            getattr(exam, "id", "?"),
            getattr(student, "id", "?"),
        )
        return _check_failed_message()
    if eligibility.get("barred"):
        return eligibility.get("reason") or _barred_fallback_message()
    return None


__all__ = ["admission_block_reason"]
