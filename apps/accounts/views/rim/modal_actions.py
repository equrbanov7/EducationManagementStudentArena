"""RİM detal kartının 2026-11-04 əməlləri — ``rim_action`` endpoint-inin allow-list budaqları.

Hər budaq öz servisini çağırır (qapı servisdədir); burada yalnız payload oxunur və istifadəçiyə göstərilən
(tərcümə olunan) nəticə mətni qurulur. Xəta ``RimAccessError`` kimi yuxarı qalxır və ``rim_action`` onu JSON-a
çevirir.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from apps.accounts.services.rim import graduation, placement, staff_archive

_CTX = "accounts.rim.modal"

MODAL_ACTIONS = frozenset({"place_unit", "graduate", "archive_staff", "unarchive_staff"})


def run_modal_action(action, actor, target, payload, *, request=None, reason=""):
    """``(message, extra)`` qaytarır."""
    if action == "place_unit":
        result = placement.place(
            actor,
            target,
            membership_id=payload.get("membership_id"),
            unit_id=str(payload.get("unit_id") or "").strip(),
            expected_unit_id=str(payload.get("expected_unit_id") or "").strip(),
            reason=reason,
            request=request,
        )
        if result["changed"]:
            message = pgettext(_CTX, "Bölmə təyin edildi: %(unit)s.") % {"unit": result["unit_name"]}
        else:
            message = pgettext(_CTX, "Dəyişiklik yoxdur — bu bölmə artıq təyin olunub.")
        return message, {"placement_result": result}

    if action == "graduate":
        row = graduation.graduate(
            actor,
            target,
            record_id=payload.get("record_id") or "",
            order_number=payload.get("order_number") or "",
            order_date=payload.get("order_date") or "",
            reason=reason,
            request=request,
        )
        message = pgettext(_CTX, "Tələbə məzun edildi — hesab arxivə keçdi, tarixçə saxlanıldı.")
        return message, {"movement": row}

    if action == "archive_staff":
        result = staff_archive.archive(actor, target, reason=reason, request=request)
        message = pgettext(
            _CTX, "Hesab arxivə göndərildi: giriş bağlandı, %(count)d rol deaktiv edildi. Tarixçə saxlanıldı."
        ) % {"count": result["memberships_archived"]}
        return message, {"archive_result": result}

    # action == "unarchive_staff"
    result = staff_archive.unarchive(actor, target, reason=reason, request=request)
    message = pgettext(_CTX, "Hesab arxivdən çıxarıldı: giriş açıldı, %(count)d rol bərpa olundu.") % {
        "count": result["memberships_restored"]
    }
    extra = {"archive_result": result}
    if result["notices"]:
        extra["restore_notices"] = list(result["notices"])
    return message, extra


__all__ = ["MODAL_ACTIONS", "run_modal_action"]
