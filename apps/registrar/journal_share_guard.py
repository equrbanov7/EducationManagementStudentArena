"""Bölünmüş jurnalın səth qapıları — POST yoxlamaları + jurnal səhifəsi kontekstinin daraldılması (sahib 2026-10-26).

Əhatə qaydaları :mod:`apps.registrar.journal_shares`-dadır; burada yalnız tətbiqi:

* **POST** — məhdud əhatəli aktor yalnız öz sətirlərinə (tələbələrinə) və öz dərs növlərinə (və ya ``Lesson.instructor``
  özü olan dərsə) yazır; Midterm / komponent / yekun / kurs və sərbəst iş — yalnız ``can_manage_scores`` ilə və yalnız
  öz sətirlərində. Pozuntu → 403 (avtomatik yadda saxlamada JSON ``code="share_scope"``) — UI belə xananı heç göstərmir,
  yəni bura yalnız əl ilə qurulmuş sorğu çatır. Pay sahibinin (sahib deyil) yeni dərsi onun öz adına yazılır.
* **GET** — tab sətirləri, dərs tipi pillələri və «Yeni dərs» modalının növləri əhatəyə qədər daralır; başlıqda çip.

Tam əhatədə (pay yoxdur, sahib payı yoxdur, inzibatçı) heç nə dəyişmir.
"""

from __future__ import annotations

import uuid

from django.http import HttpResponseForbidden
from django.utils.translation import pgettext

from . import journal_autosave
from .journal_shares import chip, journal_scope

#: Davamiyyət/bal xanası açarları: ``<prefiks>__<dərs>__<qeydiyyat>``.
MARK_PREFIXES = frozenset({"att", "score", "cell", "absent"})
#: Jurnal səhifəsinin bal idarəsi əməlləri (``journal_detail`` POST ``action``).
SCORE_ACTIONS = frozenset({"save_finals", "save_components", "save_component_scores"})
#: Tək tələbəli formaların qeydiyyat sahəsi (açar deyil, DƏYƏR).
ENROLLMENT_VALUE_FIELDS = ("cw_enrollment",)

scope = journal_scope


def _uuid_text(raw) -> str | None:
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, TypeError, AttributeError):
        return None


def posted_enrollment_ids(post) -> set:
    """POST-un toxunduğu qeydiyyat id-ləri: ``…__<uuid>`` açarlarının SON hissəsi + tək tələbəli sahələr."""
    found = set()
    for key in post:
        if "__" in key:
            value = _uuid_text(key.rsplit("__", 1)[1])
            if value:
                found.add(value)
    for field in ENROLLMENT_VALUE_FIELDS:
        value = _uuid_text(post.get(field))
        if value:
            found.add(value)
    return found


def posted_lesson_ids(post) -> set:
    found = set()
    for key in post:
        parts = key.split("__", 2)
        if len(parts) == 3 and parts[0] in MARK_PREFIXES:
            value = _uuid_text(parts[1])
            if value:
                found.add(value)
    return found


def deny(request):
    message = pgettext("registrar.journal_share", "Bu xana bölünmüş jurnalda sizin payınıza aid deyil.")
    if journal_autosave.requested(request):
        return journal_autosave.refused(message, code="share_scope", status=403)
    return HttpResponseForbidden("share_scope", content_type="text/plain; charset=utf-8")


def _rows_ok(scope_, post) -> bool:
    return all(scope_.allows_enrollment(enrollment_id) for enrollment_id in posted_enrollment_ids(post))


def _lessons_ok(scope_, offering, lesson_ids) -> bool:
    if not lesson_ids or scope_.kinds is None:
        return True
    from .models import Lesson

    lessons = list(
        Lesson.objects.filter(offering_id=offering.pk, pk__in=lesson_ids).only("id", "kind", "instructor_id")
    )
    return all(scope_.allows_lesson(lesson) for lesson in lessons)


def _assign_self(request) -> None:
    """Pay sahibinin (sahib deyil) yeni dərsi onun öz adına — modal nə göndərirsə göndərsin."""
    post = request.POST.copy()
    post["lesson_instructor"] = str(request.user.pk)
    request.POST = post


