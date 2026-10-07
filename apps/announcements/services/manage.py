"""Yazı tərəfi: yaratma, redaktə, dərc, arxiv, silmə, sənədlər, statistika.

Hər mutasiya: (1) əhatə yoxlaması (``access``), (2) atomik yazı, (3) xülasənin
yenidən qurulması (``snapshot.sync_snapshot`` — popup/sayğac dərhal görür),
(4) audit izi. Əhatəli menecerin hədəf bölmələri hər yazıda YENİDƏN yoxlanılır.

Sənəd faylları (2026-10-07) DB tranzaksiyası ilə uyğunlaşdırılır: silmə YALNIZ commit-dən
sonra (``transaction.on_commit``) — rollback olsa sətir də, fayl da qalır; yeni sənədlərin
yazılmış faylları DB hissəsi uğursuz olanda (savepoint geri alınanda) dərhal silinir — yetim
fayl qalmır.
"""

from __future__ import annotations

import logging
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import pgettext

from apps.organizations.public import create_audit_log
from core.constants import AuditAction
from core.download_types import content_type_for_name
from core.upload_security import validate_uploaded_file

from ..constants import (
    ATTACHMENT_EXTENSIONS,
    ATTACHMENT_MAX_MB,
    ATTACHMENTS_PER_ANNOUNCEMENT,
    ApplyMode,
    Status,
)
from ..models import Announcement, AnnouncementAttachment, AnnouncementReceipt
from . import access, snapshot
from .audience import normalize_families

_CTX = "announcements.manage"
logger = logging.getLogger(__name__)
_FIELDS = (
    "title",
    "summary",
    "body",
    "category",
    "priority",
    "is_pinned",
    "show_as_popup",
    "requires_ack",
    "publish_at",
    "expires_at",
    "deadline_at",
)


def _audit(request, organization, action, announcement, changes=None):
    create_audit_log(
        getattr(request, "user", None),
        organization,
        action,
        resource_type="announcement",
        resource_id=str(announcement.pk),
        resource_repr=announcement.title[:200],
        new_values=changes or None,
        request=request,
    )


def _validate_window(announcement, data) -> None:
    """``expires_at > publish_at`` — dərc olunmuş elanda boş «Dərc vaxtı» ``indi`` sayılır.

    Forma yalnız hər iki tarix göndəriləndə yoxlayır; dərc olunmuş elanda «Dərc vaxtı»
    boşaldılıb «Bitmə vaxtı» keçmişə qoyulanda servis ``publish_at = indi`` qoyub
    ``ann_window_ordered`` CHECK-inə çırpılırdı → 500 (review 2026-10-07).
    """
    expires_at = data.get("expires_at")
    publish_at = data.get("publish_at")
    if publish_at is None and announcement is not None and announcement.status == Status.PUBLISHED:
        publish_at = timezone.now()
    if expires_at and publish_at and expires_at <= publish_at:
        raise ValidationError({"expires_at": [pgettext(_CTX, "Bitmə vaxtı dərc vaxtından sonra olmalıdır.")]})


