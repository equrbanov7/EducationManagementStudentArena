"""Müəllim idxalı — toplu Excel/CSV (sahib istəyi, 2026-09-08).

Tələbə idxalı ilə EYNİ maşın (`parsing.read_rows` → plan → `create.create_account`),
yalnız sütun müqaviləsi və struktur həlli fərqlidir: tələbədə qrup/ixtisas,
müəllimdə KAFEDRA (fakültə yalnız yoxlama üçün). Hesab nüvəsi, parol siyasəti,
ilk-giriş məcburiyyəti və audit sətri paylaşılır — heç nə təkrar yazılmır.

Sütunlar: FİN*, Ad*, Soyad*, Ata adı, Doğum tarixi, Cins, E-poçt, Telefon,
İşçi kodu (tabel №), Fakültə, Kafedra*, Vəzifə, Elmi dərəcə, Elmi ad, Ünvan.
Sıra sərbəstdir — başlıq adına görə tanınır (`header_index`).
"""

from __future__ import annotations

import csv
import io
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.translation import pgettext

from apps.accounts.identity import canonical_identity
from apps.audit.public import log_action
from core.constants import AuditAction, OrgUnitType

from . import create as create_mod
from .parsing import read_rows as _read_rows
from .spec import Column, normalize_header
from .validate import PLACEHOLDER_DOMAIN, IntakeContext, RowPlan, _parse_date, _parse_gender, _text, _validate_identity

_CTX = "teacher_intake"

SHEET_NAME = "Müəllimlər"
TEMPLATE_FILENAME = "muellim_idxal_sablonu.xlsx"


def columns() -> tuple:
    return (
        Column("fin", pgettext(_CTX, "FİN"), pgettext(_CTX, "7 simvol, A-Z0-9 (məcburi)"), required=True),
        Column("first_name", pgettext(_CTX, "Ad"), pgettext(_CTX, "Məcburi"), required=True),
        Column("last_name", pgettext(_CTX, "Soyad"), pgettext(_CTX, "Məcburi"), required=True),
        Column("patronymic", pgettext(_CTX, "Ata adı"), pgettext(_CTX, "Boş qala bilər")),
        Column("birth_date", pgettext(_CTX, "Doğum tarixi"), pgettext(_CTX, "gg.aa.iiii və ya iiii-aa-gg")),
        Column("gender", pgettext(_CTX, "Cins"), pgettext(_CTX, "kişi / qadın")),
        Column("email", pgettext(_CTX, "E-poçt"), pgettext(_CTX, "Boşdursa placeholder yazılır")),
        Column("phone", pgettext(_CTX, "Telefon"), pgettext(_CTX, "Boş qala bilər")),
        Column(
            "employee_code",
            pgettext(_CTX, "İşçi kodu"),
            pgettext(_CTX, "Tabel nömrəsi — istifadəçi adı bundan qurulur"),
        ),
        Column("faculty", pgettext(_CTX, "Fakültə"), pgettext(_CTX, "Adı və ya kodu (yalnız yoxlama)")),
        Column("kafedra", pgettext(_CTX, "Kafedra"), pgettext(_CTX, "Adı və ya kodu (məcburi)"), required=True),
        Column("title", pgettext(_CTX, "Vəzifə"), pgettext(_CTX, "Məs.: baş müəllim, dosent")),
        Column("academic_degree", pgettext(_CTX, "Elmi dərəcə"), pgettext(_CTX, "Məs.: fəlsəfə doktoru")),
        Column("academic_title", pgettext(_CTX, "Elmi ad"), pgettext(_CTX, "Məs.: dosent, professor")),
        Column("address", pgettext(_CTX, "Ünvan"), pgettext(_CTX, "Boş qala bilər")),
    )


def header_index() -> dict:
    index: dict = {}
    for column in columns():
        index[normalize_header(column.header)] = column.key
        index[normalize_header(column.key)] = column.key
    for raw, key in (
        ("fin kod", "fin"),
        ("fin kodu", "fin"),
        ("ata adi", "patronymic"),
        ("e-mail", "email"),
        ("mail", "email"),
        ("telefon nomresi", "phone"),
        ("isci kodu", "employee_code"),
        ("tabel", "employee_code"),
        ("tabel nomresi", "employee_code"),
        ("tabel №", "employee_code"),
        ("kafedra adi", "kafedra"),
        ("sobe", "kafedra"),
        ("vezife", "title"),
        ("elmi derece", "academic_degree"),
        ("elmi ad", "academic_title"),
        ("unvan", "address"),
        ("adres", "address"),
    ):
        index[normalize_header(raw)] = key
    return index


