"""Validate tenant membership, rule configuration and recipient confirmation."""

from datetime import timedelta
from uuid import UUID, uuid4

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.permissions import has_permission
from core.rls import bypass_rls
from core.roles import ProfileRole

from .journal_watch_models import (
    JournalWatch,
    JournalWatchEvent,
    JournalWatchRecipient,
    JournalWatchRoute,
    PersonKind,
    WatchKind,
)

SALT = "monitoring.journal-watch.confirm.v1"


def _message(text):
    return pgettext("journal.watch", text)


def _organization(request):
    from apps.organizations.public import can_manage_journal_watch

    if not can_manage_journal_watch(request):
        raise PermissionDenied
    return request.organization


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(_message("Seçdiyiniz qeyd etibarlı deyil.")) from None


def _people(org, kind):
    membership = apps.get_model("organizations", "Membership")
    roles = apps.get_model("organizations", "Role").objects.filter(organization=org, is_active=True)
    members = membership.objects.filter(organization=org, is_active=True, role__organization=org, role__is_active=True)
    users = get_user_model().objects.filter(is_active=True)
    if kind == PersonKind.STUDENT:
        records = apps.get_model("registrar", "StudentAcademicRecord").objects.filter(organization=org, is_active=True)
        students = members.filter(role__name__in=[ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT, "telebe"])
        return users.filter(pk__in=members.values("user_id")).filter(
            Q(pk__in=students.values("user_id")) | Q(pk__in=records.values("student_id"))
        )
    if kind != PersonKind.ACTOR:
        raise ValidationError(_message("İzlənəcək şəxsin növünü seçin."))
    role_ids = [
        pk
        for pk, permissions in roles.values_list("pk", "permissions")
        if any(
            has_permission(permissions or [], key) for key in ("grade.input", "journal.correct", "journal.direct_edit")
        )
    ]
    return users.filter(Q(pk__in=members.filter(role_id__in=role_ids).values("user_id")) | Q(pk=org.owner_id))


def _name(person):
    return person.get_full_name() or person.get_username()


def search_people(request, person_kind, query):
    org = _organization(request)
    text = str(query or "").strip()[:100]
    if len(text) < 2:
        return []
    people = _people(org, person_kind)
    for word in text.split()[:5]:
        people = people.filter(
            Q(first_name__icontains=word) | Q(last_name__icontains=word) | Q(username__icontains=word)
        )
    return [
        {"id": str(p.pk), "label": f"{_name(p)} ({p.username})"}
        for p in people.order_by("last_name", "first_name", "pk")[:25]
    ]


@transaction.atomic
def save_watch(*, request, person_id, person_kind, events, recipient_ids, watch_id=None, active=True):
    org = _organization(request)
    digits = str(person_id or "")
    valid_id = digits.isascii() and digits.isdigit() and len(digits) <= 19 and 0 < int(digits) < 2**63
    person = _people(org, person_kind).filter(pk=int(digits)).first() if valid_id else None
    if not person:
        raise ValidationError(_message("Şəxs aktiv təşkilatın uyğun siyahısında tapılmadı."))
    selected = sorted(set(events or []))
    if not selected or set(selected) - set(WatchKind.values):
        raise ValidationError(_message("Ən azı bir etibarlı hadisə növü seçin."))
    ids = {_uuid(i) for i in (recipient_ids or [])}
    recipients = list(
        JournalWatchRecipient.objects.filter(organization=org, pk__in=ids, verified_at__isnull=False).order_by("pk")
    )
    if len(ids) != len(recipients):
        raise ValidationError(_message("Yalnız təsdiqlənmiş bildiriş ünvanlarını seçin."))
    if watch_id:
        watch = JournalWatch.objects.select_for_update().filter(organization=org, pk=_uuid(watch_id)).first()
        if not watch or watch.person_id != person.pk or watch.person_kind != person_kind:
            raise ValidationError(_message("Şəxsi dəyişmək üçün ayrıca izləmə qaydası yaradın."))
        created = False
    else:
        watch = JournalWatch(organization=org, person=person, person_kind=person_kind)
        created = True
    watch.event_types = selected
    watch.is_active = active is True
    watch.save()
    JournalWatchRoute.objects.filter(organization=org, watch=watch).exclude(recipient_id__in=ids).delete()
    for recipient in recipients:
        JournalWatchRoute.objects.get_or_create(organization=org, watch=watch, recipient=recipient)
    _audit(request, AuditAction.CREATE if created else AuditAction.UPDATE, watch.pk)
    return watch


