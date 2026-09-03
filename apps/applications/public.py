"""Müraciətlər modulunun PUBLIC fasadı — CONTEXT MÜQAVİLƏSİ.

Digər modullar (profil kabineti, badge borusu, gələcək hesabatlar) modulun
DAXİLİNƏ girmir: yalnız buradakı funksiyaları çağırır.

──────────────────────────────────────────────────────────────────────────────
EKRAN
──────────────────────────────────────────────────────────────────────────────
Panel profil kabinetinin BÖLMƏSİDİR (sol sidebar qalır, sağda AJAX fraqment) —
ayrıca tam səhifə DEYİL. Bölmə açarı: ``applications.public.PROFILE_SECTION``
(= ``"applications"``). Bölmə qeydiyyatı 4 yerdə eyni olmalıdır:
``sections_api.SECTION_PARTIALS``, ``AJAX_SAFE_SECTIONS``, ``profile.html``
``data-ajax-sections`` və ``rbac.allowed_sections``.

──────────────────────────────────────────────────────────────────────────────
CONTEXT QURUCUSU — ``build_applications_context(request, organization)``
──────────────────────────────────────────────────────────────────────────────
``{
    "family": "student"|"teacher"|"staff"|None,   # göndərən ailəsi
    "can_create": bool,          # application.create + aktiv üzvlük
    "is_handler": bool,          # ən azı bir şöbənin emalçısıdır
    "can_manage": bool,          # application.manage (RİM/rektor/prorektor)
    "kinds": [kind payload…],    # yalnız bu ailəyə açıq növlər + hesablanmış ünvan
    "units": [unit payload…],    # yönləndirmə dialoqu üçün
    "statuses": [status payload…],
    "counts": {"mine","inbox","watching","archive"},
    "kpis": {"sender": {…}, "handler": {…}|None},
    "endpoints": {…},            # UI-nin çağıracağı JSON marşrutları
    "rules": {"min_subject_length": 5, "min_body_length": 20, "min_note_length": 10},
}``

XƏTA FORMATI (bütün endpoint-lər): ``{"ok": false, "errors": {"<sahə>": ["mətn"]}}``.
Sahəyə bağlanmayan xəta ``"__all__"`` açarındadır; keçid xətalarında əlavə
``"code"`` açarı maşın-oxunaqlı səbəbi daşıyır (``transition.invalid_source``,
``transition.reason_required``, ``permission.not_handler``, …).
"""

from __future__ import annotations

from django.urls import reverse

from .constants import PERM_CREATE, PERM_HANDLE, PERM_MANAGE, ApplicationStatus, SenderFamily
from .payloads import (
    STATUS_CATALOG,
    detail_payload,
    kind_payload,
    row_payload,
    rules_payload,
    unit_payload,
)
from .services import access, queries, routing
from .services.catalog import seed_catalog
from .services.maintenance import close_stale_resolved
from .services.notify import PROFILE_SECTION
from .state_machine import Action, TransitionDenied, available_actions


def endpoints() -> dict:
    """UI-nin çağıracağı marşrutlar — şablon onları data-atributla ötürür."""
    return {
        "list": reverse("applications:list"),
        "catalog": reverse("applications:catalog"),
        "kpis": reverse("applications:kpis"),
        "create": reverse("applications:create"),
        #: ``{id}`` yer tutucusu — JS onu müraciətin id-si ilə əvəz edir.
        "detail": reverse("applications:detail", kwargs={"application_id": "00000000-0000-0000-0000-000000000000"}),
        "action": reverse("applications:action", kwargs={"application_id": "00000000-0000-0000-0000-000000000000"}),
    }


