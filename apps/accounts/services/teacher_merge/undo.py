"""Müəllim birləşdirməsinin GERİ QAYTARILMASI (paket ``tmerge-…``; manifest audit sətrindədir).

Yalnız hələ də paketin vəziyyətində qalan geri qaytarılır (sətir hələ hədəfdədirsə mənbəyə qayıdır).

Sıra vacibdir — DB qoruyucuları jurnal sahibi / dərs müəllimi üçün AKTİV ``grade.input`` üzvlüyü, müəllif sahələri
üçün isə AKTİV hesab + aktiv üzvlük tələb edir, mənbə isə bloklanıb:

1. mənbə MÜVƏQQƏTİ aktivləşir (``is_active``; profilin blok qeydi toxunulmur), deaktiv etdiyimiz üzvlükləri qayıdır;
   ``grade.input``-u yoxdursa deaktiv ``grade.input`` üzvlüyü müvəqqəti açılır (yoxdursa müvəqqəti yaradılır);
2. birləşdirilmiş paylar əvvəlki əhatəyə qayıdır; köçən sətirlər (paylar da) mənbəyə qayıdır;
3. deaktiv etdiyimiz paylar yenidən aktiv olur;
4. müvəqqəti üzvlük bağlanır (yaradılmışdısa silinir — yalnız bu addımın özünün yaratdığı sətir);
5. hədəfə verdiyimiz rollar geri alınır: aktivləşdirdiyimiz deaktiv olur, YARATDIĞIMIZ üzvlük sətri silinir;
6. mənbə əvvəlki halına: bizim bloklamışdıqsa «Hesabı aç», əks halda yenə ``is_active=False``.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import journal_unlock

from ..account_deletion import unblock_account
from . import guards, policy, repoint, shares
from .apply import BATCH_RESOURCE, TEACHER_ROLE

UNDO_RESOURCE = "accounts.teacher_merge_undo"


def _membership_model():
    return django_apps.get_model("organizations", "Membership")


def _temporary_authority(organization, source) -> tuple:
    """Mənbəyə müvəqqəti ``grade.input`` — (``activated`` / ``created`` / ``""``, üzvlük id-si)."""
    if guards.has_grade_input(organization, source):
        return "", None
    membership_model = _membership_model()
    for membership in membership_model.objects.filter(organization=organization, user=source, is_active=False).select_related("role"):  # fmt: skip
        if membership.role.is_active and guards.grants_grade_input(membership.role):
            membership_model.objects.filter(pk=membership.pk).update(is_active=True)
            return "activated", membership.pk
    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=organization, name=TEACHER_ROLE, is_active=True)
        .first()
    )
    if role is None:
        return "", None
    temp = membership_model.objects.filter(organization=organization, user=source, role=role, scope_unit=None).first()
    if temp is not None:
        membership_model.objects.filter(pk=temp.pk).update(is_active=True)
        return "activated", temp.pk
    temp = membership_model.objects.create(
        organization=organization, user=source, role=role, is_primary=False, is_active=True
    )
    return "created", temp.pk


def _end_temporary_authority(kind: str, pk) -> None:
    if kind == "activated":
        _membership_model().objects.filter(pk=pk).update(is_active=False)
    elif kind == "created":
        _membership_model().objects.filter(pk=pk).delete()


def _return_rows(manifest, counts) -> None:
    by_key = {relation.key: relation for relation in policy.relations()}
    with journal_unlock():
        for key, ids in (manifest.get("moved") or {}).items():
            relation = by_key.get(key)
            if relation is None:
                counts["undo_relation_missing"] += len(ids)
                continue
            model = relation.model
            pk_field = model._meta.pk
            typed = [pk_field.to_python(pk) for pk in ids]
            still = list(
                model._base_manager.filter(pk__in=typed, **{relation.attname: manifest["target"]}).values_list(
                    "pk", flat=True
                )
            )
            returned, failed = repoint.move(relation, still, manifest["target"], manifest["source"])
            counts["undo_rows_returned"] += len(returned)
            counts["undo_rows_changed"] += len(typed) - len(still)
            if failed:
                counts["undo_rows_blocked"] += len(failed)
                counts[f"undo_blocked_{relation.short}"] += len(failed)


def undo(organization, batch: str, *, actor) -> Counter:
    audit_model = django_apps.get_model("audit", "AuditLog")
    entry = audit_model.objects.filter(
        organization=organization, resource_type=BATCH_RESOURCE, resource_id=batch
    ).first()
    if entry is None:
        raise guards.MergeError("batch_not_found")
    if audit_model.objects.filter(organization=organization, resource_type=UNDO_RESOURCE, resource_id=batch).exists():
        raise guards.MergeError("batch_already_undone")
    manifest = (entry.new_values or {}).get("manifest") or {}
    user_model = get_user_model()
    source = user_model.objects.select_related("profile").filter(pk=manifest.get("source")).first()
    if source is None or user_model.objects.filter(pk=manifest.get("target")).first() is None:
        raise guards.MergeError("user_missing")
    counts: Counter = Counter()
    was_active = source.is_active
    user_model.objects.filter(pk=source.pk).update(is_active=True)
    membership_model = _membership_model()
    counts["undo_memberships_restored"] += membership_model.objects.filter(
        pk__in=manifest.get("memberships_deactivated") or [], user=source, is_active=False
    ).update(is_active=True, updated_at=timezone.now())
    kind, temp_pk = _temporary_authority(organization, source)
    shares.restore_updated(manifest, counts)
    _return_rows(manifest, counts)
    shares.reactivate(manifest, counts)
    _end_temporary_authority(kind, temp_pk)
    counts["undo_roles_withdrawn"] += membership_model.objects.filter(
        pk__in=manifest.get("memberships_activated") or [], user_id=manifest["target"], is_active=True
    ).update(is_active=False, updated_at=timezone.now())
    created = membership_model.objects.filter(pk__in=manifest.get("memberships_created") or [],
                                              user_id=manifest["target"])  # fmt: skip
    counts["undo_roles_removed"] += created.count()
    created.delete()  # yalnız bu paketin özünün yaratdığı üzvlük sətirləri — əvvəlki hal tam qayıdır
    user_model.objects.filter(pk=source.pk).update(is_active=was_active)
    source.refresh_from_db()
    profile = getattr(source, "profile", None)
    if manifest.get("blocked") and not source.is_active and profile is not None:
        if profile.block_reason == manifest.get("block_text"):
            unblock_account(source, actor=actor, reason=f"merge_duplicate_teacher undo {batch}")
            counts["undo_unblocked"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"batch": batch, "counts": dict(counts)},
        reason=f"merge_duplicate_teacher undo {batch}",
        resource_type=UNDO_RESOURCE,
        resource_id=batch,
        resource_repr=batch,
    )
    return counts


__all__ = ["UNDO_RESOURCE", "undo"]
