"""«Passiv saat» — intensiv tədrisin auditoriyadan kənar saatları (sahib 2026-11-12, MR-000303).

Müəllim (Günay Həsənova, 206/6 OT): «fənni intensiv keçirilir. Jurnalda passiv günləri qeyd etmək üçün xana yoxdur.»
Sahib: «passiv saat əlavə etmək olsun».

KÖHNƏ SİSTEM: ayrıca sahə yox idi — iki jurnalda müəllim adi dərs tarixinin xanasına «passiv» / «passiv dərs» yazıb.
Yəni hesablanan qayda yoxdur; burada sadə, ayrıca sayğac qurulur.

QAYDALAR
────────
* Açıqdır: intensiv kurs (``course_format="intensive"``) HƏMİŞƏ; adi açılış — yalnız ``passive_hours_enabled``
  bayrağı ilə (intensiv tədris olunan qrup). 206/6 OT jurnalı adi qrup açılışıdır. Bayrağı jurnal başlığındakı
  «Passiv saat» açarı dəyişir — «Praktiki məşğələ» ilə EYNİ qapı (``workload.distribute`` + kafedra əhatəsi,
  :func:`apps.registrar.practical_toggle.chair_distribute_scope`), həmçinin superadmin / RİM rəhbəri.
* Sətir = tarix + saat (1–8) + qısa qeyd/mövzu. Tarix semestrin başlanğıcı ilə bu gün arasında (intensiv kursda
  ``ends_on``-dan sonra deyil). Gələcək tarix olmur — «keçirilmiş» saatdır.
* Dərs DEYİL: davamiyyət / bal / dərs saatı həddi (#6) / «Keçirilmiş X / Y» / yük / mühasibat dəyişmir. Başlıqda
  ayrıca «Passiv: N saat» kimi görünür.
* Yazı: jurnalın birbaşa redaktoru (``journal_access.is_direct_editor``), jurnal bağlı deyilsə. Hər yazı auditdə.
"""

from __future__ import annotations

import datetime as _dt

from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from .models import PassiveHour
from .models.passive_hours import PASSIVE_HOURS_MAX, PASSIVE_NOTE_MAX_LENGTH

_CTX = "registrar.passive_hours"