def build_applications_context(request, *, organization) -> dict:
    """«Müraciətlərim» bölməsinin ilkin context-i (qalan hər şey AJAX-dır)."""
    user = getattr(request, "user", None)
    family = routing.sender_family_for(user, organization)
    can_create = bool(family) and access.has_app_permission(user, organization, PERM_CREATE)
    is_handler = access.is_handler_anywhere(user, organization)

    kinds = []
    if can_create:
        sender_unit = routing.sender_scope_unit_for(user, organization, family)
        for kind in routing.allowed_kinds_for(organization, family):
            destination, _scope, _family, _unit = routing.route_for(
                kind, user, organization=organization, family=family, sender_unit=sender_unit
            )
            kinds.append(kind_payload(kind, destination=destination))

    from .models import ApplicationUnit

    units = ApplicationUnit.objects.filter(organization=organization, is_active=True).order_by("order", "name")
    return {
        "section": PROFILE_SECTION,
        "family": family,
        "can_create": can_create,
        "is_handler": is_handler,
        "can_manage": access.has_app_permission(user, organization, PERM_MANAGE),
        "kinds": kinds,
        "units": [unit_payload(unit) for unit in units],
        "statuses": list(STATUS_CATALOG),
        "counts": queries.tab_counts(organization=organization, user=user),
        "kpis": {
            "sender": queries.sender_kpis(organization=organization, user=user),
            "handler": queries.handler_kpis(organization=organization, user=user) if is_handler else None,
        },
        "endpoints": endpoints(),
        "rules": rules_payload(),
    }


def open_application_count(user, organization) -> int:
    """Sidebar badge-i üçün ucuz sayğac (sahibin açıq + emalçının gələnləri)."""
    counts = queries.tab_counts(organization=organization, user=user)
    return int(counts.get("mine", 0)) + int(counts.get("inbox", 0))


def pending_badge_count(user, organization) -> int:
    """Sidebar badge-i: emalçıya GƏLƏN açıqlar, göndərənə MƏLUMAT gözlənilənlər.

    İki fərqli rəqəm QƏSDƏNDİR: emalçı üçün «məndə nə var», göndərən üçün
    «məndən nə istənilib». Göndərənin sadəcə açıq müraciəti onun ƏMƏLİNİ
    tələb etmir — badge yalnız hərəkət lazım olanda yanmalıdır.
    """
    if organization is None:
        return 0
    if access.is_handler_anywhere(user, organization):
        return int(queries.handler_kpis(organization=organization, user=user).get("inbox_open", 0))
    return int(queries.sender_kpis(organization=organization, user=user).get("waiting_info", 0))


def handled_unit_names(user, organization) -> list:
    """Aktorun emalçısı olduğu şöbələrin adları (kontekst zolağı üçün)."""
    from .models import ApplicationUnit

    if organization is None:
        return []
    unit_ids = access.handled_unit_ids(user, organization)
    if not unit_ids:
        return []
    return list(
        ApplicationUnit.objects.filter(organization=organization, pk__in=unit_ids)
        .order_by("order", "name")
        .values_list("name", flat=True)
    )


def assignable_handlers(user, organization, application_id) -> list:
    """«Təyin et» dialoqunun namizədləri — CARİ şöbəni əhatə edən emalçılar.

    Qapı əməl qapısı ilə EYNİDİR: yalnız müraciət üzərində qərar verə bilən
    aktor siyahını görür (fail-closed). Namizədlər bildiriş borusunun işlətdiyi
    ``handler_recipients`` ilə eyni mənbədəndir — təyin edilən adam müraciəti
    onsuz da görür.
    """
    from .models import Application
    from .payloads import person
    from .services.notify import handler_recipients

    application = (
        Application.objects.filter(organization=organization, pk=application_id)
        .select_related("current_unit", "current_scope_unit", "organization")
        .first()
    )
    if application is None or not access.can_act(user, application):
        return []
    return [person(candidate) for candidate in handler_recipients(application)]


def can_use_applications(user, organization) -> bool:
    """Menyu görünürlüyü: üç açardan HƏR HANSI BİRİ bölməni açır."""
    if organization is None:
        return False
    return any(
        access.has_app_permission(user, organization, permission)
        for permission in (PERM_CREATE, PERM_HANDLE, PERM_MANAGE)
    )


__all__ = [
    "Action",
    "ApplicationStatus",
    "PERM_CREATE",
    "PERM_HANDLE",
    "PERM_MANAGE",
    "PROFILE_SECTION",
    "STATUS_CATALOG",
    "SenderFamily",
    "TransitionDenied",
    "available_actions",
    "assignable_handlers",
    "build_applications_context",
    "can_use_applications",
    "close_stale_resolved",
    "detail_payload",
    "endpoints",
    "handled_unit_names",
    "open_application_count",
    "pending_badge_count",
    "row_payload",
    "seed_catalog",
]
