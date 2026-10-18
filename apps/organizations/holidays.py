"""Bayram və qeyri-iş günləri — OXU (keşli iş təqvimi) + YAZI servisləri (sahib 2026-10-19).

İSTEHLAKÇILAR (bayram / qeyri-iş günü = iş və dərs günü DEYİL):

* Mühasibatlıq — planın aylara bölgüsü (``accounts.services.accounting.periods.teaching_day_set``);
* «Keçilmiş dərslər» → «Cədvəldə var, qeydə alınmayıb» (``registrar.lessons_log_unrecorded``);
* keçmiş dərslərin bərpası (``registrar.lesson_backfill``) — bayramda dərs YARADILMIR;
* müraciətlərin cavab müddəti (``applications.sla``) — iş günü hesabı.

``workday`` («iş günü köçürməsi») — şənbə/bazar İŞ GÜNÜ elan olunub: iş günü hesablarında (SLA, mühasibatlıq)
iş günü sayılır; dərs cədvəli tərəfə təsiri yoxdur (cədvəl slotları həftə gününə bağlıdır).

KEŞ (sorğu sayı düz qalsın): təşkilat × TƏQVİM İLİ üzrə ``{tarix: növ}`` xəritəsi — iki qat:
proses daxili (``LOCAL_TTL``) + paylaşılan keş (``CACHE_TTL``, Redis). Yazı (model ``save``/``delete``,
toplu əlavə) :func:`invalidate` çağırır. Başqa prosesin lokal keşi ən çoxu ``LOCAL_TTL`` saniyə köhnə qala bilər.

İNVALİDASİYA TRANZAKSİYADAN SONRA (rəy 2026-10-19): prod-da ``ATOMIC_REQUESTS=True`` — yazı sorğunun
tranzaksiyasının içindədir. Paylaşılan keş ``transaction.on_commit``-də silinir (commit-dən əvvəl silinsəydi,
paralel oxu KÖHNƏ dəyəri yenidən 6 saatlıq keşə yazardı). Lokal qeyd dərhal götürülür və açar commit-ə qədər
«gözləyən» sayılır (``PENDING_TTL``): bu müddətdə oxu bazaya gedir, nəticəni HEÇ BİR keşə yazmır — öz
tranzaksiyasının hələ commit olunmamış (və ya geri alınacaq) sətirləri keşə düşməsin.

RLS: oxu ``bypass_rls()`` + AÇIQ ``organization_id`` süzgəci ilə gedir — təqvim gizli məlumat deyil, amma
fon işlərində (cron: ``close_stale_resolved``) tenant konteksti olmur və RLS boş nəticə verərdi; boş nəticə
keşə yazılsa sorğu kontekstindəki istifadəçilər də bayramsız təqvim görərdi.
"""

from __future__ import annotations

import time
import uuid
from datetime import date

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils.translation import pgettext

from .holiday_models import NON_WORKING_KINDS, AcademicHoliday, HolidayKind

_CTX = "organizations.holiday"

CACHE_TTL = 6 * 60 * 60
LOCAL_TTL = 60
#: Geri alınan tranzaksiyanın (``on_commit`` heç vaxt çağırılmır) açarı ən çoxu bu qədər keşsiz qalır.
PENDING_TTL = 120
_KEY = "emsarena:organizations:holidays:{org}:{year}"
_local: dict = {}
_pending: dict = {}

#: Bazar ertəsi – cümə (``date.weekday()``).
WORK_WEEKDAYS = (0, 1, 2, 3, 4)

