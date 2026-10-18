"""25% ödənişinin TƏXMİNİ məbləği və təhsil haqqı cədvəli (sahib 2026-10-19).

Sahib: «İlliyə görə hesablanır, amma dəqiq bilmirəm» — düstur konfiqurasiya olunandır:

    məbləğ = illik təhsil haqqı × ``retake.fee_percent`` ÷ 100 × (fənnin krediti ÷ ``retake.fee_annual_credits``)

``retake.fee_annual_credits = 0`` → kreditə bölünmür (illik × faiz). İllik haqq ``RetakeTuition`` cədvəlindən:
tədris ili × qəbul ili (tələbənin akademik qeydi) × ixtisas; ixtisasa xas sətir yoxdursa ixtisassız (defolt) sətir.

TƏDRİS İLİ (review 2026-10-19, M-10): tələbənin ÖDƏDİYİ anın — müraciət anındakı CARİ akademik dövrün
(``is_current``) ili; cari dövr yoxdursa açıq pəncərənin dövrü, o da yoxdursa kəsr dövrünün ili. Fənnin kəsr
verildiyi köhnə dövrün ili DEYİL. İstifadə olunan il və mənbəyi ``inputs``-a yazılır və tələbəyə / növbəyə
göstərilir. Kredit ≤ 0 (illik kredit > 0 ikən) → məbləğ ``None`` («0 AZN» göstərilmir). Sətir tapılmasa məbləğ ``None`` — tələbə «Məbləği Mühasibatlıqdan
öyrənin» görür. Dəqiq məbləği Mühasibatlıq təsdiqləyir; fərq xəbərdarlıqdır, blok DEYİL.

Cədvəli Mühasibatlıq saxlayır: ``retake.payment_verify`` və ya ``accounting.manage_fees`` (kataloqa əlavəsi
«Mühasibatlıq» paketinin işidir; burada yalnız adla istinad olunur).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import retake_access, retake_rules
from .models import Program, RetakeTuition, StudentAcademicRecord

_CTX = "registrar.retake"

PERM_MANAGE_FEES = "accounting.manage_fees"
_CENT = Decimal("0.01")


#: ``academic_year`` mənbəyi (``inputs["academic_year_source"]``).
YEAR_CURRENT, YEAR_WINDOW, YEAR_FAILED, YEAR_SUBMITTED = "current_period", "window_period", "failed_period", "submitted"

_YEAR_RE = re.compile(r"^(\d{4})/(\d{4})$")


def _periods():
    """``organizations.AcademicPeriod`` — app registry ilə (registrar-ın sanksiyalı üsulu)."""
    from django.apps import apps as django_apps

    return django_apps.get_model("organizations", "AcademicPeriod").objects


def can_manage(user, organization) -> bool:
    """Təşkilat səviyyəli cədvəl — açar ORG-WIDE əhatədə olmalıdır (review 2026-10-19, LOW-7)."""
    return retake_access.has_org_wide_key(
        user, organization, retake_rules.PERM_PAYMENT_VERIFY
    ) or retake_access.has_org_wide_key(user, organization, PERM_MANAGE_FEES)


def current_academic_year(organization) -> tuple:
    """``(il, mənbə)`` — cari akademik dövrün ili; yoxdursa açıq 25% pəncərəsinin dövrünün ili; yoxdursa ``("", "")``."""
    if organization is None:
        return "", ""
    period = _periods().filter(organization=organization, is_current=True).order_by("-start_date").first()
    if period is not None and period.academic_year:
        return period.academic_year, YEAR_CURRENT
    from . import retake_window

    window = retake_window.current(organization)
    if window is not None and window.period.academic_year:
        return window.period.academic_year, YEAR_WINDOW
    return "", ""


def settings_snapshot() -> dict:
    from core import runtime_settings

    return {
        "percent": runtime_settings.get_decimal("retake.fee_percent"),
        "annual_credits": runtime_settings.get_int("retake.fee_annual_credits"),
    }


def tuition_map(organization, admission_years) -> dict:
    """``(academic_year, admission_year, program_id | None)`` → ``RetakeTuition`` — tək sorğu."""
    years = {int(y) for y in admission_years if y}
    if organization is None or not years:
        return {}
    return {
        (row.academic_year, row.admission_year, row.program_id): row
        for row in RetakeTuition.objects.filter(organization=organization, admission_year__in=years)
    }


def compute(*, academic_year, admission_year, program_id, credits, rows, settings=None, year_source="") -> dict:
    """``{"amount": Decimal | None, "inputs": {...}}`` — düsturun bütün girişləri JSON-a sığır."""
    settings = settings or settings_snapshot()
    row = rows.get((academic_year, admission_year, program_id)) or rows.get((academic_year, admission_year, None))
    inputs = {
        "academic_year": academic_year,
        "academic_year_source": year_source,
        "admission_year": admission_year,
        "program_id": str(program_id) if program_id else None,
        "tuition_id": str(row.pk) if row else None,
        "annual_amount": str(row.annual_amount) if row else None,
        "percent": str(settings["percent"]),
        "credits": int(credits or 0),
        "annual_credits": int(settings["annual_credits"]),
    }
    if row is None:
        return {"amount": None, "inputs": inputs}
    if settings["annual_credits"] and int(credits or 0) <= 0:
        # Kredit bilinmir (0 / mənfi) — «0 AZN» yanıltmasın, tələbə «Mühasibatlıqdan öyrənin» görür (LOW-5).
        return {"amount": None, "inputs": {**inputs, "missing": "credits"}}
    amount = Decimal(row.annual_amount) * Decimal(settings["percent"]) / Decimal("100")
    if settings["annual_credits"]:
        amount = amount * Decimal(int(credits or 0)) / Decimal(int(settings["annual_credits"]))
    return {"amount": amount.quantize(_CENT, rounding=ROUND_HALF_UP), "inputs": inputs}


def _record(student, organization):
    return (
        StudentAcademicRecord.objects.filter(organization=organization, student=student)
        .order_by("-is_active", "-created_at")
        .first()
    )


def student_context(student, organization) -> dict:
    """Tələbə paneli üçün: akademik qeyd + cari tədris ili + təhsil haqqı xəritəsi (sabit sorğu sayı)."""
    year, source = current_academic_year(organization)
    record = _record(student, organization)
    base = {"academic_year": year, "year_source": source, "settings": settings_snapshot()}
    if record is None:
        return {**base, "record": None, "rows": {}}
    return {**base, "record": record, "rows": tuition_map(organization, [record.admission_year])}


def _year_for(context, period, override=None) -> tuple:
    if override:
        return override, YEAR_SUBMITTED
    if context.get("academic_year"):
        return context["academic_year"], context.get("year_source", "")
    return getattr(period, "academic_year", "") or "", YEAR_FAILED


def estimate(*, context, period, subject, academic_year=None) -> dict:
    """``academic_year`` verilibsə (müraciətin snapshot-u) o istifadə olunur; yoxsa cari dövrün ili."""
    year, source = _year_for(context, period, academic_year)
    record = context["record"]
    if record is None:
        return {"amount": None, "inputs": {"academic_year": year, "academic_year_source": source}}
    return compute(
        academic_year=year,
        admission_year=record.admission_year,
        program_id=record.program_id,
        credits=getattr(subject, "ects", 0),
        rows=context["rows"],
        settings=context["settings"],
        year_source=source,
    )


def _submitted_year(application):
    return (application.fee_inputs or {}).get("academic_year") or None


def for_application(application) -> dict:
    """Müraciət üçün təsdiq anındakı hesab — tədris ili MÜRACİƏT anının ili (snapshot), cədvəl / faiz cari."""
    context = student_context(application.student, application.organization)
    return estimate(
        context=context,
        period=application.period,
        subject=application.subject,
        academic_year=_submitted_year(application),
    )


def expected_map(applications) -> dict:
    """``application_id`` → gözlənilən məbləğ (snapshot; yoxdursa cari cədvəldən) — sabit sayda sorğu."""
    result, missing = {}, []
    for application in applications:
        if application.expected_fee is not None:
            result[application.pk] = application.expected_fee
        elif application.kind == "retake_25":
            missing.append(application)
    if not missing:
        return result
    organization = missing[0].organization
    records = {}
    for record in StudentAcademicRecord.objects.filter(
        organization=organization, student_id__in={a.student_id for a in missing}
    ).order_by("is_active", "created_at"):
        records[record.student_id] = record  # sonuncu (aktiv, ən yeni) qalır
    rows = tuition_map(organization, [r.admission_year for r in records.values()])
    settings = settings_snapshot()
    current_year, _source = current_academic_year(organization)
    for application in missing:
        record = records.get(application.student_id)
        if record is None:
            continue
        fee = compute(
            academic_year=_submitted_year(application) or current_year or application.period.academic_year,
            admission_year=record.admission_year,
            program_id=record.program_id,
            credits=application.subject.ects,
            rows=rows,
            settings=settings,
        )
        if fee["amount"] is not None:
            result[application.pk] = fee["amount"]
    return result


def clean_amount(raw, *, required=True, positive=False):
    """``positive=True`` — ödənilən məbləğ: 0 qəbul olunmur (LOW-6)."""
    text = str(raw if raw is not None else "").strip().replace(",", ".")
    if not text:
        if required:
            raise ValidationError(pgettext(_CTX, "Ödənilən məbləği yazın (AZN)."))
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValidationError(pgettext(_CTX, "Məbləğ rəqəm olmalıdır.")) from None
    if not value.is_finite() or value < 0 or value > Decimal("1000000"):
        raise ValidationError(pgettext(_CTX, "Məbləğ 0 ilə 1 000 000 AZN arasında olmalıdır."))
    value = value.quantize(_CENT, rounding=ROUND_HALF_UP)
    if positive and value <= 0:
        raise ValidationError(pgettext(_CTX, "Ödənilən məbləğ 0-dan böyük olmalıdır."))
    return value


# ── Təhsil haqqı cədvəli (Mühasibatlıq) ──────────────────────────────────────


def table(organization) -> list:
    return list(
        RetakeTuition.objects.filter(organization=organization)
        .select_related("program")
        .order_by("-academic_year", "-admission_year", "program__name")
    )


def known_years(organization) -> list:
    """Təşkilatın akademik dövrlərindəki tədris illəri (yenidən köhnəyə) — cədvəl seçimi bunlardır."""
    if organization is None:
        return []
    values = _periods().filter(organization=organization).values_list("academic_year", flat=True)
    return sorted({value for value in values if value}, reverse=True)


def clean_academic_year(organization, raw) -> tuple:
    """``(il, xəbərdarlıq)`` — dövrlərdə olan il; yoxdursa YALNIZ ``YYYY/YYYY+1`` formatı (xəbərdarlıqla)."""
    text = str(raw or "").strip()[:20]
    if not text:
        raise ValidationError(pgettext(_CTX, "Tədris ilini seçin."))
    if text in known_years(organization):
        return text, ""
    match = _YEAR_RE.match(text)
    if match is None or int(match.group(2)) != int(match.group(1)) + 1:
        raise ValidationError(pgettext(_CTX, "Tədris ili «2026/2027» formatında olmalıdır."))
    return text, pgettext(_CTX, "Bu tədris ili üçün hələ akademik dövr yoxdur — sətir dövr yaradılanda işləyəcək.")


def program_choices(organization) -> list:
    return list(Program.objects.filter(organization=organization).order_by("name").values_list("pk", "name"))


def _clean_year(raw) -> int:
    try:
        value = int(str(raw or "").strip())
    except ValueError:
        raise ValidationError(pgettext(_CTX, "Qəbul ili düzgün deyil.")) from None
    if not 1990 <= value <= 2100:
        raise ValidationError(pgettext(_CTX, "Qəbul ili düzgün deyil."))
    return value


@transaction.atomic
def save_tuition(
    *, actor, organization, academic_year, admission_year, program_id, annual_amount, note="", request=None
):
    """Cədvəl sətrini yarat və ya yenilə (eyni tədris ili × qəbul ili × ixtisas)."""
    if not can_manage(actor, organization):
        raise PermissionDenied
    year_text, warning = clean_academic_year(organization, academic_year)
    admission = _clean_year(admission_year)
    amount = clean_amount(annual_amount)
    program = None
    if program_id:
        program = Program.objects.filter(pk=program_id, organization=organization).first()
        if program is None:
            raise ValidationError(pgettext(_CTX, "İxtisas tapılmadı."))
    row = (
        RetakeTuition.objects.select_for_update()
        .filter(organization=organization, academic_year=year_text, admission_year=admission, program=program)
        .first()
    )
    old = str(row.annual_amount) if row else None
    try:
        with transaction.atomic():
            if row is None:
                row = RetakeTuition.objects.create(
                    organization=organization,
                    academic_year=year_text,
                    admission_year=admission,
                    program=program,
                    annual_amount=amount,
                    note=str(note or "").strip()[:300],
                    updated_by=actor,
                )
            else:
                row.annual_amount = amount
                row.note = str(note or "").strip()[:300]
                row.updated_by = actor
                row.save(update_fields=["annual_amount", "note", "updated_by", "updated_at"])
    except IntegrityError as exc:
        raise ValidationError(pgettext(_CTX, "Bu sətir artıq var.")) from exc
    log_action(
        AuditAction.UPDATE if old else AuditAction.CREATE,
        user=actor,
        organization=organization,
        obj=row,
        reason="retake_tuition_saved",
        request=request,
        resource_type="retake_tuition",
        resource_id=str(row.pk),
        old_values={"annual_amount": old},
        new_values={"academic_year": year_text, "admission_year": admission, "annual_amount": str(amount)},
    )
    row.year_warning = warning
    return row


@transaction.atomic
def delete_tuition(*, actor, organization, tuition_id, request=None):
    if not can_manage(actor, organization):
        raise PermissionDenied
    row = RetakeTuition.objects.filter(pk=tuition_id, organization=organization).first()
    if row is None:
        raise RetakeTuition.DoesNotExist
    snapshot = {
        "academic_year": row.academic_year,
        "admission_year": row.admission_year,
        "amount": str(row.annual_amount),
    }
    log_action(
        AuditAction.DELETE,
        user=actor,
        organization=organization,
        obj=row,
        reason="retake_tuition_deleted",
        request=request,
        resource_type="retake_tuition",
        resource_id=str(row.pk),
        old_values=snapshot,
    )
    row.delete()


__all__ = [
    "PERM_MANAGE_FEES",
    "can_manage",
    "clean_academic_year",
    "clean_amount",
    "compute",
    "current_academic_year",
    "delete_tuition",
    "estimate",
    "for_application",
    "known_years",
    "program_choices",
    "save_tuition",
    "settings_snapshot",
    "student_context",
    "table",
    "tuition_map",
]
