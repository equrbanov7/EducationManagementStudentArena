"""``SAYT-####`` kartlarının ``QKU-N``-ə keçirilməsi — ``recode_site_subjects`` (sahib 2026-11-04).

Sahib: «SAYT deyə başına yazılan kodlar QKU olmalıdı, SAYT hardan gəlib bilmirəm, ona görə fənlərdə təkrarlanır hələ».
Mənşə: 2026-09-09 ``import_curriculum_plans --create-subjects`` (universitet saytının planları) 96 kartı ``SAYT-####``
kimi açıb (:mod:`.plan_manual` artıq ``QKU-N`` verir — :mod:`.subject_codes`).

İŞ SIRASI: əvvəlcə dublikat birləşmələri (``merge_subjects`` — SAYT kartı MƏNBƏ, arxivlənir), SONRA bu əmr qalanları
yenidən kodlaşdırır. Qaydalar:

* yalnız arxivdə OLMAYAN ``SAYT-N`` kartlar; kartın id-si DƏYİŞMİR (bütün FK-lar yerində qalır), yalnız ``code``;
* QKU dublikatı olan SAYT kartı TOXUNULMUR (``has_qku_duplicate`` — normallaşdırılmış adı arxivdə olmayan bir
  ``QKU-N`` kartı ilə eynidir: əvvəl birləşdirilməlidir); ``--exclude`` — gözləyən birləşmələrin SAYT kodları;
* yeni kod — ardıcıl, ən böyük ``QKU-N``-dən sonra (köhnə SAYT nömrəsi sırası ilə), təşkilatda unikal;
* hər qaçış bir paketdir (``sitecode-YYYYMMDD-HHMMSS-xxxx``) — audit-də ``köhnə → yeni`` siyahısı; ``--undo <paket>``
  kodları qaytarır (kart hələ yeni koddadırsa və köhnə kod boşdursa; əks halda heç nə yazılmır).
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .subject_codes import QKU_CODE_RE, SITE_CODE_RE, is_standard_code, next_qku_number, qku_code
from .subject_duplicates import normalized_subject_key

AUDIT_RESOURCE = "registrar.subject_recode"
REASON = "SAYT-#### kartlarının QKU-N-ə keçirilməsi — sahib 2026-11-04 («SAYT … kodlar QKU olmalıdı»)"


class RecodeError(Exception):
    pass


def _subject_model():
    return django_apps.get_model("registrar", "Subject")


def new_batch_id() -> str:
    return f"sitecode-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _site_number(code: str) -> int:
    match = SITE_CODE_RE.match(code or "")
    return int(match.group(1)) if match else 0


def old_code_index(organization) -> dict:
    """``{KÖHNƏ KOD (böyük hərf): fənn id}`` — geri qaytarılmamış yenidən-kodlaşdırma paketlərindən.

    Köhnə kodu açar kimi işlədən yerlər (legacy delta ``QKU-L<id>`` axtarışı) kartı yeni koda keçəndən sonra da tapır.
    """
    AuditLog = django_apps.get_model("audit", "AuditLog")
    undone = set(
        AuditLog.objects.filter(organization=organization, resource_type=f"{AUDIT_RESOURCE}.undo").values_list(
            "resource_id", flat=True
        )
    )
    index = {}
    rows = AuditLog.objects.filter(organization=organization, resource_type=AUDIT_RESOURCE).order_by("created_at")
    for batch, changes in rows.values_list("resource_id", "changes"):
        if batch in undone or (changes or {}).get("kind") != "subject_recode":
            continue
        for item in changes.get("items") or []:
            index[str(item["old"]).upper()] = item["id"]
    return index


def plan(organization, *, exclude=(), scope="site") -> dict:
    """``{"items": [{id, old, new, name}], "has_qku_duplicate": [kod], "excluded": [kod], "counts": Counter}``.

    ``scope="all"`` (sahib 2026-11-11: «standart olsun bir») — standart ``QKU-N`` olmayan HƏR kart (``SAYT-N``,
    ``QKU-L…``, ``QKU-MR…``, ``QKU-SRC-…``, boş / boşluqlu / kiçik hərfli); qaydalar eynidir."""

    Subject = _subject_model()
    if scope == "all":
        rows = [
            row
            for row in Subject._base_manager.filter(organization=organization).order_by("code")
            if not is_standard_code(row.code)
        ]
        rows.sort(key=lambda row: (not SITE_CODE_RE.match(row.code or ""), _site_number(row.code), row.code or ""))
        return _plan_rows(organization, rows, exclude)
    rows = list(Subject._base_manager.filter(organization=organization, code__startswith="SAYT-").order_by("code"))
    rows = sorted((row for row in rows if SITE_CODE_RE.match(row.code)), key=lambda row: _site_number(row.code))
    return _plan_rows(organization, rows, exclude)


def _plan_rows(organization, rows, exclude) -> dict:
    Subject = _subject_model()
    qku_keys = {
        normalized_subject_key(name)
        for code, name in Subject._base_manager.filter(
            organization=organization, code__startswith="QKU-", is_archived=False
        ).values_list("code", "name")
        if QKU_CODE_RE.match(code or "")
    }
    excluded = {code.strip() for code in exclude if code.strip()}
    counts = Counter()
    items, duplicates, skipped = [], [], []
    number = next_qku_number(organization)
    for row in rows:
        counts["site_cards"] += 1
        if row.is_archived:
            counts["archived_skipped"] += 1
            continue
        if row.code in excluded:
            counts["excluded"] += 1
            skipped.append(row.code)
            continue
        if normalized_subject_key(row.name) in qku_keys:
            counts["has_qku_duplicate"] += 1
            duplicates.append(row.code)
            continue
        items.append({"id": str(row.pk), "old": row.code, "new": qku_code(number), "name": row.name})
        number += 1
    counts["recoded"] = len(items)
    return {"items": items, "has_qku_duplicate": duplicates, "excluded": skipped, "counts": counts}


def apply_recode(organization, items, *, batch) -> None:
    Subject = _subject_model()
    locked = {
        str(row.pk): row
        for row in Subject._base_manager.select_for_update().filter(pk__in=[item["id"] for item in items])
    }
    taken = set(
        Subject._base_manager.filter(organization=organization, code__in=[item["new"] for item in items]).values_list(
            "code", flat=True
        )
    )
    if taken:
        raise RecodeError("new_code_taken")
    now = timezone.now()
    for item in items:
        row = locked.get(item["id"])
        if row is None or row.code != item["old"] or row.is_archived:
            raise RecodeError("drift")
        Subject._base_manager.filter(pk=row.pk).update(code=item["new"], updated_at=now)
    log_action(
        action=AuditAction.UPDATE,
        organization=organization,
        resource_type=AUDIT_RESOURCE,
        resource_id=batch,
        resource_repr=f"kod → QKU-N: {len(items)} kart",
        changes={"kind": "subject_recode", "batch": batch, "items": items},
        reason=REASON,
    )


def undo_recode(organization, batch) -> list:
    AuditLog = django_apps.get_model("audit", "AuditLog")
    entry = AuditLog.objects.filter(organization=organization, resource_type=AUDIT_RESOURCE, resource_id=batch).first()
    if entry is None or (entry.changes or {}).get("kind") != "subject_recode":
        raise RecodeError("batch_unknown")
    if AuditLog.objects.filter(resource_type=f"{AUDIT_RESOURCE}.undo", resource_id=batch).exists():
        raise RecodeError("already_undone")
    items = entry.changes["items"]
    Subject = _subject_model()
    rows = {
        str(row.pk): row for row in Subject._base_manager.select_for_update().filter(pk__in=[i["id"] for i in items])
    }
    if Subject._base_manager.filter(organization=organization, code__in=[i["old"] for i in items]).exists():
        raise RecodeError("old_code_taken")
    now = timezone.now()
    for item in items:
        row = rows.get(item["id"])
        if row is None or row.code != item["new"]:
            raise RecodeError("changed_after_recode")
        Subject._base_manager.filter(pk=row.pk).update(code=item["old"], updated_at=now)
    log_action(
        action=AuditAction.UPDATE,
        organization=organization,
        resource_type=f"{AUDIT_RESOURCE}.undo",
        resource_id=batch,
        resource_repr=f"undo SAYT → QKU: {len(items)} kart",
        changes={"kind": "subject_recode_undo", "batch": batch, "items": items},
        reason=f"Geri qaytarma — {REASON}",
    )
    return items


__all__ = [
    "AUDIT_RESOURCE",
    "RecodeError",
    "apply_recode",
    "new_batch_id",
    "old_code_index",
    "plan",
    "undo_recode",
]