def _audit(request, action, pk, resource_type="monitoring.journal_watch"):
    log_action(
        action,
        user=request.user,
        organization=request.organization,
        resource_type=resource_type,
        resource_id=str(pk),
        request=request,
    )


@transaction.atomic
def delete_watch(*, request, watch_id):
    org = _organization(request)
    watch = JournalWatch.objects.select_for_update().filter(organization=org, pk=_uuid(watch_id)).first()
    if not watch:
        raise ValidationError(_message("İzləmə qaydası tapılmadı."))
    _audit(request, AuditAction.DELETE, watch.pk)
    watch.delete()


@transaction.atomic
def delete_recipient(*, request, recipient_id):
    org = _organization(request)
    recipient = (
        JournalWatchRecipient.objects.select_for_update().filter(organization=org, pk=_uuid(recipient_id)).first()
    )
    if not recipient:
        raise ValidationError(_message("Bildiriş ünvanı tapılmadı."))
    _audit(request, AuditAction.DELETE, recipient.pk, "monitoring.journal_watch_recipient")
    recipient.delete()


@transaction.atomic
def request_recipient(*, request, email):
    org = _organization(request)
    email = str(email or "").strip().lower()
    validate_email(email)
    if len(email) > 254:
        raise ValidationError(_message("E-poçt ünvanı çox uzundur."))
    now = timezone.now()
    # Serialize the organization's verified-address budget, including deleted addresses and resends.
    type(org).objects.select_for_update().filter(pk=org.pk).exists()
    rec, created = JournalWatchRecipient.objects.select_for_update().get_or_create(organization=org, email=email)
    if rec.verified_at:
        return rec
    if not created and rec.requested_at > now - timedelta(minutes=5):
        raise ValidationError(_message("Təsdiq məktubu göndərilib. Yenidən göndərmək üçün beş dəqiqə gözləyin."))
    requests = apps.get_model("audit", "AuditLog").objects.filter(
        organization=org,
        action=AuditAction.CREATE,
        resource_type="monitoring.journal_watch_recipient",
        created_at__gte=now - timedelta(hours=1),
    )
    if requests.count() >= getattr(settings, "JOURNAL_WATCH_CONFIRMATION_HOURLY_LIMIT", 20):
        raise ValidationError(
            _message("Təşkilat üzrə saatlıq təsdiq məktubu həddinə çatılıb. Sonra yenidən cəhd edin.")
        )
    rec.nonce = uuid4()
    rec.requested_at = now
    rec.confirmation_next_at = now
    rec.confirmation_attempts = 0
    rec.save(update_fields=["nonce", "requested_at", "confirmation_next_at", "confirmation_attempts"])
    from .journal_watch_mail import deliver_confirmation

    transaction.on_commit(lambda: deliver_confirmation.delay(str(org.pk), str(rec.pk)), robust=True)
    _audit(request, AuditAction.CREATE, rec.pk, "monitoring.journal_watch_recipient")
    return rec


@transaction.atomic
def confirm_recipient(*, token):
    try:
        org_id, pk, nonce = signing.loads(token, salt=SALT, max_age=86400)
    except (signing.BadSignature, ValueError, TypeError):
        raise ValidationError(_message("Təsdiq keçidinin vaxtı bitib və ya keçid etibarsızdır.")) from None
    # Signed, single-recipient lookup. The mailbox holder need not have an application account.
    with bypass_rls():
        rec = (
            JournalWatchRecipient.objects.select_for_update()
            .filter(
                organization_id=org_id,
                organization__is_active=True,
                organization__status="active",
                pk=pk,
                nonce=nonce,
                verified_at__isnull=True,
            )
            .first()
        )
        if not rec:
            raise ValidationError(_message("Təsdiq keçidi artıq işlənib və ya etibarsızdır."))
        rec.verified_at = timezone.now()
        rec.nonce = uuid4()
        rec.confirmation_next_at = None
        rec.save(update_fields=["nonce", "verified_at", "confirmation_next_at"])
        log_action(
            AuditAction.UPDATE,
            organization=rec.organization,
            resource_type="monitoring.journal_watch_recipient",
            resource_id=str(rec.pk),
            reason="mailbox_ownership_confirmed",
        )


def watch_context(request):
    org = _organization(request)
    return {
        "watches": JournalWatch.objects.filter(organization=org)
        .select_related("person")
        .prefetch_related("routes__recipient")
        .order_by("-created_at"),
        "recipients": JournalWatchRecipient.objects.filter(organization=org).order_by("email"),
        "events": JournalWatchEvent.objects.filter(organization=org).order_by("-created_at", "-pk"),
        "event_choices": WatchKind.choices,
        "person_choices": PersonKind.choices,
    }
