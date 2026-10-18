"""25% müraciət PƏNCƏRƏSİ — «İmtahan mərkəzi açsın bunu» (sahib 2026-10-19).

Qayda: müraciət yalnız (1) ``retake.applications_open`` ümumi açarı yanılıdırsa (qəza söndürücüsü, defolt
açıq) VƏ (2) təşkilatda hazırda açıq pəncərə varsa qəbul olunur. Pəncərəni ``exam_center.decide`` açarı olan
(İmtahan mərkəzi rəhbəri / əməkdaşı, RİM rəhbəri ``*`` ilə) açır və bağlayır. Hər pəncərə akademik dövrə
bağlıdır; bir dövrdə eyni anda bir açıq pəncərə (qismən unikal məhdudiyyət). Sətir silinmir — bağlanış
(kim, nə vaxt, qeyd) eyni sətrə yazılır, siyahı tarixçədir.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import retake_access
from .models import RetakeWindow

_CTX = "registrar.retake"

PERM_WINDOW = "exam_center.decide"
HISTORY_LIMIT = 20


def can_manage(user, organization) -> bool:
    """Təşkilat səviyyəli qərar — açar ORG-WIDE əhatədə olmalıdır (alt-bölmə rolu kifayət deyil)."""
    return retake_access.has_org_wide_key(user, organization, PERM_WINDOW)


def _open_q(moment):
    return Q(closed_at__isnull=True, opens_at__lte=moment) & (Q(closes_at__isnull=True) | Q(closes_at__gt=moment))


def current(organization, *, now=None):
    """Hazırda açıq pəncərə (ən son açılan) və ya ``None``."""
    if organization is None:
        return None
    moment = now or timezone.now()
    return (
        RetakeWindow.objects.filter(organization=organization)
        .filter(_open_q(moment))
        .select_related("period")
        .order_by("-opens_at")
        .first()
    )


def upcoming(organization, *, now=None):
    """Hələ açılmamış (planlaşdırılmış) ən yaxın pəncərə və ya ``None``."""
    if organization is None:
        return None
    moment = now or timezone.now()
    return (
        RetakeWindow.objects.filter(organization=organization, closed_at__isnull=True, opens_at__gt=moment)
        .select_related("period")
        .order_by("opens_at")
        .first()
    )


def history(organization, *, limit=HISTORY_LIMIT) -> list:
    return list(
        RetakeWindow.objects.filter(organization=organization).select_related("period").order_by("-opens_at")[:limit]
    )


def selectable_periods(organization, *, today=None) -> list:
    """Pəncərə açıla bilən dövrlər — yalnız CARİ və GƏLƏCƏK (bitmiş dövrə pəncərə açılmır)."""
    if organization is None:
        return []
    from django.apps import apps as django_apps

    day = today or timezone.localdate()
    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    return list(
        period_model.objects.filter(organization=organization)
        .filter(Q(is_current=True) | Q(end_date__gte=day))
        .order_by("start_date")[:12]
    )


def _auto_close_expired(organization, period, moment) -> list:
    """Vaxtı keçmiş (``closes_at`` ≤ indi), amma ``closed_at`` boş qalan pəncərələri SİSTEM adından bağla.

    Qismən unikal məhdudiyyət ``closed_at IS NULL`` üzrədir — vaxtı keçmiş pəncərə bağlanmasa həmin dövrə yeni
    pəncərə açmaq mümkün olmur (review 2026-10-19, MEDIUM-2). Bağlanış anı = planlaşdırılmış ``closes_at``."""
    expired = list(
        RetakeWindow.objects.select_for_update()
        .filter(organization=organization, period=period, closed_at__isnull=True, closes_at__lte=moment)
        .order_by("opens_at")
    )
    for window in expired:
        window.closed_at = window.closes_at
        window.closed_by = None
        window.closed_by_name = ""
        window.close_note = "Vaxtı bitdi — sistem bağladı."
        window.save(update_fields=["closed_at", "closed_by", "closed_by_name", "close_note", "updated_at"])
    return expired


def _actor_name(user) -> str:
    return ((user.get_full_name() or "").strip() or user.username)[:200] if user is not None else ""


def _parse_moment(raw, *, required):
    if isinstance(raw, datetime.datetime):
        value = raw
    else:
        text = str(raw or "").strip()
        if not text:
            if required:
                raise ValidationError(pgettext(_CTX, "Açılış vaxtı göstərilməlidir."))
            return None
        try:
            value = datetime.datetime.fromisoformat(text)
        except ValueError:
            raise ValidationError(pgettext(_CTX, "Tarix və saat düzgün deyil.")) from None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


@transaction.atomic
def open_window(*, actor, organization, period, opens_at=None, closes_at=None, note="", request=None):
    if not can_manage(actor, organization):
        raise PermissionDenied
    start = _parse_moment(opens_at, required=False) or timezone.now()
    end = _parse_moment(closes_at, required=False)
    if end is not None and end <= start:
        raise ValidationError(pgettext(_CTX, "Bağlanış vaxtı açılışdan sonra olmalıdır."))
    if period.pk not in {p.pk for p in selectable_periods(organization)}:
        raise ValidationError(pgettext(_CTX, "Pəncərə yalnız cari və ya gələcək dövr üçün açılır."))
    # Dövrün pəncərələri kilidlənir (paralel açılış), vaxtı keçmişlər sistem adından bağlanır.
    list(RetakeWindow.objects.select_for_update().filter(organization=organization, period=period))
    auto_closed = _auto_close_expired(organization, period, timezone.now())
    try:
        with transaction.atomic():
            window = RetakeWindow.objects.create(
                organization=organization,
                period=period,
                opens_at=start,
                closes_at=end,
                note=str(note or "").strip()[:300],
                opened_by=actor,
                opened_by_name=_actor_name(actor),
            )
    except IntegrityError as exc:
        raise ValidationError(
            pgettext(_CTX, "Bu dövr üçün artıq açıq (və ya planlaşdırılmış) pəncərə var — əvvəlcə onu bağlayın.")
        ) from exc
    log_action(
        AuditAction.CREATE,
        user=actor,
        organization=organization,
        obj=window,
        reason="retake_window_opened",
        request=request,
        resource_type="retake_window",
        resource_id=str(window.pk),
        new_values={
            "period": str(period.pk),
            "opens_at": start.isoformat(),
            "closes_at": end.isoformat() if end else None,
            "auto_closed": [str(w.pk) for w in auto_closed],
        },
    )
    return window


@transaction.atomic
def close_window(*, actor, organization, window_id, note="", request=None):
    if not can_manage(actor, organization):
        raise PermissionDenied
    window = RetakeWindow.objects.select_for_update().filter(pk=window_id, organization=organization).first()
    if window is None:
        raise RetakeWindow.DoesNotExist
    if window.closed_at is not None:
        raise ValidationError(pgettext(_CTX, "Pəncərə artıq bağlanıb."))
    window.closed_at = timezone.now()
    window.closed_by = actor
    window.closed_by_name = _actor_name(actor)
    window.close_note = str(note or "").strip()[:300]
    window.save(update_fields=["closed_at", "closed_by", "closed_by_name", "close_note", "updated_at"])
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=window,
        reason="retake_window_closed",
        request=request,
        resource_type="retake_window",
        resource_id=str(window.pk),
        new_values={"closed_at": window.closed_at.isoformat()},
    )
    return window


__all__ = [
    "PERM_WINDOW",
    "can_manage",
    "close_window",
    "current",
    "history",
    "open_window",
    "selectable_periods",
    "upcoming",
]
