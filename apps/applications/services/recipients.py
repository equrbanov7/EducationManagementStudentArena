"""Kataloq əsasında konkret ünvan və tələbə göndərişi yoxlaması."""

from ..state_machine import TransitionDenied


def selectable_units(units, family):
    return [unit for unit in units if family != "student" or unit.accepts_students]


def recipient_users(unit):
    from django.contrib.auth import get_user_model

    return (
        get_user_model()
        .objects.filter(
            is_active=True,
            memberships__organization_id=unit.organization_id,
            memberships__is_active=True,
            memberships__role__is_active=True,
            memberships__role__organization_id=unit.organization_id,
            memberships__role__name__in=unit.role_names,
        )
        .distinct()
        .order_by("last_name", "first_name", "pk")
    )


def _recipient_titles(unit, user_ids):
    """Hər alıcının vəzifəsi: üzvlük ``title``-ı, yoxdursa profilin ``staff_position``-ı.

    2026-11-10 (sahib): «prorektorun adı-soyadı yanında NƏ prorektoru olduğu da yazılsın» —
    məs. «Tədris işləri üzrə prorektor». Hər iki mənbə bir sorğu ilə oxunur (N+1 yox).
    """
    from django.contrib.auth import get_user_model

    from apps.organizations.models import Membership

    titles = {}
    memberships = Membership.objects.filter(
        organization_id=unit.organization_id,
        user_id__in=user_ids,
        is_active=True,
        role__name__in=unit.role_names,
    ).exclude(title="")
    for user_id, title in memberships.values_list("user_id", "title"):
        titles.setdefault(user_id, title.strip())
    missing = [pk for pk in user_ids if not titles.get(pk)]
    if missing:
        rows = get_user_model().objects.filter(pk__in=missing).values_list("pk", "profile__staff_position")
        for user_id, position in rows:
            if (position or "").strip():
                titles[user_id] = position.strip()
    return titles


def destination_payload(unit):
    if not unit.requires_recipient:
        return []
    users = list(recipient_users(unit))
    titles = _recipient_titles(unit, [user.pk for user in users])
    if "vice_rector" in unit.role_names:
        # Heyət siyahısında vəzifə bölmə başlığı ilə yazılıb («Elmi işlər üzrə») — «… üzrə prorektor» oxunsun.
        titles = {
            pk: title if "prorektor" in title.casefold() else f"{title} prorektor" for pk, title in titles.items()
        }
    return [
        {"id": str(user.pk), "name": user.get_full_name() or user.username, "title": titles.get(user.pk, "")}
        for user in users
    ]


def validate_destination(unit, user, organization, family, recipient_id):
    if unit.organization_id != organization.pk or not unit.is_active:
        raise TransitionDenied("unit.invalid", "Seçilmiş şöbə aktiv deyil.")
    if family == "student" and not unit.accepts_students:
        raise TransitionDenied("unit.student_denied", "Tələbələr bu şöbəyə müraciət göndərə bilməzlər.")
    if not unit.requires_recipient:
        return None
    try:
        recipient = recipient_users(unit).filter(pk=int(recipient_id)).first()
    except (TypeError, ValueError):
        recipient = None
    if recipient is None:
        raise TransitionDenied("recipient.required", "Müraciətin ünvanlandığı prorektoru seçin.")
    return recipient
