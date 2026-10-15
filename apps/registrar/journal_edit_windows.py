"""Jurnal vaxt qaydaları (RİM rəhbəri «Sistem tənzimləmələri»ndən dəyişir; sahib 2026-10-03 / 2026-10-15).

* dərs sətri (tarix/növ/mövzu/saat/silmə) — yaranışdan sonra ``lesson_edit_window()``;
* q/b, i/e və bal — yazılışdan sonra ``mark_edit_window()``; Postgres trigger-i eyni açarları oxuyur
  (registrar 0089: əvvəl ``journal.mark_edit_minutes``, sonra köhnə ``journal.mark_edit_hours``), ona görə
  servis və DB qaydası üst-üstə düşür;
* gecikmiş yazı — ``journal.late_entry_days`` (defolt 0 = yalnız dərs günü): müəllim dərs tarixindən ən çox
  N gün sonra həmin tarixə dərs aça və YENİ qeyd yaza bilər (:class:`EntryRule`);
* aktivləşdirmə pəncərəsi — «Aktivləşdir» yanılıdırsa dərsə YENİ qeyd yalnız aktivləşdirmədən (dərsin
  yaranışından) sonrakı ``journal.activation_write_minutes`` dəqiqədə yazılır. Əvvəlcədən (dərs günündən
  əvvəl) açılmış dərsdə saat dərsin başlama vaxtından sayılır — yoxsa belə dərsə heç vaxt yazmaq olmazdı.

FALLBACK (2026-10-15, sahib «dəqiqə olaraq»): dəqiqə açarı saxlanıbsa o; yoxdursa köhnə saat açarı (×60);
o da yoxdursa defolt 120 dəqiqə (əvvəlki sabit 2 saat qaydası). Gecikmiş yazı və aktivləşdirmə qaydaları
YALNIZ servis qatındadır (DB trigger-i yalnız mövcud xananın dəyişməsini qoruyur); ``create_lesson(allow_past=True)``
və ``save_marks(enforce_day=False)`` (RİM/İKT override, seed, backfill) onları keçir.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import pgettext

_CTX = "registrar.journal_timing"
DEFAULT_WINDOW_MINUTES = 120
LESSON_EDIT_WINDOW = timedelta(minutes=DEFAULT_WINDOW_MINUTES)  # dərs sətri yaranışdan sonra (defolt)
MARK_EDIT_WINDOW = timedelta(minutes=DEFAULT_WINDOW_MINUTES)  # iştirak/bal yazıldıqdan sonra (defolt)


def _window(minutes_key: str, hours_key: str) -> timedelta:
    from core import runtime_settings

    minutes = runtime_settings.override(minutes_key)
    if minutes:
        return timedelta(minutes=int(minutes))
    hours = runtime_settings.override(hours_key)
    if hours:
        return timedelta(hours=int(hours))
    return timedelta(minutes=int(runtime_settings.SPECS[minutes_key].default()))


def lesson_edit_window() -> timedelta:
    return _window("journal.lesson_edit_minutes", "journal.lesson_edit_hours")


def mark_edit_window() -> timedelta:
    return _window("journal.mark_edit_minutes", "journal.mark_edit_hours")


def late_entry_days() -> int:
    from core import runtime_settings

    return max(0, runtime_settings.get_int("journal.late_entry_days"))


def activation_write_window() -> timedelta | None:
    """«Aktivləşdir» söndürülüdə ``None`` (qayda yoxdur)."""
    from core import academic_rules, runtime_settings

    if not academic_rules.lesson_activation_enabled():
        return None
    return timedelta(minutes=runtime_settings.get_int("journal.activation_write_minutes"))


def earliest_entry_date(today=None):
    """Müəllimin dərs açıb yeni qeyd yaza biləcəyi ən erkən dərs tarixi."""
    return (today or timezone.localdate()) - timedelta(days=late_entry_days())


def duration_text(window: timedelta) -> str:
    """İstifadəçi mətni: «2 saat», «90 dəqiqə», «2 saat 30 dəqiqə»."""
    minutes = max(0, int(window.total_seconds() // 60))
    hours, rest = divmod(minutes, 60)
    if hours and not rest:
        return pgettext(_CTX, "%(n)s saat") % {"n": hours}
    if hours and minutes > 90:
        return pgettext(_CTX, "%(h)s saat %(m)s dəqiqə") % {"h": hours, "m": rest}
    return pgettext(_CTX, "%(n)s dəqiqə") % {"n": minutes}


def past_date_error(parsed, *, today=None) -> str:
    """Müəllimin seçdiyi dərs tarixi gecikmiş yazı həddindən köhnədirsə mesaj, yoxsa «»."""
    days = late_entry_days()
    earliest = (today or timezone.localdate()) - timedelta(days=days)
    if parsed >= earliest:
        return ""
    if not days:
        return pgettext(_CTX, "Keçmiş tarixə dərs əlavə etmək olmaz.")
    return pgettext(
        _CTX,
        "Dərs tarixi ən çox %(d)s gün geriyə ola bilər — ən erkən %(date)s. Daha köhnə tarix üçün RİM-ə müraciət edin.",
    ) % {"d": days, "date": earliest.strftime("%d.%m.%Y")}


def activation_start(lesson):
    """Aktivləşdirmə anı: dərsin yaranışı; dərs günündən ƏVVƏL açılıbsa dərsin başlama vaxtı."""
    created = lesson.created_at
    if created is None or timezone.localtime(created).date() >= lesson.date:
        return created or timezone.now()
    start = _dt.datetime.combine(lesson.date, lesson.start_time or _dt.time.min)
    return timezone.make_aware(start, timezone.get_current_timezone())


@dataclass(frozen=True)
class EntryRule:
    """YENİ qeyd (boş xanaya q/b, i/e, bal) qaydası — sorğu başına bir dəfə qurulur, xana-xana yoxlanır."""

    now: _dt.datetime
    today: _dt.date
    late_days: int
    activation_window: timedelta | None

    @classmethod
    def current(cls, *, now=None) -> "EntryRule":
        now = now or timezone.now()
        return cls(
            now=now,
            today=timezone.localdate(now),
            late_days=late_entry_days(),
            activation_window=activation_write_window(),
        )

    @property
    def earliest_date(self):
        return self.today - timedelta(days=self.late_days)

    def block_reason(self, lesson) -> str:
        """Bu dərsə yeni qeyd yazmaq olmursa səbəb, olursa «»."""
        if lesson.date > self.today:
            return pgettext(_CTX, "Gələcək tarixli dərsə qeyd hələ yazıla bilməz.")
        if lesson.date < self.earliest_date:
            if not self.late_days:
                return pgettext(_CTX, "Yeni qeyd yalnız dərsin öz günündə yazılır — keçmiş dərsə yazmaq olmaz.")
            return pgettext(
                _CTX, "Dərs tarixindən %(d)s gündən çox keçib — %(date)s tarixli dərsə yeni qeyd yazmaq olmaz."
            ) % {"d": self.late_days, "date": lesson.date.strftime("%d.%m.%Y")}
        if self.activation_window is not None and self.now > activation_start(lesson) + self.activation_window:
            return pgettext(
                _CTX,
                "Dərs aktivləşdiriləndən %(w)s keçib — q/b, i/e və bal yalnız aktivləşdirmədən sonrakı %(w)s ərzində "
                "yazılır.",
            ) % {"w": duration_text(self.activation_window)}
        return ""

    def allows(self, lesson) -> bool:
        return not self.block_reason(lesson)


def template_context(today=None) -> dict:
    """Jurnal şablonlarının mətnləri faktiki tənzimləməni göstərsin («2 saat» sabit yazılmasın)."""
    today = today or timezone.localdate()
    days = late_entry_days()
    activation = activation_write_window()
    return {
        "lesson_edit_window_label": duration_text(lesson_edit_window()),
        "mark_edit_window_label": duration_text(mark_edit_window()),
        "late_entry_days": days,
        "lesson_date_min": today - timedelta(days=days),
        "activation_write_label": duration_text(activation) if activation is not None else "",
    }


__all__ = [
    "DEFAULT_WINDOW_MINUTES",
    "EntryRule",
    "LESSON_EDIT_WINDOW",
    "MARK_EDIT_WINDOW",
    "activation_start",
    "activation_write_window",
    "duration_text",
    "earliest_entry_date",
    "late_entry_days",
    "lesson_edit_window",
    "mark_edit_window",
    "past_date_error",
    "template_context",
]