def detail_post_guard(request, offering):
    """``journal_detail`` POST — əhatədən kənar yazı → 403; hər şey qaydasındadırsa None."""
    scope_ = journal_scope(request.user, offering)
    if scope_.full:
        return None
    action = request.POST.get("action")
    if action in SCORE_ACTIONS:
        allowed = scope_.can_manage_scores and (action != "save_components" or scope_.is_owner)
        return None if allowed and _rows_ok(scope_, request.POST) else deny(request)
    if action == "add_lesson":
        from .journal_extras import locked_lesson_kind

        if not scope_.allows_kind(locked_lesson_kind(offering) or request.POST.get("lesson_kind")):
            return deny(request)
        if not scope_.is_owner:
            _assign_self(request)
        return None
    if not _rows_ok(scope_, request.POST) or not _lessons_ok(scope_, offering, posted_lesson_ids(request.POST)):
        return deny(request)
    return None


def rows_post_guard(request, offering, *, structural=False):
    """Midterm / sərbəst iş / kurs işi POST-u (``journal_actions``) — bal idarəsi + yalnız öz sətirləri.

    ``structural`` (bütün açılışa aid quruluş: sərbəst iş mövzusu / strukturu) — yalnız açılışın sahibi."""
    scope_ = journal_scope(request.user, offering)
    if scope_.full:
        return None
    if not scope_.can_manage_scores or (structural and not scope_.is_owner) or not _rows_ok(scope_, request.POST):
        return deny(request)
    return None


def lesson_post_guard(request, offering, lesson):
    """Dərs sütununun redaktəsi/silinməsi — yalnız əhatədəki dərs; növ yalnız əhatədəki növə; müəllim — özü."""
    scope_ = journal_scope(request.user, offering)
    if scope_.full:
        return None
    if not scope_.allows_lesson(lesson):
        return deny(request)
    posted_kind = request.POST.get("lesson_kind")
    if posted_kind and posted_kind != lesson.kind and not scope_.allows_kind(posted_kind):
        return deny(request)
    posted_teacher = (request.POST.get("lesson_instructor") or "").strip()
    if not scope_.is_owner and posted_teacher and posted_teacher != str(request.user.pk):
        return deny(request)
    return None


def slot_activation(user, offering, slot):
    """«Aktivləşdir» — ``(icazə, müəllim əvəzi)``: slot növü əhatədə olmalıdır; pay sahibinin dərsi öz adına."""
    scope_ = journal_scope(user, offering)
    if scope_.full:
        return True, None
    if not scope_.allows_kind(slot.kind):
        return False, None
    return True, (None if scope_.is_owner else user)


def _keep_rows(data, scope_):
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return {**data, "rows": [row for row in data["rows"] if scope_.allows_enrollment(row["enrollment"].id)]}
    return data


def _readonly_interim(grid):
    """Bal idarəsi olmayan pay sahibi (məs. yalnız seminar) Midterm xanalarını yalnız OXUYUR."""
    if not isinstance(grid, dict):
        return grid
    rows = [{**row, "cells": [{**cell, "editable": False} for cell in row["cells"]]} for row in grid.get("rows", [])]
    columns = [{**column, "open": False} for column in grid.get("columns", [])]
    return {**grid, "rows": rows, "columns": columns, "any_open": False}


def restrict_detail_context(context, scope_) -> None:
    """``journal_detail`` GET kontekstini əhatəyə qədər daralt (tam əhatədə toxunulmur)."""
    if scope_.full:
        return
    for key in ("finals", "final_breakdown", "kollokvium_grid", "selfwork_board"):
        context[key] = _keep_rows(context.get(key), scope_)
    context["coursework_rows"] = [
        row for row in context.get("coursework_rows") or [] if scope_.allows_enrollment(row["enrollment"].id)
    ]
    if not scope_.can_manage_scores:
        context["kollokvium_grid"] = _readonly_interim(context.get("kollokvium_grid"))
    tabs = [
        tab for tab in context.get("journal_kind_tabs") or [] if not tab["value"] or scope_.allows_kind(tab["value"])
    ]
    context["journal_kind_tabs"] = tabs if len(tabs) > 2 else []
    context["lesson_kinds"] = [
        (value, label) for value, label in context.get("lesson_kinds") or [] if scope_.allows_kind(value)
    ]
    context["journal_share_chip"] = chip(scope_)


def restrict_export(finals_data, scope_):
    """Jurnal ixracı (xlsx) — sətirlər əhatəyə qədər (sütunlar ``get_offering_journal(scope=…)``-dan)."""
    if scope_.full:
        return finals_data
    return _keep_rows(finals_data, scope_)


__all__ = [
    "deny",
    "detail_post_guard",
    "lesson_post_guard",
    "posted_enrollment_ids",
    "posted_lesson_ids",
    "restrict_detail_context",
    "restrict_export",
    "rows_post_guard",
    "scope",
    "slot_activation",
]