def save_announcement(request, organization, scope, data, *, announcement=None) -> Announcement:
    """Formanın ``cleaned_data``-sı → elan (yeni və ya mövcud). Əhatədən kənar → ``ValidationError``."""
    user = request.user
    if announcement is not None and not access.can_edit(scope, user, announcement, organization):
        raise PermissionDenied
    if announcement is not None and announcement.is_deleted:
        raise ValidationError(pgettext(_CTX, "Elan silinib — əvvəlcə onu bərpa edin."))
    units, errors = access.validate_units(scope, organization, data.get("audience_units") or [])
    families = normalize_families(data.get("audience_families"))
    if not families:
        errors.append(pgettext(_CTX, "Ən azı bir auditoriya seçin."))
    if errors:
        raise ValidationError({"audience_units": errors})
    _validate_window(announcement, data)
    creating = announcement is None
    announcement = announcement or Announcement(organization=organization, created_by=user)
    for field in _FIELDS:
        setattr(announcement, field, data.get(field))
    announcement.requires_ack = bool(announcement.requires_ack)
    # Məcburi ⇒ popup (forma da belə qurur; servis hər çağırana qarşı təmin edir — ann_ack_needs_popup).
    announcement.show_as_popup = bool(announcement.show_as_popup) or announcement.requires_ack
    announcement.summary = (announcement.summary or "").strip()
    announcement.body = (announcement.body or "").strip()
    announcement.audience_families = families
    announcement.audience_units = units
    mode = data.get("apply_mode") or ApplyMode.NONE
    announcement.apply_mode = mode
    announcement.apply_kind = data.get("apply_kind_obj") if mode == ApplyMode.INTERNAL else None
    announcement.apply_unit = data.get("apply_unit_obj") if mode == ApplyMode.INTERNAL else None
    announcement.apply_url = data.get("apply_url") or "" if mode == ApplyMode.URL else ""
    announcement.apply_label = (data.get("apply_label") or "").strip() if mode != ApplyMode.NONE else ""
    announcement.updated_by = user
    if announcement.status == Status.PUBLISHED and not announcement.publish_at:
        announcement.publish_at = timezone.now()
    with transaction.atomic():
        announcement.save()
        _audit(
            request,
            organization,
            AuditAction.CREATE if creating else AuditAction.UPDATE,
            announcement,
            {
                "status": announcement.status,
                "families": families,
                "units": units,
                "popup": announcement.show_as_popup,
                "mandatory": announcement.requires_ack,
            },
        )
    snapshot.sync_snapshot(organization)
    return announcement


def _stored_file(fieldfile):
    """Storage-ə artıq YAZILMIŞ faylın ``(storage, ad)`` cütü; yazılmayıbsa ``None``."""
    if fieldfile and fieldfile.name and getattr(fieldfile, "_committed", False):
        return fieldfile.storage, fieldfile.name
    return None


def _remove_files(stored) -> None:
    for storage, name in stored:
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001 — fayl silinməsi əsas əməliyyatı yıxmamalıdır
            logger.warning("announcements: attachment file %s could not be deleted", name, exc_info=True)


def _remove_files_on_commit(fieldfiles) -> None:
    """Faylları tranzaksiya COMMIT olunanda silir; rollback → callback atılır, fayl qalır."""
    stored = [pair for pair in (_stored_file(item) for item in fieldfiles) if pair]
    if stored:
        transaction.on_commit(lambda: _remove_files(stored), robust=True)


def is_hard_delete(announcement) -> bool:
    """Heç kimin görmədiyi (qəbzsiz) qaralama birdəfəlik silinir; qalan hər şey yumşaq silinir."""
    return announcement.status == Status.DRAFT and not announcement.receipts.exists()


def _delete(request, organization, announcement) -> Announcement:
    """Qəbzsiz qaralama → birdəfəlik; əks halda yumşaq silmə (qəbz/sənəd/müraciətlər toxunulmaz qalır)."""
    if is_hard_delete(announcement):
        with transaction.atomic():
            _audit(request, organization, AuditAction.DELETE, announcement, {"mode": "hard"})
            files = [attachment.file for attachment in announcement.attachments.all()]
            announcement.delete()
            _remove_files_on_commit(files)  # rollback olsa sətir qalır — faylı da qalmalıdır
    else:
        now = timezone.now()
        previous = announcement.status
        announcement.is_deleted = True
        announcement.deleted_at = now
        announcement.deleted_by = request.user
        announcement.updated_by = request.user
        with transaction.atomic():
            announcement.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"])
            _audit(request, organization, AuditAction.DELETE, announcement, {"mode": "soft", "status": previous})
    snapshot.sync_snapshot(organization)  # popup/sayğac xülasəsi + versiya → keş və sessiya işarəsi köhnəlir
    return announcement


