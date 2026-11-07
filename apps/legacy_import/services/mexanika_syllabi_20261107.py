"""Sahib 2026-11-07 (Mexanika və riyaziyyat rəsmi dərs yükü): sillabussuz jurnallar müəllimin ÖZ təsdiqli sillabusuna.

* 2232 K «Robotexnika» (Dürdanə Rüstəmova): 2026-11-07 baxış rejimində «Kopyala» ilə SƏHVƏN açılmış qaralama
  (tək versiya, təqdim edilməyib, mənbə köçürülmüş sillabus olduğu üçün 29%) passivləşir (silinmir), jurnal eyni
  müəllimin 233 K az təsdiqli sillabusuna bağlanır;
* 233 EKO az / 232 eko / 233 EKO ing «Fizika» (Səyyarə Nəbiyeva): 236 K ing-in təsdiqli sillabusuna bağlanır.

Bağlama :func:`apps.syllabus.services.sharing.link_legacy` ilədir — eyni fənn + semestr, jurnalın müəllimi =
dosyenin müəllifi, FILL-ONLY (jurnalın öz dosyesi / başqa paylaşımı varsa keçilir). Id-lər sabitdir. Dərs / xana /
qeydiyyat toxunulmur. Hər yazan icra bir audit qəbzidir (``mxsyl-…``); ``--undo`` qəbz üzrə qaytarır.
"""

from collections import Counter
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.syllabus.public import SyllabusStatus, services

from . import exact_syllabus_recovery as core

RestoreError = core.RestoreError
RESOURCE = "legacy_import.mexanika_syllabi_20261107"
APPLY_REASON = "2026-11-07 Mexanika: sillabussuz jurnallar müəllimin öz təsdiqli sillabusuna bağlandı"
UNDO_REASON = "2026-11-07 Mexanika: sillabus bağlamaları geri qaytarıldı"
ORGANIZATION_ID = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"

#: Səhvən açılmış qaralama: (dosye, versiya, jurnal).
STRAY_DRAFT = (
    "744740e6-198e-4830-ab27-de22f1c7b503",
    "e46be6f3-3674-4a81-9055-e08b8e2ebdd7",
    "6c8e9a56-9867-4581-9ee7-d274b9bf35f5",
)
#: (açar, mənbə dosye, hədəf jurnal).
LINKS = (
    ("rust_2232k", "254a665d-a762-4943-aad5-9bd93b90f5de", "6c8e9a56-9867-4581-9ee7-d274b9bf35f5"),
    ("neb_233eko", "7dcb1e59-7165-454a-a7f8-3c806e3cfb5e", "0127bd1c-a028-4ded-8312-ff25aa357d74"),
    ("neb_232eko", "7dcb1e59-7165-454a-a7f8-3c806e3cfb5e", "8658a369-e696-486b-8c01-6d12857b02f1"),
    ("neb_233ekoing", "7dcb1e59-7165-454a-a7f8-3c806e3cfb5e", "b086a31f-0392-47b2-a638-14936af1e1ff"),
)


def _receipts(org, batch=None):
    logs = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE)
    return logs.filter(resource_id=batch) if batch else logs


def _audit(org, actor, batch, reason, values):
    core.log_action(
        action=core.AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
        reason=reason,
        new_values=values,
    )


def _actor_scope(org, actor):
    if str(org.pk) != ORGANIZATION_ID or not org.is_active or not actor.is_active or not actor.is_superuser:
        raise RestoreError("active_fixed_tenant_superadmin_required")


def _retire_stray_draft(org, counts) -> bool:
    """Qaralama hələ də «toxunulmamış səhv nüsxə»dirsə passivləşdirir; artıq passivdirsə ``False``."""
    syllabus_id, version_id, offering_id = STRAY_DRAFT
    Syllabus = core.model("syllabus.Syllabus")
    syllabus = Syllabus.objects.select_for_update().filter(pk=syllabus_id, organization=org).first()
    if syllabus is None:
        raise RestoreError("stray_draft_missing")
    if not syllabus.is_active:
        counts["stray_draft_already_inactive"] += 1
        return False
    versions = list(syllabus.versions.all())
    if (
        str(syllabus.offering_id) != offering_id
        or [str(v.pk) for v in versions] != [version_id]
        or versions[0].status != SyllabusStatus.DRAFT.value
        or versions[0].submitted_at is not None
    ):
        raise RestoreError("stray_draft_changed")
    syllabus.is_active = False
    syllabus.save(update_fields=["is_active", "updated_at"])
    counts["stray_draft_retired"] += 1
    return True


def _link(org, actor, key, source_id, offering_id, counts):
    Syllabus = core.model("syllabus.Syllabus")
    Offering = core.model("registrar.CourseOffering")
    source = Syllabus.objects.filter(pk=source_id, organization=org, is_active=True).select_related("offering").first()
    offering = Offering.objects.filter(pk=offering_id, organization=org, is_active=True).first()
    if source is None or offering is None or source.approved_version_id is None:
        counts["skipped_scope"] += 1
        return "skipped_scope", None
    result = services.sharing.link_legacy(syllabus=source, offering=offering, user=actor)
    counts[result] += 1
    if result != "linked":
        return result, None
    share = core.model("syllabus.SyllabusShare").objects.get(syllabus=source, offering_id=offering.pk)
    return result, {"key": key, "share": str(share.pk), "syllabus": source_id, "offering": offering_id}


@transaction.atomic
def apply(org, actor):
    """→ ``(counts, results, batch|None)``."""
    _actor_scope(org, actor)
    counts, results, children = Counter(), [], []
    retired = False
    try:
        with transaction.atomic():
            retired = _retire_stray_draft(org, counts)
    except RestoreError as exc:
        counts[f"skipped_{exc}"] += 1
    for key, source_id, offering_id in LINKS:
        with transaction.atomic():
            result, child = _link(org, actor, key, source_id, offering_id, counts)
        results.append((key, result))
        if child is not None:
            children.append(child)
    batch = None
    if children or retired:
        batch = f"mxsyl-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
        _audit(org, actor, batch, APPLY_REASON, {"stray_draft_retired": retired, "children": children})
    return dict(counts), results, batch


@transaction.atomic
def undo(org, actor, batch):
    _actor_scope(org, actor)
    logs = _receipts(org, batch)
    if logs.filter(reason=UNDO_REASON).exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason=APPLY_REASON).first()
    if receipt is None:
        raise RestoreError("undo_batch_missing")
    counts = Counter()
    Share = core.model("syllabus.SyllabusShare")
    for child in receipt.new_values["children"]:
        deleted, _ = Share.objects.filter(
            pk=child["share"], syllabus_id=child["syllabus"], offering_id=child["offering"]
        ).delete()
        counts["shares_removed" if deleted else "share_already_gone"] += 1
    if receipt.new_values.get("stray_draft_retired"):
        syllabus = core.model("syllabus.Syllabus").objects.select_for_update().get(pk=STRAY_DRAFT[0], organization=org)
        if Share.objects.filter(offering_id=STRAY_DRAFT[2]).exists():
            raise RestoreError("undo_offering_shared_again")
        syllabus.is_active = True
        syllabus.save(update_fields=["is_active", "updated_at"])
        counts["stray_draft_restored"] += 1
    _audit(org, actor, batch, UNDO_REASON, {"receipt": str(receipt.pk)})
    return dict(counts)
