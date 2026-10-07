"""«Bu fənnin bu semestr üçün artıq sillabusu var» — təkrar istifadənin accounts glue-su.

Domen qaydaları ``apps.syllabus.services.reuse_rules``-da, yazılar
``apps.syllabus.services.reuse``-dadır.  Burada yalnız:

1. hədəf açılışın registrar məlumatı (rəsmi saat, ixtisas, qrup ağacı) toplanır və
   :class:`ReuseTarget`-ə çevrilir — sillabus modulu registrar-ı idxal etmir;
2. dialoq JSON-u qurulur (qonşular, səbəb mətnləri, «Hamısına tətbiq et» siyahısı);
3. siyahı sətirləri və redaktor banneri üçün bağ bayraqları hesablanır.

SORĞU BÜDCƏSİ: qonşu siyahısı TƏK sorğudur (``sibling_queryset`` — select_related +
annotasiya), sətir başına sorğu yoxdur; «digər qruplarınız» siyahısının saatı
``plan_hours_by_offering`` ilə toplu oxunur.
"""

from __future__ import annotations

from collections import Counter

from django.db.models import Q
from django.utils.translation import pgettext_lazy

from apps.syllabus.models import ChangeKind, Syllabus
from apps.syllabus.public import SyllabusStatus, services

from .labels import HOUR_KIND_LABELS, STATUS_TONES, transition_text

_CTX = "accounts.syllabus"

_YOU = pgettext_lazy(_CTX, "Müəllif: siz")
_NO_GROUP = pgettext_lazy(_CTX, "Semestr dosyesi")
_HOURS_UNKNOWN = pgettext_lazy(_CTX, "saat məlum deyil")
_STATE_NONE = pgettext_lazy(_CTX, "sillabus yoxdur")
_STATE_LINKED = pgettext_lazy(_CTX, "artıq bağlıdır")
_STATE_HAS = pgettext_lazy(_CTX, "öz sillabusu var")

#: «Hamısına tətbiq et» bir sorğuda ən çox bu qədər hədəf qəbul edir.
MAX_BULK_TARGETS = 30

_SYLLABUS_RELATED = (
    "subject",
    "period",
    "program",
    "chair_unit",
    "current_version",
    "approved_version",
    "reused_from",
    "reused_from__approved_version",
    "offering",
    "offering__group",
    "offering__group__parent",
)


def _person(user) -> str:
    if user is None:
        return ""
    full = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", "") or ""


def hours_text(hours) -> str:
    """«Mühazirə 30 · Seminar 15» — saat bilinmirsə izah."""
    cleaned = services.normalize_hours(hours)
    if not cleaned:
        return str(_HOURS_UNKNOWN)
    return " · ".join(f"{HOUR_KIND_LABELS[kind]} {value}" for kind, value in cleaned.items())


def group_label(syllabus) -> str:
    """Dosyenin qrup adı (açılışsız dosye — «Semestr dosyesi»)."""
    offering = syllabus.offering if syllabus is not None and syllabus.offering_id else None
    group = offering.group if offering is not None and offering.group_id else None
    return group.name if group is not None else str(_NO_GROUP)


def _offering_group(offering) -> str:
    return offering.group.name if offering.group_id else str(_NO_GROUP)


def _offering_target(offering, *, syllabus=None, hours=None, program=None):
    from apps.registrar.public import plan_hours_for_offering, program_for_offering

    if hours is None:
        hours = plan_hours_for_offering(offering)
    if not hours and syllabus is not None and syllabus.current_version_id:
        # Rəsmi plan tapılmayanda müəllimin əl ilə seçdiyi saat (redaktordakı forma).
        hours = syllabus.current_version.plan_hours or {}
    if program is None:
        program = syllabus.program if syllabus is not None else program_for_offering(offering)
    return services.ReuseTarget(
        offering=offering,
        syllabus=syllabus,
        plan_hours=dict(hours or {}),
        program=program,
        unit_hint=offering.group.parent if offering.group_id else None,
    )


