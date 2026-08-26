"""RİM semestr-sonu TOPLU jurnal bağlama/açma servisi.

SAHİBİN QƏRARI (2026-08): jurnal təsdiqə GETMİR. Müəllim balı yazır və bitir.
Semestr sonunda RİM (Rəqəmsal İnkişaf Mərkəzi) dövr üzrə jurnalları — bütün
təşkilat, bir FAKÜLTƏ və ya bir KAFEDRA əhatəsində — toplu bağlayır. Məqsəd
tələbələrin ümumi GİRİŞ BALINI yekunlaşdırmaqdır.

Bağlama = ``AssessmentScheme.approval_status = APPROVED`` + ``is_published = True``
(CheckConstraint ``registrar_scheme_publish_state_valid`` bu cütü tələb edir).
Bundan sonra jurnal redaktəyə bağlıdır (bax :func:`gradebook.journal_is_locked`).

Xüsusiyyətlər:

* **İDEMPOTENT** — artıq bağlı jurnal təkrar bağlananda dəyişmir, sadəcə
  ``already`` sayğacına düşür;
* **ATOMİK** — bütün əməliyyat tək tranzaksiyada, tək UPDATE ilə (qismən
  bağlanmış vəziyyət qalmır);
* **AUDİTLİ** — hər bağlama/açma bir AuditLog sətri yazır: kim, hansı əhatə,
  hansı dövr, neçə jurnal, səbəb;
* **AÇMAQ (reopen)** — səhv bağlamanı geri qaytarmaq üçün; SƏBƏB MƏCBURİDİR.
  Açmaq sənədli düzəliş axınını ƏVƏZ ETMİR: bağlı jurnalda tək-tək düzəliş üçün
  ``journal.correct`` + PDF yolu qalır (:mod:`apps.registrar.corrections`).

MODUL SƏRHƏDİ: registrar ``apps.organizations``-u import ETMİR — OrgUnit/
AcademicPeriod app registry ilə həll olunur.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.registrar import journal_scope
from apps.registrar.models import ApprovalStatus, AssessmentScheme, CourseOffering

#: Toplu əməliyyatın audit resurs tipi (audit axtarışında süzgəc açarı).
AUDIT_RESOURCE_TYPE = "registrar.journal_close"


class JournalCloseError(ValidationError):
    """İstifadəçiyə göstərilə bilən toplu-bağlama xətası."""


def _org_unit_model():
    from django.apps import apps as django_apps

    return django_apps.get_model("organizations", "OrgUnit")


def resolve_unit(organization, unit_id):
    """``unit_id`` → aktiv OrgUnit (yoxdursa/başqa təşkilatdırsa xəta)."""
    if not unit_id:
        return None
    unit = _org_unit_model().objects.filter(organization=organization, pk=unit_id).first()
    if unit is None:
        raise JournalCloseError("Seçilmiş bölmə tapılmadı.")
    return unit


def scope_label(unit) -> str:
    """Audit + UI üçün əhatənin insan-oxunaqlı adı."""
    return unit.name if unit is not None else "Bütün təşkilat"


def offerings_in_scope(*, organization, period, unit=None):
    """Bu dövr + əhatə üzrə dərs açılışları (``CourseOffering`` queryset).

    ``unit`` verilibsə YALNIZ həmin OrgUnit alt-ağacındakı qruplara aid
    açılışlar götürülür (fakültə → kafedra → qrup zənciri ``path`` prefiksi ilə).
    ``unit`` yoxdursa bütün təşkilat — qrupu olmayan (bütün-ixtisas) açılışlar da
    daxil olmaqla.
    """
    queryset = CourseOffering.objects.filter(organization=organization, period=period)
    if unit is None:
        return queryset
    subtree = (
        _org_unit_model()
        .objects.filter(organization=organization)
        .filter(
            _subtree_q(unit),
        )
    )
    return queryset.filter(group__in=subtree.values("pk"))


def _subtree_q(unit):
    from django.db.models import Q

    query = Q(pk=unit.pk)
    if unit.path:
        query |= Q(path__startswith=f"{unit.path}/")
    return query


def schemes_in_scope(*, organization, period, unit=None):
    """Əhatədəki açılışların ``AssessmentScheme`` sətirləri."""
    return AssessmentScheme.objects.filter(
        organization=organization,
        offering__in=offerings_in_scope(organization=organization, period=period, unit=unit).values("pk"),
    )


def preview(*, organization, period, unit=None) -> dict:
    """UI önizləməsi: əhatədə neçə jurnal var, neçəsi açıq/bağlıdır.

    ``missing`` — hələ ``AssessmentScheme`` sətri yaranmamış açılışlar (müəllim
    jurnalı heç açmayıb). Bağlama zamanı onlar da yaradılıb bağlanır ki, dövr
    üzrə boşluq qalmasın.
    """
    offerings = offerings_in_scope(organization=organization, period=period, unit=unit)
    total = offerings.count()
    schemes = schemes_in_scope(organization=organization, period=period, unit=unit)
    closed = schemes.filter(is_published=True, approval_status=ApprovalStatus.APPROVED).count()
    existing = schemes.count()
    return {
        "total": total,
        "closed": closed,
        "open": total - closed,
        "missing": max(0, total - existing),
        "scope_label": scope_label(unit),
    }


def _audit(*, organization, by_user, action, period, unit, counts, reason, request=None):
    from core.audit import log_action
    from core.constants import AuditAction

    label = scope_label(unit)
    log_action(
        AuditAction.UPDATE,
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=organization,
        obj=None,
        reason=reason,
        request=request,
        resource_type=AUDIT_RESOURCE_TYPE,
        resource_id=str(getattr(period, "pk", "")),
        resource_repr=(
            f"{action} · {label} · {getattr(period, 'name', '—')} · "
            f"{counts['changed']} jurnal (artıq: {counts['already']}, cəmi: {counts['total']})"
        ),
        changes={
            "action": action,
            "scope": label,
            "scope_unit_id": str(unit.pk) if unit is not None else "",
            "period_id": str(getattr(period, "pk", "")),
            "changed": counts["changed"],
            "already": counts["already"],
            "total": counts["total"],
        },
    )


def _ensure_schemes(*, organization, period, unit):
    """Əhatədə sxemi olmayan açılışlar üçün ``AssessmentScheme`` yaradır."""
    offerings = offerings_in_scope(organization=organization, period=period, unit=unit)
    existing = set(
        AssessmentScheme.objects.filter(offering__in=offerings.values("pk")).values_list("offering_id", flat=True)
    )
    missing = [
        AssessmentScheme(organization=organization, offering_id=offering_id)
        for offering_id in offerings.values_list("pk", flat=True)
        if offering_id not in existing
    ]
    if missing:
        AssessmentScheme.objects.bulk_create(missing, ignore_conflicts=True)
    return len(missing)


@transaction.atomic
def close_journals(*, organization, period, by_user, unit=None, reason="", request=None) -> dict:
    """Dövr + əhatə üzrə jurnalları BAĞLA (idempotent, atomik, auditli).

    Nəticə: ``{"closed": n, "already": n, "total": n, "created": n, "scope_label": str}``.
    """
    if not journal_scope.can_close_journals(by_user, organization):
        raise PermissionDenied("Jurnal bağlamaq üçün icazəniz yoxdur.")
    assert_unit_in_actor_scope(by_user, organization, unit)
    if period is None:
        raise JournalCloseError("Dövr (semestr) seçilməlidir.")

    created = _ensure_schemes(organization=organization, period=period, unit=unit)
    schemes = schemes_in_scope(organization=organization, period=period, unit=unit)
    total = schemes.count()
    already = schemes.filter(is_published=True, approval_status=ApprovalStatus.APPROVED).count()
    # Tək UPDATE — qismən bağlanma mümkün deyil; artıq bağlı sətirlərə toxunmur.
    changed = schemes.exclude(is_published=True, approval_status=ApprovalStatus.APPROVED).update(
        is_published=True,
        approval_status=ApprovalStatus.APPROVED,
    )
    counts = {"changed": changed, "already": already, "total": total}
    _audit(
        organization=organization,
        by_user=by_user,
        action="jurnal bağlandı",
        period=period,
        unit=unit,
        counts=counts,
        reason=(reason or "").strip()[:1000] or "Semestr sonu jurnal bağlanması (RİM).",
        request=request,
    )
    return {
        "closed": changed,
        "already": already,
        "total": total,
        "created": created,
        "scope_label": scope_label(unit),
    }


@transaction.atomic
def reopen_journals(*, organization, period, by_user, unit=None, reason, request=None) -> dict:
    """Səhv bağlamanı geri qaytar — SƏBƏB MƏCBURİDİR (idempotent, atomik, auditli).

    Bu, sənədli düzəliş axınını ƏVƏZ ETMİR: bağlı jurnalda bir-iki xananı
    düzəltmək üçün ``journal.correct`` + PDF yolu istifadə olunmalıdır. Açma
    yalnız TOPLU səhvi (yanlış fakültə/dövr seçilib) geri almaq üçündür.
    """
    if not journal_scope.can_close_journals(by_user, organization):
        raise PermissionDenied("Jurnal açmaq üçün icazəniz yoxdur.")
    assert_unit_in_actor_scope(by_user, organization, unit)
    if period is None:
        raise JournalCloseError("Dövr (semestr) seçilməlidir.")
    reason = (reason or "").strip()
    if not reason:
        raise JournalCloseError("Jurnalı açmaq üçün səbəb yazılmalıdır.")

    schemes = schemes_in_scope(organization=organization, period=period, unit=unit)
    total = schemes.count()
    already = schemes.exclude(is_published=True, approval_status=ApprovalStatus.APPROVED).count()
    changed = schemes.filter(is_published=True, approval_status=ApprovalStatus.APPROVED).update(
        is_published=False,
        approval_status=ApprovalStatus.DRAFT,
    )
    counts = {"changed": changed, "already": already, "total": total}
    _audit(
        organization=organization,
        by_user=by_user,
        action="jurnal açıldı",
        period=period,
        unit=unit,
        counts=counts,
        reason=reason[:1000],
        request=request,
    )
    return {
        "reopened": changed,
        "already": already,
        "total": total,
        "scope_label": scope_label(unit),
    }


def assert_unit_in_actor_scope(user, organization, unit):
    """Unit-scoped aktor yalnız ÖZ alt-ağacını bağlaya bilər (fail-closed)."""
    scope = journal_scope.close_scope(user, organization)
    if scope.is_org_wide:
        return
    if unit is None:
        raise PermissionDenied("Bütün təşkilatı bağlamaq üçün icazəniz yoxdur — fakültə/kafedra seçin.")
    covered = (
        _org_unit_model().objects.filter(organization=organization, pk=unit.pk).filter(scope.unit_subtree_q()).exists()
    )
    if not covered:
        raise PermissionDenied("Bu bölmə sizin səlahiyyət sahənizə düşmür.")