#: SABİT tarixli rəsmi bayramlar (Azərbaycan Respublikası Əmək Məcəlləsi, m. 105) — (ay, gün, ad).
#: Ramazan və Qurban bayramları (Hicri təqvim) və hökumətin iş günü köçürmələri hər il ƏL İLƏ daxil edilir.
_H, _OFF = "holiday", "day_off"
FIXED_PUBLIC_HOLIDAYS = (
    (1, 1, "Yeni il", _H),
    (1, 2, "Yeni il", _H),
    # Əmək Məcəlləsi m. 105: bayram deyil, amma QEYRİ-İŞ GÜNÜDÜR (Ümumxalq hüzn günü).
    (1, 20, "Ümumxalq hüzn günü", _OFF),
    (3, 8, "Qadınlar günü", _H),
    (3, 20, "Novruz bayramı", _H),
    (3, 21, "Novruz bayramı", _H),
    (3, 22, "Novruz bayramı", _H),
    (3, 23, "Novruz bayramı", _H),
    (3, 24, "Novruz bayramı", _H),
    (5, 9, "Faşizm üzərində qələbə günü", _H),
    (5, 28, "Müstəqillik günü", _H),
    (6, 15, "Azərbaycan xalqının Milli Qurtuluş günü", _H),
    (6, 26, "Azərbaycan Respublikasının Silahlı Qüvvələri günü", _H),
    (11, 8, "Zəfər günü", _H),
    (11, 9, "Dövlət Bayrağı günü", _H),
    (12, 31, "Dünya azərbaycanlılarının həmrəyliyi günü", _H),
)


class HolidayError(Exception):
    """Doğrulama / tapılmama — HTTP qatı ``status`` + ``field`` qaytarır (pozisional konstruktor, B042)."""

    def __init__(self, message, code="invalid", field="", status=400):
        super().__init__(message, code, field, status)
        self.message = str(message)
        self.code = code
        self.field = field
        self.status = status


# ── Oxu (keşli) ──────────────────────────────────────────────────────────────


def _org_id(organization) -> str:
    return str(getattr(organization, "pk", organization) or "")


def _load_year(org_id: str, year: int) -> dict:
    from core.rls import bypass_rls

    with bypass_rls():
        rows = AcademicHoliday.objects.filter(organization_id=org_id, date__year=year).values_list("date", "kind")
        return {day.isoformat(): kind for day, kind in rows}


