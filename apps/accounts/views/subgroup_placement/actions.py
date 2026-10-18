"""«Alt qrupa tələbə əlavə et» — YAZMA endpoint-ləri (POST).

* ``placement_place`` — multipart: ``student``, ``offering``, ``reason``, ``document`` (fayl) və/və ya
  ``order_number`` + ``order_date``, ``release_source``, ``accept_clash``. Yerləşdirmə registrar servisindədir
  (:func:`apps.registrar.public.place_in_subgroup`) — burada yalnız giriş datası, aktor qapısı və toqquşma təsdiqi.
* ``placement_undo`` — JSON: ``event``, ``reason`` — rəsmi geri götürmə (tarixçə qalır).

Cədvəl toqquşması «xəbərdarlıq» rejimində də İŞÇİNİN AÇIQ TƏSDİQİNİ tələb edir (``accept_clash``): önbaxış
toqquşmanı göstərir, təsdiq qutusu işarələnməyibsə server 409 ``clash_confirm_required`` qaytarır.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.registrar.public import (
    SubgroupPlacementError,
    evaluate_subgroup_placement,
    place_in_subgroup,
    subgroup_placement_history,
    subgroup_placement_lookups,
    undo_subgroup_placement,
)
from core.write_rate_limit import score_write_rate_limited

from .api import _error, _flag, _uuid
from .policy import forbidden, resolve_actor, view_as_blocked


def _payload(request) -> dict:
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return request.POST


def _field(data, key, limit=2000) -> str:
    return str(data.get(key) or "").strip()[:limit]


def _gate(request):
    actor = resolve_actor(request)
    if not actor.has_access:
        return actor, forbidden()
    if not actor.can_write:
        return actor, view_as_blocked()
    return actor, None


@never_cache
@login_required
@require_POST
@score_write_rate_limited("subgroup_placement")
def placement_place(request):
    """Tələbəni seçilmiş jurnala alt qrupdan yerləşdirir."""
    actor, denied = _gate(request)
    if denied is not None:
        return denied
    data = _payload(request)
    try:
        student, record = subgroup_placement_lookups.resolve_student(
            actor=actor.user, organization=actor.organization, student_id=_field(data, "student", 20)
        )
        offering = subgroup_placement_lookups.offering_for(
            organization=actor.organization, offering_id=_uuid(_field(data, "offering", 64))
        )
        release = _flag(data.get("release_source"))
        if not _flag(data.get("accept_clash")):
            plan = evaluate_subgroup_placement(
                student=student, offering=offering, actor=actor.user, release_source=release, record=record
            )
            if plan["ok"] and plan["clashes"]:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "clash_confirm_required",
                        "message": pgettext(
                            "accounts.subgroup_placement",
                            "Dərs saatı tələbənin öz cədvəli ilə üst-üstə düşür — təsdiq qutusunu işarələyin.",
                        ),
                        "clashes": plan["clashes"],
                    },
                    status=409,
                )
        result = place_in_subgroup(
            student=student,
            offering=offering,
            document={
                "file": request.FILES.get("document"),
                "number": _field(data, "order_number", 64),
                "date": _field(data, "order_date", 10),
            },
            actor=actor.user,
            reason=_field(data, "reason"),
            request=request,
            release_source=release,
        )
    except SubgroupPlacementError as exc:
        return _error(exc)
    event = result["event"]
    projection = result["credit"]["projection"]
    return JsonResponse(
        {
            "ok": True,
            "event_id": str(event.pk),
            "message": pgettext(
                "accounts.subgroup_placement", "Tələbə alt qrupa yerləşdirildi: %(subject)s · %(group)s."
            )
            % {"subject": offering.subject.name, "group": getattr(offering.group, "name", "") or "—"},
            "credit": {
                "before": projection["total_before"],
                "after": projection["total_after"],
                "limit": projection["limit"],
            },
            "warnings": result["warnings"],
            "retake": result["retake"],
            "released": result["released"],
            "placement": subgroup_placement_history.serialize(event),
        }
    )


@never_cache
@login_required
@require_POST
@score_write_rate_limited("subgroup_placement")
def placement_undo(request):
    """Yerləşdirməni geri götürür (rəsmi xidmət — qeydiyyat ``dropped``, tarixçə qalır)."""
    actor, denied = _gate(request)
    if denied is not None:
        return denied
    data = _payload(request)
    event_id = _uuid(_field(data, "event", 64))
    if event_id is None:
        return _error(SubgroupPlacementError("not_found"))
    try:
        result = undo_subgroup_placement(
            event_id=event_id,
            actor=actor.user,
            reason=_field(data, "reason"),
            organization=actor.organization,
            request=request,
        )
    except SubgroupPlacementError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "ok": True,
            "message": pgettext("accounts.subgroup_placement", "Yerləşdirmə geri götürüldü — tarixçə saxlanılır."),
            "credit": {"total": result["credit"]["total"], "limit": result["credit"]["limit"]},
        }
    )


__all__ = ["placement_place", "placement_undo"]
