"""Dublikat işçi hesabı → əsas hesab: köçürmə və audit (sahib 2026-11-03).

Hər ``fields.MOVES`` sətri üçün (yalnız bu təşkilatın sətirləri, soft-silinmişlər daxil):

1. mənbəyə işarə edən sətirlər kilidlənir; hədəfdə eyni məntiqi sətir varsa (``Move.conflict``) sətir ATLANIR
   və ``<açar>_conflict`` sayılır (mənbədə qalır — mənbə bloklu olduğundan heç nəyə təsir etmir);
2. qalanları ŞƏRTİ UPDATE ilə (``<sahə>=mənbə``) hədəfə keçir — ``updated_at`` daxil heç bir başqa sahə dəyişmir;
3. hər qrup üçün AYRI audit sətri (``accounts.staff_merge``, ``resource_id`` = paket): model, sahə, id-lər.

Sonda mənbə hesab bloklu qalır: artıq bloklanıb/silinibsə toxunulmur, aktivdirsə (heç daxil olmayıb) «Hesabı
dayandır» ilə bloklanır. Paketin xülasəsi ``accounts.staff_merge_batch`` audit sətrindədir.

İdempotentdir: ikinci işə salınmada köçəcək sətir qalmır (``moved=0``).

``--undo`` QƏSDƏN YOXDUR: açılış/dərs müəllimi DB trigger-i (``registrar_guard_active_member``, 0041) sahəni yalnız
``grade.input`` hüququ olan AKTİV üzvə yazmağa icazə verir — bloklu dublikata geri yazmaq trigger-də dayanardı.
Geri dönüş yolu: apply-dan əvvəlki DB ehtiyat nüsxəsi (workflow alır) + audit sətirlərindəki dəqiq id-lər.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .. import account_block_reasons as block_reasons
from ..account_deletion import block_account
from .fields import MOVES

RESOURCE = "accounts.staff_merge"
BATCH_RESOURCE = "accounts.staff_merge_batch"
BLOCK_REASON_CODE = "other"
BLOCK_CONTACT_CODE = "rim"


def new_batch() -> str:
    return f"stfmerge-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _model(label: str):
    return django_apps.get_model(label)


def _scoped(model, organization):
    manager = model._base_manager
    if any(f.name == "organization" for f in model._meta.concrete_fields):
        return manager.filter(organization=organization)
    return manager.all()


def block_text(target_username: str) -> str:
    detail = f"Dublikat işçi hesabı — əsas hesab: {target_username}"
    return block_reasons.audit_text(BLOCK_REASON_CODE, "", detail)[:300]


def _move_one(move, organization, source, target, *, actor, reason, batch, counts: Counter) -> None:
    model = _model(move.label)
    attname = f"{move.field}_id"
    rows = list(_scoped(model, organization).select_for_update(of=("self",)).filter(**{attname: source.pk}))
    ids, conflicts = [], 0
    for row in rows:
        if move.conflict is not None and move.conflict(model, row, target.pk):
            conflicts += 1
        else:
            ids.append(row.pk)
    moved = model._base_manager.filter(pk__in=ids, **{attname: source.pk}).update(**{attname: target.pk}) if ids else 0
    counts[f"{move.key}_moved"] += moved
    counts["moved"] += moved
    if conflicts:
        counts[f"{move.key}_conflict"] += conflicts
        counts["conflicts"] += conflicts
    if moved:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            changes={
                "model": move.label,
                "field": move.field,
                "from_user_id": source.pk,
                "to_user_id": target.pk,
                "ids": [str(pk) for pk in ids],
            },
            reason=reason,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=f"{move.label}.{move.field}",
        )


def execute(organization, source, target, *, actor, reason: str, batch: str) -> Counter:
    counts: Counter = Counter()
    for move in MOVES:
        _move_one(move, organization, source, target, actor=actor, reason=reason, batch=batch, counts=counts)
    blocked_now = False
    if source.is_active:
        block_account(
            source,
            actor=actor,
            reason=block_text(target.username),
            reason_code=BLOCK_REASON_CODE,
            contact_code=BLOCK_CONTACT_CODE,
            contact_note=f"Əsas hesab: {target.username}"[:200],
        )
        blocked_now = True
    counts["source_blocked_now"] = int(blocked_now)
    counts["source_blocked"] = int(not get_user_model().objects.get(pk=source.pk).is_active)
    if counts["moved"] or blocked_now:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            changes={
                "batch": batch,
                "from_user_id": source.pk,
                "to_user_id": target.pk,
                "source_blocked_now": blocked_now,
                "counts": dict(counts),
            },
            reason=reason,
            resource_type=BATCH_RESOURCE,
            resource_id=batch,
            resource_repr="Dublikat işçi hesabı → əsas hesab",
        )
    return counts


def remaining(organization, source) -> dict:
    """Mənbəyə hələ də işarə edən (bu təşkilatdakı və ya təşkilatsız) sətirlərin SAYI — ``app_model_field`` açarı ilə."""
    left = {}
    for relation in get_user_model()._meta.get_fields(include_hidden=True):
        if not relation.auto_created or relation.concrete or relation.related_model is None:
            continue
        if relation.many_to_many:
            continue
        model = relation.related_model
        attname = relation.field.attname
        number = _scoped(model, organization).filter(**{attname: source.pk}).count()
        if number:
            left[f"{model._meta.label_lower.replace('.', '_')}_{relation.field.name}"] = number
    return dict(sorted(left.items()))
