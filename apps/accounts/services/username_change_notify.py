"""İstifadəçi adı dəyişəndə sahibinə in-app bildiriş + e-poçt (sahib 2026-10-20).

Mətnlər İNDİ (sorğunun aktiv dilində) hazırlanır, çatdırılma tranzaksiya COMMIT olandan SONRA və BEST-EFFORT
gedir — bildiriş / poçt xətası dəyişikliyi geri qaytarmır. E-poçt yalnız real ünvana gedir (``…@placeholder.invalid``
yer-tutucu ünvanlara yox); ``core.email_tasks.send_template_email_async`` (Celery, M365 backend) ilə.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext

from ..identity import email_is_placeholder

logger = logging.getLogger(__name__)

CTX = "accounts.username_change"
EMAIL_TEMPLATE = "accounts/emails/username_changed.html"


def _texts(*, old_username: str, new_username: str) -> dict:
    title = pgettext(CTX, "İstifadəçi adınız dəyişdirildi")
    changed = pgettext(CTX, "İstifadəçi adınız dəyişdirildi: %(old)s → %(new)s.") % {
        "old": old_username,
        "new": new_username,
    }
    login = pgettext(CTX, "Bundan sonra sistemə yeni adla və ya e-poçtunuzla daxil olun; köhnə ad artıq işləmir.")
    warning = pgettext(CTX, "Bu dəyişikliyi siz etməmisinizsə, dərhal RİM-ə müraciət edin.")
    return {"title": title, "lines": [changed, login, warning]}


def notify_username_changed(user, profile, *, old_username: str) -> None:
    texts = _texts(old_username=old_username, new_username=user.username)
    link = f"{reverse('accounts:profile')}?section=edit-profile"
    organization = getattr(profile, "organization", None)
    address = (user.email or "").strip()
    name = (user.get_full_name() or "").strip() or user.username
    transaction.on_commit(
        lambda: _deliver(user, texts=texts, link=link, organization=organization, address=address, name=name)
    )


def _deliver(user, *, texts: dict, link: str, organization, address: str, name: str) -> None:
    try:
        from apps.notifications.public import create_notification

        create_notification(
            recipient=user,
            title=texts["title"][:255],
            message=" ".join(texts["lines"])[:2000],
            link=link,
            notification_type="system",
            metadata={"kind": "username_changed"},
            organization=organization,
        )
    except Exception:  # noqa: BLE001 — bildiriş heç vaxt əsas yazını sındırmır
        logger.warning("Username change in-app notification failed.", exc_info=True)
    if "@" not in address or email_is_placeholder(address):
        return
    try:
        from core.email_tasks import send_template_email_async
        from core.utils import build_absolute_url

        send_template_email_async.delay(
            subject=texts["title"][:200],
            template_name=EMAIL_TEMPLATE,
            context={"heading": texts["title"], "name": name, "lines": texts["lines"], "url": build_absolute_url(link)},
            recipient_list=[address],
        )
    except Exception:  # noqa: BLE001 — növbə/SMTP əlçatmazdırsa in-app bildiriş yenə qalır
        logger.warning("Username change e-mail enqueue failed.", exc_info=True)


__all__ = ["notify_username_changed"]
