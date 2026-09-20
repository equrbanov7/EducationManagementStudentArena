"""Ekran 06 «Qruplar» — ANA QRUPU ALT QRUPLARA BÖLMƏ (sahib qərarı 2026-09-20).

«Lab dərsində və ya qrup çox olanda ana qrupdan müəyyən tələbələri seçib 2 və
daha çox alt qrup yaratmaq; sistem əvvəlcə bərabər bölsün, sonra tələbələri
tərəflər arasında keçirmək və alt qrupu adlandırmaq mümkün olsun.»

Server tərəfi TƏK əməldir (`action=split_group`, bax :mod:`group_actions`):

* ``id``        — ana qrup (aktorun əhatəsində, aktiv);
* ``reason``    — səbəb (≥3 simvol; audit + köçürmə səbəbi);
* ``subgroups`` — JSON siyahı ``[{"name": "234 K-1", "record_ids": [...]}, …]``
  (2–``MAX_SUBGROUPS`` element). Bir tələbə YALNIZ bir alt qrupda ola bilər;
  seçilməyən tələbələr ANA qrupda qalır.

Alt qrup ``OrgUnit(group)``-dur, ana qrupla EYNİ ixtisas altında; metadata
(kurs, dil sektoru, təhsil forması, qəbul ili, tutum) ana qrupdan köçürülür və
``settings["parent_group"]`` ana qrupun id-sini saxlayır — jurnal «alt qrup
birləşməsi» (registrar.subgroup_rollup) bu izi tanıyır. Tələbə köçürməsi
YALNIZ rəsmi xidmətlə (`student_transfer.transfer_student_group`) gedir: DB
qapısı sadə FK yazısına icazə vermir, jurnal tarixçəsi qorunur. Bütün əməl bir
transaksiyadadır — bir tələbədə xəta olarsa heç nə yaradılmır.
"""

from __future__ import annotations

import json

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from .group_actions import _error, _visible_group
from .groups_registry import SETTING_KEYS
from .models import OrgUnit
from .views.shared._helpers import _unique_unit_slug

_CTX = "accounts.groups"
MIN_SUBGROUPS = 2
MAX_SUBGROUPS = 6
MAX_NAME_LENGTH = 255


def parse_subgroups(raw) -> list[dict]:
    """``subgroups`` JSON-unu təmizləyir: ad + təkrarsız id siyahısı.

    Qaytarır ``[{"name": str, "record_ids": [str, …]}]``; forma səhvdirsə
    ``ValueError(code)`` — çağıran onu 400 cavabına çevirir.
    """
    try:
        items = json.loads(raw or "[]")
    except (TypeError, ValueError) as exc:
        raise ValueError("subgroups_invalid") from exc
    if not isinstance(items, list):
        raise ValueError("subgroups_invalid")
    cleaned: list[dict] = []
    seen_names: set[str] = set()
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("subgroups_invalid")
        name = " ".join(str(item.get("name") or "").split())[:MAX_NAME_LENGTH]
        if not name:
            raise ValueError("name_required")
        key = name.casefold()
        if key in seen_names:
            raise ValueError("name_duplicate")
        seen_names.add(key)
        ids = []
        for value in item.get("record_ids") or []:
            value = str(value or "").strip()
            if not value:
                continue
            if value in seen_ids:
                raise ValueError("student_duplicate")
            seen_ids.add(value)
            ids.append(value)
        cleaned.append({"name": name, "record_ids": ids})
    if len(cleaned) < MIN_SUBGROUPS:
        raise ValueError("too_few")
    if len(cleaned) > MAX_SUBGROUPS:
        raise ValueError("too_many")
    return cleaned


_MESSAGES = {
    "subgroups_invalid": pgettext(_CTX, "Alt qrup bölgüsü oxunmadı — səhifəni yeniləyib yenidən cəhd edin."),
    "name_required": pgettext(_CTX, "Hər alt qrupun adı olmalıdır."),
    "name_duplicate": pgettext(_CTX, "Alt qrup adları bir-birindən fərqli olmalıdır."),
    "student_duplicate": pgettext(_CTX, "Bir tələbə yalnız bir alt qrupda ola bilər."),
    "too_few": pgettext(_CTX, "Ən azı 2 alt qrup olmalıdır."),
    "too_many": pgettext(_CTX, "Ən çoxu 6 alt qrup yaratmaq olar."),
}


