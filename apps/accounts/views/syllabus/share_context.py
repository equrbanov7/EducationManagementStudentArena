"""«Bir sillabus — bir neçə jurnal» (sahib 2026-10-27) — accounts glue.

Qaydalar və yazı ``apps.syllabus.services.sharing``-dədir; burada yalnız:

1. təkrar istifadə dialoqunun mənbə kartlarına «Eyni sillabusu bu qrupda da istifadə et» seçiminin səbəb kodu;
2. «digər qruplarınız» siyahısında paylaşılmış qrupun vəziyyəti;
3. redaktorun paylaşım bloku — sillabusu öz yerində istifadə edən qruplar («Ayır») və hələ sillabusu olmayan
   öz qruplarınız (layihənin seçim komponenti + «Əlavə et»);
4. siyahı sətrinin «həmçinin bu qruplarda» qeydi.

SORĞU BÜDCƏSİ: dialoqda hədəfin vəziyyəti BİR dəfə hesablanır (mənbə başına sorğu yoxdur); redaktor bloku ən çox
dörd sorğudur; siyahı səhifəsi üçün bir sorğu.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.models import ShareSource, Syllabus, SyllabusShare
from apps.syllabus.public import PERM_EDIT, services

from .labels import transition_text

_CTX = "accounts.syllabus"

_NO_GROUP = pgettext_lazy(_CTX, "Semestr dosyesi")
_STATE_SHARED = pgettext_lazy(_CTX, "eyni sillabusu istifadə edir")
_LEGACY = pgettext_lazy(_CTX, "köhnə sistemdən")


def _group_name(offering) -> str:
    group = offering.group if offering is not None and offering.group_id else None
    return group.name if group is not None else str(_NO_GROUP)


def target_state(target) -> str:
    """Dialoq hədəfi paylaşıma açıqdırmı — ``""`` və ya səbəb kodu (BİR dəfə, mənbədən asılı deyil)."""
    sharing = services.sharing
    if target.offering is None:
        return services.reuse_rules.CODE_NOT_SIBLING
    if target.syllabus is not None:
        return sharing.CODE_HAS_OWN
    return sharing.target_code(target.offering)


def sibling_share(row, *, actor, target, state_code) -> dict:
    """Mənbə kartının ``can_share`` / ``share_reason`` sahələri."""
    if target.offering is None:
        code = services.reuse_rules.CODE_NOT_SIBLING
    else:
        code = services.sharing.share_code(row, actor=actor, offering=target.offering, state_code=state_code)
    return {"can_share": not code, "share_reason": transition_text(code) if code else ""}


def shared_targets(organization, offering_ids) -> dict:
    """``{offering_id: Syllabus}`` — paylaşımla ARTIQ sillabusu olan açılışlar (iki sorğu)."""
    shared = services.shared_syllabus_ids(list(offering_ids))
    if not shared:
        return {}
    rows = Syllabus.objects.filter(organization=organization, pk__in=set(shared.values())).select_related(
        "offering", "offering__group"
    )
    by_pk = {row.pk: row for row in rows}
    return {offering_id: by_pk[pk] for offering_id, pk in shared.items() if pk in by_pk}


def candidate_shared(target) -> dict | None:
    """«Digər qruplarınız» sətri paylaşılıbsa ``{state, state_label}`` (hədəfin dosyesi başqa açılışındır)."""
    syllabus = target.syllabus
    if syllabus is None or target.offering is None or syllabus.offering_id == target.offering.pk:
        return None
    label = f"{_STATE_SHARED} — {_group_name(syllabus.offering)}" if syllabus.offering_id else str(_STATE_SHARED)
    return {"state": "shared", "state_label": label}


def editor_share_state(request, organization, *, syllabus, is_author: bool) -> dict:
    """Redaktorun paylaşım bloku: ``{"mode": "share", shares, free, can_act, syllabus}`` və ya ``{"mode": ""}``."""
    if (
        syllabus is None
        or not syllabus.is_active
        or syllabus.offering_id is None
        or syllabus.period_id is None
        or syllabus.reused_from_id is not None
    ):
        return {"mode": ""}
    shares = [
        {
            "offering": str(row.offering_id),
            "group": _group_name(row.offering),
            "legacy": row.source == ShareSource.LEGACY.value,
            "legacy_label": str(_LEGACY),
        }
        for row in services.sharing.shares_of(syllabus)
    ]
    free = []
    actor = services.resolve_actor(getattr(request, "user", None), organization, request=request)
    can_act = bool(is_author and actor.has(PERM_EDIT))
    if can_act:
        from apps.registrar.public import instructor_offerings

        offerings = [
            offering
            for offering in instructor_offerings(
                organization=organization,
                user=actor.user,
                subject_id=syllabus.subject_id,
                period_id=syllabus.period_id,
            )
            if offering.pk != syllabus.offering_id
        ]
        ids = [offering.pk for offering in offerings]
        taken = set(
            Syllabus.objects.filter(organization=organization, offering_id__in=ids, is_active=True).values_list(
                "offering_id", flat=True
            )
        ) | set(SyllabusShare.objects.filter(offering_id__in=ids).values_list("offering_id", flat=True))
        free = [
            {"offering": str(offering.pk), "group": _group_name(offering)}
            for offering in offerings
            if offering.pk not in taken
        ]
    if not shares and not free:
        return {"mode": ""}
    return {"mode": "share", "syllabus": str(syllabus.pk), "shares": shares, "free": free, "can_act": can_act}


def page_shared_groups(page_syllabi) -> dict:
    """``{syllabus_id: [qrup adı, …]}`` — siyahı səhifəsinin «həmçinin bu qruplarda» qeydi (BİR sorğu)."""
    ids = [row.pk for row in page_syllabi if row.offering_id]
    if not ids:
        return {}
    groups: dict = {}
    for syllabus_id, name in (
        services.sharing.effective_shares()
        .filter(syllabus_id__in=ids)
        .order_by("offering__group__name")
        .values_list("syllabus_id", "offering__group__name")
    ):
        groups.setdefault(syllabus_id, []).append(name or str(_NO_GROUP))
    return groups


__all__ = [
    "candidate_shared",
    "editor_share_state",
    "page_shared_groups",
    "shared_targets",
    "sibling_share",
    "target_state",
]
