"""İmtahan mərkəzi (zal) axını ilə verilən imtahan növləri — YEGANƏ mənbə (sahib 2026-10-20).

Sahib: «Midterm də Final imtahanı kimidir — orada da URL /midterm olsun. Final imtahanındakı proses,
məsuliyyət və ciddilik nədirsə eynisi». Bu modul «bu imtahan mərkəz axınındadırmı» sualına cavab verən
YEGANƏ yerdir; zal prosesinə aid hər yoxlama (giriş URL-i, kabinetdən start qadağası, cihaz bağlantısı,
giriş sessiyası, 5 dəqiqəlik nəticə baxışı + çıxış, «cihaz dəyişikliyi», PIN axtarışı) bunu çağırır.

* **final** — həmişə mərkəz axınındadır (əvvəlki kimi).
* **midterm** — «Sistem tənzimləmələri» → ``exam.midterm_via_center`` yandırılıbsa (``core.runtime_settings_midterm``).
  Söndürüləndə midterm əvvəlki kabinet axınına qayıdır (fərdi ``ExamStudentPin`` ilə ``exam_code_check``).

Mərkəz axınına AİD OLMAYAN final-only semantika bu moduldan istifadə ETMİR və dəyişməyib: jurnalın
«yekun» sütunu / bal körpüsü (``journal_sync``), registrar yekun nəticəsi, 25% təkrar imtahan qaydası
(``registrar.retake_chance``), rəsmi cəhd tarixçəsi (``registrar.exam_attempt_history``).

**Keçid təhlükəsizliyi.** Açar yandırılmazdan ƏVVƏL kabinetdən başlamış, hələ açıq midterm cəhdi (bileti
yoxdur) normal bitir: :func:`legacy_open_attempt` onu tanıyır — kabinet onu davam etdirməyə icazə verir,
nəticə səhifəsi isə onu mərkəz nəticəsi saymır (:func:`attempt_in_center`).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

FINAL_KIND = "final"
MIDTERM_KIND = "midterm"
#: Mərkəz axınını dəstəkləyən BÜTÜN növlər (statik). Hazırda aktiv olanlar — :func:`active_center_kinds`.
CENTER_EXAM_KINDS = frozenset({FINAL_KIND, MIDTERM_KIND})

_ENTRY_URL_NAMES = {
    FINAL_KIND: "exams:final_exam_entry",
    MIDTERM_KIND: "exams:midterm_exam_entry",
}
_OPEN_STATUSES = ("draft", "in_progress")
_CTX = "exams.center_exams"


def midterm_via_center() -> bool:
    from core.runtime_settings_midterm import midterm_via_center as _flag

    return _flag()


def is_center_kind(kind) -> bool:
    if kind == FINAL_KIND:
        return True
    return kind == MIDTERM_KIND and midterm_via_center()


def active_center_kinds() -> frozenset:
    """Hazırda mərkəz axını ilə verilən növlər (açar söndürülübsə yalnız final)."""
    return CENTER_EXAM_KINDS if midterm_via_center() else frozenset({FINAL_KIND})


def exam_kind(exam) -> str:
    return getattr(exam, "exam_type_extended", None) or ""


def is_center_exam(exam) -> bool:
    """Bu imtahan imtahan mərkəzi (zal) axını ilə verilirmi."""
    return exam is not None and is_center_kind(exam_kind(exam))


def entry_url_name(kind) -> str:
    return _ENTRY_URL_NAMES.get(kind, _ENTRY_URL_NAMES[FINAL_KIND])


def entry_url(kind) -> str:
    return reverse(entry_url_name(kind))


def entry_url_for_exam(exam) -> str:
    """İmtahanın zal giriş səhifəsi (``/exams/final/`` və ya ``/exams/midterm/``)."""
    return entry_url(exam_kind(exam))


def kind_label(kind) -> str:
    if kind == MIDTERM_KIND:
        return pgettext(_CTX, "Midterm")
    if kind == FINAL_KIND:
        return pgettext(_CTX, "Final")
    return ""


def center_entry_required_message(exam) -> str:
    """Kabinetdən / birbaşa start cəhdində tələbəyə göstərilən izah (növə görə URL ilə)."""
    if exam_kind(exam) == MIDTERM_KIND:
        return pgettext(
            _CTX,
            "Bu imtahana imtahan zalında /exams/midterm/ ünvanından istifadəçi adınız və PIN ilə daxil olun.",
        )
    return pgettext(
        _CTX,
        "Bu imtahana imtahan zalında /exams/final/ ünvanından istifadəçi adınız və PIN ilə daxil olun.",
    )


def cabinet_center_notice(exam) -> str:
    """Kabinet modalındakı xəbərdarlıq (final/midterm)."""
    if exam_kind(exam) == MIDTERM_KIND:
        return pgettext(
            _CTX,
            "Bu, midterm imtahanıdır. İmtahana imtahan zalında /exams/midterm/ ünvanından istifadəçi adı və PIN ilə "
            "daxil olun. Kabinetdən birbaşa başlamaq mümkün deyil.",
        )
    return pgettext(
        _CTX,
        "Bu, final imtahanıdır. İmtahan yalnız təyin olunmuş vaxt aralığında, imtahan giriş səhifəsindən "
        "istifadəçi adı və PIN ilə verilir. Kabinetdən birbaşa başlamaq mümkün deyil.",
    )


def legacy_open_attempt(exam, user):
    """Mərkəz axınından ƏVVƏL kabinetdən başlamış, hələ açıq (biletsiz) midterm cəhdi və ya ``None``.

    Yalnız midterm üçündür (final həmişə mərkəz axınında olub). Vaxtı keçmiş cəhd əvvəlcə bağlanır
    (``expire_if_time_limit_reached``) — ölü cəhd «davam» bəhanəsi ilə yeni kabinet cəhdinə yol açmasın.
    """
    if exam_kind(exam) != MIDTERM_KIND or user is None or not getattr(user, "pk", None):
        return None
    from apps.exams.models import ExamAttempt

    candidates = ExamAttempt.objects.filter(
        exam=exam, user=user, status__in=_OPEN_STATUSES, is_trial=False, final_tickets__isnull=True
    ).order_by("-started_at")
    for attempt in candidates:
        if attempt.expire_if_time_limit_reached():
            continue
        return attempt
    return None


def attempt_has_center_ticket(attempt) -> bool:
    from apps.exams.models import FinalExamTicket
    from core.rls import bypass_rls

    # Dar, cəhd + sahib süzgəcli oxu (public PIN axınında aktiv-org konteksti cəhdin org-u olmaya bilər).
    with bypass_rls():
        return FinalExamTicket.objects.filter(attempt_id=attempt.pk, student_id=attempt.user_id).exists()


def attempt_in_center(attempt) -> bool:
    """Bu cəhd mərkəz axınının nəticə qaydalarına (5 dəqiqəlik baxış → çıxış) tabedirmi.

    Final — həmişə (əvvəlki davranış). Midterm — mərkəz açarı yandırılıbsa VƏ cəhd zal girişindən
    (bilet) yaranıbsa; kabinetdən başlamış köhnə cəhd kabinet nəticəsi kimi qalır. Sınaq heç vaxt.
    """
    exam = getattr(attempt, "exam", None)
    if exam is None or getattr(attempt, "is_trial", False):
        return False
    kind = exam_kind(exam)
    if kind == FINAL_KIND:
        return True
    if not is_center_kind(kind):
        return False
    return attempt_has_center_ticket(attempt)


__all__ = [
    "CENTER_EXAM_KINDS",
    "FINAL_KIND",
    "MIDTERM_KIND",
    "active_center_kinds",
    "attempt_has_center_ticket",
    "attempt_in_center",
    "cabinet_center_notice",
    "center_entry_required_message",
    "entry_url",
    "entry_url_for_exam",
    "entry_url_name",
    "exam_kind",
    "is_center_exam",
    "is_center_kind",
    "kind_label",
    "legacy_open_attempt",
    "midterm_via_center",
]
