"""Jurnal vaxt qaydaları (RİM rəhbəri «Sistem tənzimləmələri»ndən dəyişir; sahib 2026-10-03 / 2026-10-15 / 2026-10-25).

SAHİB 2026-10-25: «1 həftəlik aktiv saxlayacağıq ki, müəllim keçən həftədə datanı yazmadıqlarını yaza bilsin …
müəllim kiməsə q/b və ya bal yazıbsa, yazdığından 15 dəqiqə sonra onu geri dəyişə bilməsin, olduğu kimi qalsın.
Bunun üçün RİM-ə müraciət edib təqdimat yazmaq lazım olduğunu qeyd etsin.» Ona görə defoltlar:
``journal.late_entry_days`` = 7 (YAZMA PƏNCƏRƏSİ: dərs tarixindən 7 gün sonrayadək dərs açmaq və boş xanaya
yazmaq olur; gələcək tarix olmaz — :func:`lesson_date_error` / :class:`EntryRule`) və ``journal.mark_edit_minutes``
= 15 (XANA KİLİDİ: ilk yazılışdan — ``LessonMark.created_at`` — 15 dəqiqə sonra xana donur; köçürülmüş xana,
``entered_by`` boş, həmişə kilidlidir — :func:`mark_lock_reason`). Kilidli xananın mesajı :func:`lock_message`.

SAHİB 2026-10-26: «15 dəqiqə sonra i/e-ni dəyişmək olmur — onu dəyişmək olsun; qb-ni və balı dəyişmək olmasın.»
Ona görə kilid YALNIZ q/b (və üzrlü qayıb) və BAL daşıyan xanaya düşür. Balsız i/e xanası (``status=present``,
``score`` boş — :func:`is_open_presence`) pəncərədən sonra da, köçürülmüş olsa da dəyişir, amma YENİ qeyd kimi:
dərsə yeni qeyd yazmaq olursa (:class:`EntryRule` — 7 günlük yazma pəncərəsi, aktivləşdirmə pəncərəsi). Müddəti
bitmiş dərsin i/e xanası ``LOCK_ENTRY`` ilə kilidlidir. Pəncərədən sonra dəyişdirilən i/e xanasının kilid saatı
YENİDƏN başlayır (``created_at`` = dəyişiklik anı): yeni q/b/bal da yazılışından 15 dəqiqə sonra donur.
DB trigger-i (registrar 0106) eyni istisnanı edir — ``registrar_lessonmark``-da köhnə dəyəri balsız i/e olan
sətrin UPDATE-i pəncərədən asılı deyil (yazma pəncərəsi isə yalnız servis qatındadır).

* dərs sətri (tarix/növ/mövzu/saat/silmə) — yaranışdan sonra ``lesson_edit_window()``;
* q/b və bal — yazılışdan sonra ``mark_edit_window()`` (balsız i/e — yazma pəncərəsi); Postgres trigger-i eyni açarları oxuyur
  (registrar 0089: əvvəl ``journal.mark_edit_minutes``, sonra köhnə ``journal.mark_edit_hours``), ona görə
  servis və DB qaydası üst-üstə düşür;
* gecikmiş yazı — ``journal.late_entry_days`` (defolt 7; 0 = yalnız dərs günü): müəllim dərs tarixindən ən çox
  N gün sonra həmin tarixə dərs aça və YENİ qeyd yaza bilər (:class:`EntryRule`);
* aktivləşdirmə pəncərəsi — «Aktivləşdir» yanılıdırsa dərsə YENİ qeyd yalnız aktivləşdirmədən (dərsin
  yaranışından) sonrakı ``journal.activation_write_minutes`` dəqiqədə yazılır. Əvvəlcədən (dərs günündən
  əvvəl) açılmış dərsdə saat dərsin başlama vaxtından sayılır — yoxsa belə dərsə heç vaxt yazmaq olmazdı.

FALLBACK (2026-10-15, sahib «dəqiqə olaraq»): dəqiqə açarı saxlanıbsa o; yoxdursa köhnə saat açarı (×60);
o da yoxdursa açarın defoltu (xana: 15 dəqiqə — sahib 2026-10-25; dərs sətri: 120 dəqiqə). Gecikmiş yazı və aktivləşdirmə qaydaları
YALNIZ servis qatındadır (DB trigger-i yalnız mövcud xananın dəyişməsini qoruyur); ``create_lesson(allow_past=True)``
və ``save_marks(enforce_day=False)`` (RİM/İKT override, seed, backfill) onları keçir.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar.models import AttendanceStatus

_CTX = "registrar.journal_timing"
DEFAULT_WINDOW_MINUTES = 120
DEFAULT_MARK_LOCK_MINUTES = 15  # sahib 2026-10-25: xana ilk yazılışdan 15 dəqiqə sonra donur
DEFAULT_LATE_ENTRY_DAYS = 7  # sahib 2026-10-25: «1 həftəlik aktiv saxlayacağıq»
LESSON_EDIT_WINDOW = timedelta(minutes=DEFAULT_WINDOW_MINUTES)  # dərs sətri yaranışdan sonra (defolt)
MARK_EDIT_WINDOW = timedelta(minutes=DEFAULT_MARK_LOCK_MINUTES)  # iştirak/bal ilk yazılışdan sonra (defolt)

#: Xana kilidinin səbəbi (:func:`mark_lock_reason`).
LOCK_TIME = "time"  # müəllim yazıb, pəncərə bitib
LOCK_LEGACY = "legacy"  # köhnə sistemdən köçürülüb (``entered_by`` boş)
LOCK_CORRECTED = "corrected"  # RİM-in rəsmi (sənədli) düzəlişi var
LOCK_ENTRY = "entry"  # balsız i/e xanası, amma dərsin yazma müddəti bitib (sahib 2026-10-26)

#: «RİM-ə müraciət edib təqdimat yazın» keçidinin müraciət növü — müəllimin göndərə bildiyi və RİM-ə gedən
#: YEGANƏ növ «Texniki problem»dir (qeydi: «Sistemə giriş, jurnal, e-poçt»). Ayrıca «Jurnal düzəlişi» növü
#: kataloqa əlavə olunsa yalnız bu sabit dəyişir.
FIX_APPLICATION_KIND = "texniki"


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


def earliest_entry_date(today=None, *, days=None):
    """Müəllimin dərs açıb yeni qeyd yaza biləcəyi ən erkən dərs tarixi (YAZMA PƏNCƏRƏSİNİN TƏK hesabı)."""
    return (today or timezone.localdate()) - timedelta(days=late_entry_days() if days is None else days)


def duration_text(window: timedelta) -> str:
    """İstifadəçi mətni: «2 saat», «90 dəqiqə», «2 saat 30 dəqiqə»."""
    minutes = max(0, int(window.total_seconds() // 60))
    hours, rest = divmod(minutes, 60)
    if hours and not rest:
        return pgettext(_CTX, "%(n)s saat") % {"n": hours}
    if hours and minutes > 90:
        return pgettext(_CTX, "%(h)s saat %(m)s dəqiqə") % {"h": hours, "m": rest}
    return pgettext(_CTX, "%(n)s dəqiqə") % {"n": minutes}


def lesson_date_error(parsed, *, today=None) -> str:
    """Müəllimin seçdiyi dərs tarixi yazma pəncərəsindən kənardırsa mesaj, yoxsa «».

    Gələcək tarix olmaz; ən erkən :func:`earliest_entry_date`. Dərs yaratma/redaktə (servis), modalın tarix
    seçicisi (``min``/``max`` — :func:`template_context`) və boş xanaya yazı (:class:`EntryRule`) eyni həddədir.
    """
    today = today or timezone.localdate()
    if parsed > today:
        return pgettext(_CTX, "Gələcək tarixə dərs əlavə etmək olmaz.")
    days = late_entry_days()
    earliest = earliest_entry_date(today, days=days)
    if parsed >= earliest:
        return ""
    if not days:
        return pgettext(_CTX, "Keçmiş tarixə dərs əlavə etmək olmaz.")
    return pgettext(
        _CTX,
        "Dərs tarixi ən çox %(d)s gün geriyə ola bilər — ən erkən %(date)s. Daha köhnə tarix üçün RİM-ə müraciət edin.",
    ) % {"d": days, "date": earliest.strftime("%d.%m.%Y")}


# Köhnə ad (indi gələcək tarixi də yoxlayır).
past_date_error = lesson_date_error


def is_open_presence(mark) -> bool:
    """Balsız i/e xanası (``status=present``, ``score`` boş) — pəncərədən sonra da dəyişə bilən YEGANƏ dəyər."""
    return mark is not None and mark.status == AttendanceStatus.PRESENT and mark.score is None


def _within_window(mark, *, now, window) -> bool:
    """Müəllimin yazdığı xana İLK yazılışından pəncərə ərzindədir (köçürülmüş xana heç vaxt)."""
    if getattr(mark, "entered_by_id", None) is None:
        return False
    return (now - mark.created_at) <= (window if window is not None else mark_edit_window())


def reopens_presence(mark, *, now=None, window=None) -> bool:
    """Pəncərədən kənar (və ya köçürülmüş) balsız i/e xanası — dəyişikliyi YENİ qeyd kimi yazılır
    (:class:`EntryRule`-a tabedir, kilid saatı yenidən başlayır; sahib 2026-10-26)."""
    return is_open_presence(mark) and not _within_window(mark, now=now or timezone.now(), window=window)


def mark_lock_reason(mark, *, now=None, window=None, entry_open=True) -> str:
    """Müəllim bu xananı DƏYİŞƏ bilmirsə səbəb (``LOCK_TIME`` / ``LOCK_LEGACY`` / ``LOCK_ENTRY``), bilirsə «».

    Boş xana (``None``) kilidli deyil (yeni qeyd :class:`EntryRule`-a tabedir). Kilid İLK yazılışdan
    (``created_at``) sayılır — sonrakı düzəliş saatı uzatmır. Kilid YALNIZ q/b və bal daşıyan xanaya düşür
    (sahib 2026-10-26): balsız i/e xanası pəncərədən sonra da dəyişir, bu dərsə yeni qeyd yazmaq olursa
    (``entry_open`` — çağıran ``EntryRule.allows(lesson)`` ötürür), olmursa ``LOCK_ENTRY``. Rəsmi düzəliş
    kilidi ayrıca yoxlanır (sorğu tələb edir). Sistem yazıları (midterm/imtahan sinxronu, rəsmi düzəliş) bu
    qaydaya tabe deyil.
    """
    if mark is None:
        return ""
    now = now or timezone.now()
    if _within_window(mark, now=now, window=window):
        return ""
    if is_open_presence(mark):
        return "" if entry_open else LOCK_ENTRY
    if getattr(mark, "entered_by_id", None) is None:
        return LOCK_LEGACY
    return LOCK_TIME


def lock_message(reason: str, *, window=None) -> str:
    """Kilidli xananın istifadəçi mətni (UI dialoqu, forma xəbərdarlığı, avtomatik yadda saxlamanın 409-u)."""
    if reason == LOCK_LEGACY:
        return pgettext(
            _CTX,
            "Bu qeyd köhnə sistemdən köçürülüb və dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə müraciət edib "
            "təqdimat yazın.",
        )
    if reason == LOCK_CORRECTED:
        return pgettext(
            _CTX,
            "Bu xanaya rəsmi düzəliş edilib və dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə müraciət edib "
            "təqdimat yazın.",
        )
    if reason == LOCK_ENTRY:
        return pgettext(
            _CTX,
            "Bu dərsin yazma müddəti bitib — i/e qeydi artıq dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə müraciət "
            "edib təqdimat yazın.",
        )
    minutes = max(1, int((window if window is not None else mark_edit_window()).total_seconds() // 60))
    return pgettext(
        _CTX,
        "Bu q/b və ya bal %(m)s dəqiqədən çox əvvəl yazılıb və dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə "
        "müraciət edib təqdimat yazın.",
    ) % {"m": minutes}


def fix_request_url() -> str:
    """«RİM-ə müraciət» keçidi — Müraciətlər bölməsi, növ öncədən seçilmiş (``?new_kind=``)."""
    from django.urls import reverse

    return "%s?section=applications&new_kind=%s" % (reverse("accounts:profile"), FIX_APPLICATION_KIND)


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
        return earliest_entry_date(self.today, days=self.late_days)

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
    mark_window = mark_edit_window()
    return {
        "lesson_edit_window_label": duration_text(lesson_edit_window()),
        "mark_edit_window_label": duration_text(mark_window),
        "late_entry_days": days,
        "lesson_date_min": earliest_entry_date(today, days=days),
        "lesson_date_max": today,
        "activation_write_label": duration_text(activation) if activation is not None else "",
        # Kilidli xana dialoqu (journal_mark_lock.js) — mətnlər cədvəlin data-atributlarına bir dəfə yazılır.
        "mark_lock_messages": {
            LOCK_TIME: lock_message(LOCK_TIME, window=mark_window),
            LOCK_LEGACY: lock_message(LOCK_LEGACY),
            LOCK_ENTRY: lock_message(LOCK_ENTRY),
        },
        "mark_lock_request_url": fix_request_url(),
    }


__all__ = [
    "DEFAULT_LATE_ENTRY_DAYS",
    "DEFAULT_MARK_LOCK_MINUTES",
    "DEFAULT_WINDOW_MINUTES",
    "EntryRule",
    "FIX_APPLICATION_KIND",
    "LESSON_EDIT_WINDOW",
    "LOCK_CORRECTED",
    "LOCK_ENTRY",
    "LOCK_LEGACY",
    "LOCK_TIME",
    "MARK_EDIT_WINDOW",
    "activation_start",
    "activation_write_window",
    "duration_text",
    "earliest_entry_date",
    "fix_request_url",
    "is_open_presence",
    "late_entry_days",
    "lesson_date_error",
    "lesson_edit_window",
    "lock_message",
    "mark_edit_window",
    "mark_lock_reason",
    "past_date_error",
    "reopens_presence",
    "template_context",
]
