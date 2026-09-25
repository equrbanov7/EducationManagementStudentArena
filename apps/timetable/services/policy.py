"""Qrup növbə siyasəti — pillə defoltları və qrup istisnaları (audit ilə).

Sahibin qaydası: magistr dərsi SƏHƏR qoyulmur (defolt: yalnız axşam); bakalavr
səhər + günorta; qiyabi qruplar həftəlik cədvələ susmaya görə daxil edilmir.
Koordinator istənilən qrup üçün bunu dəyişə bilər (məs. 1-ci kurs yalnız səhər).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction
from django.utils.translation import pgettext

from apps.registrar.public import schedule_grid

from ..constants import BAND_CODES, BUILTIN_POLICY, Band, PolicyLevel
from ..sources.groups import load_groups, policy_rows, prune_groups, resolve_policy

_CTX = "timetable.policy"


class PolicyError(Exception):
    def __init__(self, message, errors=None):
        errors = dict(errors or {})
        super().__init__(message, errors)
        self.message = message
        self.errors = errors


def _model():
    return django_apps.get_model("timetable", "GroupTimePolicy")


def clean(organization, data, *, allow_empty_bands=False) -> dict:
    errors: dict = {}
    bands = [str(b) for b in (data.get("bands") or []) if str(b) in BAND_CODES]
    bands = [code for code in BAND_CODES if code in bands]
    if not bands and not allow_empty_bands:
        errors["bands"] = pgettext(_CTX, "Ən azı bir növbə seçilməlidir.")
    weekdays = sorted({int(d) for d in (data.get("weekdays") or []) if str(d).isdigit() and 1 <= int(d) <= 7})
    pairs = len(schedule_grid.lesson_periods(organization))
    max_pairs = data.get("max_pairs_per_day")
    if max_pairs in (None, ""):
        max_pairs = None
    else:
        try:
            max_pairs = int(max_pairs)
        except (TypeError, ValueError):
            max_pairs = -1
        if not 1 <= max_pairs <= pairs:
            errors["max_pairs_per_day"] = pgettext(_CTX, "Gündəlik limit 1–%(max)s aralığında olmalıdır.") % {
                "max": pairs
            }
    if errors:
        raise PolicyError(pgettext(_CTX, "Siyasət yadda saxlanılmadı — sahələri yoxlayın."), errors)
    return {
        "bands": bands,
        "weekdays": weekdays,
        "max_pairs_per_day": max_pairs,
        "is_excluded": bool(data.get("is_excluded")),
        "note": str(data.get("note") or "").strip()[:500],
    }


def _audit(action, *, actor, organization, row, old, request, label):
    from core.audit import log_action

    log_action(
        action,
        user=actor,
        organization=organization,
        obj=row,
        old_values=old or None,
        new_values={
            "bands": row.bands,
            "weekdays": row.weekdays,
            "max_pairs_per_day": row.max_pairs_per_day,
            "is_excluded": row.is_excluded,
        },
        request=request,
        resource_type="timetable.GroupTimePolicy",
        resource_id=str(row.pk),
        resource_repr=label,
    )


def _snapshot(row):
    if row is None:
        return {}
    return {
        "bands": row.bands,
        "weekdays": row.weekdays,
        "max_pairs_per_day": row.max_pairs_per_day,
        "is_excluded": row.is_excluded,
    }


def save_level(*, actor, organization, level, data, request=None):
    from core.constants import AuditAction

    if level not in dict(PolicyLevel.choices):
        raise PolicyError(pgettext(_CTX, "Naməlum pillə."))
    cleaned = clean(organization, data)
    with transaction.atomic():
        row = (
            _model()
            .objects.select_for_update()
            .filter(organization=organization, group__isnull=True, level=level)
            .first()
        )
        old = _snapshot(row)
        row = row or _model()(organization=organization, level=level)
        for field, value in cleaned.items():
            setattr(row, field, value)
        row.updated_by = actor if getattr(actor, "pk", None) else None
        row.save()
        _audit(
            AuditAction.UPDATE if old else AuditAction.CREATE,
            actor=actor,
            organization=organization,
            row=row,
            old=old,
            request=request,
            label=str(dict(PolicyLevel.choices)[level]),
        )
    return row


def save_group(*, actor, organization, group, data, request=None):
    """Qrup istisnası; ``data["reset"]`` → istisna silinir (defolta qayıdış, audit ilə)."""
    from core.constants import AuditAction

    Model = _model()
    with transaction.atomic():
        row = Model.objects.select_for_update().filter(organization=organization, group=group).first()
        old = _snapshot(row)
        if data.get("reset"):
            if row is not None:
                _audit(
                    AuditAction.DELETE,
                    actor=actor,
                    organization=organization,
                    row=row,
                    old=old,
                    request=request,
                    label=group.name,
                )
                row.delete()
            return None
        cleaned = clean(organization, data, allow_empty_bands=True)
        row = row or Model(organization=organization, group=group)
        for field, value in cleaned.items():
            setattr(row, field, value)
        row.updated_by = actor if getattr(actor, "pk", None) else None
        row.save()
        _audit(
            AuditAction.UPDATE if old else AuditAction.CREATE,
            actor=actor,
            organization=organization,
            row=row,
            old=old,
            request=request,
            label=group.name,
        )
    return row


def level_rows(organization) -> list:
    _by_group, by_level = policy_rows(organization)
    out = []
    for level, label in PolicyLevel.choices:
        row = by_level.get(level)
        builtin = BUILTIN_POLICY[level]
        out.append(
            {
                "level": level,
                "label": str(label),
                "bands": list(row.bands) if row is not None and row.bands else list(builtin["bands"]),
                "max_pairs_per_day": (row.max_pairs_per_day if row is not None else None)
                or builtin["max_pairs_per_day"],
                "is_excluded": bool(row.is_excluded) if row is not None else builtin["is_excluded"],
                "weekdays": list(row.weekdays or []) if row is not None else [],
                "is_custom": row is not None,
            }
        )
    return out


def group_rows(actor, organization, period, groups) -> list:
    """Semestrdə açılışı olan qruplar (+ ailəsi) və onların effektiv siyasəti."""
    Offering = django_apps.get_model("registrar", "CourseOffering")
    infos = load_groups(organization, groups)
    active = {
        str(gid)
        for gid in Offering.objects.filter(
            organization=organization, period=period, group_id__in=list(infos), is_active=True
        ).values_list("group_id", flat=True)
    }
    infos = prune_groups(infos, active)
    by_group, by_level = policy_rows(organization)
    band_labels = dict(Band.choices)
    degree_labels = dict(PolicyLevel.choices)
    form_labels = {"full_time": pgettext(_CTX, "əyani"), "part_time": pgettext(_CTX, "qiyabi")}
    out = []
    for info in sorted(infos.values(), key=lambda item: item.name):
        policy = resolve_policy(info, by_group, by_level)
        out.append(
            {
                "id": info.id,
                "name": info.name,
                "degree": str(degree_labels.get(info.degree, info.degree)),
                "form": str(form_labels.get(info.form, info.form)),
                "students": info.students,
                "level": policy["level"],
                "bands": policy["bands"],
                "bands_label": ", ".join(str(band_labels.get(code, code)) for code in policy["bands"]),
                "max_pairs_per_day": policy["max_pairs_per_day"],
                "is_excluded": policy["is_excluded"],
                "is_custom": policy["source"] == "group",
                "parent": infos[info.parent].name if info.parent and info.parent in infos else "",
            }
        )
    return out


__all__ = ["PolicyError", "clean", "group_rows", "level_rows", "save_group", "save_level"]
