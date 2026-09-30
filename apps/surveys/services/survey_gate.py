"""Sorğu qurucusu (2026-09-30) — ümumi sorğuların kabinet qapısı və inbox vəziyyəti.

Kampaniya qapısından (``services/gate.py``) AYRI və ondan sonra işləyir; mövcud axın toxunulmur.

Siyasətlər (yalnız məcburi sorğuda; könüllü sorğu HEÇ VAXT bağlamır):

* ``block`` — doldurulana qədər kabinet bağlıdır;
* ``skip_once`` — ilk dəfə «Bu dəfə keç» (bu sessiya, ≤ 24 saat); keçid DB-də qalır
  (``SurveyGateSkip``) — növbəti girişdə qapı sərtdir və düymə yoxdur;
* ``defer_days`` — açılışdan N gün ərzində 24 saatlıq «Sonra doldur», sonra sərt.

Sorğu büdcəsi: dərc olunmuş sorğu yoxdursa və ya istifadəçinin rol ailəsi heç bir aktiv sorğunun
auditoriyasına düşmürsə SIFIR sorğu (xülasə ``Organization.settings``-də, üzvlüklər middleware-dən);
əks halda sessiya keşi (``STATE_TTL_SECONDS``, xülasə versiyası ilə) — təzədirsə yenə sıfır.
"""

from __future__ import annotations

import time

from ..constants import SESSION_SURVEY_STATE_KEY, STATE_TTL_SECONDS, GatePolicy
from .audience import audience_families, role_families, user_in_audience
from .gate_snapshot import active_survey_entries, snapshot_version
from .survey_respond import defer_active, skip_active


def generic_entries(request, today) -> list:
    """Bu istifadəçinin rol ailəsinə uyğun aktiv sorğuların xülasəsi (sıfır sorğu)."""
    user = getattr(request, "user", None)
    organization = getattr(request, "organization", None)
    if user is None or not getattr(user, "is_authenticated", False) or organization is None:
        return []
    if getattr(user, "is_superuser", False) or getattr(request, "is_view_as", False):
        return []
    entries = active_survey_entries(organization, today)
    if not entries:
        return []
    families = role_families(getattr(request, "org_memberships", None))
    if not families:
        return []
    return [entry for entry in entries if audience_families(entry["audience"]) & families]


def _compute_rows(request, organization, ids) -> dict:
    from ..models import Survey, SurveyGateSkip, SurveyParticipation

    surveys = list(Survey.objects.filter(organization=organization, pk__in=ids))
    memberships = getattr(request, "org_memberships", None)
    done = {
        str(pk)
        for pk in SurveyParticipation.objects.filter(survey_id__in=ids, user=request.user).values_list(
            "survey_id", flat=True
        )
    }
    skipped = {
        str(pk)
        for pk in SurveyGateSkip.objects.filter(survey_id__in=ids, user=request.user).values_list(
            "survey_id", flat=True
        )
    }
    return {
        str(survey.pk): [
            int(user_in_audience(survey, request.user, memberships)),
            int(str(survey.pk) in done),
            int(str(survey.pk) in skipped),
        ]
        for survey in surveys
    }


def compute_state(request, organization, entries, *, force=False) -> list:
    """``[{"id", "mandatory", "policy", "grace_until", "closes_on", "eligible", "done", "skipped"}]``."""
    version = snapshot_version(organization)
    now = int(time.time())
    ids = sorted(entry["id"] for entry in entries)
    session = getattr(request, "session", None)
    cached = session.get(SESSION_SURVEY_STATE_KEY) if session is not None else None
    flags = None
    if (
        not force
        and isinstance(cached, dict)
        and cached.get("v") == version
        and cached.get("u") == request.user.pk
        and now - int(cached.get("at") or 0) < STATE_TTL_SECONDS
        and sorted(cached.get("s", {})) == ids
    ):
        flags = cached["s"]
    if flags is None:
        flags = _compute_rows(request, organization, ids)
        if session is not None:
            session[SESSION_SURVEY_STATE_KEY] = {"v": version, "u": request.user.pk, "at": now, "s": flags}
    rows = []
    for entry in entries:
        eligible, done, skipped = flags.get(entry["id"], [0, 0, 0])
        rows.append({**entry, "eligible": bool(eligible), "done": bool(done), "skipped": bool(skipped)})
    return rows


def invalidate_state(request) -> None:
    if hasattr(request, "session"):
        request.session.pop(SESSION_SURVEY_STATE_KEY, None)


def blocking_row(request, rows, today):
    """Kabineti bağlayan ilk məcburi sorğu (``None`` — bağlamır)."""
    for row in rows:
        if not (row["mandatory"] and row["eligible"] and not row["done"]):
            continue
        policy = row["policy"]
        if policy == GatePolicy.SKIP_ONCE and skip_active(request, row["id"]):
            continue
        if (
            policy == GatePolicy.DEFER_DAYS
            and row["grace_until"]
            and today <= row["grace_until"]
            and defer_active(request, row["id"])
        ):
            continue
        return row
    return None


def pending_count(rows) -> int:
    return sum(1 for row in rows if row["eligible"] and not row["done"])
