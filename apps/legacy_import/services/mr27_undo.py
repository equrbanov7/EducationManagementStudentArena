"""Auditli kompensasiya: immutable kimlik ledger-i saxlanır, əməli təsir geri alınır."""

from collections import Counter

from django.apps import apps

from apps.accounts.public import block_account
from apps.audit.public import log_action
from core.constants import AuditAction
from core.rls import bypass_rls

from .mr27_plan import OFFERING, ORG, RecoveryError
from .mr27_recovery import RESOURCE, audit, fingerprint, model


def _has_untracked_usage(obj, ids):
    """Boolean-only SELECT guard; heç bir məlumat/PK çağırana qaytarılmır."""
    for field in obj._meta.many_to_many:
        if getattr(obj, field.name).exists():
            return True
    for relation in obj._meta.related_objects:
        if relation.many_to_many:
            if getattr(obj, relation.get_accessor_name()).exists():
                return True
            continue
        related = relation.related_model
        query = related._base_manager.filter(**{relation.field.name: obj.pk})
        if query.exclude(pk__in=ids.get(related._meta.label_lower, set())).exists():
            return True
    return False


def undo(org, actor, batch):
    if str(org.pk) != ORG or not actor.is_superuser or not actor.is_active:
        raise RecoveryError("actor_or_tenant_scope")
    model("registrar.CourseOffering").objects.select_for_update().get(pk=OFFERING, organization=org)
    logs = model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE, resource_id=batch)
    if logs.filter(reason="MR-000027 compensating undo").exists():
        return {"already_undone": 1}
    original = logs.filter(reason="MR-000027 source-backed recovery").first()
    if original is None:
        raise RecoveryError("undo_batch_missing")
    manifest = original.new_values
    rows = []
    ids = {}
    for item in manifest["created"]:
        label = item["model"]
        obj = apps.get_model(label).objects.select_for_update().filter(pk=item["id"]).first()
        if obj is None or fingerprint(obj) != item["fingerprint"]:
            raise RecoveryError("undo_row_changed")
        if obj._meta.label_lower == "auth.user" and obj.has_usable_password():
            raise RecoveryError("undo_credential_issued")
        rows.append((obj, item["mode"]))
        ids.setdefault(label, set()).add(str(obj.pk))
    # AuthUser globaldır: yalnız bu paketin ən çox2 yeni istifadəçisi üçün
    # superadmin READ existence probe foreign tenant istifadəsini də görməlidir.
    # Bypass bu pure SELECT helper-dən sonra bağlanır; bütün yazılar tenant-RLS altındadır.
    if len(ids.get("auth.user", set())) > 2:
        raise RecoveryError("undo_manifest_scope")
    for obj, _mode in rows:
        if obj._meta.label_lower == "auth.user":
            with bypass_rls():
                used = _has_untracked_usage(obj, ids)
        else:
            used = _has_untracked_usage(obj, ids)
        if used:
            raise RecoveryError("undo_foreign_usage")
    before = manifest.get("absence_before", [])
    for item in before:
        e = model("registrar.Enrollment").objects.select_for_update().get(pk=item["id"], organization=org)
        if e.absence_hours != item["after"]:
            raise RecoveryError("undo_absence_changed")
    counts = Counter()
    for obj, mode in reversed(rows):
        if mode == "delete":
            log_action(
                action=AuditAction.DELETE,
                user=actor,
                organization=org,
                obj=obj,
                reason=f"MR-000027 undo {batch}",
                changes={"batch": batch},
            )
            obj.delete()
            counts[f"deleted_{obj._meta.model_name}"] += 1
    # User/profile/SAR/Program-a bağlanmış canonical ledger tarixçəsi QƏSDƏN qalır.
    for obj, mode in rows:
        if mode == "delete":
            continue
        label = obj._meta.label_lower
        if label == "auth.user":
            block_account(obj, actor=actor, reason=f"MR-000027 bərpası geri alınıb: {batch}")
            counts["blocked_users"] += 1
        elif label == "organizations.membership":
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
        elif label == "registrar.enrollment":
            obj.status = "dropped"
            obj.save(update_fields=["status", "updated_at"])
            counts["dropped_enrollments"] += 1
        elif label in {
            "registrar.studentacademicrecord",
            "registrar.curriculum",
            "registrar.program",
            "organizations.orgunit",
        }:
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
            counts[f"retired_{obj._meta.model_name}"] += 1
    for item in before:
        model("registrar.Enrollment").objects.filter(pk=item["id"], organization=org).update(
            absence_hours=item["absence_hours"]
        )
    audit(
        org, actor, batch, {"original": str(original.pk), "counts": dict(counts)}, reason="MR-000027 compensating undo"
    )
    return dict(counts)
