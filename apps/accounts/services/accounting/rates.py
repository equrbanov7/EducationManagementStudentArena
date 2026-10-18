"""«Dərs saatının ödəniş dərəcələri» — cədvəl, məbləğ hesabı və idarəetmə (sahib 2026-10-19, tövsiyə olunan variant).

HESAB (İLKİN — rəsmi əmək haqqı hesabı DEYİL)
--------------------------------------------
Müəllimin vəzifəsi (``workload.TeacherWorkloadProfile.position``, semestrin tədris ili) və uyğun dərəcə varsa:

    məbləğ (növ) = dövrün keçirilmiş saatı (növ) × dərəcə (il × vəzifə × növ; növə xas sətir yoxdursa «bütün növlər»)

Cəm = növ məbləğlərinin cəmi; ``Decimal``, 2 rəqəm, ``ROUND_HALF_UP`` (hər növ ayrıca yuvarlanır, cəm dəqiqdir).
Vəzifə yoxdursa (yük profili yoxdur) və ya saatı olan bir növün dərəcəsi yoxdursa məbləğ BOŞDUR (``None``) —
«Dərəcə təyin edilməyib» göstərilir, HEÇ VAXT 0 yazılmır. Saatı olmayan növ üçün dərəcə tələb olunmur.

Saathesabı / ştat: jurnal dərsi konkret yük bölgüsü sətrinə bağlı DEYİL — ona görə məbləğ BÜTÜN keçirilmiş saat
üçündür, saathesabı hissə isə PLAN üzrə etiketlənir (``TeacherAssignment.is_hourly_paid`` saatları; profili
saathesabı olan müəllimin bütün saatı saathesabıdır).

KİM: məbləği ``accounting.view`` daşıyan hər kəs görür (panel qapısı ilə eyni). Cədvəli YALNIZ ``accounting.manage_fees``
açarını TƏŞKİLAT əhatəsində daşıyan dəyişir (mühasib, RİM rəhbəri; superadmin / təşkilat sahibi). «Başqasının
adından» rejimində yazı yoxdur. Hər dəyişiklik ``core.audit.log_action``-a yazılır.

TARİXÇƏ: sətir silinmir — dəyişiklik köhnəni «əvəzləndi» səbəbi ilə arxivləyir, «Sil» «ləğv edildi» ilə arxivləyir
(DB trigger-i: ``accounts/0033``). Sorğu büdcəsi: ilin bütün sətirləri 1 sorğu (aktiv + tarixçə).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from . import constants as C

PERM_MANAGE_FEES = "accounting.manage_fees"
CENT = Decimal("0.01")
RATE_MAX = Decimal("10000")
HISTORY_LIMIT = 50

PAY_OK = "ok"
PAY_NO_POSITION = "no_position"
PAY_NO_RATE = "no_rate"
PAY_PARTIAL = "partial"

AUDIT_RESOURCE = "accounts.pay_rate"


def _model():
    return django_apps.get_model("accounts", "TeachingPayRate")


def _actor_name(user) -> str:
    if user is None:
        return ""
    return ((user.get_full_name() or "").strip() or getattr(user, "username", ""))[:200]


# ── Seçimlər ─────────────────────────────────────────────────────────────────


def position_choices() -> list[tuple[str, str]]:
    """Vəzifə açarları ``workload`` modulundan (app registry — statik import yoxdur)."""
    field = django_apps.get_model("workload", "TeacherWorkloadProfile")._meta.get_field("position")
    return [(key, str(label)) for key, label in field.flatchoices]


def activity_choices() -> list[tuple[str, str]]:
    return [("", pgettext(C.CTX, "Bütün növlər")), *((key, str(label)) for key, label in C.KINDS)]


def _labels(choices) -> dict:
    return {key: label for key, label in choices}


# ── Hesab ────────────────────────────────────────────────────────────────────


def year_rows(organization, academic_year: str) -> list:
    """İlin BÜTÜN sətirləri (aktiv + arxiv) — 1 sorğu; aktivlər əvvəl."""
    if organization is None or not academic_year:
        return []
    return list(
        _model()
        .objects.filter(organization=organization, academic_year=academic_year)
        .order_by("archived_at", "position", "activity", "-created_at")
    )


def active_map(rows) -> dict:
    """``(vəzifə, növ)`` → aktiv sətir (``""`` növ — bütün növlər)."""
    return {(row.position, row.activity): row for row in rows if row.archived_at is None}


def rate_for(rates: dict, position: str, kind: str):
    if not position:
        return None
    return rates.get((position, kind)) or rates.get((position, ""))


def amount(hours, rate) -> Decimal:
    """Saat × dərəcə, 2 rəqəm, ``ROUND_HALF_UP``."""
    return (Decimal(str(hours or 0)) * Decimal(rate)).quantize(CENT, rounding=ROUND_HALF_UP)


def row_pay(row: dict, rates: dict) -> dict:
    """Bir müəllim sətrinin məbləği (dövrün keçirilmiş saatı üzrə) — sorğusuz."""
    position = row.get("position_key") or ""
    kinds, missing, needed = {}, [], []
    for key in C.KIND_KEYS:
        hours = int(row["kinds"].get(key, 0) or 0)
        rate = rate_for(rates, position, key)
        kinds[key] = {
            "hours": hours,
            "rate": rate.hourly_rate if rate else None,
            "rate_id": str(rate.pk) if rate else None,
            "amount": amount(hours, rate.hourly_rate) if rate else None,
        }
        if hours > 0:
            needed.append(key)
            if rate is None:
                missing.append(key)
    if not position:
        status = PAY_NO_POSITION
    elif needed and len(missing) == len(needed):
        status = PAY_NO_RATE
    elif missing:
        status = PAY_PARTIAL
    elif not needed and not any((pos == position) for pos, _kind in rates):
        status = PAY_NO_RATE  # saat yoxdur, amma vəzifənin heç bir dərəcəsi də yoxdur — «0» yazılmır
    else:
        status = PAY_OK
    total = sum((cell["amount"] for cell in kinds.values() if cell["amount"] is not None), Decimal("0.00"))
    return {
        "status": status,
        "kinds": kinds,
        "missing": missing,
        "amount": total.quantize(CENT) if status == PAY_OK else None,
        "hourly_note": hourly_note(row),
    }


def hourly_note(row: dict) -> str:
    """Saathesabı ↔ ştat etiketi (PLAN üzrə — jurnal dərsi bölgü sətrinə bağlı deyil)."""
    from ..hr_analytics.constants import STAFF_HOURLY

    if row.get("staff_type") == STAFF_HOURLY:
        return pgettext(C.CTX, "Saathesabı müəllim — bütün saatlar saathesabı ödənilir.")
    planned = int(row.get("planned_sem") or 0)
    hourly = int(row.get("planned_hourly_sem") or 0)
    if planned <= 0:
        return ""
    if hourly <= 0:
        return pgettext(C.CTX, "Plan üzrə bütün saatlar ştat yükündədir.")
    return pgettext(C.CTX, "Plan üzrə (semestr): ştat yükü {norm} saat, saathesabı {hourly} saat.").format(
        norm=max(planned - hourly, 0), hourly=hourly
    )


def attach(rows, rates: dict) -> None:
    """Hər sətrə ``pay`` açarı (yerində)."""
    for row in rows:
        row["pay"] = row_pay(row, rates)


def totals(rows) -> dict:
    """KPI «Hesablanmış məbləğ»: dərəcəsi tam olan müəllimlərin cəmi + dərəcəsiz müəllimlərin sayı."""
    priced = [row["pay"]["amount"] for row in rows if row.get("pay") and row["pay"]["amount"] is not None]
    return {
        "amount": sum(priced, Decimal("0.00")).quantize(CENT),
        "priced": len(priced),
        "missing": sum(1 for row in rows if row.get("pay") and row["pay"]["amount"] is None),
    }


def missing_text(pay: dict) -> str:
    if pay["status"] == PAY_NO_POSITION:
        return pgettext(C.CTX, "Dərəcə təyin edilməyib (vəzifə yoxdur)")
    if pay["status"] == PAY_PARTIAL:
        labels = _labels((key, str(label)) for key, label in C.KINDS)
        return pgettext(C.CTX, "Dərəcə təyin edilməyib: {kinds}").format(
            kinds=", ".join(labels[key].lower() for key in pay["missing"])
        )
    return pgettext(C.CTX, "Dərəcə təyin edilməyib")


# ── İdarəetmə ────────────────────────────────────────────────────────────────


def can_manage(user, organization, *, request=None) -> bool:
    """``accounting.manage_fees`` TƏŞKİLAT əhatəsində (UNIT rolu bütün təşkilatın dərəcəsini dəyişmir)."""
    if user is None or not getattr(user, "is_authenticated", False) or organization is None:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    from apps.accounts.views._helpers.rbac import _collect_actor_permissions
    from apps.organizations.public import get_permission_scope
    from core.permissions import has_permission

    permissions, _grantable = _collect_actor_permissions(user, organization)
    if not has_permission(list(permissions), PERM_MANAGE_FEES):
        return False
    scope = get_permission_scope(user, organization, PERM_MANAGE_FEES, request=request)
    return bool(scope.has_structure_access and scope.is_org_wide)


def clean_rate(raw) -> Decimal:
    text = str(raw if raw is not None else "").strip().replace(" ", "").replace(",", ".")
    if not text:
        raise ValidationError(pgettext(C.CTX, "Saat dərəcəsini yazın (AZN)."))
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValidationError(pgettext(C.CTX, "Dərəcə rəqəm olmalıdır.")) from None
    if not value.is_finite() or value <= 0 or value > RATE_MAX:
        raise ValidationError(pgettext(C.CTX, "Dərəcə 0-dan böyük və 10 000 AZN-dən az olmalıdır."))
    value = value.quantize(CENT, rounding=ROUND_HALF_UP)
    if value <= 0:
        raise ValidationError(pgettext(C.CTX, "Dərəcə 0-dan böyük və 10 000 AZN-dən az olmalıdır."))
    return value


def known_years(organization) -> list[str]:
    if organization is None:
        return []
    values = (
        django_apps.get_model("organizations", "AcademicPeriod")
        .objects.filter(organization=organization)
        .values_list("academic_year", flat=True)
    )
    return sorted({value for value in values if value}, reverse=True)


def _clean_key(organization, academic_year, position, activity) -> tuple[str, str, str]:
    year = str(academic_year or "").strip()[:20]
    if not year or year not in known_years(organization):
        raise ValidationError(pgettext(C.CTX, "Tədris ilini seçin (akademik dövrlərdə olan il)."))
    position = str(position or "").strip()
    if position not in _labels(position_choices()):
        raise ValidationError(pgettext(C.CTX, "Vəzifəni seçin."))
    activity = str(activity or "").strip()
    if activity not in ("", *C.KIND_KEYS):
        raise ValidationError(pgettext(C.CTX, "Dərs növü düzgün deyil."))
    return year, position, activity


def _snapshot(row) -> dict:
    return {
        "id": str(row.pk),
        "academic_year": row.academic_year,
        "position": row.position,
        "activity": row.activity,
        "hourly_rate": str(row.hourly_rate),
    }


def _archive(row, *, actor, reason) -> None:
    row.archived_at = timezone.now()
    row.archived_by = actor
    row.archived_by_name = _actor_name(actor)
    row.archive_reason = reason
    row.save(update_fields=["archived_at", "archived_by", "archived_by_name", "archive_reason", "updated_at"])


@transaction.atomic
def save_rate(*, actor, organization, academic_year, position, activity="", hourly_rate, note="", request=None):
    """Dərəcəni yarat və ya dəyiş (köhnə aktiv sətir «əvəzləndi» ilə arxivlənir — tarixçə qalır)."""
    from core.audit import log_action
    from core.constants import AuditAction

    from ...models import PayRateArchiveReason

    if not can_manage(actor, organization, request=request):
        raise PermissionDenied
    year, position, activity = _clean_key(organization, academic_year, position, activity)
    rate = clean_rate(hourly_rate)
    note = str(note or "").strip()[:300]
    model = _model()
    current = (
        model.objects.select_for_update()
        .filter(
            organization=organization,
            academic_year=year,
            position=position,
            activity=activity,
            archived_at__isnull=True,
        )
        .first()
    )
    if current is not None and current.hourly_rate == rate and current.note == note:
        raise ValidationError(pgettext(C.CTX, "Bu dərəcə artıq qüvvədədir — dəyişiklik yoxdur."))
    old = _snapshot(current) if current is not None else None
    try:
        with transaction.atomic():
            if current is not None:
                _archive(current, actor=actor, reason=PayRateArchiveReason.REPLACED)
            row = model.objects.create(
                organization=organization,
                academic_year=year,
                position=position,
                activity=activity,
                hourly_rate=rate,
                note=note,
                created_by=actor,
                created_by_name=_actor_name(actor),
            )
    except IntegrityError as exc:
        raise ValidationError(pgettext(C.CTX, "Bu dərəcə eyni anda başqa istifadəçi tərəfindən dəyişdirilib.")) from exc
    log_action(
        AuditAction.UPDATE if old else AuditAction.CREATE,
        user=actor,
        organization=organization,
        obj=row,
        reason="pay_rate_replaced" if old else "pay_rate_created",
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(row.pk),
        old_values=old or {},
        new_values=_snapshot(row),
    )
    return row


@transaction.atomic
def archive_rate(*, actor, organization, rate_id, request=None):
    """«Sil» — sətir SİLİNMİR, «ləğv edildi» səbəbi ilə arxivlənir."""
    from core.audit import log_action
    from core.constants import AuditAction

    from ...models import PayRateArchiveReason

    if not can_manage(actor, organization, request=request):
        raise PermissionDenied
    model = _model()
    row = (
        model.objects.select_for_update()
        .filter(pk=rate_id, organization=organization, archived_at__isnull=True)
        .first()
    )
    if row is None:
        raise model.DoesNotExist
    _archive(row, actor=actor, reason=PayRateArchiveReason.REMOVED)
    log_action(
        AuditAction.DELETE,
        user=actor,
        organization=organization,
        obj=row,
        reason="pay_rate_archived",
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(row.pk),
        old_values=_snapshot(row),
        new_values={"archived": True},
    )
    return row


__all__ = [
    "PAY_NO_POSITION",
    "PAY_NO_RATE",
    "PAY_OK",
    "PAY_PARTIAL",
    "PERM_MANAGE_FEES",
    "active_map",
    "activity_choices",
    "amount",
    "archive_rate",
    "attach",
    "can_manage",
    "clean_rate",
    "hourly_note",
    "known_years",
    "missing_text",
    "position_choices",
    "rate_for",
    "row_pay",
    "save_rate",
    "totals",
    "year_rows",
]
