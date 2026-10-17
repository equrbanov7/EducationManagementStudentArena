"""Final imtahan mərkəzi naviqasiya bayrağının request-ömürlü memo-su (PERF-1 F-03, 2026-10-17).

``_role_capabilities`` bir kabinet bölməsi render-ində 2 dəfə, badges çağırışında 1 dəfə
işləyir; hər dəfə nəzarət əhatəsi (``supervision_scope``) 3 sorğu atırdı. Nəticə
istifadəçi obyektinə yapışdırılır — ``request.user`` hər request-də yenidən yüklənir,
ona görə memo request ömrü qədər yaşayır (``rbac_my_group._enrolled_group_ids`` ilə eyni
konvensiya). İcazənin özü view/consumer qatında memo-suz yenidən yoxlanır.
"""

from __future__ import annotations

_SUPERVISES_MEMO_ATTR = "_ems_supervises_final_memo"


def supervises_final_sessions(user) -> bool:
    """``apps.exams.public.user_supervises_final_sessions`` — istifadəçi obyekti başına bir dəfə."""
    memo = getattr(user, _SUPERVISES_MEMO_ATTR, None)
    if isinstance(memo, bool):
        return memo
    from apps.exams.public import user_supervises_final_sessions

    result = bool(user_supervises_final_sessions(user))
    try:
        setattr(user, _SUPERVISES_MEMO_ATTR, result)
    except Exception:  # noqa: BLE001 — dəyişməz istifadəçi obyekti (nadir)
        pass
    return result


__all__ = ["supervises_final_sessions"]
