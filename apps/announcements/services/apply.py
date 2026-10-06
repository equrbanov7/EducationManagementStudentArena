"""«Müraciət et» — elanın müəllifinin seçdiyi ünvana müraciət.

* ``internal`` — ``apps.applications.public.submit_linked_application``: adi göndərişlə EYNİ
  qapılar (icazə, ailə, növ, SLA, bildiriş, audit); hədəf şöbə elanda seçilibsə odur.
  Mövzu/mətn elana istinadla avtomatik doldurulur, istifadəçi qısa qeyd əlavə edə bilər.
* ``url`` — klik qəbzdə qeyd olunur, istifadəçi keçidə yönləndirilir.

İkiqat müraciət: qəbz sətri ``select_for_update`` ilə kilidlənir; ``applied_at`` artıq
varsa yeni müraciət YARADILMIR (mövcud nömrə qaytarılır). Son tarix keçibsə və ya elan
aktiv deyilsə müraciət bağlıdır.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.applications.public import TransitionDenied, submit_linked_application

from ..constants import APPLY_NOTE_MAX, PROFILE_SECTION, ApplyMode
from ..models import AnnouncementReceipt

_CTX = "announcements.apply"


@dataclass(frozen=True)
class ApplyResult:
    ok: bool
    created: bool = False
    number: str = ""
    redirect: str = ""
    error: str = ""


def apply_closed_reason(announcement, now=None) -> str:
    """Boş sətir — müraciət açıqdır; əks halda istifadəçiyə göstərilən səbəb."""
    now = now or timezone.now()
    if announcement.is_deleted:
        return pgettext(_CTX, "Elan silinib — müraciət qəbul olunmur.")
    if not announcement.has_apply:
        return pgettext(_CTX, "Bu elan üzrə müraciət nəzərdə tutulmayıb.")
    if not announcement.is_visible_now(now):
        return pgettext(_CTX, "Elanın müddəti bitib.")
    if announcement.deadline_passed(now):
        return pgettext(_CTX, "Müraciətin son tarixi keçib.")
    if announcement.apply_mode == ApplyMode.INTERNAL and announcement.apply_kind_id is None:
        return pgettext(_CTX, "Müraciət ünvanı konfiqurasiya olunmayıb — elanın müəllifinə bildirin.")
    return ""


def _detail_url(announcement) -> str:
    return f"{reverse('accounts:profile')}?section={PROFILE_SECTION}&elan={announcement.pk}"


def _locked_receipt(organization, user, announcement):
    receipt, _created = AnnouncementReceipt.objects.get_or_create(
        organization=organization, user=user, announcement=announcement
    )
    return AnnouncementReceipt.objects.select_for_update().get(pk=receipt.pk)


def apply(request, announcement, note: str = "") -> ApplyResult:
    if getattr(request, "is_view_as", False):
        return ApplyResult(ok=False, error=pgettext(_CTX, "Baxış rejimində müraciət etmək olmaz."))
    reason = apply_closed_reason(announcement)
    if reason:
        return ApplyResult(ok=False, error=reason)
    note = (note or "").strip()
    if len(note) > APPLY_NOTE_MAX:
        return ApplyResult(
            ok=False, error=pgettext(_CTX, "Qeyd ən çox %(n)s simvol ola bilər.") % {"n": APPLY_NOTE_MAX}
        )
    organization, user = request.organization, request.user
    with transaction.atomic():
        receipt = _locked_receipt(organization, user, announcement)
        if receipt.applied_at is not None:
            return ApplyResult(
                ok=True, created=False, number=receipt.application_number, redirect=announcement.apply_url
            )
        now = timezone.now()
        if announcement.apply_mode == ApplyMode.URL:
            AnnouncementReceipt.objects.filter(pk=receipt.pk).update(applied_at=now, read_at=receipt.read_at or now)
            return ApplyResult(ok=True, created=True, redirect=announcement.apply_url)
        subject = pgettext(_CTX, "Elan: %(title)s") % {"title": announcement.title}
        body = pgettext(_CTX, "«%(title)s» elanına müraciət.") % {"title": announcement.title}
        if note:
            body = f"{body}\n\n{note}"
        body = f"{body}\n\n{pgettext(_CTX, 'Elan')}: {request.build_absolute_uri(_detail_url(announcement))}"
        try:
            with transaction.atomic():
                application = submit_linked_application(
                    organization=organization,
                    user=user,
                    kind=announcement.apply_kind,
                    subject=subject[:255],
                    body=body,
                    unit=announcement.apply_unit,
                    request=request,
                )
        except TransitionDenied as exc:
            return ApplyResult(ok=False, error=str(exc))
        except ValidationError as exc:
            return ApplyResult(ok=False, error="; ".join(exc.messages))
        AnnouncementReceipt.objects.filter(pk=receipt.pk).update(
            applied_at=now,
            read_at=receipt.read_at or now,
            application_id=application.pk,
            application_number=application.number,
            updated_at=now,
        )
    return ApplyResult(ok=True, created=True, number=application.number)


__all__ = ["ApplyResult", "apply", "apply_closed_reason"]
