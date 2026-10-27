"""İmtahan balının daxil edilməsi — MİDTERM / FİNAL qaydaları, sütun şəbəkəsi və 15 dəqiqə pəncərəsi.

SAHİBİN TƏLƏBİ (2026-10-25, «İmtahan balının daxil edilməsi» ekranı):

1. **İmtahan növü** — midterm (maks 30) / final (maks 50), ekranın başında aydın seçim; sistem semestr
   təqviminə görə özü defolt seçir (:func:`default_assessment`), daxil edən dəyişə bilər.
2. **Sütunlar (suallar)** — midterm-də defolt 3, finalda 5 sütun; sütun əlavə/silmək olur, hər sütunun maks
   balı redaktə olunur, AMMA sütunların maks cəmi HƏMİŞƏ imtahanın tavanıdır (:func:`clean_column_maxes`);
   «bərabər böl» — tam ədədlər, qalıq sonuncu sütuna (:func:`equal_split`).
3. **15 dəqiqə qaydası** — təsdiqdən sonra DAXİL EDƏN balı sənədsiz dəyişə bilər (:class:`ChangeRules`,
   ``exam.score_edit_minutes``); sonra yalnız (a) RİM rəhbəri — təqdimat (səbəb + qeyd + sənəd) və ya
   (b) APELLYASİYA — yalnız İmtahan Mərkəzinin rəhbəri, apellyasiya sənədi MƏCBURİ (:func:`decide_change`). Hər dəyişiklik append-only
   ``ExamScoreEntry`` sətridir (kim, köhnə → yeni, nə vaxt, sənəd) — paralel apellyasiya mexanizmi yoxdur:
   rəqəmsal apellyasiyanın jurnal təsiri də eyni ``kind=appeal`` sətri ilə yazılır
   (``exam_score_entry.record_appeal_score_change``).

Tavanlar: final — sxemdən (``finals.exam_score_max`` = 100 − giriş tavanı = 50); midterm — RİM qaydası
(``interim_assessment.midterm_max`` = 30; sərbəst iş açıqdırsa 20). Hər ikisi server tərəfində məcburidir.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import pgettext

from core import superadmin_waiver

from .models.exam_score_entry import QUESTION_COUNT_MAX, ExamAssessment, ExamScoreEntry, ExamScoreEntryKind

_CTX = "registrar.exam_score_entry"

FINAL = ExamAssessment.FINAL
MIDTERM = ExamAssessment.MIDTERM

#: Defolt sütun sayı (sahib: «midterm-də defolt 3 sütun»; final — köhnə vərəq qaydası 5 sual).
DEFAULT_COLUMNS = {MIDTERM: 3, FINAL: 5}

#: Final sessiyası təyin olunmayıbsa semestrin son N günü «final dövrü» sayılır.
FINAL_TAIL_DAYS = 14
#: Midterm pəncərəsi bağlandıqdan sonra da bu qədər gün midterm defolt qalır (gecikmiş köçürmə).
MIDTERM_GRACE_DAYS = 14


# ── Növ və tavan ─────────────────────────────────────────────────────────────


def clean_assessment(raw, *, default=FINAL) -> str:
    """``midterm`` / ``final``; boş → ``default``; yad dəyər → ``ValidationError``."""
    value = (raw or "").strip() if isinstance(raw, str) else raw
    if not value:
        return default
    if value not in ExamAssessment.values:
        raise ValidationError(pgettext(_CTX, "İmtahan növü midterm və ya final olmalıdır."))
    return value


def midterm_available(offering) -> bool:
    """Midterm yalnız 2026/2027-dən (Midterm rejimli dövrlərdə) — keçmiş dövrlərdə K1–K3 var."""
    from . import interim_assessment

    return offering is not None and interim_assessment.is_midterm_offering(offering)


def available_assessments(offering) -> tuple:
    return (MIDTERM, FINAL) if midterm_available(offering) else (FINAL,)


def assert_assessment_allowed(offering, assessment) -> None:
    if assessment == MIDTERM and not midterm_available(offering):
        raise ValidationError(pgettext(_CTX, "Bu semestrdə midterm yoxdur (kollokvium rejimi) — yalnız final."))


def midterm_cap() -> int:
    from . import interim_assessment

    return int(interim_assessment.midterm_max())


def cap_for(offering, assessment, *, scheme=None) -> int:
    """İmtahanın tavanı: midterm 30 (RİM qaydası), final — sxemdən (50)."""
    if assessment == MIDTERM:
        return midterm_cap()
    from . import finals, gradebook

    scheme = scheme or gradebook.ensure_assessment_scheme(offering=offering)
    return int(finals.exam_score_max(scheme))


def label_for(assessment) -> str:
    return str(ExamAssessment(assessment).label) if assessment in ExamAssessment.values else ""


# ── Təqvimə görə defolt ──────────────────────────────────────────────────────


def _midterm_window(period):
    from .models import KollokviumWindow

    return (
        KollokviumWindow.objects.filter(period=period, k_index=0)
        .order_by("-is_active", "-opens_on")
        .values("opens_on", "closes_on")
        .first()
    )


def default_assessment(period, *, organization=None, today=None, midterm_ok=None) -> str:
    """Semestr təqviminə görə defolt imtahan (daxil edən dəyişə bilər).

    Qayda (yuxarıdan aşağı, ilk uyğun gələn):

    * dövr Midterm rejimində deyil (2025/2026 və əvvəl) → final;
    * imtahan sessiyası (``exam_session_start``) başlayıb → final;
    * İmtahan Mərkəzinin midterm bal-yazma pəncərəsi (``KollokviumWindow`` k=0) açıqdır və ya
      :data:`MIDTERM_GRACE_DAYS` gün əvvəl bağlanıb → midterm;
    * semestr bitib və ya son :data:`FINAL_TAIL_DAYS` gündədir (sessiya təyin olunmayıbsa) → final;
    * əks halda (semestrin ortası) → midterm.
    """
    from core.academic_rules import period_uses_new_rules

    if period is None:
        return FINAL
    if midterm_ok is None:
        midterm_ok = period_uses_new_rules(period, organization)
    if not midterm_ok:
        return FINAL
    today = today or timezone.localdate()
    session_start = getattr(period, "exam_session_start", None)
    if session_start and today >= session_start:
        return FINAL
    window = _midterm_window(period)
    if window and window["opens_on"] <= today <= window["closes_on"] + timedelta(days=MIDTERM_GRACE_DAYS):
        return MIDTERM
    end_date = getattr(period, "end_date", None)
    final_from = session_start or (end_date - timedelta(days=FINAL_TAIL_DAYS) if end_date else None)
    if final_from and today >= final_from:
        return FINAL
    return MIDTERM


# ── Sütun şəbəkəsi ───────────────────────────────────────────────────────────


def equal_split(cap: int, count: int) -> list:
    """«Bərabər böl»: ``cap`` balı ``count`` sütuna TAM ədədlərlə; qalıq SONUNCU sütuna (30/4 → 7,7,7,9)."""
    cap, count = int(cap), max(1, int(count))
    base, rest = divmod(cap, count)
    if base < 1:  # sütun sayı tavandan çoxdursa hər sütun ən azı 1 (sayı tavana endirilir)
        return [1] * cap
    return [base] * (count - 1) + [base + rest]


def default_columns(assessment, cap: int) -> list:
    return equal_split(cap, DEFAULT_COLUMNS.get(assessment, DEFAULT_COLUMNS[FINAL]))


def _parse_int(raw):
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except Exception:  # noqa: BLE001 — Decimal-in bütün parse xətaları eyni mesaja düşür
        raise ValidationError(pgettext(_CTX, "Sütunun maksimum balı tam ədəd olmalıdır.")) from None
    if not value.is_finite() or value != value.to_integral_value():
        raise ValidationError(pgettext(_CTX, "Sütunun maksimum balı tam ədəd olmalıdır."))
    return int(value)


def parse_column_maxes(raw) -> list | None:
    """``"10,10,10"`` / ``[10, 10, 10]`` → siyahı; boş → ``None`` (köhnə bərabər şəbəkə)."""
    if raw is None:
        return None
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    values = [_parse_int(item) for item in items]
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValidationError(pgettext(_CTX, "Hər sütunun maksimum balı yazılmalıdır."))
    return values


def clean_column_maxes(raw, cap: int) -> list:
    """Sütunların maks balları — sahibin qaydası (hamısı fail-closed, mesaj dəqiq):

    * sütun sayı 1..:data:`QUESTION_COUNT_MAX`;
    * hər sütun TAM ədəd, 1..``cap``;
    * cəm ``cap``-a BƏRABƏR (midterm 30 / final 50) — az da, çox da olmaz.
    """
    values = parse_column_maxes(raw)
    if not values:
        raise ValidationError(pgettext(_CTX, "Ən azı bir sütun (sual) olmalıdır."))
    if len(values) > QUESTION_COUNT_MAX:
        raise ValidationError(pgettext(_CTX, "Sütun sayı %(max)s-dən çox ola bilməz.") % {"max": QUESTION_COUNT_MAX})
    for index, value in enumerate(values, start=1):
        if value < 1 or value > int(cap):
            raise ValidationError(
                pgettext(_CTX, "S%(n)s sütununun maksimumu 1 ilə %(max)s arasında olmalıdır.")
                % {"n": index, "max": int(cap)}
            )
    total = sum(values)
    if total != int(cap):
        raise ValidationError(
            pgettext(_CTX, "Sütunların maksimum cəmi %(cap)s olmalıdır (indi %(total)s).")
            % {"cap": int(cap), "total": total}
        )
    return values


# ── 15 dəqiqə pəncərəsi və dəyişiklik qaydası ───────────────────────────────


def edit_window() -> timedelta:
    from core.runtime_settings_exam_scores import edit_minutes

    return timedelta(minutes=edit_minutes())


def edit_window_label() -> str:
    from .journal_edit_windows import duration_text

    return duration_text(edit_window())


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def initial_entries(enrollment_ids, assessment) -> dict:
    """``{enrollment_id: (entered_by_id, created_at)}`` — İLK təsdiq (``kind=initial``) sətirləri, BİR sorğu.

    Formadan gələn yad / boş id-lər (``score__<yad>``) səssizcə atılır — sətir onsuz da yazıda rədd olunur.
    """
    ids = [value for value in (_uuid_or_none(raw) for raw in enrollment_ids) if value is not None]
    if not ids:
        return {}
    rows = (
        ExamScoreEntry.objects.filter(enrollment_id__in=ids, assessment=assessment, kind=ExamScoreEntryKind.INITIAL)
        .order_by("created_at")
        .values_list("enrollment_id", "entered_by_id", "created_at")
    )
    result: dict = {}
    for enrollment_id, entered_by_id, created_at in rows:
        result.setdefault(enrollment_id, (entered_by_id, created_at))
    return result


@dataclass
class ChangeRules:
    """Bir sorğunun (aktor × açılış × imtahan) dəyişiklik qaydası — sətir-sətir sorğusuz tətbiq olunur."""

    user_id: object = None
    can_rim_correct: bool = False
    can_appeal: bool = False
    window: timedelta = field(default_factory=lambda: edit_window())
    initial: dict = field(default_factory=dict)
    now: datetime.datetime = field(default_factory=lambda: timezone.now())

    @classmethod
    def build(cls, *, user, organization, enrollment_ids, assessment) -> "ChangeRules":
        from .exam_score_period_lock import change_permissions

        can_rim_correct, can_appeal = change_permissions(user, organization)
        return cls(
            user_id=getattr(user, "pk", None),
            can_rim_correct=can_rim_correct,
            can_appeal=can_appeal,
            initial=initial_entries(enrollment_ids, assessment),
        )

    def deadline(self, enrollment_id):
        """Bu aktorun bu sətirdə sənədsiz düzəliş edə biləcəyi son an (deyilsə ``None``)."""
        first = self.initial.get(enrollment_id)
        if first is None or self.user_id is None or first[0] != self.user_id:
            return None
        return first[1] + self.window

    def window_open(self, enrollment_id) -> bool:
        deadline = self.deadline(enrollment_id)
        return deadline is not None and self.now <= deadline


def window_closed_error(window=None) -> ValidationError:
    from .journal_edit_windows import duration_text

    return ValidationError(
        pgettext(
            _CTX,
            "Təsdiqdən %(w)s keçib — bal yalnız apellyasiya (sənəd məcburi) və ya RİM rəhbərinin təqdimat "
            "əsasında düzəlişi ilə dəyişdirilə bilər.",
        )
        % {"w": duration_text(window or edit_window())}
    )


def rim_only_error() -> ValidationError:
    return ValidationError(
        pgettext(_CTX, "Təqdimat əsasında düzəliş yalnız RİM rəhbəri tərəfindən edilir — apellyasiya seçin.")
    )


def appeal_head_only_error() -> ValidationError:
    return ValidationError(
        pgettext(_CTX, "Apellyasiya əsasında dəyişiklik yalnız İmtahan Mərkəzinin rəhbəri tərəfindən edilir.")
    )


def appeal_document_error() -> ValidationError:
    return ValidationError(pgettext(_CTX, "Apellyasiya ilə dəyişiklik üçün apellyasiya sənədi yüklənməlidir."))


def decide_after_window(
    *, rules, enrollment_id, kind, reason, note, evidence, sheet, require_justification, by_user=None
):
    """Yazılmış balın dəyişdirilməsi (cari dövr) → yazılacaq sətrin növü; qadağandırsa ``ValidationError``.

    * ``kind=appeal`` — APELLYASİYA: yalnız İmtahan Mərkəzinin rəhbəri / RİM rəhbəri / superadmin, sənəd (sətrin
      və ya vərəqin faylı) MƏCBURİ;
    * ``kind=correction`` — yalnız RİM rəhbəri / superadmin, tam təqdimatla (səbəb + qeyd + sənəd);
    * növ yoxdursa — daxil edənin öz pəncərəsi açıqdırsa ``window_edit`` (sənədsiz), yoxsa rədd.
    """
    if kind == ExamScoreEntryKind.APPEAL:
        if not rules.can_appeal:
            raise appeal_head_only_error()
        if not evidence and not (sheet is not None and sheet.evidence) and not superadmin_waiver.waives(by_user):
            raise appeal_document_error()  # superadmin sənədsiz keçir (sahib 2026-10-27)
        return ExamScoreEntryKind.APPEAL
    if kind == ExamScoreEntryKind.CORRECTION:
        if not rules.can_rim_correct:
            raise rim_only_error()
        require_justification(reason=reason, note=note, evidence=evidence, sheet=sheet, by_user=by_user)
        return ExamScoreEntryKind.CORRECTION
    if rules.window_open(enrollment_id):
        return ExamScoreEntryKind.WINDOW_EDIT
    raise window_closed_error(rules.window)


__all__ = [
    "ChangeRules",
    "DEFAULT_COLUMNS",
    "FINAL",
    "MIDTERM",
    "appeal_document_error",
    "appeal_head_only_error",
    "assert_assessment_allowed",
    "available_assessments",
    "cap_for",
    "clean_assessment",
    "clean_column_maxes",
    "decide_after_window",
    "default_assessment",
    "default_columns",
    "edit_window",
    "edit_window_label",
    "equal_split",
    "initial_entries",
    "label_for",
    "midterm_available",
    "midterm_cap",
    "parse_column_maxes",
    "rim_only_error",
    "window_closed_error",
]