def _undelete(request, organization, announcement) -> Announcement:
    """Silinmiş elanı bərpa edir — həmişə QARALAMA kimi (yenidən dərc şüurlu addımdır)."""
    announcement.is_deleted = False
    announcement.deleted_at = None
    announcement.deleted_by = None
    announcement.status = Status.DRAFT
    announcement.archived_at = None
    announcement.updated_by = request.user
    with transaction.atomic():
        announcement.save()
        _audit(request, organization, AuditAction.UPDATE, announcement, {"action": "undelete", "status": Status.DRAFT})
    snapshot.sync_snapshot(organization)
    return announcement


def transition(request, organization, scope, announcement, action: str) -> Announcement:
    """``publish`` / ``unpublish`` (→ qaralama) / ``archive`` / ``restore`` (→ qaralama) / ``delete`` /
    ``undelete`` (silinmişdən → qaralama).

    ``delete`` istənilən vəziyyətdə işləyir (əhatə qapısı redaktə ilə EYNİDİR): qəbzsiz qaralama
    birdəfəlik, qalanı yumşaq silinir. Silinmiş elan üzərində yalnız ``undelete`` mümkündür.
    """
    if not access.can_edit(scope, request.user, announcement, organization):
        raise PermissionDenied
    if announcement.is_deleted and action != "undelete":
        raise ValidationError(pgettext(_CTX, "Elan silinib — əvvəlcə onu bərpa edin."))
    if action == "undelete":
        if not announcement.is_deleted:
            raise ValidationError(pgettext(_CTX, "Elan silinməyib."))
        return _undelete(request, organization, announcement)
    if action == "delete":
        return _delete(request, organization, announcement)
    now = timezone.now()
    if action == "publish":
        if announcement.status == Status.ARCHIVED:
            raise ValidationError(pgettext(_CTX, "Arxivdəki elanı əvvəlcə bərpa edin."))
        if not announcement.audience_families:
            raise ValidationError(pgettext(_CTX, "Ən azı bir auditoriya seçin."))
        if announcement.expires_at and announcement.expires_at <= now:
            raise ValidationError(pgettext(_CTX, "Bitmə vaxtı keçib — əvvəlcə tarixi dəyişin."))
        announcement.status = Status.PUBLISHED
        announcement.publish_at = announcement.publish_at or now
        announcement.published_at = now
    elif action == "unpublish":
        announcement.status = Status.DRAFT
    elif action == "archive":
        announcement.status = Status.ARCHIVED
        announcement.archived_at = now
    elif action == "restore":
        announcement.status = Status.DRAFT
        announcement.archived_at = None
    else:
        raise ValidationError(pgettext(_CTX, "Naməlum əməliyyat."))
    announcement.updated_by = request.user
    with transaction.atomic():
        announcement.save()
        _audit(
            request, organization, AuditAction.UPDATE, announcement, {"action": action, "status": announcement.status}
        )
    snapshot.sync_snapshot(organization)
    return announcement


def add_attachments(request, organization, announcement, files) -> list:
    incoming = [item for item in files or [] if item]
    if announcement.attachments.count() + len(incoming) > ATTACHMENTS_PER_ANNOUNCEMENT:
        raise ValidationError(
            {
                "files": [
                    pgettext(_CTX, "Bir elana ən çox %(n)s sənəd əlavə etmək olar.")
                    % {"n": ATTACHMENTS_PER_ANNOUNCEMENT}
                ]
            }
        )
    created, stored = [], []
    try:
        # Savepoint: hər hansı sənəd (yoxlama / DB) uğursuz olsa əvvəlki sətirlər geri alınır,
        # onların artıq storage-ə yazılmış faylları isə aşağıda silinir.
        with transaction.atomic():
            for uploaded in incoming:
                validate_uploaded_file(
                    uploaded, allowed_extensions=set(ATTACHMENT_EXTENSIONS), max_size_mb=ATTACHMENT_MAX_MB
                )
                attachment = AnnouncementAttachment(
                    organization=organization,
                    announcement=announcement,
                    file=uploaded,
                    original_name=(getattr(uploaded, "name", "") or "sened")[:255],
                    size=int(getattr(uploaded, "size", 0) or 0),
                    content_type=content_type_for_name(getattr(uploaded, "name", "")),
                    uploaded_by=request.user,
                )
                attachment.full_clean()
                try:
                    attachment.save()
                finally:  # fayl yazılıb, INSERT uğursuz olubsa da silinməlidir
                    pair = _stored_file(attachment.file)
                    if pair:
                        stored.append(pair)
                created.append(attachment)
    except BaseException:
        _remove_files(stored)
        raise
    return created