def target_for_syllabus(syllabus):
    """Mövcud dosye hədəfi (redaktordakı qaralama, siyahıdakı «qaralama» sətri)."""
    if syllabus.offering_id:
        return _offering_target(syllabus.offering, syllabus=syllabus)
    hours = syllabus.current_version.plan_hours if syllabus.current_version_id else {}
    return services.ReuseTarget(syllabus=syllabus, plan_hours=dict(hours or {}), program=syllabus.program)


def load_syllabus(organization, syllabus_id):
    if syllabus_id is None:
        return None
    return (
        Syllabus.objects.filter(organization=organization, pk=syllabus_id, is_active=True)
        .select_related(*_SYLLABUS_RELATED)
        .first()
    )


def resolve_target(organization, actor, *, offering_id=None, syllabus_id=None):
    """Dialoqun hədəfi — YALNIZ aktorun öz açılışı / öz dosyesi (fail-closed ``None``)."""
    from apps.registrar.public import instructor_offering

    if syllabus_id is not None:
        syllabus = load_syllabus(organization, syllabus_id)
        if syllabus is None or not services.is_author(actor, syllabus):
            return None
        return target_for_syllabus(syllabus)
    offering = instructor_offering(organization=organization, user=actor.user, offering_id=offering_id)
    if offering is None:
        return None
    existing = Syllabus.objects.filter(organization=organization, offering=offering).select_related(*_SYLLABUS_RELATED)
    return _offering_target(offering, syllabus=existing.first())


def _slot(target):
    holder = target.syllabus if target.syllabus is not None else target.offering
    return holder.subject, holder.period


def candidate_targets(organization, actor, *, subject_id, period_id, exclude_offering_id=None, only_ids=None):
    """Aktorun bu fənn + semestr üzrə digər açılışları → ``[(ReuseTarget, chair_id)]``.

    Sorğular SABİTDİR: açılışlar (1), saatlar (``plan_hours_by_offering``),
    ixtisaslar (1), mövcud dosyelər (1); kafedra həlli qrup valideyninə görə memo-lanır.
    """
    from apps.registrar.public import instructor_offerings, plan_hours_by_offering, programs_by_offering

    offerings = [
        offering
        for offering in instructor_offerings(
            organization=organization, user=actor.user, subject_id=subject_id, period_id=period_id
        )
        if offering.pk != exclude_offering_id and (only_ids is None or offering.pk in only_ids)
    ][:MAX_BULK_TARGETS]
    if not offerings:
        return []
    hours = plan_hours_by_offering(offerings)
    programs = programs_by_offering(offerings)
    existing = {
        row.offering_id: row
        for row in Syllabus.objects.filter(organization=organization, offering_id__in=[row.pk for row in offerings])
    }
    chair_memo: dict = {}
    result = []
    for offering in offerings:
        target = services.ReuseTarget(
            offering=offering,
            syllabus=existing.get(offering.pk),
            plan_hours=hours.get(offering.pk) or {},
            program=programs.get(offering.pk),
            unit_hint=offering.group.parent if offering.group_id else None,
        )
        key = getattr(target.unit_hint, "pk", None)
        if key not in chair_memo:
            chair_memo[key] = services.reuse.target_chair_unit_id(target, actor)
        result.append((target, chair_memo[key]))
    return result


def _candidate_public(target) -> dict:
    syllabus = target.syllabus
    if syllabus is None:
        state, label = "none", _STATE_NONE
    elif syllabus.reused_from_id:
        state, label = "linked", _STATE_LINKED
    else:
        state, label = "has", _STATE_HAS
    return {
        "offering": str(target.offering.pk),
        "group": _offering_group(target.offering),
        "hours_text": hours_text(target.plan_hours),
        "state": state,
        "state_label": str(label),
        "linked_to": str(syllabus.reused_from_id) if syllabus is not None and syllabus.reused_from_id else "",
    }


def _status(row):
    version = row.current_version
    status = version.status if version is not None else SyllabusStatus.DRAFT.value
    return status, version


