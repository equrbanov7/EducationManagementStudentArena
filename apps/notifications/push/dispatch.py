"""Bildiriş yarandı → telefona push: planlaşdırma (sorğu axını) + çatdırma (Celery işi).

1. :func:`schedule` — ``crud.create_notification*`` hər yaradılışdan sonra çağırır. Push söndürülübsə / kredensial
   yoxdursa DƏRHAL qayıdır (sorğu yoxdur, Redis-ə yazı yoxdur). Əks halda ``transaction.on_commit``-də (bildiriş
   commit olunmayıbsa push da getmir) aktiv cihazı OLAN alıcıların bildiriş id-ləri ``PUSH_SEND_CHUNK``-lıq
   hissələrlə ``notifications.push_send`` işinə verilir. Heç vaxt istisna atmır — bildiriş yaradılması
   push-dan asılı deyil.
2. :func:`deliver` — iş daxilində: bildirişlər (silinməmiş, hələ OXUNMAMIŞ) + alıcıların aktiv cihazları + oxunmamış
   say (iOS nişanı) bir dəfə oxunur; şəbəkə sorğuları tranzaksiyadan KƏNARDA gedir; sonda uğurlu cihazlara
   ``last_success_at``, FCM-in tanımadığı tokenlərə deaktivasiya yazılır. Vaxt büdcəsi aşılarsa qalan bildirişlər
   yeni işə verilir (Celery soft limit 240 s).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from . import config

logger = logging.getLogger(__name__)

#: Bir işin şəbəkə büdcəsi (saniyə) — keçəndə qalan bildirişlər növbəti işə.
TIME_BUDGET_SECONDS = 150
_LOOKUP_BATCH = 1000


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def schedule(notifications) -> None:
    """Yeni yaradılmış bildirişlər üçün push-u commit-dən sonra növbəyə qoyur (no-op: push söndürülüb)."""
    try:
        if not notifications or not config.push_enabled():
            return
        pairs = [(item.pk, item.recipient_id) for item in notifications if item.pk and item.recipient_id]
    except Exception:  # noqa: BLE001 — bildiriş yaradılması push-a görə sınmasın
        logger.warning("Push: planlaşdırma alınmadı.", exc_info=True)
        return
    if pairs:
        transaction.on_commit(lambda: _enqueue(pairs))


def _users_with_devices(user_ids) -> set:
    from apps.notifications.models import PushDevice
    from core.rls import bypass_rls

    found: set = set()
    ordered = sorted(user_ids)
    with bypass_rls():
        for batch in _chunks(ordered, _LOOKUP_BATCH):
            found.update(
                PushDevice.objects.filter(user_id__in=batch, is_active=True)
                .values_list("user_id", flat=True)
                .distinct()
            )
    return found


def _enqueue(pairs) -> int:
    """Cihazı olan alıcıların bildirişlərini hissələrlə işə verir; qaytarır: növbəyə qoyulan bildiriş sayı."""
    try:
        with_devices = _users_with_devices({recipient for _pk, recipient in pairs})
        ids = [pk for pk, recipient in pairs if recipient in with_devices]
        if not ids:
            return 0
        from apps.notifications.tasks import push_send_task

        for chunk in _chunks(ids, config.chunk_size()):
            push_send_task.delay(list(chunk))
        return len(ids)
    except Exception:  # noqa: BLE001 — broker əlçatmazdırsa bildiriş kabinetdə qalır
        logger.warning("Push: növbəyə qoyma alınmadı (%s bildiriş).", len(pairs), exc_info=True)
        return 0


def _load(notification_ids):
    from apps.notifications.models import InAppNotification, PushDevice

    notifications = list(
        InAppNotification.objects.filter(pk__in=notification_ids, deleted_at__isnull=True, is_read=False).order_by("pk")
    )
    recipients = {item.recipient_id for item in notifications}
    devices: dict = defaultdict(list)
    unread: dict = {}
    if recipients:
        for device in PushDevice.objects.filter(user_id__in=recipients, is_active=True).order_by("pk"):
            devices[device.user_id].append(device)
        unread = dict(
            InAppNotification.objects.filter(recipient_id__in=recipients, deleted_at__isnull=True, is_read=False)
            .values("recipient_id")
            .annotate(total=Count("id"))
            .values_list("recipient_id", "total")
        )
    return notifications, devices, unread


def _plan(notifications, devices, unread):
    """``[(notification, device, message)]`` — susdurulmuş növlər atılır; mətn hər dil üçün bir dəfə qurulur."""
    from .messages import build_message, localized_text, normalize_language

    plan = []
    for notification in notifications:
        texts: dict = {}
        for device in devices.get(notification.recipient_id, ()):
            muted = device.muted_types if isinstance(device.muted_types, list) else []
            if notification.notification_type in muted:
                continue
            lang = normalize_language(device.language)
            if lang not in texts:
                texts[lang] = localized_text(notification, lang)
            title, body = texts[lang]
            message = build_message(
                token=device.token,
                platform=device.platform,
                notification=notification,
                title=title,
                body=body,
                unread=unread.get(notification.recipient_id, 0),
            )
            plan.append((notification, device, message))
    return plan


def deliver(notification_ids, *, scope=None, client_factory=None) -> dict:
    """Bildirişləri alıcıların aktiv cihazlarına göndərir; qaytarır: nəticə sayları (loq/test üçün)."""
    from apps.notifications.models import PushDevice

    from .fcm import DEACTIVATING, AuthError, FCMClient

    if scope is None:
        from core.rls import bypass_rls as scope  # alıcı süzgəci sərhəddir; bildirişlər bütün tenant-lardandır
    counts: dict = defaultdict(int)
    ids = [int(pk) for pk in notification_ids or [] if str(pk).isdigit()]
    if not ids:
        return dict(counts)
    if not config.push_enabled():
        counts["disabled"] = len(ids)
        return dict(counts)

    with scope():
        notifications, devices, unread = _load(ids)
        plan = _plan(notifications, devices, unread)
    if not plan:
        counts["no_target"] = len(ids)
        return dict(counts)

    client = (client_factory or FCMClient)(config.credentials())
    delivered: list = []
    deactivate: dict = defaultdict(list)
    leftover: list = []
    started = time.monotonic()
    try:
        for index, (notification, device, message) in enumerate(plan):
            if time.monotonic() - started > TIME_BUDGET_SECONDS:
                # Qismən göndərilmiş bildiriş təkrarlanmır (eyni telefona iki push olmasın).
                started_ids = {item[0].pk for item in plan[:index]}
                leftover = sorted({item[0].pk for item in plan[index:]} - started_ids)
                break
            result = client.send(message)
            counts[result.outcome] += 1
            if result.outcome == "ok":
                delivered.append(device.pk)
            elif result.outcome in DEACTIVATING:
                deactivate[result.outcome].append(device.pk)
            elif result.outcome == "error":
                logger.warning(
                    "Push: FCM xətası (bildiriş %s): HTTP %s %s", notification.pk, result.status, result.detail
                )
    except AuthError as exc:
        # Açar yararsızdır / Google rədd etdi — partiyanın qalanını göndərməyə dəyməz.
        logger.error("Push: FCM access token alınmadı — %s", exc)
        counts["auth_failed"] += 1
    finally:
        client.close()

    now = timezone.now()
    with scope():
        if delivered:
            PushDevice.objects.filter(pk__in=delivered).update(last_success_at=now)
        for reason, device_ids in deactivate.items():
            PushDevice.objects.filter(pk__in=device_ids, is_active=True).update(
                is_active=False, deactivated_at=now, deactivated_reason=reason
            )
    if leftover:
        from apps.notifications.tasks import push_send_task

        push_send_task.delay(leftover)
        counts["requeued"] = len(leftover)
    logger.info("Push: %s", dict(counts))
    return dict(counts)


def send_test(*, user, title: str, body: str) -> dict:
    """«Özümə test push» — istifadəçinin aktiv cihazlarına SİNXRON göndərir (bildiriş sətri YARADILMIR).

    Qaytarır: ``{"configured", "enabled", "devices", <nəticə>: say}`` — mobil komanda / RİM yoxlaması üçün.
    Yararsız token burada da deaktiv edilir.
    """
    from types import SimpleNamespace

    from apps.notifications.models import NotificationType, PushDevice
    from core.rls import bypass_rls

    from .fcm import DEACTIVATING, AuthError, FCMClient
    from .messages import build_message

    with bypass_rls():
        devices = list(PushDevice.objects.filter(user=user, is_active=True).order_by("pk"))
    report: dict = {"configured": config.is_configured(), "enabled": config.push_enabled(), "devices": len(devices)}
    if not (report["configured"] and devices):
        return report
    fake = SimpleNamespace(pk=0, notification_type=NotificationType.SYSTEM, link="", created_at=timezone.now())
    client = FCMClient(config.credentials())
    deactivate: dict = defaultdict(list)
    try:
        for device in devices:
            message = build_message(
                token=device.token, platform=device.platform, notification=fake, title=title, body=body, unread=0
            )
            result = client.send(message)
            report[result.outcome] = report.get(result.outcome, 0) + 1
            if result.outcome in DEACTIVATING:
                deactivate[result.outcome].append(device.pk)
            elif result.outcome == "error":
                report.setdefault("errors", []).append(f"HTTP {result.status} {result.detail}"[:200])
    except AuthError as exc:
        report["auth_failed"] = str(exc)
    finally:
        client.close()
    now = timezone.now()
    with bypass_rls():
        for reason, device_ids in deactivate.items():
            PushDevice.objects.filter(pk__in=device_ids).update(
                is_active=False, deactivated_at=now, deactivated_reason=reason
            )
    return report


__all__ = ["TIME_BUDGET_SECONDS", "deliver", "schedule", "send_test"]
