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


def destination_payload(unit):
    if not unit.requires_recipient:
        return []
    return [{"id": str(user.pk), "name": user.get_full_name() or user.username} for user in recipient_users(unit)]


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
