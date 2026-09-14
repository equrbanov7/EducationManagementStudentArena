"""Profil "superadmin-exam-rooms" bölməsi — imtahan zalı + kompüter/MAC.

2026-09-11 redizayn (sahib: «yenidən, daha təkmil formada; iki başlıq
olmasın»): zallar böyük kartlar yox, `ems_ui` dilində CƏDVƏLDİR — üstdə KPI
sırası, avto filtr (ad/kod axtarışı, status, bina), server tərəfli sıralama
və səhifələmə. Zalın kompüterləri və əməlləri sətirdən açılan ÇEKMECƏDƏDİR
(`_drawer.html`); yaratma/redaktə formaları ortaq `_form_dialog.html`
dialoqlarıdır (sətir dəyərləri `data-tof-prefill` JSON-u ilə doldurulur).

Kontekst `ems_ui` komponent müqavilələrinə uyğundur (`_kpi_row`,
`_filter_bar`, `_data_table`). ``section`` dict-i YERİNDƏ mutasiya olunur
(superadmin_orgs pattern-i). Superadmin cross-org (org seçici); bayraqlı
qeyri-superadmin yalnız aktiv təşkilatı. İcazə yoxlamaları DƏYİŞMƏYİB.
"""

import json
import re
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, Sum
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params

_CTX = "accounts.superadmin_exam_rooms"
_SECTION = "superadmin-exam-rooms"
_LIVE_STATES = ("entry_open", "active")
_PAGE_SIZE = 25
_CELL_DIR = "accounts/profile/sections/superadmin/exam_rooms/"

#: Sütun sıralaması — açar ↔ `order_by` (ikinci açar sabit sıra üçündür).
_SORTS = {
    "name": ("name", "id"),
    "-name": ("-name", "-id"),
    "code": ("code", "id"),
    "-code": ("-code", "-id"),
    "capacity": ("capacity", "name", "id"),
    "-capacity": ("-capacity", "name", "id"),
    "computers": ("computer_registered", "name", "id"),
    "-computers": ("-computer_registered", "name", "id"),
}