def _sibling_row(row, *, actor, target, chair_id, target_code, candidates, chair_memo=None) -> dict:
    from .rows import approver_text

    rules = services.reuse_rules
    approved = row.approved_version if row.approved_version_id else None
    base = approved or row.current_version
    base_hours = getattr(base, "plan_hours", None) or {}
    copyable = bool(row._copyable)
    # Köhnə dosyedə kafedra ixtisasa işarə edə bilər — təsdiq marşrutunun EFFEKTİV kafedrası (memo ilə).
    source_chair = rules.effective_chair_unit_id(row, chair_memo if chair_memo is not None else {})
    link_code = rules.link_code(
        row,
        actor=actor,
        target_hours=target.plan_hours,
        target_chair_unit_id=chair_id,
        target_code=target_code,
        source_chair_unit_id=source_chair,
    )
    copy_code = rules.copy_code(row, actor=actor, target_code=target_code, copyable=copyable)
    modes = {}
    for candidate, candidate_chair in candidates:
        if candidate.syllabus is not None:
            continue
        free_link = rules.link_code(
            row,
            actor=actor,
            target_hours=candidate.plan_hours,
            target_chair_unit_id=candidate_chair,
            target_code="",
            source_chair_unit_id=source_chair,
        )
        free_copy = rules.copy_code(row, actor=actor, target_code="", copyable=copyable)
        modes[str(candidate.offering.pk)] = "link" if not free_link else ("copy" if not free_copy else "")
    status, version = _status(row)
    return {
        "id": str(row.pk),
        "group": group_label(row),
        "author": str(_YOU) if row._own else _person(row.author),
        "own": bool(row._own),
        "status_key": status,
        "status_label": str(SyllabusStatus(status).label),
        "status_tone": STATUS_TONES.get(status, "neutral"),
        "version_label": base.label if base is not None else "—",
        "approver": approver_text(row, approved) if approved is not None else "",
        "hours_text": hours_text(base_hours),
        "hours_same": services.hours_match(base_hours, target.plan_hours),
        "hours_rows": [
            {**item, "label": str(HOUR_KIND_LABELS[item["kind"]])}
            for item in rules.hours_rows(base_hours, target.plan_hours)
        ],
        "linked_count": int(row._linked or 0),
        "can_link": not link_code,
        "link_reason": transition_text(link_code) if link_code else "",
        "can_copy": not copy_code,
        "copy_reason": transition_text(copy_code) if copy_code else "",
        "modes": modes,
    }


def build_options(organization, actor, target) -> dict:
    """Dialoqun JSON-u — bax ``reuse_api.syllabus_reuse_options``."""
    subject, period = _slot(target)
    target_syllabus = target.syllabus
    siblings = list(
        services.sibling_queryset(
            organization=organization,
            actor=actor,
            subject_id=subject.pk,
            period_id=getattr(period, "pk", None),
            exclude_syllabus_id=getattr(target_syllabus, "pk", None),
            exclude_offering_id=target.offering_id,
        )
    )
    target_code = services.reuse_rules.target_state_code(target_syllabus)
    chair_memo: dict = {}
    chair_id = services.reuse.target_chair_unit_id(target, actor)
    candidates = (
        candidate_targets(
            organization,
            actor,
            subject_id=subject.pk,
            period_id=getattr(period, "pk", None),
            exclude_offering_id=target.offering_id,
        )
        if siblings
        else []
    )
    group = _offering_group(target.offering) if target.offering is not None else group_label(target_syllabus)
    return {
        "target": {
            "kind": "syllabus" if target_syllabus is not None else "offering",
            "id": str(target_syllabus.pk if target_syllabus is not None else target.offering.pk),
            "offering": str(target.offering_id or ""),
            "group": group,
            "subject": f"{subject.code} · {subject.name}",
            "period": f"{period.year_display} · {period.name}" if period is not None else "",
            "hours_text": hours_text(target.plan_hours),
            "hours_known": bool(services.normalize_hours(target.plan_hours)),
            "replaces_draft": target_syllabus is not None,
            "blocked": bool(target_code),
            "blocked_reason": transition_text(target_code) if target_code else "",
        },
        "siblings": [
            _sibling_row(
                row,
                actor=actor,
                target=target,
                chair_id=chair_id,
                target_code=target_code,
                candidates=candidates,
                chair_memo=chair_memo,
            )
            for row in siblings
        ],
        "candidates": [_candidate_public(candidate) for candidate, _chair in candidates],
        "can_create_blank": target_syllabus is None,
    }