def remove_attachment(organization, announcement, attachment_id) -> bool:
    if announcement.is_deleted:  # silinmiş elanın sənədləri audit üçün saxlanılır
        return False
    try:
        attachment_id = uuid.UUID(str(attachment_id))
    except (TypeError, ValueError, AttributeError):
        return False
    attachment = announcement.attachments.filter(organization=organization, pk=attachment_id).first()
    if attachment is None:
        return False
    with transaction.atomic():
        attachment.delete()
        _remove_files_on_commit([attachment.file])  # fayl yalnız sətir silinməsi commit olunanda gedir
    return True


def manage_list(organization, scope, user, *, q="", state="all", category="", page=1, page_size=20) -> dict:
    """İdarə siyahısı + hər elan üçün qəbz statistikası (sabit sayda sorğu)."""
    from .queries import search_q

    now = timezone.now()
    queryset = Announcement.objects.filter(organization=organization).filter(
        access.manageable_q(scope, user, organization)
    )
    # «Silinmişlər» ayrıca filtrdir; qalan bütün görünüşlərdə silinmiş elan yoxdur.
    queryset = queryset.filter(is_deleted=state == "deleted")
    live = Q(status=Status.PUBLISHED)
    state_q = {
        "draft": Q(status=Status.DRAFT),
        "archived": Q(status=Status.ARCHIVED),
        "scheduled": live & Q(publish_at__gt=now),
        "active": live & Q(publish_at__lte=now) & (Q(expires_at__isnull=True) | Q(expires_at__gt=now)),
        "expired": live & Q(expires_at__lte=now),
    }.get(state)
    if state_q is not None:
        queryset = queryset.filter(state_q)
    if category:
        queryset = queryset.filter(category=category)
    if q:
        queryset = queryset.filter(search_q(q))
    queryset = queryset.order_by("-deleted_at" if state == "deleted" else "-updated_at")
    total = queryset.count()
    pages = max(1, -(-total // page_size))
    page = max(1, min(page, pages))
    rows = list(queryset.select_related("created_by", "deleted_by")[(page - 1) * page_size : page * page_size])
    stats = receipt_stats([row.pk for row in rows])
    for row in rows:
        row.state = row.effective_state(now)
        row.stats = stats.get(row.pk, dict(EMPTY_STATS))
    return {"items": rows, "total": total, "page": page, "pages": pages}


#: Qəbzi olmayan elanın statistikası (şablonlar bütün açarları gözləyir).
EMPTY_STATS = {"seen": 0, "read": 0, "applied": 0, "acked": 0}


def receipt_stats(announcement_ids) -> dict:
    if not announcement_ids:
        return {}
    rows = (
        AnnouncementReceipt.objects.filter(announcement_id__in=announcement_ids)
        .values("announcement_id")
        .annotate(
            seen=Count("pk", filter=Q(popup_seen_at__isnull=False)),
            read=Count("pk", filter=Q(read_at__isnull=False)),
            applied=Count("pk", filter=Q(applied_at__isnull=False)),
            acked=Count("pk", filter=Q(acknowledged_at__isnull=False)),
        )
    )
    return {row["announcement_id"]: row for row in rows}


def targeted_count(announcement) -> int:
    """Hədəf auditoriyanın təxmini sayı — bir ``COUNT`` sorğusu (bax ``recipients.targeted_users``)."""
    from .recipients import audience_count

    return audience_count(announcement.organization_id, announcement.audience_families, announcement.audience_units)


__all__ = [
    "EMPTY_STATS",
    "add_attachments",
    "is_hard_delete",
    "manage_list",
    "receipt_stats",
    "remove_attachment",
    "save_announcement",
    "targeted_count",
    "transition",
]
