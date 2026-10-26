"""«Dəyərləndirilmiş nəticələr» süzgəcləri — dövr / tarix-saat aralığı, imtahan kateqoriyası, fənn (2026-10-27).

Sahib 2026-10-27:

* «Dövr» — hazır seçimlər (son 7 / 30 / 90 gün) QALIR; üstəlik «Seçilmiş aralıq»: istənilən
  ``başlanğıc – son`` tarix-saat (``gg.aa.iiii ss:dd``, layihənin ``EMSDateTime`` sahəsi; ISO da
  qəbul olunur). Yalnız tarix yazılan «son» günün SONUNA qədərdir. Hazır seçim aktivdirsə aralıq
  sahələri nəzərə alınmır (və boşaldılır) — iki ziddiyyətli süzgəc eyni vaxtda işləmir.
* «Növ» — mövcud növlərə (İmtahanlar / test / yazılı / Laboratoriya …) imtahan KATEQORİYASI
  əlavə olunur: Midterm / Final / Quiz (``Exam.exam_type_extended``).
* «Fənn» — sətirlərin fənni (imtahan: akademik fənn və ya kurs; digər işlər: kurs).

Tarix sahəsi: qiymətləndirmə anı, yoxdursa təhvil anı — ekrandakı «Tarix» sütunu ilə eyni qayda.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

#: «Növ» seçicisində imtahanın alt növü (2026-10-17): ``exam_test`` / ``exam_written`` → «exams» + növ süzgəci.
EXAM_KIND_FILTERS = {"exam_test": "test", "exam_written": "written"}
#: «Növ» seçicisində imtahan kateqoriyası (2026-10-27): Midterm / Final / Quiz.
EXAM_CATEGORY_FILTERS = {"exam_midterm": "midterm", "exam_final": "final", "exam_quiz": "quiz"}
#: «Dövr» süzgəci — qiymətləndirmə (yoxsa göndərilmə) tarixi son N gün daxilində.
PERIOD_FILTERS = {"7": 7, "30": 30, "90": 90}
#: «Dövr» = istifadəçinin seçdiyi tarix-saat aralığı.
PERIOD_CUSTOM = "custom"


@dataclass(frozen=True)
class DateWindow:
    period: str
    since: datetime.datetime | None
    until: datetime.datetime | None
    from_text: str
    to_text: str

    @property
    def active(self) -> bool:
        return self.since is not None or self.until is not None


def _parse_bound(raw: str, *, end_of_day: bool):
    """Mətn → (aware datetime, kanonik mətn); oxunmayan dəyər (None, "") — süzgəc tətbiq olunmur."""
    from core.datetime_input import DAY_FIRST_RE, DISPLAY_FORMAT, ISO_RE, DateTimeTextError, parse_datetime_text

    text = (raw or "").strip()[:40]
    if not text:
        return None, ""
    try:
        value = parse_datetime_text(text, require_time=False)
    except DateTimeTextError:
        return None, ""
    if value is None:
        return None, ""
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    match = DAY_FIRST_RE.match(text) or ISO_RE.match(text)
    if end_of_day and match is not None and match.group(4) is None:  # yalnız tarix → günün sonu
        value = value + timedelta(days=1) - timedelta(microseconds=1)
    return value, timezone.localtime(value).strftime(DISPLAY_FORMAT)


def resolve_date_window(period: str, raw_from: str, raw_to: str, *, now=None) -> DateWindow:
    period = (period or "").strip()
    if period in PERIOD_FILTERS:
        since = (now or timezone.now()) - timedelta(days=PERIOD_FILTERS[period])
        return DateWindow(period, since, None, "", "")
    since, from_text = _parse_bound(raw_from, end_of_day=False)
    until, to_text = _parse_bound(raw_to, end_of_day=True)
    if since is not None and until is not None and since > until:
        since, until = until, since
        from_text, to_text = to_text, from_text
    if since is not None or until is not None or period == PERIOD_CUSTOM:
        return DateWindow(PERIOD_CUSTOM, since, until, from_text, to_text)
    return DateWindow("", None, None, "", "")


def attempt_window_q(window: DateWindow):
    """İmtahan cəhdi: yoxlanma anı, yoxdursa bitmə, o da yoxdursa başlama — aralıq daxilində."""
    condition = Q()
    for lookup, bound in (("gte", window.since), ("lte", window.until)):
        if bound is None:
            continue
        condition &= (
            Q(**{f"teacher_checked_at__{lookup}": bound})
            | Q(teacher_checked_at__isnull=True, **{f"finished_at__{lookup}": bound})
            | Q(teacher_checked_at__isnull=True, finished_at__isnull=True, **{f"started_at__{lookup}": bound})
        )
    return condition


def graded_window_q(window: DateWindow):
    """Tapşırıq / kurs işi / lab: qiymətləndirmə anı, yoxdursa təhvil anı — aralıq daxilində."""
    condition = Q()
    for lookup, bound in (("gte", window.since), ("lte", window.until)):
        if bound is None:
            continue
        condition &= Q(**{f"graded_at__{lookup}": bound}) | Q(
            graded_at__isnull=True, **{f"submitted_at__{lookup}": bound}
        )
    return condition


def item_in_window(item, window: DateWindow) -> bool:
    moment = item.get("reviewed_at") or item.get("submitted_at")
    if not window.active:
        return True
    if moment is None:
        return False
    if window.since is not None and moment < window.since:
        return False
    return window.until is None or moment <= window.until


def subject_options(items) -> list[str]:
    return sorted({item["subject_title"] for item in items if item.get("subject_title")}, key=str.lower)


__all__ = [
    "EXAM_CATEGORY_FILTERS",
    "EXAM_KIND_FILTERS",
    "PERIOD_CUSTOM",
    "PERIOD_FILTERS",
    "DateWindow",
    "attempt_window_q",
    "graded_window_q",
    "item_in_window",
    "resolve_date_window",
    "subject_options",
]
