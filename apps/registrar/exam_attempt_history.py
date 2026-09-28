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

Audit 2026-09-28 EXA-03 (sahibin 2026-09-07 memo-su — «hər təkrar cəhd və
apellyasiya izlənsin, koordinator/dekanlıq görsün»): tarixçə yanlış data
göstərirdi. İndi:

* YALNIZ yekun (``exam_type_extended="final"``) cəhdlər — midterm/quiz «rəsmi»
  kimi görünmür (``FinalGrade.exam_score`` də yalnız finaldan yazılır);
* faiz jurnala yazılan RƏSMİ faizlə eynidir (test → apellyasiya bonusu daxil,
  yazılı → ``teacher_score`` ÷ çatdırılan snapshot tavanı, yoxlanmamış → «—»);
* rəsmi = ən son BİTMİŞ (``finished_at``) qeyri-sınaq final cəhdi;
* hər cəhdə apellyasiya sətirləri (``appeals``: qərar, bal fərqi, baxan, tarix).

Faiz və apellyasiya sətirləri ``appeals`` modulundan app registry üzərindən
(``AppealsConfig.attempt_history_provider``) alınır — yenə statik import yoxdur.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Bitmiş sayılan cəhd statusları (yarımçıq/başlanmış cəhd tarixçəyə düşmür).
_FINISHED_STATUSES = ("submitted", "expired")

#: Tarixçəyə düşən kateqoriya — yalnız yekun imtahan (``journal_sync`` ilə eyni qayda).
_FINAL_CATEGORY = "final"

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


def _history_provider():
    """``appeals`` modulunun tarixçə provayderi (app registry) və ya ``None``."""
    from django.apps import apps as django_apps

    try:
        config = django_apps.get_app_config("appeals")
    except LookupError:
        return None
    factory = getattr(config, "attempt_history_provider", None)
    return factory() if callable(factory) else None


def _final_attempts(**filters):
    """Tarixçə sorğusu — bitmiş, qeyri-sınaq YEKUN cəhdlər, köhnədən yeniyə (rəsmi = sonuncu)."""
    from django.db.models.functions import Coalesce

    return (
        _attempt_model()
        .objects.filter(
            is_trial=False,
            status__in=_FINISHED_STATUSES,
            exam__exam_type_extended=_FINAL_CATEGORY,
            **filters,
        )
        .select_related("exam")
        .order_by(Coalesce("finished_at", "started_at"), "attempt_number", "id")
    )


def _history_extras(attempts):
    """(faiz xəritəsi, apellyasiya sətirləri) — provayder yoxdursa/sınarsa boş (səhifə sınmır)."""
    provider = _history_provider()
    if provider is None or not attempts:
        return {}, {}
    try:
        percents = provider.attempt_percents(attempts)
        appeals = provider.appeal_rows_by_attempt([attempt.id for attempt in attempts])
    except Exception:  # noqa: BLE001 — tarixçə heç vaxt səhifəni sındırmır
        logger.exception("exam_attempt_history: provider failed for %s attempts", len(attempts))
        return {}, {}
    return percents, appeals


def attempt_rows_for_subject(*, student, subject_id, organization):
    """Bir fənn üzrə tələbənin BÜTÜN bitmiş cəhdləri (köhnədən yeniyə).

    Nəticə sətirləri::

        {"number": 1, "label": "1-ci", "percent": 80.0, "is_official": False,
         "exam_title": "…", "finished_at": …, "is_expelled": False,
         "attempt_id": 7, "appeals": [{"status": "accepted", "delta_points": …,
         "reviewer_name": "…", "reviewed_at": …, …}]}

    ``is_official`` — YALNIZ sonuncu (ən yeni) cəhddə ``True``. Boş siyahı =
    bu fənn üzrə rəqəmsal cəhd yoxdur (kağız imtahan) — səth heç nə göstərmir.
    """
    if not subject_id or student is None or organization is None:
        return []
    try:
        attempts = list(_final_attempts(user=student, exam__subject_id=subject_id, exam__organization=organization))
    except LookupError:  # exams modulu quraşdırılmayıb (test/tenant konfiqurasiyası)
        return []
    # Sətir formatı TƏK yerdən (toplu variant da eyni funksiyanı işlədir).
    percents, appeals = _history_extras(attempts)
    return _rows_from_attempts(attempts, percents, appeals)


def _rows_from_attempts(attempts, percents, appeals) -> list:
    """Sıralanmış cəhd sətirlərini UI formatına çevir (rəsmi = SONUNCU bitmiş final cəhdi)."""
    last_index = len(attempts) - 1
    return [
        {
            "number": index + 1,
            "label": ordinal_label(index + 1),
            "percent": percents.get(attempt.id),
            "is_official": index == last_index,
            "exam_title": getattr(attempt.exam, "title", "") or "",
            "finished_at": attempt.finished_at or attempt.started_at,
            "is_expelled": getattr(attempt, "supervision_status", "") == "removed",
            "attempt_id": attempt.id,
            "appeals": appeals.get(attempt.id, []),
        }
        for index, attempt in enumerate(attempts)
    ]


def _grouped_rows(attempts, key) -> dict:
    """Cəhdləri ``key(attempt)`` üzrə qruplaşdır — faiz/apellyasiya TƏK toplu çağırışla."""
    percents, appeals = _history_extras(attempts)
    grouped: dict = {}
    for attempt in attempts:
        grouped.setdefault(key(attempt), []).append(attempt)
    return {group: _rows_from_attempts(rows, percents, appeals) for group, rows in grouped.items()}


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
        attempts = list(_final_attempts(user_id__in=ids, exam__subject_id=subject_id, exam__organization=organization))
    except LookupError:  # exams modulu quraşdırılmayıb
        return {}
    return _grouped_rows(attempts, lambda attempt: attempt.user_id)


def attempt_rows_by_subject(*, student, subject_ids, organization) -> dict:
    """``subject_id`` → cəhd sətirləri — BİR tələbənin bütün fənləri, **tək sorğu**.

    2026-09-12 (tələbə kabineti redizaynı): «Fənlərim» hər fənn üçün
    :func:`attempt_rows_for_enrollment` çağırırdı — fənn başına bir sorğu
    (N+1); sorğu sayı fənn sayı ilə artırdı.  Bu, :func:`attempt_rows_by_student`-in
    tələbə-mərkəzli güzgüsüdür: sıralama və «rəsmi = SONUNCU cəhd» qaydası eynidir,
    yalnız qruplaşdırma açarı fərqlidir (burada fənn).
    """
    ids = [sid for sid in subject_ids if sid is not None]
    if not ids or student is None or organization is None:
        return {}
    try:
        attempts = list(_final_attempts(user=student, exam__subject_id__in=ids, exam__organization=organization))
    except LookupError:  # exams modulu quraşdırılmayıb
        return {}
    return _grouped_rows(attempts, lambda attempt: attempt.exam.subject_id)


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
