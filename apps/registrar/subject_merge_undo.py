"""Fənn birləşdirməsinin GERİ QAYTARILMASI — audit izindən (2026-10-19).

``manage.py undo_subject_merge --audit-id <id>`` (default dry-run). Birləşmə audit qeydinin
``changes`` sahəsi hər köçən sətrin id-sini və əvvəlki fənnini, plandan çıxarılan sətirlərin
tam snapshot-unu, imtahan qrupu əlaqələrini və JSON açarlarını saxlayır; geri qaytarma YALNIZ
həmin izə görə işləyir.

TƏHLÜKƏSİZLİK ŞƏRTLƏRİ (biri pozulsa heç nə yazılmır, səbəblər siyahılanır):
* qeyd birləşmə qeydidir və hələ geri qaytarılmayıb;
* mənbə kartları hələ də «Birləşdirildi → …» səbəbi ilə arxivdədir;
* köçən hər sətir hələ mövcuddur və HƏDƏF fənnə baxır (başqa yerə köçürülməyib/silinməyib);
* plandan çıxarılan sətrin planı hələ qaralama/qaytarılmış statusdadır və həmin yer boşdur;
* JSON prioritetləri birləşmədən sonra dəyişməyib.
Sonra bütün yazı bir tranzaksiyada aparılır; dry-run eyni yazını edib GERİ QAYTARIR (DB
unikallıq qaydaları da real yoxlanır).

MƏHDUDİYYƏT: birləşmədən SONRA hədəf fənn üzrə yaradılan yeni sətirlər (yeni açılış, plan sətri)
hədəfdə qalır — onların hansı karta «aid olduğu» məlum deyil. ``ExamChanceGrant`` heç vaxt
köçmür (dəyişməz tarixçə), ona görə geri qaytarmaya ehtiyac yoxdur.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.audit import log_action
from core.constants import AuditAction

from .models import CurriculumSubject, Subject
from .subject_merge import AUDIT_RESOURCE, AUDIT_UNDO_RESOURCE, CHANGES_VERSION, MergeError, clean_reason
from .subject_merge_apply import (
    allow_offering_subject_change,
    check_deferred_constraints,
    clear_offering_subject_change,
    repoint_rows,
)
from .subject_merge_conflicts import EDITABLE_PLAN_STATUSES
from .subject_merge_inventory import M2M, RELATIONS, relation


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün daxili siqnal."""


def _audit_model():
    return django_apps.get_model("audit", "AuditLog")


def _through():
    rel = next(item for item in RELATIONS if item.strategy == M2M)
    return rel.model()._meta.get_field(rel.field).remote_field.through


def load_entry(audit_id):
    AuditLog = _audit_model()
    try:
        entry = AuditLog.objects.filter(pk=str(audit_id).strip(), resource_type=AUDIT_RESOURCE).first()
    except (TypeError, ValueError):
        entry = None
    if entry is None or not isinstance(entry.changes, dict) or entry.changes.get("kind") != "subject_merge":
        raise MergeError("not_found", "Birləşmə audit qeydi tapılmadı.", status=404)
    if entry.changes.get("version") != CHANGES_VERSION:
        raise MergeError("bad_version", "Audit qeydinin formatı tanınmır.")
    return entry


def _check_sources(changes, issues) -> dict:
    sources = {str(item.pk): item for item in Subject.objects.filter(pk__in=changes["sources"])}
    for source_id, code in zip(changes["sources"], changes["source_codes"], strict=True):
        source = sources.get(source_id)
        if source is None:
            issues.append(f"Mənbə fənn tapılmadı: {code}")
        elif not source.is_archived or source.archived_reason != changes["archive_reason"]:
            issues.append(f"{code}: kart birləşmədən sonra dəyişib (arxivdən çıxarılıb və ya səbəbi dəyişib)")
    return sources


