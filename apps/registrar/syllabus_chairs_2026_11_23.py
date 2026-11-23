"""MR-000681 (2026-11-23): sillabusun kafedrası jurnalın DƏRS YÜKÜ kafedrasına (``fix_syllabus_chairs_20261123``).

Nərmin Heydərovanın təsdiqlənmiş «Avropa fəlsəfəsi» (134 F) və «Multikulturalizmə giriş» (334F1/F2) sillabuslarında
kafedra «Tarix» görünürdü, halbuki dərs yükü Fəlsəfə kafedrasının tapşırığındadır. Səbəb MR-000562/579 ilə eynidir:
köhnə sistemdən köçürülmüş dosyelərdə kafedra müəllifin İLK üzvlüyündən götürülüb (Fəlsəfə + Tarix üzvü olan müəllim
→ Tarix). Yeni dosyelər artıq yükün kafedrasını götürür (``api._official_chair``); bu modul MÖVCUD sətirləri düzəldir.

Qayda (uydurma bağ yaradılmır):

* yalnız AKTİV, CARİ semestrin jurnalına (``offering``) bağlı dosye (köhnə semestrlərdə yük yoxdur — kafedra
  fənn kartından gələrdi, bu sübut deyil);
* jurnalın rəsmi kafedrası (:func:`offering_chairs.official_offering_chairs` — dərs yükü sətri, yoxdursa fənnin
  aparıcı kafedrası) TAM BİRDİRSƏ və kafedra tiplidirsə;
* dosyenin ``chair_unit``-i ondan fərqlidirsə → həmin kafedra. Bir neçə kafedra / heç biri — toxunulmur.

Köhnə dəyər auditdə saxlanılır (``batch``); ``undo`` onu qaytarır. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.syllabus_chairs_20261123"
UNDO_RESOURCE = f"{RESOURCE}.undo"
REASON = "MR-000681: sillabusun kafedrası jurnalın dərs yükü kafedrasına uyğunlaşdırıldı"
UNDO_REASON = "MR-000681: sillabus kafedrasının geri qaytarılması"
CHAIR_TYPES = ("chair", "department")


def _model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"sychair-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def plan(organization) -> list[tuple]:
    """``[(syllabus_id, köhnə_kafedra_id | None, yeni_kafedra_id)]`` — yazmır."""
    from .offering_chairs import official_offering_chairs

    Syllabus = _model("syllabus", "Syllabus")
    rows = list(
        Syllabus.objects.filter(
            organization=organization, is_active=True, offering__isnull=False, offering__period__is_current=True
        ).values_list("pk", "offering_id", "chair_unit_id")
    )
    if not rows:
        return []
    offerings = _model("registrar", "CourseOffering").objects.filter(pk__in={offering for _pk, offering, _c in rows})
    chairs = official_offering_chairs(offerings, organization.pk)
    candidates = {next(iter(found)) for found in chairs.values() if len(found) == 1}
    valid = {
        str(pk)
        for pk in _model("organizations", "OrgUnit")
        .objects.filter(organization=organization, pk__in=candidates, unit_type__in=CHAIR_TYPES)
        .values_list("pk", flat=True)
    }
    out = []
    for pk, offering_id, chair_id in rows:
        found = chairs.get(offering_id) or ()
        if len(found) != 1:
            continue
        target = str(next(iter(found)))
        if target in valid and target != str(chair_id or ""):
            out.append((pk, chair_id, target))
    return out


def run(*, organization, actor, counts: Counter, batch: str = "") -> str:
    """Yazır; dry-run-u çağıran tranzaksiyanı geri qaytarmaqla edir (``run_plan``)."""
    batch = batch or new_batch()
    Syllabus = _model("syllabus", "Syllabus")
    changes = plan(organization)
    counts["candidates"] += len(changes)
    with transaction.atomic():
        for syllabus_id, old_chair, new_chair in changes:
            updated = Syllabus.objects.filter(
                organization=organization, pk=syllabus_id, chair_unit_id=old_chair
            ).update(chair_unit_id=new_chair, updated_at=timezone.now())
            if not updated:
                counts["skip_changed"] += 1
                continue
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=str(syllabus_id),
                resource_repr="Sillabusun kafedrası",
                old_values={"chair_unit": str(old_chair or "")},
                new_values={"chair_unit": new_chair, "batch": batch},
            )
            counts["chair_fixed"] += 1
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("audit", "AuditLog")
    Syllabus = _model("syllabus", "Syllabus")
    with transaction.atomic():
        for entry in AuditLog.objects.filter(
            organization=organization, resource_type=RESOURCE, new_values__batch=batch
        ).order_by("-created_at"):
            old = (entry.old_values or {}).get("chair_unit") or None
            if not Syllabus.objects.filter(organization=organization, pk=entry.resource_id).update(
                chair_unit_id=old, updated_at=timezone.now()
            ):
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
                resource_repr="Sillabus kafedrasının geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["RESOURCE", "plan", "run", "undo"]
