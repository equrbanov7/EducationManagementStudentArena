"""Profil "superadmin-exam-rooms" bölməsi — imtahan zalı + kompüter/MAC.

``section`` dict-ini YERİNDƏ mutasiya edir (superadmin_orgs pattern-i ilə eyni).
Superadmin cross-org (org seçici); bayraqlı qeyri-superadmin yalnız aktiv təşkilatı.
"""

from django.db.models import Count, Prefetch, Q
from django.urls import reverse

from apps.accounts.views._helpers.formatting import _append_query_params

_LIVE_STATES = ("entry_open", "active")


def build_exam_rooms_section(request, section, *, is_superadmin, active_organization, allowed_sections, active_section):
    if "superadmin-exam-rooms" not in allowed_sections or active_section != "superadmin-exam-rooms":
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

    section["is_superadmin"] = is_superadmin
    section["org_options"] = org_options
    section["selected_org"] = selected_org
    section["post_next_url"] = _append_query_params(
        reverse("accounts:profile"),
        section="superadmin-exam-rooms",
        **({"room_org": str(selected_org.pk)} if (is_superadmin and selected_org) else {}),
    )

    if selected_org is None:
        section["rooms"] = []
        section["room_managers"] = []
        return

    computers_prefetch = Prefetch(
        "computers",
        queryset=ExamRoomComputer.objects.order_by("seat_number", "label", "id"),
    )
    rooms = list(
        ExamRoom.objects.filter(organization=selected_org)
        .annotate(
            live_session_count=Count("sessions", filter=Q(sessions__state__in=_LIVE_STATES), distinct=True),
        )
        .prefetch_related(computers_prefetch, "invigilators")
        .order_by("name", "id")
    )
    # Kompüter sayğaclarını hazırlanmış siyahıdan hesabla (əlavə sorğu yox).
    for room in rooms:
        comps = list(room.computers.all())
        room.computer_registered = len(comps)
        room.computer_with_ip = sum(1 for c in comps if c.ip_address)
    section["rooms"] = rooms

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
    else:
        section["room_managers"] = []