class PassiveHourError(Exception):
    """İstifadəçiyə göstərilə bilən imtina."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.text = str(message)


def enabled(offering) -> bool:
    return bool(getattr(offering, "is_intensive", False) or getattr(offering, "passive_hours_enabled", False))


def can_switch(user, offering) -> bool:
    """Adi açılışda bayrağı aç/bağla (intensiv kursda bayraq lazım deyil)."""
    if offering is None or getattr(offering, "is_intensive", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_ikt_rehber", False):
        return True
    from .practical_toggle import chair_distribute_scope

    return chair_distribute_scope(user, offering)


def switch(*, offering, user, on: bool) -> bool:
    """Bayrağı yaz (dəyişibsə ``True``); yazılmış qeydlər bağlananda silinmir — yalnız gizlənir."""
    on = bool(on)
    if offering.passive_hours_enabled == on:
        return False
    offering.passive_hours_enabled = on
    offering.save(update_fields=["passive_hours_enabled", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=user,
        organization=offering.organization,
        obj=offering,
        reason="registrar: «Passiv saat» qeydi (intensiv tədris, sahib 2026-11-12)",
        old_values={"passive_hours_enabled": not on},
        new_values={"passive_hours_enabled": on},
    )
    return True


def can_edit(user, offering) -> bool:
    from .gradebook import journal_is_locked
    from .journal_access import is_direct_editor

    return enabled(offering) and is_direct_editor(user, offering) and not journal_is_locked(offering)


def total_hours(offering) -> int:
    return int(PassiveHour.objects.filter(offering=offering).aggregate(total=Sum("hours"))["total"] or 0)


def _bounds(offering, today):
    period = getattr(offering, "period", None)
    low = getattr(period, "start_date", None) if period is not None else None
    high = today
    if getattr(offering, "is_intensive", False) and offering.ends_on and offering.ends_on < high:
        high = offering.ends_on
    return low, high


def clean(offering, *, day, hours, note, today=None) -> tuple[_dt.date, int, str]:
    today = today or timezone.localdate()
    if isinstance(day, str):
        try:
            day = _dt.date.fromisoformat(day.strip())
        except ValueError:
            day = None
    if not isinstance(day, _dt.date):
        raise PassiveHourError("date", pgettext(_CTX, "Tarixi seçin."))
    low, high = _bounds(offering, today)
    if (low and day < low) or day > high:
        raise PassiveHourError(
            "date",
            pgettext(_CTX, "Passiv saatın tarixi %(lo)s – %(hi)s aralığında olmalıdır.")
            % {"lo": f"{low:%d.%m.%Y}" if low else "—", "hi": f"{high:%d.%m.%Y}"},
        )
    try:
        hours = int(str(hours).strip())
    except (TypeError, ValueError):
        hours = 0
    if not 1 <= hours <= PASSIVE_HOURS_MAX:
        raise PassiveHourError(
            "hours", pgettext(_CTX, "Saat 1 ilə %(max)s arasında olmalıdır.") % {"max": PASSIVE_HOURS_MAX}
        )
    note = " ".join(str(note or "").split())
    if len(note) > PASSIVE_NOTE_MAX_LENGTH:
        raise PassiveHourError(
            "note",
            pgettext(_CTX, "Qeyd ən çox %(max)s simvol ola bilər.") % {"max": PASSIVE_NOTE_MAX_LENGTH},
        )
    return day, hours, note


@transaction.atomic
def add(*, offering, user, day, hours, note="", today=None) -> PassiveHour:
    if not enabled(offering):
        raise PassiveHourError("disabled", pgettext(_CTX, "Bu jurnalda passiv saat qeydi açıq deyil."))
    day, hours, note = clean(offering, day=day, hours=hours, note=note, today=today)
    row = PassiveHour.objects.create(
        organization_id=offering.organization_id,
        offering=offering,
        date=day,
        hours=hours,
        note=note,
        created_by=user,
    )
    _audit(
        AuditAction.CREATE,
        user,
        offering,
        row.pk,
        old=None,
        new={"date": day.isoformat(), "hours": hours, "note": note},
    )
    return row


@transaction.atomic
def remove(*, offering, user, entry_id) -> bool:
    row = PassiveHour.objects.filter(offering=offering, pk=entry_id).first()
    if row is None:
        return False
    old = {"date": row.date.isoformat(), "hours": row.hours, "note": row.note}
    row_id = row.pk
    row.delete()  # Django ``pk``-nı ``None`` edir — audit üçün əvvəlcədən saxlanılır
    _audit(AuditAction.DELETE, user, offering, row_id, old=old, new=None)
    return True


def _audit(action, user, offering, row_id, *, old, new):
    log_action(
        action=action,
        user=user,
        organization=offering.organization,
        old_values=old,
        new_values=new,
        resource_type="registrar.PassiveHour",
        resource_id=str(row_id),
        resource_repr=f"{offering.subject.code} · {pgettext(_CTX, 'Passiv saat')}",
    )


def page_context(user, offering, *, can_edit_journal: bool) -> dict:
    """Jurnal başlığı üçün ``passive_hours``: ``None`` (heç nə göstərilmir) və ya açar + siyahı + cəm + forma URL-ləri."""
    switchable = can_switch(user, offering)
    if not enabled(offering):
        if not switchable:
            return {"passive_hours": None}
        return {"passive_hours": {"enabled": False, "switch_url": _url("switch", offering)}}
    rows = list(PassiveHour.objects.filter(offering=offering).order_by("date", "created_at"))
    editable = bool(can_edit_journal) and can_edit(user, offering)
    if not rows and not editable and not switchable:
        return {"passive_hours": None}
    low, high = _bounds(offering, timezone.localdate())
    return {
        "passive_hours": {
            "enabled": True,
            "rows": rows,
            "total": sum(row.hours for row in rows),
            "can_edit": editable,
            "switch_url": _url("switch", offering) if switchable else "",
            "add_url": _url("add", offering),
            "delete_url": _url("delete", offering),
            "min_date": low,
            "max_date": high,
            "max_hours": PASSIVE_HOURS_MAX,
            "note_max": PASSIVE_NOTE_MAX_LENGTH,
        }
    }


def _url(name, offering):
    return reverse(f"registrar:journal_passive_hours_{name}", args=[offering.pk])


__all__ = [
    "PassiveHourError",
    "add",
    "can_edit",
    "can_switch",
    "clean",
    "enabled",
    "page_context",
    "remove",
    "switch",
    "total_hours",
]