def year_map(organization, year: int) -> dict:
    """``{"YYYY-MM-DD": növ}`` — təşkilatın bir təqvim ilindəki qeydləri (keşli)."""
    org_id = _org_id(organization)
    if not org_id:
        return {}
    key = _KEY.format(org=org_id, year=int(year))
    now = time.monotonic()
    if _pending.get(key, 0) > now:
        return _load_year(org_id, int(year))  # yazı hələ commit olunmayıb — keşə toxunulmur
    _pending.pop(key, None)
    hit = _local.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    data = None
    try:
        data = cache.get(key)
    except Exception:  # noqa: BLE001 — Redis əlçatmazdırsa bazaya düş
        data = None
    if not isinstance(data, dict):
        data = _load_year(org_id, int(year))
        try:
            cache.set(key, data, CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    if len(_local) > 512:
        _local.clear()
    _local[key] = (now + LOCAL_TTL, data)
    return data


def invalidate(organization, years) -> None:
    """Lokal qeyd DƏRHAL götürülür; paylaşılan keş commit-dən SONRA silinir (bax modul sənədi)."""
    org_id = _org_id(organization)
    keys = [_KEY.format(org=org_id, year=int(year)) for year in years]
    until = time.monotonic() + PENDING_TTL
    for key in keys:
        _local.pop(key, None)
        _pending[key] = until

    def _after_commit():
        for key in keys:
            _local.pop(key, None)
            _pending.pop(key, None)
        try:
            cache.delete_many(keys)
        except Exception:  # noqa: BLE001
            pass

    transaction.on_commit(_after_commit)


class WorkCalendar:
    """Təşkilatın iş təqvimi — bayram / qeyri-iş günü / iş gününə köçürülmüş istirahət günü.

    ``day in calendar`` → gün İŞ GÜNÜ DEYİL (bayram və ya qeyri-iş günü); köhnə ``holidays`` (tarix çoxluğu)
    arqumentləri ilə uyğundur. Bir obyekt daxilində hər təqvim ili BİR dəfə oxunur.
    """

    def __init__(self, organization):
        self.organization_id = _org_id(organization)
        self._years: dict = {}

    def _year(self, year: int) -> dict:
        if year not in self._years:
            self._years[year] = year_map(self.organization_id, year) if self.organization_id else {}
        return self._years[year]

    def kind(self, day: date) -> str:
        return self._year(day.year).get(day.isoformat(), "")

    def is_non_working(self, day: date) -> bool:
        return self.kind(day) in NON_WORKING_KINDS

    def is_extra_workday(self, day: date) -> bool:
        return self.kind(day) == HolidayKind.WORKDAY.value

    def is_working_day(self, day: date, weekdays=WORK_WEEKDAYS) -> bool:
        kind = self.kind(day)
        if kind == HolidayKind.WORKDAY.value:
            return True
        if kind in NON_WORKING_KINDS:
            return False
        return day.weekday() in weekdays

    def __contains__(self, day) -> bool:
        return isinstance(day, date) and self.is_non_working(day)

    def non_working_between(self, start: date, end: date) -> set:
        days: set = set()
        for year in range(start.year, end.year + 1):
            for iso, kind in self._year(year).items():
                day = date.fromisoformat(iso)
                if start <= day <= end and kind in NON_WORKING_KINDS:
                    days.add(day)
        return days

    def extra_workdays_between(self, start: date, end: date) -> set:
        days: set = set()
        for year in range(start.year, end.year + 1):
            for iso, kind in self._year(year).items():
                day = date.fromisoformat(iso)
                if start <= day <= end and kind == HolidayKind.WORKDAY.value:
                    days.add(day)
        return days


def work_calendar(organization) -> WorkCalendar:
    return WorkCalendar(organization)


# ── Akademik il köməkçiləri ──────────────────────────────────────────────────


def academic_year_start(academic_year) -> int | None:
    """«2026/2027» / «2026-2027» / «2026» → 2026; tanınmasa ``None``."""
    text = str(academic_year or "").strip()
    digits = text[:4]
    if len(digits) == 4 and digits.isdigit() and 1990 < int(digits) < 2200:
        return int(digits)
    return None


def academic_year_bounds(start_year: int) -> tuple[date, date]:
    """Tədris ili: 1 sentyabr — növbəti ilin 31 avqustu."""
    return date(start_year, 9, 1), date(start_year + 1, 8, 31)


def academic_year_label(start_year: int) -> str:
    return f"{start_year}/{start_year + 1}"


def current_academic_year_start(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 9 else today.year - 1


def fixed_holidays_for(start_year: int) -> list:
    """Tədris ilinin sabit tarixli günləri — ``[(tarix, ad, növ)]`` (sentyabr–dekabr: ``start_year``, qalanı +1)."""
    items = []
    for month, day, name, kind in FIXED_PUBLIC_HOLIDAYS:
        year = start_year if month >= 9 else start_year + 1
        items.append((date(year, month, day), name, kind))
    return sorted(items)


def holidays_between(organization, start: date, end: date):
    """UI siyahısı — adi ORM (sorğu kontekstinin RLS-i ilə)."""
    return AcademicHoliday.objects.filter(organization=organization, date__gte=start, date__lte=end).order_by("date")


# ── Yazı ─────────────────────────────────────────────────────────────────────


def _audit(action, *, actor, organization, obj, request, reason, old=None, new=None):
    from core.audit import log_action

    log_action(
        action=action,
        user=actor,
        organization=organization,
        obj=obj,
        request=request,
        reason=reason,
        old_values=old,
        new_values=new,
    )


def _snapshot(holiday) -> dict:
    return {"date": holiday.date.isoformat(), "name": holiday.name, "kind": holiday.kind, "note": holiday.note}


def _parse_date(raw):
    try:
        value = date.fromisoformat(str(raw or "").strip())
    except ValueError:
        raise HolidayError(pgettext(_CTX, "Tarix düzgün deyil."), code="bad_date", field="date") from None
    if not 2000 <= value.year <= 2100:
        raise HolidayError(pgettext(_CTX, "Tarix düzgün deyil."), code="bad_date", field="date")
    return value


def _find(organization, holiday_id):
    """Təşkilatın öz qeydi; yanlış / yad id → ``None`` (çağıran 404 verir)."""
    try:
        pk = uuid.UUID(str(holiday_id or "").strip())
    except ValueError:
        return None
    return AcademicHoliday.objects.filter(organization=organization, pk=pk).first()


def save_holiday(*, organization, actor, request=None, holiday_id="", raw_date="", name="", kind="", note=""):
    """Yarat / redaktə et → ``(holiday, created)``; səhv → :class:`HolidayError`."""
    from core.constants import AuditAction

    day = _parse_date(raw_date)
    name = (name or "").strip()[:150]
    note = (note or "").strip()[:300]
    kind = (kind or "").strip() or HolidayKind.HOLIDAY.value
    if not name:
        raise HolidayError(pgettext(_CTX, "Günün adı boş ola bilməz."), code="name_required", field="name")
    if kind not in HolidayKind.values:
        raise HolidayError(pgettext(_CTX, "Günün növü düzgün deyil."), code="bad_kind", field="kind")
    if kind == HolidayKind.WORKDAY.value and day.weekday() < 5:
        raise HolidayError(
            pgettext(
                _CTX, "«İş günü köçürməsi» yalnız şənbə və ya bazar gününə yazılır — həmin gün iş günü elan olunur."
            ),
            code="workday_on_weekday",
            field="kind",
        )

    holiday_id = (holiday_id or "").strip()
    old = None
    if holiday_id:
        holiday = _find(organization, holiday_id)
        if holiday is None:
            raise HolidayError(pgettext(_CTX, "Qeyd tapılmadı."), code="not_found", status=404)
        old = _snapshot(holiday)
    else:
        holiday = AcademicHoliday(organization=organization, created_by=actor if getattr(actor, "pk", None) else None)
    created = not holiday_id
    holiday.date, holiday.name, holiday.kind, holiday.note = day, name, kind, note
    try:
        with transaction.atomic():
            holiday.save()
    except IntegrityError:
        raise HolidayError(
            pgettext(_CTX, "Bu tarix artıq təqvimdədir — mövcud qeydi redaktə edin."), code="duplicate", field="date"
        ) from None
    _audit(
        AuditAction.CREATE if created else AuditAction.UPDATE,
        actor=actor,
        organization=organization,
        obj=holiday,
        request=request,
        reason="calendar: holiday saved",
        old=old,
        new=_snapshot(holiday),
    )
    return holiday, created


def delete_holiday(*, organization, actor, request=None, holiday_id=""):
    from core.constants import AuditAction

    holiday = _find(organization, holiday_id)
    if holiday is None:
        raise HolidayError(pgettext(_CTX, "Qeyd tapılmadı."), code="not_found", status=404)
    old = _snapshot(holiday)
    _audit(
        AuditAction.DELETE,
        actor=actor,
        organization=organization,
        obj=holiday,
        request=request,
        reason="calendar: holiday removed",
        old=old,
    )
    holiday.delete()
    return old


def seed_fixed_holidays(*, organization, actor, request=None, start_year: int) -> dict:
    """Tədris ilinin SABİT tarixli bayramlarını əlavə edir — mövcud tarixlər ATLANIR (idempotent)."""
    from core.constants import AuditAction

    items = fixed_holidays_for(start_year)
    first, last = items[0][0], items[-1][0]
    taken = set(
        AcademicHoliday.objects.filter(organization=organization, date__gte=first, date__lte=last).values_list(
            "date", flat=True
        )
    )
    creator = actor if getattr(actor, "pk", None) else None
    fresh = [
        AcademicHoliday(organization=organization, date=day, name=name, kind=kind, created_by=creator)
        for day, name, kind in items
        if day not in taken
    ]
    if fresh:
        with transaction.atomic():
            AcademicHoliday.objects.bulk_create(fresh, ignore_conflicts=True)
        invalidate(organization, {item.date.year for item in fresh})
    result = {
        "academic_year": academic_year_label(start_year),
        "created": len(fresh),
        "skipped": len(items) - len(fresh),
        "dates": [item.date.isoformat() for item in fresh],
    }
    _audit(
        AuditAction.CREATE,
        actor=actor,
        organization=organization,
        obj=organization,
        request=request,
        reason="calendar: fixed public holidays seeded",
        new=result,
    )
    return result


__all__ = [
    "CACHE_TTL",
    "FIXED_PUBLIC_HOLIDAYS",
    "HolidayError",
    "WORK_WEEKDAYS",
    "WorkCalendar",
    "academic_year_bounds",
    "academic_year_label",
    "academic_year_start",
    "current_academic_year_start",
    "delete_holiday",
    "fixed_holidays_for",
    "holidays_between",
    "invalidate",
    "save_holiday",
    "seed_fixed_holidays",
    "work_calendar",
    "year_map",
]
