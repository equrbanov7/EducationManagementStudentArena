"""RİM müraciətləri 2026-11-19: iki sillabus bağı düzəlişi (sabit id-lər; ``fix_syllabus_links_20261119``).

* **MR-000562** (Eynulla Baxşəliyev): 7 sillabusun kafedrası «Tarix» göstərilir — müəllim iki kafedranın üzvüdür,
  qrupu ixtisasa bağlı olmayan dosyelər yaradılarkən birinci üzvlük (Tarix) götürülüb. Dərs yükündə bu fənlər
  Fəlsəfə kafedrasındadır → ``chair_unit`` = Fəlsəfə kafedrası.
* **MR-000550** (Albina Qasımova): 236 YDK «Ümumi xarici dil» (QKU-2693) jurnalının dosyesi köhnə fənnə (QKU-2577
  «VoİP sistemlərinin təhlükəsizliyi») bağlı qalıb — jurnal «sillabus yoxdur» deyir, «Sillabus yarat» isə həmin
  səhv dosyeni açır. Dosyenin ``subject``-i jurnalın fənninə, kafedrası fənnin kafedrasına çəkilir
  (``legacy_import`` delta ``collisions`` ilə eyni addım).

Hər yazıdan əvvəl gözlənilən vəziyyət yoxlanır (uyğun gəlməsə ``skip_*`` sayılır, toxunulmur); köhnə dəyərlər
auditdə saxlanılır, ``undo`` onları qaytarır. Başqa dosye bu dosyeni təkrar istifadə edirsə (``reused_from``) fənn
dəyişmir — kompozit açar pozulmasın.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.syllabus_links_20261119"
UNDO_RESOURCE = f"{RESOURCE}.undo"
CHAIR_REASON = "MR-000562: sillabusun kafedrası dərs yükünə uyğun (Fəlsəfə kafedrası)"
SUBJECT_REASON = "MR-000550: sillabus jurnalın fənninə bağlandı (köhnə fənn bağı qalmışdı)"
UNDO_REASON = "MR-000550/562: sillabus bağının geri qaytarılması"

#: MR-000562 — Fəlsəfə kafedrası.
PHILOSOPHY_CHAIR = "c9734ad2-c397-4c03-ab70-16a4cd7419ed"
CHAIR_SYLLABI = (
    "d529085b-5926-4bf5-9738-95f09f3d18ee",
    "cf121559-3f80-432b-99df-983561ca8553",
    "a725f125-dc6a-4d2e-b23e-c56a5c9ea842",
    "48a2f401-2072-4143-8b7a-088df403f582",
    "b4bab847-32ea-4e07-bc8d-b341f98e188e",
    "228354a5-9204-4899-9b03-f897319a9bb4",
    "2074e92b-2bee-427f-a18b-36dece27c18e",
)
#: MR-000550 — (dosye, gözlənilən jurnal, dosyenin hazırkı səhv fənn kodu).
SUBJECT_FIXES = (("637be7e0-1a0f-4c71-800d-1b369a7c3c90", "e41172b8-934c-4070-870e-169bde5faedd", "QKU-2577"),)
CHAIR_TYPES = ("chair", "department")


def _model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"sylink-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _log(*, actor, organization, reason, syllabus, old, new, batch, kind):
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=reason,
        resource_type=RESOURCE,
        resource_id=str(syllabus.pk),
        resource_repr=f"Sillabus bağı — {kind}",
        old_values=old,
        new_values={**new, "batch": batch, "kind": kind},
    )


def _fix_chairs(*, organization, actor, counts, batch, syllabi, chair_id):
    Syllabus = _model("syllabus", "Syllabus")
    chair = (
        _model("organizations", "OrgUnit")
        .objects.filter(organization=organization, pk=chair_id, unit_type__in=CHAIR_TYPES)
        .first()
    )
    if chair is None:
        counts["skip_chair_unknown"] += 1
        return
    for syllabus in Syllabus.objects.select_for_update().filter(organization=organization, pk__in=syllabi):
        if syllabus.chair_unit_id == chair.pk:
            counts["chair_already"] += 1
            continue
        old = {"chair_unit": str(syllabus.chair_unit_id or "")}
        Syllabus.objects.filter(pk=syllabus.pk).update(chair_unit=chair, updated_at=timezone.now())
        _log(
            actor=actor,
            organization=organization,
            reason=CHAIR_REASON,
            syllabus=syllabus,
            old=old,
            new={"chair_unit": str(chair.pk)},
            batch=batch,
            kind="chair",
        )
        counts["chair_fixed"] += 1
    counts["chair_missing"] += (
        len(set(syllabi)) - Syllabus.objects.filter(organization=organization, pk__in=syllabi).count()
    )


def _fix_subjects(*, organization, actor, counts, batch, fixes):
    Syllabus = _model("syllabus", "Syllabus")
    for syllabus_id, offering_id, wrong_code in fixes:
        syllabus = (
            Syllabus.objects.select_for_update(of=("self",))
            .select_related("subject", "offering__subject")
            .filter(organization=organization, pk=syllabus_id)
            .first()
        )
        if syllabus is None or str(syllabus.offering_id or "") != offering_id:
            counts["skip_subject_not_bound"] += 1
            continue
        target = syllabus.offering.subject
        if syllabus.subject_id == target.pk:
            counts["subject_already"] += 1
            continue
        if syllabus.subject.code != wrong_code:
            counts["skip_subject_unexpected"] += 1
            continue
        if syllabus.reused_from_id or Syllabus.objects.filter(reused_from_id=syllabus.pk).exists():
            counts["skip_subject_reused"] += 1
            continue
        old = {"subject": str(syllabus.subject_id), "chair_unit": str(syllabus.chair_unit_id or "")}
        new_chair = target.chair_unit_id or syllabus.chair_unit_id
        Syllabus.objects.filter(pk=syllabus.pk).update(
            subject=target, chair_unit_id=new_chair, updated_at=timezone.now()
        )
        _log(
            actor=actor,
            organization=organization,
            reason=SUBJECT_REASON,
            syllabus=syllabus,
            old=old,
            new={"subject": str(target.pk), "chair_unit": str(new_chair or "")},
            batch=batch,
            kind="subject",
        )
        counts["subject_fixed"] += 1


def run(*, organization, actor, counts: Counter, batch: str = "", chair_syllabi=None, chair_id=None, fixes=None) -> str:
    batch = batch or new_batch()
    with transaction.atomic():
        _fix_chairs(
            organization=organization,
            actor=actor,
            counts=counts,
            batch=batch,
            syllabi=CHAIR_SYLLABI if chair_syllabi is None else chair_syllabi,
            chair_id=PHILOSOPHY_CHAIR if chair_id is None else chair_id,
        )
        _fix_subjects(
            organization=organization,
            actor=actor,
            counts=counts,
            batch=batch,
            fixes=SUBJECT_FIXES if fixes is None else fixes,
        )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("audit", "AuditLog")
    Syllabus = _model("syllabus", "Syllabus")
    with transaction.atomic():
        for entry in AuditLog.objects.filter(
            organization=organization, resource_type=RESOURCE, new_values__batch=batch
        ).order_by("-created_at"):
            old = entry.old_values or {}
            values = {"chair_unit_id": old.get("chair_unit") or None, "updated_at": timezone.now()}
            if "subject" in old:
                values["subject_id"] = old["subject"]
            if not Syllabus.objects.filter(organization=organization, pk=entry.resource_id).update(**values):
                counts["undo_missing"] += 1
                continue
            counts["undone"] += 1
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=UNDO_REASON,
                resource_type=UNDO_RESOURCE,
                resource_id=entry.resource_id,
                resource_repr="Sillabus bağının geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["CHAIR_SYLLABI", "PHILOSOPHY_CHAIR", "RESOURCE", "SUBJECT_FIXES", "run", "undo"]