def _check_moved(changes, issues) -> None:
    target_id = changes["target"]
    for key, rows in changes["moved"].items():
        model = relation(key).model()
        attname = model._meta.get_field(relation(key).field).attname
        ids = [pk for pk_list in rows.values() for pk in pk_list]
        current = dict(model._base_manager.filter(pk__in=ids).values_list("pk", attname))
        current = {str(pk): str(value) for pk, value in current.items()}
        missing = [pk for pk in ids if pk not in current]
        elsewhere = [pk for pk in ids if pk in current and current[pk] != target_id]
        if missing:
            issues.append(f"{key}: {len(missing)} sətir artıq yoxdur ({', '.join(missing[:5])})")
        if elsewhere:
            issues.append(
                f"{key}: {len(elsewhere)} sətir hədəf fəndən başqa yerə köçürülüb ({', '.join(elsewhere[:5])})"
            )
    through = _through()
    moved_links = [entry["id"] for entry in changes["m2m"]["move"]]
    if moved_links:
        found = through.objects.filter(pk__in=moved_links, subject_id=target_id).count()
        if found != len(moved_links):
            issues.append("İmtahan qrupu əlaqələri birləşmədən sonra dəyişib")


def _check_plan_rows(changes, issues) -> None:
    for snapshot in changes["deleted_plan_rows"]:
        Curriculum = django_apps.get_model("registrar", "Curriculum")
        plan = Curriculum.objects.filter(pk=snapshot["curriculum_id"]).first()
        if plan is None or plan.status not in EDITABLE_PLAN_STATUSES:
            issues.append(f"Plan sətri bərpa edilə bilmir: plan {snapshot['curriculum_id']} artıq qaralama deyil")
            continue
        taken = CurriculumSubject.objects.filter(
            curriculum_id=snapshot["curriculum_id"],
            subject_id=snapshot["subject_id"],
            semester_number=snapshot["semester_number"],
        ).exists()
        if taken or CurriculumSubject.objects.filter(pk=snapshot["id"]).exists():
            issues.append(f"Plan sətri bərpa edilə bilmir: {snapshot['id']} yeri tutulub")


def _check_json(changes, issues) -> None:
    for ref in changes["json_refs"]:
        model = django_apps.get_model(ref["model"])
        if not model._base_manager.filter(pk=ref["id"], **{ref["field"]: ref["after"]}).exists():
            issues.append(f"{ref['model']} {ref['id']}: prioritetlər birləşmədən sonra dəyişib")


def inspect(entry) -> list:
    """Geri qaytarmanı bloklayan səbəblər (boş siyahı → təhlükəsizdir)."""
    changes = entry.changes
    issues = []
    AuditLog = _audit_model()
    if AuditLog.objects.filter(resource_type=AUDIT_UNDO_RESOURCE, resource_id=str(entry.pk)).exists():
        issues.append("Bu birləşmə artıq geri qaytarılıb")
        return issues
    if not Subject.objects.filter(pk=changes["target"]).exists():
        issues.append("Hədəf fənn tapılmadı")
        return issues
    _check_sources(changes, issues)
    _check_moved(changes, issues)
    _check_plan_rows(changes, issues)
    _check_json(changes, issues)
    return issues


def _restore_plan_rows(snapshots) -> None:
    for snapshot in snapshots:
        values = {}
        for field in CurriculumSubject._meta.concrete_fields:
            if field.attname in snapshot:
                values[field.attname] = field.to_python(snapshot[field.attname])
        CurriculumSubject._base_manager.bulk_create([CurriculumSubject(**values)])
        stamps = {name: parse_datetime(snapshot[name]) for name in ("created_at", "updated_at") if snapshot.get(name)}
        if stamps:
            CurriculumSubject._base_manager.filter(pk=snapshot["id"]).update(**stamps)


