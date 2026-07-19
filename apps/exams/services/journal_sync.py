"""İmtahan mərkəzi → elektron jurnal sinxronizasiyası (exams tərəf).

Registrar ``public`` fasadına (``apps.registrar.public``) LAZY çağırışlarla
körpü qurur — modul-səviyyə asılılığı yaratmır, RLS/tenant konteksti aktiv
request-dən miras alınır. Bütün yazılar BEST-EFFORT-dur: jurnal körpüsü heç
vaxt imtahan axınını sındırmır (registrar tərəf yoxdursa/xəta olarsa sükutla
keçir, loglanır).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _attempt_percent(attempt):
    """İmtahan cəhdinin normallaşdırılmış faizi (0–100) — test və ya yazılı.

    Yazılı imtahan hələ yoxlanmayıbsa ``None`` (körpü gözləyir; manual-grading
    bitəndə yenidən çağırılır)."""
    exam = attempt.exam
    if getattr(exam, "exam_type", None) == "test":
        try:
            return float(attempt.score_percent)
        except Exception:
            return None
    teacher_score = getattr(attempt, "teacher_score", None)
    if teacher_score is None:
        return None
    try:
        max_score = sum(q.points for q in exam.questions.all()) or 0
    except Exception:
        max_score = 0
    if not max_score:
        return None
    return round(float(teacher_score) * 100.0 / float(max_score), 1)


def sync_attempt_to_journal(attempt, *, request=None):
    """Bitmiş imtahan cəhdinin nəticəsini registrar ``FinalGrade``-ə yaz.

    İmtahan bir jurnal fənninə bağlı deyilsə (``exam.subject`` null) no-op.
    Proctordan qovulan (``supervision_status == "removed"``) → 0 = avtomatik F.
    """
    exam = getattr(attempt, "exam", None)
    subject_id = getattr(exam, "subject_id", None)
    if not exam or not subject_id:
        return None
    organization = getattr(exam, "organization", None)
    if organization is None:
        return None

    is_expelled = getattr(attempt, "supervision_status", "") == "removed"
    percent = 0 if is_expelled else _attempt_percent(attempt)
    if percent is None:
        return None  # yazılı imtahan hələ yoxlanılmayıb

    by_user = getattr(request, "user", None) or getattr(attempt, "user", None)
    try:
        from apps.registrar.public import record_exam_result

        return record_exam_result(
            student=attempt.user,
            subject_id=subject_id,
            organization=organization,
            score_percent=percent,
            is_expelled=is_expelled,
            by_user=by_user,
        )
    except Exception:  # körpü heç vaxt imtahanı sındırmır
        logger.exception("journal_sync: failed to write attempt %s to FinalGrade", getattr(attempt, "id", "?"))
        return None


def registrar_block_reason(request, exam):
    """Tələbə bu fənn üzrə qayıba görə imtahandan kəsilibsə səbəb mətni, yoxsa ``None``.

    İmtahan jurnal fənninə bağlı deyilsə həmişə ``None`` (qapı tətbiq olunmur).
    """
    subject_id = getattr(exam, "subject_id", None)
    organization = getattr(exam, "organization", None)
    user = getattr(request, "user", None)
    if not subject_id or organization is None or user is None or not user.is_authenticated:
        return None
    try:
        from apps.registrar.public import exam_eligibility

        elig = exam_eligibility(student=user, subject_id=subject_id, organization=organization)
    except Exception:
        logger.exception("journal_sync: eligibility check failed for exam %s", getattr(exam, "id", "?"))
        return None
    return elig.get("reason") if elig.get("barred") else None
