"""İlk-giriş qapısının final/midterm (imtahan zalı) istisnası (sahib 2026-10-21).

İstifadəçi adı + PIN ilə girən tələbə ilk girişi (e-poçt + öz parolu) bitirməyibsə belə imtahan ZAMANI
parol təyini ekranına atılmır. Açıq olanlar: PIN giriş səhifələri və zal sessiyası (doğrulanmış bilet) olan
imtahan-verən yollar (``ProfileCompletionMiddleware.EXAM_TAKER_URL_NAMES``). Kabinetin qalanı qapılı qalır.
"""

from __future__ import annotations

from django.urls import Resolver404, resolve

CENTER_ENTRY_URL_NAMES = frozenset({"final_exam_entry", "midterm_exam_entry"})
#: ``apps.exams.services.final_center.entry.ENTRY_SESSION_KEY`` ilə eyni (sessiyada doğrulanmış bilet).
CENTER_SESSION_KEY = "final_exam_ticket_id"


def is_center_exam_path(request, path: str) -> bool:
    if not path.startswith("/exams/"):
        return False
    from apps.accounts.middleware_profile_completion import ProfileCompletionMiddleware

    try:
        match = resolve(path)
    except Resolver404:
        return False
    except Exception:  # noqa: BLE001 — URLconf hazır deyil
        return False
    if match.namespace != "exams":
        return False
    if match.url_name in CENTER_ENTRY_URL_NAMES:
        return True
    session = getattr(request, "session", None)
    has_center_ticket = bool(session is not None and session.get(CENTER_SESSION_KEY))
    return has_center_ticket and match.url_name in ProfileCompletionMiddleware.EXAM_TAKER_URL_NAMES


__all__ = ["CENTER_ENTRY_URL_NAMES", "CENTER_SESSION_KEY", "is_center_exam_path"]