def _write(entry, actor, reason) -> None:
    changes = entry.changes
    target_id = changes["target"]
    now = timezone.now()
    for source_id in changes["sources"]:
        # Öz savepoint-i: xətada SET LOCAL icazəsi savepoint ilə sıfırlanır, təmizləmə pozulmuş
        # tranzaksiyada işləmir — əsl DB xətası görünür (review 2026-10-19).
        with transaction.atomic():
            allow_offering_subject_change([target_id], source_id)
            for key, rows in changes["moved"].items():
                ids = rows.get(source_id) or []
                if ids and repoint_rows(relation(key), ids, source_id, now) != len(ids):
                    raise MergeError("drift", "Sətir sayı tutmadı — geri qaytarma dayandırıldı.", status=409)
            clear_offering_subject_change()
    through = _through()
    for link in changes["m2m"]["move"]:
        through.objects.filter(pk=link["id"]).update(subject_id=link["from"])
    for link in changes["m2m"]["drop"]:
        through.objects.get_or_create(studentgroup_id=link["group"], subject_id=link["from"])
    _restore_plan_rows(changes["deleted_plan_rows"])
    for ref in changes["json_refs"]:
        model = django_apps.get_model(ref["model"])
        model._base_manager.filter(pk=ref["id"]).update(**{ref["field"]: ref["before"]})
    for card in (entry.old_values or {}).get("sources", []):
        Subject.objects.filter(pk=card["id"]).update(
            is_archived=card["is_archived"],
            is_active=card["is_active"],
            archived_reason=card["archived_reason"],
            archived_at=parse_datetime(card["archived_at"]) if card.get("archived_at") else None,
            archived_by_id=card.get("archived_by_id"),
            updated_at=now,
        )
    target = Subject.objects.get(pk=target_id)
    log_action(
        action=AuditAction.UPDATE,
        user=actor if getattr(actor, "pk", None) else None,
        organization=entry.organization,
        obj=target,
        resource_type=AUDIT_UNDO_RESOURCE,
        resource_id=str(entry.pk),
        resource_repr=f"undo: {entry.resource_repr}"[:500],
        old_values={"target": target_id},
        new_values={"sources": changes["sources"]},
        changes={"kind": "subject_merge_undo", "merge_audit_id": str(entry.pk), "counts": changes.get("counts", {})},
        reason=reason,
    )


def undo(*, audit_id, actor=None, apply=False, reason="") -> dict:
    """Hesabat: ``{"issues", "counts", "applied", ...}``. ``apply=False`` — yoxlama + geri alınan sınaq yazısı."""
    entry = load_entry(audit_id)
    if apply:
        reason = clean_reason(reason)
    report = {
        "audit_id": str(entry.pk),
        "target": entry.changes.get("target_code"),
        "sources": entry.changes.get("source_codes"),
        "counts": entry.changes.get("counts", {}),
        "issues": [],
        "applied": False,
    }
    with transaction.atomic():
        AuditLog = _audit_model()
        list(AuditLog.objects.select_for_update().filter(pk=entry.pk).values_list("pk", flat=True))
        list(
            Subject.objects.select_for_update()
            .filter(pk__in=[entry.changes["target"], *entry.changes["sources"]])
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        report["issues"] = inspect(entry)
        if report["issues"]:
            return report
        try:
            with transaction.atomic():
                # Gecikdirilmiş qaydalar (``syllabus_reuse_same_org_subject`` DEFERRABLE INITIALLY DEFERRED)
                # hər ifadədə yoxlansın — dry-run da (savepoint geri qaytarılmazdan ƏVVƏL) onları görsün.
                check_deferred_constraints()
                _write(entry, actor, reason or "dry-run")
                check_deferred_constraints()
                if not apply:
                    raise _DryRun
        except _DryRun:
            return report
        except DatabaseError as exc:  # unikallıq/trigger — real DB qaydası pozulur
            report["issues"].append(f"DB qaydası geri qaytarmaya imkan vermir: {exc}".strip()[:500])
            return report
    report["applied"] = True
    return report


__all__ = ["inspect", "load_entry", "undo"]