def build_exam_rooms_section(request, section, *, is_superadmin, active_organization, allowed_sections, active_section):
    if _SECTION not in allowed_sections or active_section != _SECTION:
        return

    from apps.exams.public import ExamRoom, ExamRoomComputer
    from apps.organizations.models import Organization

    # ── Hədəf təşkilat ─────────────────────────────────────────────────────
    if is_superadmin:
        org_options = list(Organization.objects.filter(is_active=True).order_by("name").values("id", "name"))
        selected_org_id = (request.GET.get("room_org") or "").strip()
        selected_org = None
        if selected_org_id:
            selected_org = Organization.objects.filter(pk=selected_org_id).first()
        # Defolt: superadminin AKTİV təşkilatı — əlifba üzrə ilk org yox.
        # (Əks halda MAC «yanlış» təşkilatın eyni adlı zalına yazılır və
        # istifadəçi öz org kontekstində onu görmür.)
        if selected_org is None and active_organization is not None:
            selected_org = active_organization
        if selected_org is None and org_options:
            selected_org = Organization.objects.filter(pk=org_options[0]["id"]).first()
    else:
        org_options = []
        selected_org = active_organization

    filters = _read_filters(request)
    base_params = {
        "section": _SECTION,
        **({"room_org": str(selected_org.pk)} if (is_superadmin and selected_org) else {}),
        "xr_q": filters["q"],
        "xr_status": filters["status"],
        "xr_building": filters["building"],
        "xr_sort": filters["sort"] if filters["sort"] != "name" else "",
    }
    query = {k: v for k, v in base_params.items() if v}

    section["is_superadmin"] = is_superadmin
    section["org_options"] = org_options
    section["selected_org"] = selected_org
    section["action_url"] = reverse("accounts:superadmin_exam_rooms")
    section["subtitle"] = pgettext(
        _CTX,
        "Zalları, kompüterləri və MAC/IP qeydlərini idarə edin. Bu bölmə yalnız superadmin "
        "(və ya təyin olunmuş zal idarəçisi) üçündür.",
    )
    # POST-dan sonra istifadəçi EYNİ filtr/səhifəyə qayıdır (vurğulanan sətir görünsün).
    section["post_next_url"] = _append_query_params(
        reverse("accounts:profile"),
        **query,
        **({"xr_page": filters["page"]} if filters["page"] else {}),
    )
    section["rooms"] = []
    section["table_rows"] = []
    section["room_managers"] = []
    section["table_state"] = "empty"

    if selected_org is None:
        section["kpi_tiles"] = []
        section["filter_fields"] = []
        section["columns"] = []
        section["page_obj"] = None
        section["pagination_query"] = ""
        return

    org_rooms = ExamRoom.objects.filter(organization=selected_org)
    buildings = _buildings(org_rooms)

    # ── Siyahı: filtr → sıralama → səhifə ─────────────────────────────────
    queryset = org_rooms.annotate(computer_registered=Count("computers", distinct=True))
    if filters["q"]:
        queryset = queryset.filter(Q(name__icontains=filters["q"]) | Q(code__icontains=filters["q"]))
    if filters["status"]:
        queryset = queryset.filter(is_active=(filters["status"] == "active"))
    if filters["building"]:
        queryset = queryset.filter(building=filters["building"])
    queryset = queryset.order_by(*_SORTS[filters["sort"]]).prefetch_related(
        Prefetch("computers", queryset=ExamRoomComputer.objects.order_by("seat_number", "label", "id")),
        "invigilators",
    )
    page_obj = Paginator(queryset, _PAGE_SIZE).get_page(filters["page"] or 1)
    rooms = list(page_obj.object_list)

    # Canlı oturum sayı ayrıca (yüngül) sorğudur — `computers` ilə eyni
    # sorğuda ikinci join sətir partlayışı yaradırdı.
    live_by_room = dict(
        ExamRoom.objects.filter(pk__in=[room.pk for room in rooms])
        .annotate(live=Count("sessions", filter=Q(sessions__state__in=_LIVE_STATES), distinct=True))
        .values_list("pk", "live")
    )
    for room in rooms:
        _decorate_room(room, live_by_room.get(room.pk, 0))

    is_filtered = bool(filters["q"] or filters["status"] or filters["building"])
    section["rooms"] = rooms
    section["page_obj"] = page_obj
    section["pagination_query"] = urlencode(query)
    section["table_state"] = "ready" if rooms else "empty"
    section["columns"] = _columns(base_params, filters["sort"])
    section["table_rows"] = [_table_row(room) for room in rooms]
    section["filter_fields"] = _filter_fields(filters, buildings)
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(n)d zal") % {"n": page_obj.paginator.count}
    section["kpi_tiles"] = _kpi_tiles(org_rooms, ExamRoomComputer.objects.filter(organization=selected_org))
    section["state_title"] = (
        pgettext(_CTX, "Filtrə uyğun zal yoxdur") if is_filtered else pgettext(_CTX, "Bu təşkilatda hələ zal yoxdur")
    )
    section["state_body"] = (
        pgettext(_CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.")
        if is_filtered
        else pgettext(_CTX, "«Yeni zal» ilə ilk zalı yaradın; kompüterlər zalın çekmecəsindən əlavə olunur.")
    )
    section["new_room_prefill"] = _prefill(
        action="create_room",
        room_id="",
        name="",
        code="",
        building="",
        floor="",
        capacity="0",
        computer_count="0",
        notes="",
        is_active="1",
    )
    # Ortaq dialoqların gizli sahələri. `keep` olanlar prefill-dən kənardadır
    # (`data-tof-keep` — açılışda sıfırlanmır); `action`/`room_id`/`computer_id`
    # isə HƏR prefill-də açıq verilir ki, əvvəlki açılışın dəyəri qalmasın.
    # `data-sar-form`: göndərişdən əvvəl HTML5 validasiya (dialoq `novalidate`-dir).
    section["form_data"] = {"data-sar-form": "1"}
    org_field = {"name": "organization_id", "value": str(selected_org.pk), "keep": True}
    next_field = {"name": "next", "value": section["post_next_url"], "keep": True}
    section["room_hidden"] = [
        {"name": "action", "value": "create_room"},
        {"name": "room_id", "value": ""},
        org_field,
        next_field,
    ]
    section["computer_hidden"] = [
        {"name": "action", "value": "add_computer"},
        {"name": "room_id", "value": ""},
        {"name": "computer_id", "value": ""},
        org_field,
        next_field,
    ]
    section["bulk_hidden"] = [
        {"name": "action", "value": "bulk_add_computers", "keep": True},
        {"name": "room_id", "value": ""},
        org_field,
        next_field,
    ]

    # ── Zal idarəçiləri (grant) — yalnız superadmin ────────────────────────
    if is_superadmin:
        from django.contrib.auth import get_user_model

        from core.rls import bypass_rls

        User = get_user_model()
        with bypass_rls():
            section["room_managers"] = list(
                User.objects.filter(profile__can_manage_exam_rooms=True)
                .exclude(is_superuser=True)
                .order_by("username")
                .values("id", "username", "email", "first_name", "last_name")
            )


# ─── Köməkçilər ──────────────────────────────────────────────────────────────


def _read_filters(request):
    """URL-dəki `xr_*` parametrləri (applied vəziyyət); naməlum dəyər = defolt."""
    sort = (request.GET.get("xr_sort") or "").strip()
    status = (request.GET.get("xr_status") or "").strip()
    return {
        "q": (request.GET.get("xr_q") or "").strip()[:120],
        "status": status if status in ("active", "inactive") else "",
        "building": (request.GET.get("xr_building") or "").strip()[:120],
        "sort": sort if sort in _SORTS else "name",
        "page": (request.GET.get("xr_page") or "").strip(),
    }


def _natural_key(value):
    """«2», «10», «Korpus A» — rəqəmli binalar say kimi sıralanır."""
    return [(0, int(part)) if part.isdigit() else (1, part.lower()) for part in re.split(r"(\d+)", value) if part]


def _buildings(org_rooms):
    values = {b for b in org_rooms.exclude(building="").order_by().values_list("building", flat=True) if b}
    return sorted(values, key=_natural_key)


def _prefill(**values):
    """`data-tof-prefill` JSON-u — bütün dəyərlər SƏTİRDİR (form sahələrinə yazılır)."""
    return json.dumps({key: "" if value is None else str(value) for key, value in values.items()}, ensure_ascii=False)


def _decorate_room(room, live_count):
    """Sətir/çekmecə üçün hesablanan sahələr — əlavə sorğu YOX (prefetch-dən)."""
    computers = list(room.computers.all())
    room.computer_rows = computers
    room.computer_with_ip = sum(1 for c in computers if c.ip_address)
    room.invigilator_count = len(room.invigilators.all())
    room.live_session_count = live_count
    room.status_key = "active" if room.is_active else "inactive"
    room.plan_mismatch = bool(room.computer_count and room.computer_registered != room.computer_count)
    room.drawer_id = f"sarRoomDrawer-{room.pk}"
    room.drawer_subtitle = " · ".join(part for part in (room.code, room.building, room.floor) if part)
    room.edit_prefill = _prefill(
        action="update_room",
        room_id=room.pk,
        name=room.name,
        code=room.code,
        building=room.building,
        floor=room.floor,
        capacity=room.capacity,
        computer_count=room.computer_count,
        notes=room.notes,
        is_active="1" if room.is_active else "",
    )
    room.computer_add_prefill = _prefill(
        action="add_computer",
        room_id=room.pk,
        computer_id="",
        label="",
        seat_number="",
        mac_address="",
        ip_address="",
        notes="",
        is_active="1",
    )
    room.bulk_prefill = _prefill(action="bulk_add_computers", room_id=room.pk, bulk_text="")
    for computer in computers:
        computer.status_key = "active" if computer.is_active else "off"
        computer.edit_prefill = _prefill(
            action="update_computer",
            room_id=room.pk,
            computer_id=computer.pk,
            label=computer.label,
            seat_number=computer.seat_number if computer.seat_number is not None else "",
            mac_address=computer.mac_address,
            ip_address=computer.ip_address or "",
            notes=computer.notes,
            is_active="1" if computer.is_active else "",
        )


def _table_row(room):
    """`_data_table.html` müqaviləsi: birinci sütun `th scope=row`, sonuncu əməllər."""
    return {
        "row_head": room.name,
        "head_include": f"{_CELL_DIR}_cell_room.html",
        "cells": [
            {"text": room.code, "mono": True, "nowrap": True},
            {"text": room.capacity, "num": True},
            {"include": f"{_CELL_DIR}_cell_computers.html", "num": True},
            {"text": room.computer_with_ip, "num": True},
            {"text": room.invigilator_count, "num": True},
            {"include": f"{_CELL_DIR}_cell_status.html", "nowrap": True},
        ],
        "actions_include": f"{_CELL_DIR}_row_actions.html",
        "room": room,
    }


def _sort_url(base_params, key, current):
    params = dict(base_params)
    params["xr_sort"] = f"-{key}" if current == key else key
    return f"{reverse('accounts:profile')}?{urlencode({k: v for k, v in params.items() if v})}"


def _sort_dir(current, key):
    if current == key:
        return "ascending"
    if current == f"-{key}":
        return "descending"
    return None


def _columns(base_params, current):
    # Birinci sütun sətir başlığı, sonuncu əməllər xanasıdır — ikisinin də
    # başlığı OLMALIDIR (bax `_data_table.html`), yoxsa başlıqlar sürüşür.
    specs = (
        ("name", pgettext(_CTX, "Zal")),
        ("code", pgettext(_CTX, "Kod")),
        ("capacity", pgettext(_CTX, "Yer")),
        ("computers", pgettext(_CTX, "Kompüter")),
        ("", pgettext(_CTX, "IP ilə")),
        ("", pgettext(_CTX, "Nəzarətçi")),
        ("", pgettext(_CTX, "Status")),
        ("", pgettext(_CTX, "Əməllər")),
    )
    return [
        {
            "key": key,
            "label": label,
            "sortable": bool(key),
            "sort_url": _sort_url(base_params, key, current) if key else "",
            "sort_dir": _sort_dir(current, key) if key else None,
        }
        for key, label in specs
    ]


def _filter_fields(filters, buildings):
    any_label = pgettext(_CTX, "Hamısı")
    fields = [
        {
            "name": "xr_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": filters["q"],
            "wide": True,
            "placeholder": pgettext(_CTX, "Zal adı və ya kodu"),
        },
        {
            "name": "xr_status",
            "label": pgettext(_CTX, "Status"),
            "kind": "select",
            "value": filters["status"],
            "options": [
                {"value": "", "label": any_label},
                {"value": "active", "label": pgettext(_CTX, "Aktiv")},
                {"value": "inactive", "label": pgettext(_CTX, "Deaktiv")},
            ],
        },
    ]
    if buildings:
        fields.append(
            {
                "name": "xr_building",
                "label": pgettext(_CTX, "Bina"),
                "kind": "select",
                "value": filters["building"],
                "searchable": len(buildings) > 8,
                "options": [{"value": "", "label": any_label}] + [{"value": b, "label": b} for b in buildings],
            }
        )
    return fields


def _kpi_tiles(org_rooms, org_computers):
    """KPI-lar BÜTÜN təşkilat üzrədir (filtrdən asılı deyil) — iki aqreqat sorğu."""
    # Alias-lar model sahəsi ilə EYNİ ola bilməz (`capacity=Sum("capacity")` →
    # FieldError «'capacity' is an aggregate»).
    rooms = org_rooms.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        seats=Sum("capacity"),
        active_seats=Sum("capacity", filter=Q(is_active=True)),
        planned=Sum("computer_count"),
    )
    computers = org_computers.aggregate(
        total=Count("id"),
        with_ip=Count("id", filter=Q(ip_address__isnull=False)),
    )
    live_rooms = org_rooms.filter(sessions__state__in=_LIVE_STATES).distinct().count()
    inactive = (rooms["total"] or 0) - (rooms["active"] or 0)
    plan = rooms["planned"] or 0
    registered = computers["total"] or 0
    tiles = [
        {"label": pgettext(_CTX, "Zal"), "value": rooms["total"] or 0, "tone": "primary"},
        {
            "label": pgettext(_CTX, "Aktiv zal"),
            "value": rooms["active"] or 0,
            "tone": "accent-success",
            "note": (
                pgettext(_CTX, "%(n)d deaktiv") % {"n": inactive} if inactive else pgettext(_CTX, "hamısı aktivdir")
            ),
        },
        {
            "label": pgettext(_CTX, "Ümumi yer"),
            "value": rooms["seats"] or 0,
            "note": pgettext(_CTX, "aktiv zallarda %(n)d") % {"n": rooms["active_seats"] or 0},
        },
        {
            "label": pgettext(_CTX, "Kompüter"),
            "value": registered,
            "tone": "accent-warning" if plan and registered != plan else "",
            "note": (
                pgettext(_CTX, "%(ip)d IP ilə · plan %(plan)d") % {"ip": computers["with_ip"] or 0, "plan": plan}
                if plan
                else pgettext(_CTX, "%(ip)d IP ilə") % {"ip": computers["with_ip"] or 0}
            ),
        },
    ]
    if live_rooms:
        tiles.append(
            {
                "label": pgettext(_CTX, "Canlı oturum"),
                "value": live_rooms,
                "tone": "accent-danger",
                "note": pgettext(_CTX, "hazırda imtahan gedən zal"),
            }
        )
    return tiles
