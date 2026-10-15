"""«Sistem tənzimləmələri» bölməsinin yazma / oxuma servisi (sahib 2026-10-03).

İCAZƏ: yalnız RİM rəhbəri (``ikt_rehber`` aktiv üzvlüyü) və superadmin — sahib: «ancaq RİM rəhbərində olsun».
Başqasının adından baxış (view-as) yazmır. Dəyər defolta bərabər yazılanda sətir SİLİNİR (defolt işləsin).
Hər dəyişiklik audit jurnalına köhnə → yeni dəyərlə düşür.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import pgettext

from core import runtime_settings as rs
from core.audit import log_action
from core.constants import AuditAction

_CTX = "accounts.runtime_settings"


class RuntimeSettingsError(Exception):
    def __init__(self, errors: dict):
        super().__init__(errors)
        self.errors = errors


def can_manage(user, request=None) -> bool:
    """RİM rəhbəri və ya superadmin; view-as sessiyası heç vaxt."""
    if not getattr(user, "is_authenticated", False):
        return False
    if request is not None and getattr(request, "session", None) is not None:
        from apps.accounts.services.view_as import get_view_as_state

        if get_view_as_state(request):
            return False
    if user.is_superuser:
        return True
    from apps.organizations.models import Membership

    return Membership.objects.filter(user=user, is_active=True, role__is_active=True, role__name="ikt_rehber").exists()


def _field(spec, stored: dict, meta: dict) -> dict:
    current = rs.get(spec.key)
    default = spec.default()
    item = {
        "key": spec.key,
        "kind": spec.kind,
        "label": str(spec.label),
        "help": str(spec.help or ""),
        "unit": str(spec.unit or ""),
        "min": spec.min,
        "max": spec.max,
        "step": "0.01" if spec.kind == "decimal" else "1",
        # Onluq dəyər mətn kimi (lokal «1,5» number input-u sındırır): forma «1.5» göstərir.
        "value": rs.decimal_text(current) if spec.kind == "decimal" else current,
        "default": rs.decimal_text(default) if spec.kind == "decimal" else default,
        "overridden": spec.key in stored and rs.coerce(spec, stored[spec.key]) is not None,
        "updated_by": meta.get(spec.key, {}).get("by", ""),
        "updated_at": meta.get(spec.key, {}).get("at"),
    }
    if spec.kind == "rate":
        parts = rs._rate_parts(current) or (0, 0)
        default_parts = rs._rate_parts(default) or (0, 0)
        item.update(count=parts[0], window=parts[1], default_count=default_parts[0], default_window=default_parts[1])
    if spec.kind == "choice":
        item["choices"] = [{"value": code, "label": str(label)} for code, label in spec.choices()]
    return item


def describe() -> list:
    """Bölmə üçün: qruplar → sahələr (cari dəyər, defolt, kim/nə vaxt dəyişib)."""
    from apps.accounts.models import RuntimeSetting

    rows = list(RuntimeSetting.objects.select_related("updated_by"))
    stored = {row.key: row.value for row in rows}
    meta = {
        row.key: {
            "by": (row.updated_by.get_full_name() or row.updated_by.username) if row.updated_by_id else "",
            "at": row.updated_at,
        }
        for row in rows
    }
    groups = []
    for group_key, group_label in rs.GROUPS:
        # Gizli (köhnəlmiş) açarlar göstərilmir — bax ``Spec.hidden``.
        fields = [
            _field(spec, stored, meta) for spec in rs.SPECS.values() if spec.group == group_key and not spec.hidden
        ]
        if fields:
            groups.append({"key": group_key, "label": str(group_label), "fields": fields})
    return groups


#: «Standarta qaytar» — sətir silinir, mühitin defoltu işləyir (defolt hədd xaricində olsa belə).
_RESET = object()


def _as_text(spec, value) -> str:
    if spec.kind == "rate":
        parts = rs._rate_parts(value)
        return f"{parts[0]}/{parts[1]}m" if parts else ""
    if spec.kind == "bool":
        # Forma bayrağı «1»/«0» göndərir; ``str(True)`` («True») ilə müqayisə «dəyişib» sanardı.
        coerced = rs.coerce(spec, value)
        return "" if coerced is None else ("1" if coerced else "0")
    if spec.kind == "decimal":
        return rs.decimal_text(value)
    return str(value if value is not None else "")


def _current_text(spec) -> str:
    """Cari dəyərin formada göründüyü şəkil (dəyişiklik olub-olmadığını müqayisə üçün)."""
    return _as_text(spec, rs.get(spec.key))


def _incoming_value(spec, data):
    if spec.kind == "rate":
        count, window = data.get(f"{spec.key}.count"), data.get(f"{spec.key}.window")
        if count in (None, "") and window in (None, ""):
            return None
        return f"{str(count or '').strip()}/{str(window or '').strip()}m"
    raw = data.get(spec.key)
    if raw is None:
        return None
    text = str(raw).strip()
    if spec.kind == "decimal":
        # «1.50» ilə «1.5» eyni dəyərdir — müqayisə normallaşmış mətnlə gedir.
        return rs.decimal_text(text) or text
    return text


#: Bir-biri ilə uyğun olmalı cütlər: (aşağı hədd, yuxarı hədd) — aşağı yuxarıdan böyük ola bilməz.
_ORDERED_PAIRS = (("workload.staff_rate_min", "workload.staff_rate_max"),)


def _pair_errors(planned: dict) -> dict:
    errors = {}
    for low_key, high_key in _ORDERED_PAIRS:
        if low_key not in planned and high_key not in planned:
            continue
        low = planned.get(low_key, rs.get(low_key))
        high = planned.get(high_key, rs.get(high_key))
        low = rs.SPECS[low_key].default() if low is _RESET else low
        high = rs.SPECS[high_key].default() if high is _RESET else high
        if low is not None and high is not None and low > high:
            message = pgettext(_CTX, "Ən az dəyər ən çox dəyərdən böyük ola bilməz.")
            errors.update({key: message for key in (low_key, high_key) if key in planned})
    return errors


def save_values(*, actor, data, request=None) -> dict:
    """Formadan gələn dəyərləri yoxlayıb yazır. ``{"changed": [...]}``; xəta → ``RuntimeSettingsError``."""
    from apps.accounts.models import RuntimeSetting

    errors, planned = {}, {}
    for spec in rs.SPECS.values():
        if spec.hidden:
            continue  # köhnəlmiş açar formadan yazılmır (bazadakı dəyər yalnız fallbackdır)
        incoming = _incoming_value(spec, data)
        if incoming is None or incoming == _current_text(spec):
            # Forma bütün sahələri göndərir — DƏYİŞMƏYƏN sahə yoxlanmır (məs. mühitin hədd xaricindəki defoltu).
            continue
        if incoming == _as_text(spec, spec.default()):
            planned[spec.key] = _RESET
            continue
        value = rs.coerce(spec, incoming)
        if value is None:
            if spec.kind == "choice":
                errors[spec.key] = pgettext(_CTX, "Siyahıdan seçin.")
            elif spec.kind == "bool":
                errors[spec.key] = pgettext(_CTX, "Yandırılmış və ya söndürülmüş olmalıdır.")
            else:
                errors[spec.key] = pgettext(_CTX, "Dəyər %(min)s–%(max)s aralığında olmalıdır.") % {
                    "min": spec.min,
                    "max": spec.max,
                }
            continue
        planned[spec.key] = value
    if not errors:
        errors = _pair_errors(planned)
    if errors:
        raise RuntimeSettingsError(errors)

    changed = []
    with transaction.atomic():
        existing = {row.key: row for row in RuntimeSetting.objects.select_for_update().filter(key__in=planned)}
        # Yeni açar yazılanda / sıfırlananda onun əvəz etdiyi köhnə sətir silinir — sıfırlanmış dəqiqə
        # pəncərəsinin arxasından köhnə saat dəyəri fallback kimi «dirilməsin» (2026-10-15).
        legacy = [rs.SPECS[key].legacy_key for key in planned if rs.SPECS[key].legacy_key]
        if legacy:
            RuntimeSetting.objects.filter(key__in=legacy).delete()
        for key, value in planned.items():
            spec = rs.SPECS[key]
            old = rs.coerce(spec, existing[key].value) if key in existing else None
            default = spec.default()
            if value is _RESET or value == rs.coerce(spec, default):
                if key in existing:
                    existing[key].delete()
                    changed.append(
                        {
                            "key": key,
                            "old": rs.storable(spec, old),
                            "new": rs.storable(spec, default),
                            "reset": True,
                        }
                    )
                continue
            if old == value:
                continue
            RuntimeSetting.objects.update_or_create(
                key=key, defaults={"value": rs.storable(spec, value), "updated_by": actor}
            )
            changed.append(
                {
                    "key": key,
                    "old": rs.storable(spec, old if old is not None else default),
                    "new": rs.storable(spec, value),
                    "reset": False,
                }
            )
        if changed:
            log_action(
                AuditAction.UPDATE,
                user=actor,
                request=request,
                resource_type="core.runtime_settings",
                resource_id="system",
                resource_repr="Sistem tənzimləmələri",
                reason="runtime settings changed",
                changes={"changed": changed},
            )
    rs.invalidate()
    return {"changed": changed}


__all__ = ["RuntimeSettingsError", "can_manage", "describe", "save_values"]