def required_keys() -> set:
    return {column.key for column in columns() if column.required}


def build_template() -> tuple[bytes, str, str]:
    headers = [column.header for column in columns()]
    hints = [column.hint for column in columns()]
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
    except Exception:  # pragma: no cover — paket olmayan mühit
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerow(hints)
        return ("﻿" + buffer.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", "muellim_idxal_sablonu.csv"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME
    sheet.append(headers)
    sheet.append(hints)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for cell in sheet[2]:
        cell.font = Font(italic=True, size=9)
    for position, column in enumerate(columns(), start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=position).column_letter].width = max(
            14, min(28, len(column.header) + 6)
        )
    sheet.freeze_panes = "A3"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", TEMPLATE_FILENAME


def read_rows(uploaded_file) -> list:
    rows = _read_rows(uploaded_file, index=header_index(), required=required_keys(), sheet_name=SHEET_NAME)
    for row in rows:
        # Kontekstin «mövcud kod» yoxlaması `student_code` açarına baxır — işçi kodu
        # eyni sahəyə (`institutional_identifier`) yazılır, ona görə alias qoyulur.
        row.setdefault("student_code", row.get("employee_code", ""))
    return rows


# ─── Plan ────────────────────────────────────────────────────────────────────


def _validate_unit(plan: RowPlan, row: dict, context: IntakeContext) -> bool:
    raw = _text(row.get("kafedra"))
    plan.group_name = raw
    if not raw:
        plan.fail("kafedra_required", pgettext(_CTX, "Kafedra boşdur."))
        return False
    unit, code = context.find_unit(raw, OrgUnitType.CHAIR)
    if code == "missing":
        unit, code = context.find_unit(raw, OrgUnitType.DEPARTMENT)
    if code == "missing":
        plan.fail("kafedra_unknown", pgettext(_CTX, "Kafedra tapılmadı: %s") % raw)
        return False
    if code == "ambiguous":
        plan.fail("kafedra_ambiguous", pgettext(_CTX, "Bu adla birdən çox kafedra var — kodla göstərin: %s") % raw)
        return False
    faculty_raw = _text(row.get("faculty"))
    if faculty_raw:
        faculty, faculty_code = context.find_unit(faculty_raw, OrgUnitType.FACULTY)
        if faculty_code:
            plan.fail("faculty_unknown", pgettext(_CTX, "Fakültə tapılmadı: %s") % faculty_raw)
            return False
        if str(faculty.pk) not in context.ancestor_ids(unit):
            plan.fail(
                "faculty_mismatch",
                pgettext(_CTX, "Fakültə kafedranın strukturuna uyğun gəlmir: %s") % faculty_raw,
            )
            return False
    plan.group_name = unit.name
    plan.targets["unit"] = unit
    return True


def _validate_person(plan: RowPlan, row: dict) -> bool:
    birth_date, ok = _parse_date(row.get("birth_date"))
    if not ok:
        plan.fail("birth_date_invalid", pgettext(_CTX, "Doğum tarixi tanınmadı (gg.aa.iiii formatını işlədin)."))
        return False
    if birth_date is not None and not (date(1900, 1, 1) <= birth_date <= date.today()):
        plan.fail("birth_date_out_of_range", pgettext(_CTX, "Doğum tarixi məntiqsizdir."))
        return False
    gender, known = _parse_gender(row.get("gender"))
    if not known and _text(row.get("gender")):
        plan.warnings.append(pgettext(_CTX, "Cins tanınmadı — «təyin edilməyib» qalır."))
    plan.values.update(
        {
            "birth_date": birth_date,
            "gender": gender,
            "title": _text(row.get("title"))[:150],
            "academic_degree": _text(row.get("academic_degree"))[:150],
            "academic_title": _text(row.get("academic_title"))[:150],
            "address": _text(row.get("address"))[:255],
            "department": plan.group_name,
            "employee_code": _text(row.get("employee_code"))[:50],
        }
    )
    return True


