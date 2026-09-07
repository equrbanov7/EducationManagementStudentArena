"""Bildiriş sətrinin GÖRÜNTÜ metadatası — ikon, ton, zaman qrupu, vaxt mətni.

Niyə view-də? Şablonda bu məlumat 8 budaqlı ``{% if %}`` zənciri idi (hər növ
üçün ayrı ikon sətri) və hər sətirdə təkrar icra olunurdu. Burada bir dəfə,
DATA kimi hesablanır; şablon yalnız çap edir.

Zaman qrupu (``ui_bucket``) modern bildiriş mərkəzlərinin standart naxışıdır:
50+ elementlik düz axın divara çevrilir, «Bu gün / Dünən / …» başlıqları isə
skan etməyi mümkün edir. Qruplaşma ARDICIL elementlər üzərindədir — sorğu
``-created_at`` ilə sıralandığı üçün şablondakı ``{% regroup %}`` doğru işləyir.
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import pgettext

_CTX = "profile.notifications"

#: Bildiriş növü → (Font Awesome ikonu, palitra tonu).
#: Ton `notifications.css`-dəki `.profile-notif-icon--<ton>` sinfidir.
TYPE_UI = {
    "assignment": ("fa-file-pen", "amber"),
    "exam": ("fa-clipboard-list", "blue"),
    "grade": ("fa-star", "green"),
    "course": ("fa-book-open", "cyan"),
    "live_exam": ("fa-tower-broadcast", "red"),
    "approval": ("fa-user-check", "violet"),
    "application": ("fa-comment-dots", "blue"),
    "system": ("fa-gear", "slate"),
}
DEFAULT_TYPE_UI = ("fa-bell", "slate")

#: Nisbi vaxtın absolut tarixə keçdiyi hədd. «3 həftə əvvəl» faydasızdır —
#: bu yaşdan sonra istifadəçi konkret tarix axtarır.
RELATIVE_TIME_DAYS = 7


def _bucket(days_ago: int) -> str:
    """Dörd dəstə kifayətdir: «bu gün / dünən / bu həftə» əməl tələb edən
    pəncərədir, qalanı arxivdir. Daha xırda bölgü (məs. «bu ay») başlıq sayını
    artırır, skan etməyi isə asanlaşdırmır."""
    if days_ago <= 0:
        return pgettext(_CTX, "Bu gün")
    if days_ago == 1:
        return pgettext(_CTX, "Dünən")
    if days_ago < RELATIVE_TIME_DAYS:
        return pgettext(_CTX, "Bu həftə")
    return pgettext(_CTX, "Daha əvvəl")


def decorate(notifications) -> list:
    """Hər bildirişə ``ui_icon`` / ``ui_tone`` / ``ui_bucket`` / ``ui_time`` yazır.

    Obyektlər DB-yə yazılmır — sadəcə şablon üçün keçici atributlar.
    """
    now = timezone.localtime()
    today = now.date()
    items = list(notifications)
    for notification in items:
        icon, tone = TYPE_UI.get(notification.notification_type, DEFAULT_TYPE_UI)
        notification.ui_icon = icon
        notification.ui_tone = tone
        created = timezone.localtime(notification.created_at)
        days_ago = (today - created.date()).days
        notification.ui_bucket = _bucket(days_ago)
        if days_ago < RELATIVE_TIME_DAYS:
            # `depth=1`: «3 saat, 54 dəqiqə» əvəzinə «3 saat». Vaxt sütununda
            # dəqiqlik yox, BİR baxışda oxunaqlıq lazımdır.
            # `timesince` gələcək tarixdə boş qaytarır — saat fərqi/klok sürüşməsi
            # olan sətirdə vaxt sahəsi tamamilə boş qalmasın.
            notification.ui_time = timesince(created, now, depth=1) or pgettext(_CTX, "indicə")
        else:
            notification.ui_time = created.strftime("%d.%m.%Y")
    return items


__all__ = ["TYPE_UI", "decorate"]
