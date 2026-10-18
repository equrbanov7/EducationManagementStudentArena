"""Yazı qatı — əlavə, redaktə, yeniləmə, «göndərildi», xitam, işçinin təsdiqi.

Müqavilə (çağıranlar üçün):
* Səlahiyyət HƏR yazıdan ƏVVƏL yoxlanılır (``ATOMIC_REQUESTS`` altında da heç bir sətir yazılmamış rədd olunur):
  açar yoxdur → 403, əhatədən kənar / başqa təşkilat → 404 (mövcudluq bildirilmir), view-as → 403.
* Hər yazı: sətir ``select_for_update`` ilə kilidlənir, APPEND-ONLY ``EmploymentContractEvent`` + audit jurnalı
  (``core.audit.log_action``) yazılır, bildiriş ``transaction.on_commit``-dən sonra gedir.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from ..constants import (
    CLOSABLE_STATUSES,
    CTX,
    END_FORBIDDEN_TYPES,
    END_REQUIRED_TYPES,
    NOTE_MAX,
    NOTES_MAX,
    NUMBER_MAX,
    OPEN_STATUSES,
    POSITION_MAX,
    POST_ACK_EDITABLE_FIELDS,
    SNAPSHOT_KEY,
    TERMINATION_REASON_MIN,
    ContractStatus,
    ContractType,
    EventKind,
)
from ..models import EmploymentContract, EmploymentContractEvent
from . import notify
from .access import is_eligible_employee, primary_unit, staff_in_scope
from .errors import ContractError
from .files import delete_after_commit, discard_on_error, track
from .uploads import clean_upload

AUDIT_RESOURCE = "hr_contracts.contract"
#: Yararsız UUID Django-da ``ValidationError`` verir — hamısı «tapılmadı» kimi cavablanır.
LOOKUP_ERRORS = (EmploymentContract.DoesNotExist, ValueError, TypeError, ValidationError)

#: Redaktə fərqində izlənən sahələr (``data["changes"]``).
TRACKED_FIELDS = (
    "number",
    "contract_type",
    "position",
    "unit_id",
    "start_date",
    "end_date",
    "probation_end",
    "weekly_hours",
    "staff_rate",
    "notes",
    "status",
)


# ── Ümumi köməkçilər ─────────────────────────────────────────────────────────


def _forbidden() -> ContractError:
    return ContractError("forbidden", pgettext(CTX, "Bu əməl üçün icazəniz yoxdur."), status=403)


def _not_found() -> ContractError:
    return ContractError("not_found", pgettext(CTX, "Müqavilə tapılmadı."), status=404)


def require_manager(actor) -> None:
    if actor.view_as:
        raise ContractError("view_as_read_only", pgettext(CTX, "Baxış rejimində dəyişiklik etmək olmaz."), status=403)
    if not actor.can_manage:
        raise _forbidden()


def load_for_manage(actor, contract_id, *, lock: bool = True) -> EmploymentContract:
    """İdarə üçün müqavilə — icazə ƏVVƏL, sonra əhatə (kənar → 404)."""
    require_manager(actor)
    rows = EmploymentContract.objects.filter(organization=actor.organization)
    if lock:
        rows = rows.select_for_update(of=("self",))
    try:
        contract = rows.select_related("unit", "employee", "organization").get(pk=contract_id)
    except LOOKUP_ERRORS:
        raise _not_found()
    if not actor.manages(contract):
        raise _not_found()
    return contract


def _value(value):
    if isinstance(value, (dt.date, Decimal)):
        return str(value)
    if value is None:
        return None
    return str(value) if not isinstance(value, (int, float, bool)) else value


def snapshot(contract) -> dict:
    return {field: _value(getattr(contract, field)) for field in TRACKED_FIELDS}


def record_event(contract, kind, *, actor=None, note: str = "", threshold=None, end_date=None, data=None):
    return EmploymentContractEvent.objects.create(
        organization_id=contract.organization_id,
        contract=contract,
        kind=kind,
        actor=actor,
        actor_name=notify.person_name(actor)[:200] if actor is not None else "",
        threshold=threshold,
        end_date=end_date,
        note=str(note or "")[:NOTES_MAX],
        data=data or {},
    )


def _audit(request, actor_user, organization, contract, action, reason, *, old=None, new=None):
    log_action(
        action,
        user=actor_user,
        organization=organization,
        obj=contract,
        old_values=old,
        new_values=new,
        reason=reason,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(contract.pk),
        resource_repr=f"{contract.number} · {notify.person_name(contract.employee)}"[:200],
    )


# ── Forma oxunuşu ────────────────────────────────────────────────────────────


def _text(data, name: str, limit: int) -> str:
    return " ".join(str(data.get(name) or "").split())[:limit]


def _date(data, name: str, *, required: bool = False):
    raw = str(data.get(name) or "").strip()
    if not raw:
        if required:
            raise ContractError("required", pgettext(CTX, "Bu sahə məcburidir."), field=name)
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise ContractError("invalid_date", pgettext(CTX, "Tarix düzgün deyil."), field=name)


def _decimal(data, name: str, *, maximum: Decimal):
    raw = str(data.get(name) or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ContractError("invalid_number", pgettext(CTX, "Rəqəm düzgün deyil."), field=name)
    if value <= 0 or value > maximum:
        raise ContractError(
            "out_of_range",
            pgettext(CTX, "Dəyər 0-dan böyük və {max}-dən kiçik olmalıdır.").format(max=maximum),
            field=name,
        )
    return value


def _unit(actor, raw):
    if not raw:
        return None
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    try:
        return OrgUnit.objects.get(organization=actor.organization, pk=raw, is_active=True)
    except (OrgUnit.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ContractError("unit_invalid", pgettext(CTX, "Bölmə tapılmadı."), field="unit")


def parse_fields(actor, data) -> dict:
    """Forma sahələri → tipli dəyərlər (işçi və status xaric — onlar ayrıca yoxlanılır)."""
    number = _text(data, "number", NUMBER_MAX)
    if not number:
        raise ContractError("required", pgettext(CTX, "Müqavilə nömrəsini yazın."), field="number")
    contract_type = str(data.get("contract_type") or "")
    if contract_type not in ContractType.values:
        raise ContractError("type_invalid", pgettext(CTX, "Müqavilə növünü seçin."), field="contract_type")
    start = _date(data, "start_date", required=True)
    end = _date(data, "end_date")
    if contract_type in END_FORBIDDEN_TYPES:
        end = None
    elif contract_type in END_REQUIRED_TYPES and end is None:
        raise ContractError(
            "end_required", pgettext(CTX, "Müddətli müqavilədə bitmə tarixi məcburidir."), field="end_date"
        )
    if end is not None and end < start:
        raise ContractError(
            "end_before_start", pgettext(CTX, "Bitmə tarixi başlama tarixindən əvvəl ola bilməz."), field="end_date"
        )
    probation = _date(data, "probation_end")
    if probation is not None and (probation < start or (end is not None and probation > end)):
        raise ContractError(
            "probation_invalid",
            pgettext(CTX, "Sınaq müddəti müqavilə müddətinin içində olmalıdır."),
            field="probation_end",
        )
    unit = _unit(actor, str(data.get("unit") or "").strip())
    return {
        "number": number,
        "contract_type": contract_type,
        "position": _text(data, "position", POSITION_MAX),
        "unit": unit,
        "start_date": start,
        "end_date": end,
        "probation_end": probation,
        "weekly_hours": _decimal(data, "weekly_hours", maximum=Decimal("60")),
        "staff_rate": _decimal(data, "staff_rate", maximum=Decimal("2")),
        "notes": str(data.get("notes") or "").strip()[:NOTES_MAX],
    }


def _check_unit_scope(actor, unit) -> None:
    if actor.manages_unit(unit):
        return
    if unit is None:
        raise ContractError("unit_required", pgettext(CTX, "Öz əhatənizdəki bölməni seçin."), field="unit")
    raise ContractError("unit_out_of_scope", pgettext(CTX, "Bu bölmə sizin əhatənizdən kənardadır."), field="unit")


def _check_number_unique(actor, number: str, *, exclude_pk=None) -> None:
    rows = EmploymentContract.objects.filter(organization=actor.organization, number__iexact=number).exclude(
        status=ContractStatus.DISCARDED
    )
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    if rows.exists():
        raise ContractError("number_taken", pgettext(CTX, "Bu nömrəli müqavilə artıq qeydə alınıb."), field="number")


def _employee(actor, raw):
    try:
        user_id = int(str(raw or "").strip())
    except ValueError:
        raise ContractError("employee_required", pgettext(CTX, "İşçini seçin."), field="employee")
    if not is_eligible_employee(user_id, actor.organization):
        raise ContractError(
            "employee_invalid",
            pgettext(CTX, "Seçilmiş şəxs bu təşkilatın aktiv əməkdaşı deyil (tələbəyə əmək müqaviləsi bağlanmır)."),
            field="employee",
        )
    # Rəy A3: UNIT əhatəli menecer yalnız öz alt-ağacındakı heyətə müqavilə bağlayır (kənar → 404, mövcudluq bildirilmir).
    if not actor.manage_scope.is_org_wide and not (
        staff_in_scope(actor.organization, actor.manage_scope).filter(user_id=user_id).exists()
    ):
        raise ContractError("employee_out_of_scope", pgettext(CTX, "İşçi tapılmadı."), field="employee", status=404)
    return get_user_model().objects.get(pk=user_id)


def _apply(contract, fields: dict) -> None:
    for name, value in fields.items():
        setattr(contract, name, value)


def _save(contract) -> None:
    try:
        with transaction.atomic():
            contract.full_clean(exclude=["file", "employee", "organization", "created_by", "sent_by", "renewed_by"])
            contract.save()
    except IntegrityError as exc:
        if "hrc_unique_number_per_org" in str(exc):
            raise ContractError(
                "number_taken", pgettext(CTX, "Bu nömrəli müqavilə artıq qeydə alınıb."), field="number"
            ) from exc
        raise ContractError(
            "conflict", pgettext(CTX, "Məlumat ziddiyyətlidir — səhifəni yeniləyib yenidən cəhd edin."), status=409
        ) from exc
    except ValidationError as exc:
        raise ContractError("invalid", "; ".join(str(message) for message in exc.messages))


# ── Əlavə / redaktə / yeniləmə ───────────────────────────────────────────────


@transaction.atomic
def save_contract(actor, data, files, *, request=None) -> tuple[EmploymentContract, bool]:
    """Yeni müqavilə (``id`` boş) və ya redaktə; ``renew_of`` verilibsə — yeniləmə. ``(müqavilə, yaradıldı)``.

    Xəta ilə geri qayıdışda bu çağırışda yazılmış fayl silinir (``files.discard_on_error``, rəy A5).
    """
    require_manager(actor)
    with discard_on_error():
        contract_id = str(data.get("id") or "").strip()
        if contract_id:
            return _update(actor, contract_id, data, files, request=request), False
        return _create(actor, data, files, request=request), True


def _create(actor, data, files, *, request=None) -> EmploymentContract:
    renew_of = str(data.get("renew_of") or "").strip()
    previous = load_for_manage(actor, renew_of) if renew_of else None
    if previous is not None:
        if previous.status not in CLOSABLE_STATUSES or previous.renewed_by_id:
            raise ContractError(
                "not_renewable", pgettext(CTX, "Bu müqavilə artıq yenilənib və ya xitam verilib."), status=409
            )
        employee = previous.employee
    else:
        employee = _employee(actor, data.get("employee"))
    fields = parse_fields(actor, data)
    if fields["unit"] is None and previous is None:
        fields["unit"] = _default_unit(actor, employee)
    _check_unit_scope(actor, fields["unit"])
    _check_number_unique(actor, fields["number"])
    if previous is not None and fields["start_date"] <= previous.start_date:
        raise ContractError(
            "start_before_previous",
            pgettext(CTX, "Yeni müqavilə əvvəlkindən sonra başlamalıdır."),
            field="start_date",
        )
    status = ContractStatus.DRAFT if str(data.get("status") or "") == ContractStatus.DRAFT else ContractStatus.ACTIVE
    upload, original = clean_upload(files.get("file") if files else None)
    contract = EmploymentContract(
        organization=actor.organization, employee=employee, status=status, created_by=actor.user, **fields
    )
    if upload is not None:
        contract.file = upload
        contract.file_name = original
    _save(contract)
    if upload is not None:
        track(contract.file)
    record_event(
        contract,
        EventKind.CREATED,
        actor=actor.user,
        data={"values": snapshot(contract), "renewal_of": str(previous.pk) if previous else None, "file": bool(upload)},
    )
    _audit(request, actor.user, actor.organization, contract, AuditAction.CREATE, "hr_contracts: created",
           new=snapshot(contract))  # fmt: skip
    if previous is not None:
        _mark_renewed(actor, previous, contract, request=request)
    sync_employee_snapshot(actor.organization)
    return contract


def _default_unit(actor, employee):
    unit = primary_unit(employee.pk, actor.organization)
    return unit if actor.manages_unit(unit) else None


def _mark_renewed(actor, previous, contract, *, request=None) -> None:
    old = snapshot(previous)
    previous.status = ContractStatus.RENEWED
    previous.renewed_by = contract
    previous.save(update_fields=["status", "renewed_by", "updated_at"])
    record_event(previous, EventKind.RENEWED, actor=actor.user, data={"renewed_by": str(contract.pk)})
    _audit(request, actor.user, actor.organization, previous, AuditAction.UPDATE, "hr_contracts: renewed",
           old=old, new={**snapshot(previous), "renewed_by": str(contract.pk)})  # fmt: skip


def _update(actor, contract_id, data, files, *, request=None) -> EmploymentContract:
    contract = load_for_manage(actor, contract_id)
    if contract.status not in OPEN_STATUSES:
        raise ContractError(
            "closed", pgettext(CTX, "Xitam verilmiş və ya yenilənmiş müqavilə redaktə olunmur."), status=409
        )
    fields = parse_fields(actor, data)
    before = snapshot(contract)
    was_draft = contract.status == ContractStatus.DRAFT
    _check_unit_scope(actor, fields["unit"])
    _check_number_unique(actor, fields["number"], exclude_pk=contract.pk)
    _apply(contract, fields)
    if was_draft and str(data.get("status") or "") == ContractStatus.ACTIVE:
        contract.status = ContractStatus.ACTIVE
    after_values = snapshot(contract)
    terms_changed = any(
        before[key] != after_values[key] for key in TRACKED_FIELDS if key not in POST_ACK_EDITABLE_FIELDS
    )
    raw_upload = files.get("file") if files else None
    if contract.acknowledged_at is not None and (terms_changed or raw_upload):
        # Rəy A1: işçi YEKUN mətni təsdiqləyib — şərtlər və fayl artıq dəyişmir, yalnız daxili HR qeydi (``notes``).
        raise ContractError(
            "acknowledged_locked",
            pgettext(CTX, "Təsdiqlənmiş müqavilə dəyişdirilə bilməz — «Yenilə» ilə yeni müqavilə yaradın."),
            status=409,
        )
    upload, original = clean_upload(raw_upload)
    old_file = contract.file.name if contract.file else ""
    if upload is not None:
        contract.file = upload
        contract.file_name = original
    resend_required = contract.sent_at is not None and contract.acknowledged_at is None and (terms_changed or upload)
    if resend_required:
        # Rəy A1: göndərilmiş, təsdiqlənməmiş mətn dəyişdi — işçi köhnə mətni təsdiqləməsin; yenidən göndərilməlidir.
        contract.sent_at = None
        contract.sent_note = ""
    _save(contract)
    if upload is not None:
        track(contract.file)
        if old_file and old_file != contract.file.name:
            delete_after_commit(contract.file.storage, old_file)
    after = snapshot(contract)
    changes = {key: [before[key], after[key]] for key in TRACKED_FIELDS if before[key] != after[key]}
    if changes:
        record_event(contract, EventKind.EDITED, actor=actor.user, data={"changes": changes})
    if resend_required:
        record_event(contract, EventKind.RESEND_REQUIRED, actor=actor.user)
        sync_employee_snapshot(actor.organization)
    if was_draft and contract.status == ContractStatus.ACTIVE:
        record_event(contract, EventKind.ACTIVATED, actor=actor.user)
        sync_employee_snapshot(actor.organization)
    if upload is not None:
        record_event(contract, EventKind.FILE_REPLACED, actor=actor.user, data={"file_name": original})
    if changes or upload is not None:
        _audit(request, actor.user, actor.organization, contract, AuditAction.UPDATE, "hr_contracts: edited",
               old=before, new={**after, "file_replaced": upload is not None})  # fmt: skip
    return contract


# ── «Göndərildi» / xitam / təsdiq ───────────────────────────────────────────


@transaction.atomic
def mark_sent(actor, contract_id, *, note: str = "", request=None) -> EmploymentContract:
    contract = load_for_manage(actor, contract_id)
    if contract.status not in OPEN_STATUSES:
        raise ContractError("closed", pgettext(CTX, "Bu müqavilə artıq bağlanıb."), status=409)
    if contract.acknowledged_at is not None:
        raise ContractError("already_acknowledged", pgettext(CTX, "İşçi bu müqaviləni artıq təsdiqləyib."), status=409)
    resend = contract.sent_at is not None
    if contract.status == ContractStatus.DRAFT:
        # Rəy A2: işçi heç vaxt «qaralama» görmür — göndərilən qaralama əvvəlcə qüvvəyə minir.
        contract.status = ContractStatus.ACTIVE
        record_event(contract, EventKind.ACTIVATED, actor=actor.user, data={"via": "sent"})
    contract.sent_at = timezone.now()
    contract.sent_by = actor.user
    contract.sent_note = str(note or "").strip()[:NOTE_MAX]
    contract.save(update_fields=["status", "sent_at", "sent_by", "sent_note", "updated_at"])
    record_event(contract, EventKind.SENT, actor=actor.user, note=contract.sent_note, data={"resend": resend})
    _audit(request, actor.user, actor.organization, contract, AuditAction.UPDATE, "hr_contracts: sent",
           new={"sent_at": contract.sent_at.isoformat(), "note": contract.sent_note, "resend": resend})  # fmt: skip
    sync_employee_snapshot(actor.organization)
    notify.contract_sent(contract)
    return contract


@transaction.atomic
def terminate(actor, contract_id, *, reason: str, on=None, request=None) -> EmploymentContract:
    contract = load_for_manage(actor, contract_id)
    if contract.status == ContractStatus.DRAFT:
        raise ContractError(
            "draft",
            pgettext(CTX, "Qaralamaya xitam verilmir — «Qaralamanı ləğv et» əməlindən istifadə edin."),
            status=409,
        )
    if contract.status not in CLOSABLE_STATUSES:
        raise ContractError("closed", pgettext(CTX, "Bu müqavilə artıq bağlanıb."), status=409)
    reason = str(reason or "").strip()
    if len(reason) < TERMINATION_REASON_MIN:
        raise ContractError(
            "reason_required",
            pgettext(CTX, "Xitamın səbəbini yazın (ən azı {n} simvol).").format(n=TERMINATION_REASON_MIN),
            field="reason",
        )
    if isinstance(on, str):
        on = _date({"terminated_at": on}, "terminated_at")
    on = on or timezone.localdate()
    if on < contract.start_date:
        raise ContractError(
            "date_invalid", pgettext(CTX, "Xitam tarixi müqavilənin başlanğıcından əvvəl ola bilməz."),
            field="terminated_at",
        )  # fmt: skip
    old = snapshot(contract)
    contract.status = ContractStatus.TERMINATED
    contract.terminated_at = on
    contract.termination_reason = reason[:NOTES_MAX]
    contract.save(update_fields=["status", "terminated_at", "termination_reason", "updated_at"])
    record_event(contract, EventKind.TERMINATED, actor=actor.user, note=reason, data={"terminated_at": on.isoformat()})
    _audit(request, actor.user, actor.organization, contract, AuditAction.UPDATE, "hr_contracts: terminated",
           old=old, new={**snapshot(contract), "terminated_at": on.isoformat()})  # fmt: skip
    return contract


@transaction.atomic
def discard(actor, contract_id, *, note: str = "", request=None) -> EmploymentContract:
    """«Qaralamanı ləğv et» (rəy A2) — yalnız qaralama; sətir və hadisələr qalır, işçiyə HEÇ VAXT görünmür."""
    contract = load_for_manage(actor, contract_id)
    if contract.status != ContractStatus.DRAFT:
        raise ContractError("not_draft", pgettext(CTX, "Yalnız qaralama ləğv edilə bilər."), status=409)
    old = snapshot(contract)
    contract.status = ContractStatus.DISCARDED
    contract.save(update_fields=["status", "updated_at"])
    record_event(contract, EventKind.DISCARDED, actor=actor.user, note=str(note or "").strip())
    _audit(request, actor.user, actor.organization, contract, AuditAction.UPDATE, "hr_contracts: draft discarded",
           old=old, new=snapshot(contract))  # fmt: skip
    return contract


@transaction.atomic
def acknowledge(user, organization, contract_id, *, note: str = "", request=None) -> EmploymentContract:
    """İşçinin «Tanış oldum, təsdiqləyirəm» təsdiqi — YALNIZ öz müqaviləsi; geri alınmır."""
    if request is not None and getattr(request, "is_view_as", False):
        raise ContractError("view_as_read_only", pgettext(CTX, "Baxış rejimində dəyişiklik etmək olmaz."), status=403)
    try:
        contract = (
            EmploymentContract.objects.select_for_update(of=("self",))
            .select_related("organization", "employee", "sent_by")
            .get(organization=organization, pk=contract_id, employee=user)
        )
    except LOOKUP_ERRORS as exc:
        raise _not_found() from exc
    if contract.sent_at is None:
        raise _not_found()
    if contract.acknowledged_at is not None:
        raise ContractError(
            "already_acknowledged", pgettext(CTX, "Siz bu müqaviləni artıq təsdiqləmisiniz."), status=409
        )
    if contract.status not in OPEN_STATUSES:
        raise ContractError("closed", pgettext(CTX, "Bu müqavilə artıq bağlanıb."), status=409)
    contract.acknowledged_at = timezone.now()
    contract.acknowledge_note = str(note or "").strip()[:NOTE_MAX]
    contract.save(update_fields=["acknowledged_at", "acknowledge_note", "updated_at"])
    record_event(contract, EventKind.ACKNOWLEDGED, actor=user, note=contract.acknowledge_note)
    _audit(request, user, organization, contract, AuditAction.UPDATE, "hr_contracts: acknowledged",
           new={"acknowledged_at": contract.acknowledged_at.isoformat(), "note": contract.acknowledge_note})  # fmt: skip
    notify.contract_acknowledged(contract)
    return contract


# ── «Müqavilələrim» menyu xülasəsi (sorğusuz menyu) ────────────────────────


def sync_employee_snapshot(organization) -> list:
    """``Organization.settings[SNAPSHOT_KEY]`` = görünən müqaviləsi olan işçi id-ləri (atomik, ``touch=False``)."""
    from apps.organizations.public import set_settings_keys

    from .queries import employees_with_contracts

    ids = sorted(employees_with_contracts(organization))
    set_settings_keys(organization, {SNAPSHOT_KEY: ids}, touch=False)
    return ids


__all__ = [
    "AUDIT_RESOURCE",
    "LOOKUP_ERRORS",
    "acknowledge",
    "discard",
    "load_for_manage",
    "mark_sent",
    "parse_fields",
    "record_event",
    "require_manager",
    "save_contract",
    "snapshot",
    "sync_employee_snapshot",
    "terminate",
]