def _validate_credentials(plan: RowPlan, row: dict, context: IntakeContext) -> bool:
    code = _text(row.get("employee_code"))[:50]
    if code and code in context.existing_codes:
        plan.skip("employee_code_exists", pgettext(_CTX, "Bu işçi kodu artıq istifadə olunub — sətir ötürülür."))
        return False
    if code:
        context.existing_codes.add(code)
    plan.username = context.claim_username(create_mod.username_base(create_mod.KIND_TEACHER, code=code, fin=plan.fin))
    email = _text(row.get("email"))
    placeholder = "intake.%s@%s" % (plan.fin.lower(), PLACEHOLDER_DOMAIN)
    if not email:
        plan.email = placeholder
        plan.warnings.append(pgettext(_CTX, "E-poçt yoxdur — placeholder yazılır (ilk girişdə istifadəçi özü yazır)."))
    else:
        try:
            validate_email(email)
        except ValidationError:
            plan.fail("email_invalid", pgettext(_CTX, "E-poçt formatı yanlışdır."))
            return False
        key = canonical_identity(email)
        if key in context.existing_emails or key in context.seen_emails:
            plan.email = placeholder
            plan.warnings.append(pgettext(_CTX, "E-poçt artıq istifadə olunur — placeholder yazılır."))
        else:
            context.seen_emails.add(key)
            plan.email = email
    plan.values["student_code"] = code
    plan.values["email"] = plan.email
    plan.values["username"] = plan.username
    return True


def build_plans(organization, rows) -> list:
    """Sətirləri plana çevirir — HEÇ NƏ YAZMIR (quru icra = tətbiq)."""
    context = IntakeContext(organization, rows)
    plans: list = []
    for row in rows:
        plan = RowPlan(row=int(row.get("_row") or 0))
        if (
            _validate_identity(plan, row, context)
            and _validate_unit(plan, row, context)
            and _validate_person(plan, row)
            and _validate_credentials(plan, row, context)
        ):
            plan.code = "will_create"
            plan.message = pgettext(_CTX, "Yaradılacaq.")
        plans.append(plan)
    return plans


def summarize(plans) -> dict:
    return {
        "total": len(plans),
        "create": sum(1 for plan in plans if plan.status == "create"),
        "skip": sum(1 for plan in plans if plan.status == "skip"),
        "error": sum(1 for plan in plans if plan.status == "error"),
    }


def apply_plans(*, organization, plans, actor, request=None) -> dict:
    """Planları icra edir — sətir başına savepoint; parol yalnız cavabda."""
    role = create_mod.teacher_role(organization)
    results: list = []
    credentials: list = []
    created = failed = skipped = 0
    for plan in plans:
        if plan.status != "create":
            if plan.status == "skip":
                skipped += 1
            else:
                failed += 1
            results.append(plan.as_dict())
            continue
        try:
            with transaction.atomic():
                user, password = create_mod.create_account(
                    organization=organization,
                    kind=create_mod.KIND_TEACHER,
                    values=plan.values,
                    role=role,
                    actor=actor,
                    request=request,
                    scope_unit=plan.targets.get("unit"),
                    group_name="",
                    specialization="",
                    audit_reason="teacher_intake_created",
                    membership_title=plan.values.get("title", ""),
                    employee_id=plan.values.get("employee_code", ""),
                )
        except Exception as exc:  # noqa: BLE001 — sətir izolyasiyası qəsdəndir
            failed += 1
            from django.db import DataError

            detail = (
                pgettext(_CTX, "sahə uzunluğu həddi keçildi")
                if isinstance(exc, DataError)
                else (str(exc)[:180] or exc.__class__.__name__)
            )
            plan.fail("apply_failed", pgettext(_CTX, "Sətir yazılmadı: %s") % detail)
            results.append(plan.as_dict())
            continue
        created += 1
        plan.status = "created"
        plan.code = "created"
        plan.message = pgettext(_CTX, "Hesab yaradıldı.")
        row = plan.as_dict()
        row["status"] = "created"
        results.append(row)
        credentials.append(
            {
                "username": user.username,
                "password": password,
                "full_name": plan.full_name,
                "fin": plan.fin,
                "group": plan.group_name,
            }
        )
    log_action(
        action=AuditAction.CREATE,
        user=actor,
        organization=organization,
        reason="teacher_intake_batch",
        resource_type="teacher_intake",
        resource_repr="teacher_intake_batch",
        changes={"created": created, "skipped": skipped, "failed": failed, "total": len(plans)},
        request=request,
    )
    return {
        "rows": results,
        "credentials": credentials,
        "summary": {"total": len(plans), "created": created, "skipped": skipped, "failed": failed},
    }


__all__ = [
    "SHEET_NAME",
    "apply_plans",
    "build_plans",
    "build_template",
    "columns",
    "header_index",
    "read_rows",
    "summarize",
]
