"""Fənn birləşdirməsi — K2/K3 həllərinin YAZISI və GERİ QAYTARILMASI (sahib 2026-11-04).

* **K2** — ləğv olunmuş BOŞ əkiz açılış (``offering_twin``) SİLİNİR. Silməzdən əvvəl tam snapshot audit-ə yazılır:
  açılışın öz sətri + qeydiyyatlar, cədvəl slotları (yumşaq silinmişlər də), qiymətləndirmə sxemi/komponentləri,
  sərbəst iş mövzuları, jurnal payları (+ tələbə siyahısı) və imtahan bağlantıları. İmtahan bağlantısı
  saxlanılan jurnala KEÇİR (ləğv olunmuş/silinmiş jurnala bağlı imtahan qalmır). Geri qaytarma hər sətri EYNİ
  id ilə yaradır, imtahan bağını qaytarır (saxlanılana birləşmədə əlavə olunubsa — çıxarır).
* **K3** — qiymətsiz təkrar qeydiyyat (``enrollment_ungraded``) ``dropped`` olur (SİLİNMİR, xanası varsa qalır);
  əvvəlki status audit-dədir, geri qaytarmada bərpa olunur.

Silinmə anında boşluq kilid altında YENİDƏN yoxlanılır (:func:`.twin_inert.offering_blockers`); dəyişibsə → ``drift``.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .twin_inert import offering_blockers
from .twin_merge_empty import exam_through, repoint_exam_links

#: Snapshot sırası = bərpa sırası (FK asılılığı: açılış → sxem/komponent/mövzu → qeydiyyat → slot → pay).
CHILD_MODELS = (
    "AssessmentScheme",
    "AssessmentComponent",
    "SelfWorkTopic",
    "Enrollment",
    "ScheduleSlot",
    "JournalShare",
)
_STAMPS = ("created_at", "updated_at")


def _model(name: str):
    return django_apps.get_model("registrar", name)


def _share_through():
    return _model("JournalShare")._meta.get_field("enrollments").remote_field.through


def snapshot_offering(offering, keep_id) -> dict:
    from .subject_merge_apply import row_snapshot

    rows = {
        name: [row_snapshot(row) for row in _model(name)._base_manager.filter(offering=offering).order_by("pk")]
        for name in CHILD_MODELS
    }
    share_links = [
        {"share": str(share), "enrollment": str(enrollment)}
        for share, enrollment in _share_through()
        .objects.filter(journalshare__offering=offering)
        .values_list("journalshare_id", "enrollment_id")
        .order_by("journalshare_id", "enrollment_id")
    ]
    return {
        "offering": row_snapshot(offering),
        "keep": str(keep_id),
        "rows": rows,
        "share_links": share_links,
    }


def delete_twins(plan, drift) -> list:
    """K2: planın boş əkizlərini snapshot-la sil. Qaytarır: snapshot-lar (audit üçün)."""

    CourseOffering = _model("CourseOffering")
    ids = plan.get("deleted_offerings") or []
    if not ids:
        return []
    rows = list(CourseOffering._base_manager.select_for_update(of=("self",)).filter(pk__in=ids).order_by("pk"))
    if len(rows) != len(ids):
        raise drift()
    snapshots = []
    for offering in rows:
        if offering.is_active or offering_blockers(offering):
            raise drift()
        snapshot = snapshot_offering(offering, plan["twin_keep"][str(offering.pk)])
        snapshot["exam_links"] = repoint_exam_links(offering.pk, snapshot["keep"])
        CourseOffering._base_manager.filter(pk=offering.pk).delete()
        snapshots.append(snapshot)
    return snapshots


def drop_enrollments(plan, drift) -> list:
    """K3: qiymətsiz təkrar qeydiyyatları ``dropped`` et. Qaytarır: ``[{"id", "status"}]``."""

    Enrollment = _model("Enrollment")
    ids = plan.get("dropped_enrollments") or []
    if not ids:
        return []
    rows = list(Enrollment._base_manager.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(rows) != len(ids) or any(row.status == Enrollment.Status.DROPPED for row in rows):
        raise drift()
    Enrollment._base_manager.filter(pk__in=ids).update(status=Enrollment.Status.DROPPED, updated_at=timezone.now())
    return [{"id": str(row.pk), "status": row.status} for row in rows]


# ── Geri qaytarma ─────────────────────────────────────────────────────────


def _restore_rows(model, snapshots) -> None:
    if not snapshots:
        return
    objects = []
    for snapshot in snapshots:
        values = {
            field.attname: field.to_python(snapshot[field.attname])
            for field in model._meta.concrete_fields
            if field.attname in snapshot
        }
        objects.append(model(**values))
    model._base_manager.bulk_create(objects)
    for snapshot in snapshots:  # bulk_create auto_now(_add) sahələrini «indi» edir — köhnə vaxtlar qaytarılır
        stamps = {name: parse_datetime(snapshot[name]) for name in _STAMPS if snapshot.get(name)}
        if stamps:
            model._base_manager.filter(pk=snapshot["id"]).update(**stamps)


def check_twins(changes, issues) -> None:
    CourseOffering, Enrollment = _model("CourseOffering"), _model("Enrollment")
    for snapshot in changes.get("deleted_offerings", []):
        if CourseOffering._base_manager.filter(pk=snapshot["offering"]["id"]).exists():
            issues.append(f"Silinmiş boş əkiz jurnal bərpa edilə bilmir: {snapshot['offering']['id']} artıq var")
    ids = [item["id"] for item in changes.get("dropped_enrollments", [])]
    still = Enrollment._base_manager.filter(pk__in=ids, status=Enrollment.Status.DROPPED).count()
    if still != len(ids):
        issues.append("Bağlanmış təkrar qeydiyyatlar birləşmədən sonra dəyişib")


def restore_twins(changes) -> None:
    """K2 + K3 geri qaytarma (``_write``-ın sonunda — fənn kartları artıq bərpa olunub)."""

    Enrollment = _model("Enrollment")
    for item in changes.get("dropped_enrollments", []):
        Enrollment._base_manager.filter(pk=item["id"]).update(status=item["status"], updated_at=timezone.now())
    through = exam_through()
    for snapshot in changes.get("deleted_offerings", []):
        _restore_rows(_model("CourseOffering"), [snapshot["offering"]])
        for name in CHILD_MODELS:
            _restore_rows(_model(name), snapshot["rows"].get(name, []))
        _share_through().objects.bulk_create(
            [
                _share_through()(journalshare_id=link["share"], enrollment_id=link["enrollment"])
                for link in snapshot.get("share_links", [])
            ]
        )
        twin_id = snapshot["offering"]["id"]
        for link in snapshot.get("exam_links", []):
            if link["target_added"]:
                through.objects.filter(exam_id=link["exam"], courseoffering_id=snapshot["keep"]).delete()
            through.objects.get_or_create(exam_id=link["exam"], courseoffering_id=twin_id)


__all__ = ["CHILD_MODELS", "check_twins", "delete_twins", "drop_enrollments", "restore_twins", "snapshot_offering"]
