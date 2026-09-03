"""Çox cəhdli imtahanın tarixçəsi — «əvvəlki bal itməsin» (sahibin qərarı M1/M2).

Azərbaycanda 2-ci cəhd (25% imtahanı) 1-cini LƏĞV EDİR: rəsmi olan SONUNCU
cəhddir. Bu davranış düzdür və dəyişmir. Amma əvvəlki cəhdlərin balı itməməli,
UI-da AÇIQ görünməlidir — «1-ci cəhd: 80 · ləğv olundu», «2-ci cəhd: 65 · rəsmi».

Data onsuz da ``exams.ExamAttempt`` sətirlərində var; burada onu bir oxu
səthinə çeviririk ki, həm tələbə kabineti, həm imtahan mərkəzi/müəllim
görünüşü eyni siyahını göstərsin.

MODUL SƏRHƏDİ (VACİB): ``exams`` modulu registrar-ı import edir
(``apps/exams/services/journal_sync.py``). Əks istiqamətdə STATİK import
qoysaq ``exams<->registrar`` dövri cütü yaranar və ``scripts/module_deps.py``
qapısı düşər. Ona görə model app registry-dən götürülür — registrar-ın
``organizations`` modellərini oxuduğu ilə eyni sanksiyalı üsul
(bax ``apps/registrar/public.py`` şərhi). Registrar faylında heç bir
``from apps.exams`` sətri YOXDUR.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Bitmiş sayılan cəhd statusları (yarımçıq/başlanmış cəhd tarixçəyə düşmür).
_FINISHED_STATUSES = ("submitted", "expired")

#: AZ sıra sayı şəkilçisi — son rəqəmə görə (1-ci, 3-cü, 6-cı, 9-cu…).
#: Şablonda hesablamaq mümkün deyil, ona görə etiket burada hazırlanır.
_ORDINAL_SUFFIX = {
    0: "-cı",
    1: "-ci",
    2: "-ci",
    3: "-cü",
    4: "-cü",
    5: "-ci",
    6: "-cı",
    7: "-ci",
    8: "-ci",
    9: "-cu",
}


def ordinal_label(number: int) -> str:
    """«1-ci», «2-ci», «3-cü»… — cəhd nömrəsinin AZ sıra sayı."""
    return f"{number}{_ORDINAL_SUFFIX.get(int(number) % 10, '-ci')}"


def _attempt_model():
    from django.apps import apps as django_apps

    return django_apps.get_model("exams", "ExamAttempt")


def _safe_percent(attempt):
    """Cəhdin faizi — hesablama sınarsa tarixçə yenə də göstərilsin."""
    try:
        value = attempt.score_percent
    except Exception:  # noqa: BLE001 — tarixçə heç vaxt səhifəni sındırmır
        logger.exception("exam_attempt_history: score_percent failed for attempt %s", getattr(attempt, "id", "?"))
        return None
    if value is None:
        return None
    return round(float(value), 1)


def attempt_rows_for_subject(*, student, subject_id, organization):
    """Bir fənn üzrə tələbənin BÜTÜN bitmiş cəhdləri (köhnədən yeniyə).

    Nəticə sətirləri::

        {"number": 1, "label": "1-ci", "percent": 80.0, "is_official": False,
         "exam_title": "…", "finished_at": …, "is_expelled": False}

    ``is_official`` — YALNIZ sonuncu (ən yeni) cəhddə ``True``. Boş siyahı =
    bu fənn üzrə rəqəmsal cəhd yoxdur (kağız imtahan) — səth heç nə göstərmir.
    """
    if not subject_id or student is None or organization is None:
        return []
    try:
        attempt_model = _attempt_model()
    except LookupError:  # exams modulu quraşdırılmayıb (test/tenant konfiqurasiyası)
        return []

    attempts = list(
        attempt_model.objects.filter(
            user=student,
            exam__subject_id=subject_id,
            exam__organization=organization,
            is_trial=False,
            status__in=_FINISHED_STATUSES,
        )
        .select_related("exam")
        .order_by("started_at", "attempt_number")
    )
    # Sətir formatı TƏK yerdən (toplu variant da eyni funksiyanı işlədir).
    return _rows_from_attempts(attempts)


def _rows_from_attempts(attempts) -> list:
    """Sıralanmış cəhd sətirlərini UI formatına çevir (rəsmi = SONUNCU)."""
    last_index = len(attempts) - 1
    return [
        {
            "number": index + 1,
            "label": ordinal_label(index + 1),
            "percent": _safe_percent(attempt),
            "is_official": index == last_index,
            "exam_title": getattr(attempt.exam, "title", "") or "",
            "finished_at": attempt.finished_at or attempt.started_at,
            "is_expelled": getattr(attempt, "supervision_status", "") == "removed",
        }
        for index, attempt in enumerate(attempts)
    ]


def attempt_rows_by_student(*, student_ids, subject_id, organization) -> dict:
    """``student_id`` → cəhd sətirləri — bir fənn üzrə BÜTÜN roster, **tək sorğu**.

    :func:`attempt_rows_for_subject`-in toplu güzgüsüdür: müəllim jurnalının
    «Yekun» tab-ı sətir-sətir çağıranda 555 tələbəli açılışda 555 sorğu olurdu
    (2026-09-02 performans ölçməsi).  Sıralama və «rəsmi cəhd» qaydası eynidir.
    """
    ids = [sid for sid in student_ids if sid is not None]
    if not ids or not subject_id or organization is None:
        return {}
    try:
        attempt_model = _attempt_model()
    except LookupError:  # exams modulu quraşdırılmayıb
        return {}
    attempts = (
        attempt_model.objects.filter(
            user_id__in=ids,
            exam__subject_id=subject_id,
            exam__organization=organization,
            is_trial=False,
            status__in=_FINISHED_STATUSES,
        )
        .select_related("exam")
        .order_by("started_at", "attempt_number")
    )
    by_student: dict = {}
    for attempt in attempts:
        by_student.setdefault(attempt.user_id, []).append(attempt)
    return {student_id: _rows_from_attempts(rows) for student_id, rows in by_student.items()}


def attempt_rows_for_enrollment(enrollment):
    """``attempt_rows_for_subject`` — qeydiyyat sətrindən (offering → subject)."""
    offering = getattr(enrollment, "offering", None)
    if offering is None:
        return []
    return attempt_rows_for_subject(
        student=enrollment.student,
        subject_id=offering.subject_id,
        organization=enrollment.organization,
    )


def has_superseded_attempts(rows) -> bool:
    """Ləğv olunmuş (rəsmi olmayan) cəhd varmı — UI zolağını göstərmək üçün."""
    return len(rows) > 1
