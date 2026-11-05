"""Boş əkiz birləşməsinin (:mod:`.twin_merge_empty`) jurnalın özünə geri qaytarılması — sahib 2026-11-05 (MR-161).

Hal: boş əkiz E (DÜZGÜN fənn kartı, rəsmi baxılmış yük sətrinin jurnalı) datalı jurnala D (SƏHV fənn kartı) birləşib,
E ləğv olunub. Sonra məlum olur ki, data D-də deyil, E-də (düzgün fənndə) qalmalıdır. D-nin fənnini yerində dəyişmək
(``fix_offering_subject``) mümkün deyil: ləğv olunmuş E unikal açarı (fənn, dövr, qrup) tutur, E-ni silmək isə
geri qaytarılmaz itki olardı. Ona görə E boş birləşmənin ``changes.manifest``-i ilə DƏQİQ bərpa olunur, sonra data
adi qaydalarla D → E köçür (:mod:`.twin_merge_scored`).

Bərpa (yalnız manifestdəki sətirlər, kilid altında):

* E ``is_active=True``;
* manifestdə ``dropped`` edilmiş E qeydiyyatları yenidən ``enrolled`` — YALNIZ tələbə D-də hələ ``enrolled``-dirsə
  (aradakı siyahı qərarı əzilmir; qalanlar ``restore_enrollment_skipped``); sonradan dəyişmiş sətir sayılır;
* cədvəl: E-nin manifestdə yumşaq silinmiş slotları silinmiş QALIR — D-yə köçmüş və D-nin öz canlı slotları
  birləşmədə E-yə keçir (E-də canlı slot yoxdur); imtahan bağları birləşmədə D → E qayıdır;
* pay köçürülübsə (``move_shares``) bərpa avtomatik deyil → dayanır (``restore_shares_moved``).

İdempotentdir: E artıq aktivdirsə heç nə yazılmır (``restore_already_active``).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge_empty import KIND as EMPTY_KIND

KIND = "twin_merge_empty_restore"
REASON = "Boş əkiz birləşməsinin geri qaytarılması: data düzgün fənnin jurnalına köçəcək — sahib 2026-11-05 (MR-161)"


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def empty_merge_manifest(organization, twin_id, keep_id):
    """Boş birləşmənin audit manifesti (E sətrindəki ən son ``twin_merge_empty``) və ya ``None``."""

    rows = (
        _model("AuditLog", "audit")
        .objects.filter(organization=organization, object_id=str(twin_id), changes__kind=EMPTY_KIND)
        .order_by("-created_at")
        .values_list("changes", flat=True)
    )
    for changes in rows[:1]:
        manifest = (changes or {}).get("manifest") or {}
        if manifest.get("source") == str(twin_id) and manifest.get("target") == str(keep_id):
            return manifest
    return None


def restore_empty_merge(*, organization, actor, counts, twin_id, keep_id) -> bool:
    """E-ni (``twin_id``) bərpa et. ``True`` — davam etmək olar (bərpa olundu və ya artıq aktivdir)."""

    CourseOffering, Enrollment = _model("CourseOffering"), _model("Enrollment")
    rows = {
        str(row.pk): row
        for row in CourseOffering.objects.select_for_update(of=("self",)).filter(
            organization=organization, pk__in=[twin_id, keep_id]
        )
    }
    twin, keep = rows.get(str(twin_id)), rows.get(str(keep_id))
    if twin is None or keep is None:
        counts["restore_pair_missing"] += 1
        return False
    if twin.is_active:
        counts["restore_already_active"] += 1
        return True
    if not keep.is_active:
        counts["restore_keep_inactive"] += 1
        return False
    manifest = empty_merge_manifest(organization, twin.pk, keep.pk)
    if manifest is None:
        counts["restore_manifest_missing"] += 1
        return False
    if any(entry.get("action") == "moved" for entry in manifest.get("shares") or []):
        counts["restore_shares_moved"] += 1
        return False
    active = set(Enrollment.objects.filter(offering=keep, status="enrolled").values_list("student_id", flat=True))
    restored, skipped = [], []
    ids = manifest.get("source_enrollments_dropped") or []
    for row in Enrollment.objects.select_for_update().filter(offering=twin, pk__in=ids).order_by("pk"):
        if row.status != "dropped":
            counts["restore_enrollment_changed"] += 1
        elif row.student_id not in active:
            skipped.append(str(row.pk))
        else:
            restored.append(str(row.pk))
    Enrollment.objects.filter(pk__in=restored).update(status="enrolled", updated_at=timezone.now())
    twin.is_active = True
    twin.save(update_fields=["is_active", "updated_at"])
    counts["restore_enrollments"] += len(restored)
    counts["restore_enrollment_skipped"] += len(skipped)
    counts["offerings_restored"] += 1
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=twin,
        reason=f"registrar: twin offering restore — {REASON}",
        old_values={"is_active": False},
        new_values={"is_active": True, "enrollments_restored": len(restored), "keep": str(keep.pk)},
        changes={"kind": KIND, "restored_enrollments": restored, "skipped_enrollments": skipped},
    )
    return True


__all__ = ["KIND", "empty_merge_manifest", "restore_empty_merge"]
