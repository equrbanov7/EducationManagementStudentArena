"""İmtahan mərkəzi → elektron jurnal sinxronizasiyası (exams tərəf).

Registrar ``public`` fasadına (``apps.registrar.public``) LAZY çağırışlarla
körpü qurur — modul-səviyyə asılılığı yaratmır, RLS/tenant konteksti aktiv
request-dən miras alınır. Bütün yazılar BEST-EFFORT-dur: jurnal körpüsü heç
vaxt imtahan axınını sındırmır (registrar tərəf yoxdursa/xəta olarsa sükutla
keçir, loglanır).

AKTOR QAYDASI (2026-08 auditi, G7): jurnala yazan ``by_user`` HEÇ VAXT imtahan
verən tələbənin özü ola bilməz. Əvvəl `request.user or attempt.user` yazılırdı
və heç bir çağıran `request` ötürmədiyi üçün rəsmi qiymət «tələbənin öz adına»
düşürdü. İndi:

* əl ilə yoxlanan yazılı imtahan → aktor YOXLAYAN MÜƏLLİM (``grader`` / ``graded_by``);
* avtomatik qiymətlənən test və proctor qovulması → aktor SİSTEM (``None``),
  audit izində «avtomatik» qeydi ilə (``FinalGrade.entered_by`` NULL-a icazə
  verir və PG ``registrar_guard_same_org_actor`` triggeri NULL-u buraxır).

İDEMPOTENTLİK: ``registrar.finals.set_exam_score`` ``FinalGrade``-i
``get_or_create`` ilə tapır və audit izini yalnız bal DƏYİŞƏNDƏ yazır — eyni
cəhdin təkrar sinxronizasiyası nə dublikat sətir, nə dublikat audit yaradır.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _test_attempt_percent(attempt):
    """Test cəhdinin faizi — apellyasiya bonusu NƏZƏRƏ ALINMAQLA.

    Bonus ``ScoreAdjustment``-da saxlanılır (cavab açarı dəyişmir), ona görə
    xam ``attempt.score_percent`` qəbul olunmuş apellyasiyanı görmür. Bonusu
    ``score_adjustments`` genişlənmə nöqtəsindən alırıq (appeals ready()-də
    qoşulur; qoşulmayıbsa neytral ``None`` → xam faizə düşürük)."""
    from apps.exams import score_adjustments

    try:
        effective = score_adjustments.effective_test_score(attempt)
    except Exception:  # noqa: BLE001 — bonus hesablanmasa xam bal yenə yazılmalıdır
        logger.exception("journal_sync: effective test score failed for attempt %s", getattr(attempt, "id", "?"))
        effective = None
    if effective is not None:
        return float(effective["effective_percentage"])
    return float(attempt.score_percent)


def _written_attempt_max_score(attempt, exam):
    """Yazılı cəhdin bal tavanı — ÇATDIRILAN sual dəstindən.

    Randomizer hər cəhdə bankın yalnız bir alt-dəstini çatdırır
    (``random_question_count``, dil variantı override-ı) və manual grading hər
    cavabı ``answer_max_points`` (çatdırılma snapshot-u) ilə clamp edir. Buna
    görə məxrəc BÜTÜN bank deyil, məhz çatdırılan cavabların cəmidir — əks
    halda 20 suallıq bankdan 10 sual alan tələbənin faizi İKİ DƏFƏ aşağı
    düşürdü. Cavab sətri yoxdursa (köhnə cəhdlər) bank cəminə düşürük."""
    from apps.exams.services.manual_grading import answer_max_points

    try:
        answers = list(attempt.answers.select_related("question"))
    except Exception:  # noqa: BLE001
        answers = []
    if answers:
        return sum(answer_max_points(answer) for answer in answers)
    try:
        return sum(q.points for q in exam.questions.all()) or 0
    except Exception:  # noqa: BLE001
        return 0


def _attempt_percent(attempt):
    """İmtahan cəhdinin normallaşdırılmış faizi (0–100) — test və ya yazılı.

    Yazılı imtahan hələ yoxlanmayıbsa ``None`` (körpü gözləyir; manual-grading
    bitəndə yenidən çağırılır)."""
    exam = attempt.exam
    if getattr(exam, "exam_type", None) == "test":
        try:
            return _test_attempt_percent(attempt)
        except Exception:  # noqa: BLE001
            return None
    teacher_score = getattr(attempt, "teacher_score", None)
    if teacher_score is None:
        return None
    max_score = _written_attempt_max_score(attempt, exam)
    if not max_score:
        return None
    return round(float(teacher_score) * 100.0 / float(max_score), 1)


def _resolve_actor(attempt, actor):
    """Jurnal yazısının aktoru — tələbənin özü ASLA qaytarılmır.

    Sıra: açıq verilmiş ``actor`` (yoxlayan müəllim / apellyasiya reviewer-i) →
    cəhdin ``graded_by``-ı → ``None`` (sistem, avtomatik qiymətləndirmə)."""
    student_id = getattr(attempt, "user_id", None)
    for candidate in (actor, getattr(attempt, "graded_by", None)):
        candidate_id = getattr(candidate, "pk", None)
        if candidate_id is None or candidate_id == student_id:
            continue
        return candidate
    return None


def sync_attempt_to_journal(attempt, *, actor=None):
    """Bitmiş imtahan cəhdinin nəticəsini registrar ``FinalGrade``-ə yaz.

    İmtahan bir jurnal fənninə bağlı deyilsə (``exam.subject`` null) no-op.
    Proctordan qovulan (``supervision_status == "removed"``) → 0 = avtomatik F.
    ``actor`` — yazını edən müəllim/reviewer; verilmirsə cəhdin ``graded_by``-ı,
    o da yoxdursa sistem (``None``) aktor kimi yazılır (bax modul docstring-i).
    """
    exam = getattr(attempt, "exam", None)
    subject_id = getattr(exam, "subject_id", None)
    if not exam or not subject_id:
        return None
    if getattr(attempt, "is_trial", False):
        return None  # müəllimin "Sınaq keç" cəhdi nəticələrə sayılmır
    organization = getattr(exam, "organization", None)
    if organization is None:
        return None

    is_expelled = getattr(attempt, "supervision_status", "") == "removed"
    percent = 0 if is_expelled else _attempt_percent(attempt)
    if percent is None:
        return None  # yazılı imtahan hələ yoxlanılmayıb

    by_user = _resolve_actor(attempt, actor)
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


def schedule_journal_sync(attempt, *, actor=None):
    """Jurnal yazısını TRANZAKSİYA TƏSDİQİNDƏN SONRAYA planla.

    Cəhd/bal yazısı geri qayıdarsa (rollback) jurnala yalan nəticə düşməsin;
    həmçinin körpünün gecikməsi imtahan sorğusunu bloklamasın. ``on_commit``
    atomik blok yoxdursa callback-i dərhal işlədir — hər iki halda doğru."""
    from django.db import transaction

    transaction.on_commit(lambda: sync_attempt_to_journal(attempt, actor=actor))


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