def inherited_settings(source: OrgUnit) -> dict:
    """Ana qrupun metadatası (kurs, dil, forma, qəbul ili, tutum) + `parent_group`."""
    raw = source.settings if isinstance(source.settings, dict) else {}
    out = {key: raw.get(key, "") for key in SETTING_KEYS}
    out["parent_group"] = str(source.pk)
    return out


@transaction.atomic
def split_group(request, organization, scope):
    """`action=split_group` — ana qrupu alt qruplara böl (bax modul şərhi)."""
    source = _visible_group(organization, scope, request.POST.get("id"))
    if source is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found", field="id")
    if not source.is_active:
        return _error(pgettext(_CTX, "Arxivlənmiş qrup bölünmür."), code="archived", field="id")

    reason = (request.POST.get("reason") or "").strip()[:500]
    if len(reason) < 3:
        return _error(pgettext(_CTX, "Səbəb yazılmalıdır (ən azı 3 simvol)."), code="reason_required", field="reason")

    try:
        subgroups = parse_subgroups(request.POST.get("subgroups"))
    except ValueError as exc:
        code = str(exc)
        return _error(_MESSAGES.get(code, _MESSAGES["subgroups_invalid"]), code=code, field="subgroups")

    from django.db.models import Q

    wanted_names = [item["name"] for item in subgroups]
    name_q = Q()
    for name in wanted_names:
        name_q |= Q(name__iexact=name)
    taken_fold = {
        name.casefold()
        for name in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP)
        .filter(name_q)
        .values_list("name", flat=True)
    }
    for name in wanted_names:
        if name.casefold() in taken_fold:
            return _error(
                pgettext(_CTX, "«%(name)s» adlı qrup artıq var — başqa ad seçin.") % {"name": name},
                code="name_taken",
                field="subgroups",
            )

    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    all_ids = [rid for item in subgroups for rid in item["record_ids"]]
    if not all_ids:
        return _error(
            pgettext(_CTX, "Heç bir tələbə alt qrupa yerləşdirilməyib."), code="students_required", field="subgroups"
        )
    records = {
        str(record.pk): record
        for record in StudentAcademicRecord.objects.filter(
            organization=organization, group=source, is_active=True, status="enrolled", pk__in=all_ids
        ).select_related("student", "program", "organization", "group")
    }
    missing = [rid for rid in all_ids if rid not in records]
    if missing:
        return _error(
            pgettext(_CTX, "Seçilmiş tələbələrdən bəziləri bu qrupun aktiv tələbəsi deyil — siyahını yeniləyin."),
            code="student_outside_group",
            field="subgroups",
        )

    from . import student_transfer as group_transfer

    period = organization.academic_periods.filter(is_current=True, is_active=True).first()
    settings_blob = inherited_settings(source)
    created = []
    moved_total = 0
    try:
        for item in subgroups:
            unit = OrgUnit.objects.create(
                organization=organization,
                parent=source.parent,
                unit_type=OrgUnitType.GROUP,
                name=item["name"],
                slug=_unique_unit_slug(organization, item["name"], "group"),
                code="",
                settings=dict(settings_blob),
                is_active=True,
            )
            moved = 0
            for rid in item["record_ids"]:
                result = group_transfer.transfer_student_group(
                    record=records[rid], new_group=unit, period=period, by_user=request.user, reason=reason
                )
                moved += 1 if result.get("record") is not None else 0
            moved_total += moved
            created.append({"id": str(unit.pk), "name": unit.name, "students": moved})
            log_action(
                action=AuditAction.CREATE,
                user=request.user,
                organization=organization,
                obj=unit,
                request=request,
                reason=f"groups: subgroup created by splitting {source.name} — {reason}",
                new_values={
                    "parent_group": str(source.pk),
                    "parent_group_name": source.name,
                    "students": [records[rid].student.username for rid in item["record_ids"]],
                },
            )
    except ValidationError as exc:
        messages = getattr(exc, "messages", None) or [str(exc)]
        transaction.set_rollback(True)
        return _error(" ".join(str(message) for message in messages), status=409, code="transfer_rejected")

    remaining = StudentAcademicRecord.objects.filter(
        organization=organization, group=source, is_active=True, status="enrolled"
    ).count()
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=source,
        request=request,
        reason=f"groups: group split into subgroups — {reason}",
        new_values={"subgroups": created, "moved": moved_total, "remaining": remaining},
    )
    return JsonResponse(
        {"ok": True, "id": str(source.pk), "created": created, "moved": moved_total, "remaining": remaining}
    )
