"""MR-000537 (2026-11-18): Səkinə Abasovanın iki köçürülmüş sillabusunda «colloquium» cümlələri silinir.

Müəllim: «Sillabusda ümumi görünüş bölməsində "colloquium" sözü yazılan cümlələr silinməlidir.»  Mətn köhnə
sistemdən gələn ``assess`` bölməsinin ``note`` sahəsidir (köhnə bal qaydası — kollokvium / sərbəst iş / 70 bal);
redaktorda bu sahənin inputu yoxdur, müəllim özü silə bilmir.

Yalnız iki sabit versiya (müəllif — 9564, köhnə sistemdən); «colloquium» sözü olan hər cümlə (nöqtəyə qədər)
çıxarılır, qalan mətn toxunulmaz qalır.  Köhnə ``note`` auditdə saxlanılır; ``undo`` onu qaytarır.
"""

from __future__ import annotations

import re
import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.colloquium_note_20261118"
REASON = "MR-000537: müəllimin xahişi ilə sillabusun qiymətləndirmə qeydindən «colloquium» cümlələri silindi"
UNDO_REASON = "MR-000537: qiymətləndirmə qeydinin geri qaytarılması"
AUTHOR_ID = 9564
VERSIONS = (
    "c8961465-5c9f-45f2-8987-795718dd983a",  # a4694393 — 536 T İNG, XDİAK-1 (elementary)
    "748ba736-4f31-4025-b76b-7a40fa2d726f",  # 9a9da58b — 536 T, XDİAK-1 (elementary)
)
ASSESS = "assess"
_SENTENCE = re.compile(r"[^.!?\n]*colloquium[^.!?\n]*[.!?]?[ \t]*", re.IGNORECASE)


def _model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"colloq-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def strip_colloquium(text: str) -> tuple[str, int]:
    """``(yeni mətn, silinən cümlə sayı)`` — «colloquium» olan hər cümlə çıxarılır."""
    cleaned, removed = _SENTENCE.subn("", text or "")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned).strip()
    return cleaned, removed


def run(*, organization, actor, counts: Counter, batch: str, versions=None, author_id=None) -> str:
    batch = batch or new_batch()
    versions = VERSIONS if versions is None else versions
    author_id = AUTHOR_ID if author_id is None else author_id
    SyllabusSection = _model("syllabus", "SyllabusSection")
    with transaction.atomic():
        for version_id in versions:
            row = (
                SyllabusSection.objects.select_for_update()
                .select_related("version__syllabus")
                .filter(organization=organization, version_id=version_id, section_id=ASSESS)
                .first()
            )
            if row is None or row.version.syllabus.author_id != author_id:
                counts["skip_not_found"] += 1
                continue
            data = dict(row.data or {})
            note = data.get("note")
            if not isinstance(note, str) or "colloquium" not in note.lower():
                counts["skip_no_colloquium"] += 1
                continue
            cleaned, removed = strip_colloquium(note)
            data["note"] = cleaned
            row.data = data
            row.revision += 1
            row.save(update_fields=["data", "revision", "updated_at"])
            counts["notes_cleaned"] += 1
            counts["sentences_removed"] += removed
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=str(row.pk),
                resource_repr="Sillabusun qiymətləndirmə qeydi — «colloquium» cümlələri",
                old_values={"note": note},
                new_values={"batch": batch, "version": str(version_id), "removed": removed},
            )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("audit", "AuditLog")
    SyllabusSection = _model("syllabus", "SyllabusSection")
    with transaction.atomic():
        for entry in AuditLog.objects.filter(
            organization=organization, resource_type=RESOURCE, new_values__batch=batch
        ):
            row = SyllabusSection.objects.select_for_update().filter(pk=entry.resource_id).first()
            if row is None:
                counts["undo_missing"] += 1
                continue
            data = dict(row.data or {})
            data["note"] = (entry.old_values or {}).get("note") or ""
            row.data = data
            row.revision += 1
            row.save(update_fields=["data", "revision", "updated_at"])
            counts["undone"] += 1
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=UNDO_REASON,
                resource_type=f"{RESOURCE}.undo",
                resource_id=entry.resource_id,
                resource_repr="Qiymətləndirmə qeydinin geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["RESOURCE", "VERSIONS", "run", "strip_colloquium", "undo"]