# ── Siyahı sətirləri ────────────────────────────────────────────────────────────


def page_flags(page_syllabi, visible, *, user_id=None) -> dict:
    """Səhifə dosyeləri üçün bağ bayraqları — SƏHİFƏ başına ən çox iki sorğu.

    ``{syllabus_id: {linked, behind, source_group, linked_count, behind_count, siblings}}``.
    """
    page = list(page_syllabi)
    if not page:
        return {}
    summary = services.reuse.linked_summary(page)
    open_drafts = [
        row
        for row in page
        if row.offering_id
        and row.period_id
        and not row.reused_from_id
        and row.approved_version_id is None
        and row.current_version is not None
        and row.current_version.status == SyllabusStatus.DRAFT.value
        # Artıq bir mənbədən kopyalanmış qaralamaya təklif təkrarlanmır (səs-küy olmasın).
        and row.current_version.change_kind != ChangeKind.COPIED.value
    ]
    pairs: Counter = Counter()
    if open_drafts:
        for subject_id, period_id in (
            visible.order_by()
            .filter(
                subject_id__in={row.subject_id for row in open_drafts},
                period_id__in={row.period_id for row in open_drafts},
                reused_from__isnull=True,
            )
            # Yalnız baxanın ÖZ dosyeləri mənbə ola bilər (rəhbər siyahısında başqaları da var).
            .filter(Q(author_id=user_id) | Q(offering__instructor_id=user_id) if user_id else Q())
            .values_list("subject_id", "period_id")
        ):
            pairs[(subject_id, period_id)] += 1
    flags = {}
    for row in page:
        entry = summary.get(row.pk, {})
        siblings = pairs.get((row.subject_id, row.period_id), 0) - 1 if row in open_drafts else 0
        flags[row.pk] = {
            "linked": bool(row.reused_from_id),
            "behind": services.reuse.is_behind(row),
            "source_group": group_label(row.reused_from) if row.reused_from_id else "",
            "linked_count": entry.get("linked", 0),
            "behind_count": entry.get("behind", 0),
            "siblings": max(siblings, 0),
        }
    return flags


# ── Redaktor banneri ────────────────────────────────────────────────────────────


def editor_reuse_state(request, organization, *, syllabus, version, is_author: bool) -> dict:
    """Redaktorun bağ banneri: ``linked`` | ``source`` | ``offer`` | ``""``."""
    actor = services.resolve_actor(getattr(request, "user", None), organization, request=request)
    if syllabus.reused_from_id:
        return {
            "mode": "linked",
            "group": group_label(syllabus.reused_from),
            "behind": services.reuse.is_behind(syllabus),
            "can_act": is_author,
            "syllabus": str(syllabus.pk),
        }
    summary = services.reuse.linked_summary([syllabus]).get(syllabus.pk)
    if summary and summary["linked"]:
        return {
            "mode": "source",
            "linked": summary["linked"],
            "behind": summary["behind"],
            "can_act": is_author,
            "syllabus": str(syllabus.pk),
        }
    if (
        is_author
        and syllabus.period_id
        and syllabus.approved_version_id is None
        and version.status == SyllabusStatus.DRAFT.value
        and version.change_kind != ChangeKind.COPIED.value
    ):
        count = (
            services.sibling_queryset(
                organization=organization,
                actor=actor,
                subject_id=syllabus.subject_id,
                period_id=syllabus.period_id,
                exclude_syllabus_id=syllabus.pk,
                exclude_offering_id=syllabus.offering_id,
            )
            .filter(services.own_q(actor))  # mənbə yalnız öz dosyesi ola bilər (rəhbər də)
            .order_by()
            .values("pk")
            .count()
        )
        if count:
            return {"mode": "offer", "count": count, "syllabus": str(syllabus.pk)}
    return {"mode": ""}


__all__ = [
    "MAX_BULK_TARGETS",
    "build_options",
    "candidate_targets",
    "editor_reuse_state",
    "group_label",
    "hours_text",
    "load_syllabus",
    "page_flags",
    "resolve_target",
    "target_for_syllabus",
]
