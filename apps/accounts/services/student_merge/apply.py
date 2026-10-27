"""Tələbə dublikatının əsas hesaba BİRLƏŞDİRİLMƏSİ və geri qaytarılması (RİM MR-000030.2, 2026-10-27).

Hər cüt (``plan.check_pair`` keçibsə) öz savepoint-ində:

1. **qeydiyyatlar** (bütün dövrlər) — dublikatın hər qeydiyyatı üçün:
   * əsas hesabın EYNİ açılışda qeydiyyatı var → xanalar (``LessonMark``) və komponent balları (``ComponentScore``)
     ona daşınır — YALNIZ BOŞ hədəfə (eyni dəyər → mənbə sətri silinir; fərqli dəyər → toxunulmur, ``*_conflict``);
     dublikat qeydiyyatın üzv olduğu bölünmüş jurnal payına əsas qeydiyyat əlavə olunur; dublikat qeydiyyatda başqa
     data qalmayıbsa ``enrolled`` → ``dropped``;
   * əsas hesabın həmin fənn + dövrdə BAŞQA açılışda qeydiyyatı var → datasız dublikat qeydiyyat ``dropped``,
     datalı saxlanılır (``enrollment_other_offering_kept`` — sahibin qərarı);
   * əsas hesabın həmin fənn + dövrdə qeydiyyatı yoxdur → qeydiyyatın özü əsas hesaba keçir (əvəzləmə zənciri
     yoxdursa);
2. **imtahan cəhdləri** — əsas hesabın həmin imtahanda cəhdi yoxdursa cəhd ona keçir, varsa toxunulmur;
3. qayıb saatı hər iki tərəfdə yenidən hesablanır;
4. **hesab** — dublikatın aktiv üzvlükləri ``is_active=False``, hesab «Hesabı dayandır» ilə dondurulur (səbəb
   «Digər — Dublikat tələbə hesabı — əsas hesab: …»). Tələbə qeydi (``StudentAcademicRecord``) dəyişmir.

Xananın / balın id-si, statusu, balı, ``entered_by`` və ``created_at``-ı saxlanılır (dərs/qeydiyyat dəyişməz olduğundan
köhnə sətir silinib eyni id ilə yenidən yazılır). Paketin manifesti BİR audit sətrindədir
(``accounts.student_merge_batch``); ``undo`` hələ də paketin vəziyyətində qalanı geri qaytarır.
"""

from __future__ import annotations

import secrets
from collections import Counter
from decimal import Decimal

from django.apps import apps as django_apps
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.audit import log_action
from core.constants import AuditAction

from .. import account_block_reasons as block_reasons
from ..account_deletion import block_account, unblock_account
from . import plan as plan_service

BATCH_RESOURCE = "accounts.student_merge_batch"
BLOCK_REASON_CODE = "other"
BLOCK_CONTACT_CODE = "rim"
#: Qeydiyyatda «data» sayılan sətirlər — biri qalırsa dublikat qeydiyyat çıxarılmır.
DATA_MODELS = (
    "LessonMark",
    "ComponentScore",
    "CriterionScore",
    "FinalGrade",
    "ResitRecord",
    "CourseWork",
    "SelfWorkMark",
    "ExamScoreEntry",
    "LegacyGradeFact",
    "ExternalCreditRecognition",
    "RetakeApplication",
)
SHOWN = (
    "pairs_in_file",
    "pairs_merged",
    "pairs_skipped",
    "marks_moved",
    "marks_same_removed",
    "marks_conflict",
    "scores_moved",
    "scores_same_removed",
    "scores_conflict",
    "enrollments_dropped",
    "enrollments_moved",
    "enrollments_kept_has_data",
    "enrollment_other_offering_kept",
    "enrollment_kept_supersession",
    "share_links_added",
    "attempts_moved",
    "attempts_conflict",
    "memberships_deactivated",
    "accounts_blocked",
)


def new_batch() -> str:
    return f"stmerge-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _model(name):
    return django_apps.get_model("registrar", name)


def block_text(keep_username: str) -> str:
    return block_reasons.audit_text(BLOCK_REASON_CODE, "", f"Dublikat tələbə hesabı — əsas hesab: {keep_username}")[
        :300
    ]


def _same(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return Decimal(left) == Decimal(right)


def _restore_created_at(table: str, pairs) -> None:
    """``auto_now_add`` yeni vaxt yazır — köhnə sətrin yaranma vaxtı (kilid pəncərəsi ondan sayılır) qaytarılır."""
    if not pairs:
        return
    with connection.cursor() as cursor:
        for start in range(0, len(pairs), 500):
            part = pairs[start : start + 500]
            values = ", ".join(["(%s::uuid, %s::timestamptz)"] * len(part))
            cursor.execute(
                f"UPDATE {table} t SET created_at = v.created FROM (VALUES {values}) AS v(id, created) WHERE t.id = v.id",
                [value for pk, created in part for value in (str(pk), created)],
            )


def _rehome(model, rows, key_field: str, value_fields, target_enrollment_id, entry: list, counts: Counter, prefix: str):
    """``rows`` (dublikat qeydiyyatın sətirləri) → hədəf qeydiyyat; yalnız boş hədəfə, eyni id ilə."""
    if not rows:
        return
    existing = {
        getattr(row, key_field): row
        for row in model.objects.filter(
            enrollment_id=target_enrollment_id, **{f"{key_field}__in": [getattr(row, key_field) for row in rows]}
        )
    }
    moving, removing = [], []
    for row in rows:
        target = existing.get(getattr(row, key_field))
        if target is None:
            moving.append(row)
        elif all(
            _same(getattr(target, f), getattr(row, f)) if f == "score" else getattr(target, f) == getattr(row, f)
            for f in value_fields
        ):
            removing.append(row)
        else:
            counts[f"{prefix}_conflict"] += 1
    if not moving and not removing:
        return
    for row in moving + removing:
        entry.append(
            {
                "model": model.__name__,
                "id": str(row.pk),
                "key": str(getattr(row, key_field)),
                "from": str(row.enrollment_id),
                "to": str(target_enrollment_id),
                "moved": row in moving,
                "values": {f: (None if getattr(row, f) is None else str(getattr(row, f))) for f in value_fields},
                "entered_by": row.entered_by_id,
                "created_at": row.created_at.isoformat(),
            }
        )
    stamps = [(row.pk, row.created_at) for row in moving]
    model.objects.filter(pk__in=[row.pk for row in moving + removing]).delete()
    for row in moving:
        row.enrollment_id = target_enrollment_id
        row._state.adding = True
    model.objects.bulk_create(moving, batch_size=500)
    _restore_created_at(model._meta.db_table, stamps)
    counts[f"{prefix}_moved"] += len(moving)
    counts[f"{prefix}_same_removed"] += len(removing)


def _has_data(enrollment_id) -> bool:
    return any(_model(name).objects.filter(enrollment_id=enrollment_id).exists() for name in DATA_MODELS)


def _merge_enrollments(organization, duplicate, keep, manifest: dict, counts: Counter, touched: set) -> None:
    enrollment_model = _model("Enrollment")
    share_model = _model("JournalShare")
    own = list(enrollment_model.objects.filter(organization=organization, student=duplicate).select_related("offering"))
    keep_rows = list(
        enrollment_model.objects.filter(organization=organization, student=keep).select_related("offering")
    )
    by_offering = {row.offering_id: row for row in keep_rows}
    by_subject = {(row.offering.subject_id, row.offering.period_id) for row in keep_rows}
    superseded_targets = set(
        enrollment_model.objects.filter(superseded_by__in=[row.pk for row in own]).values_list(
            "superseded_by_id", flat=True
        )
    )
    for enrollment in own:
        target = by_offering.get(enrollment.offering_id)
        if target is not None:
            marks = list(_model("LessonMark").objects.filter(enrollment=enrollment).select_for_update(of=("self",)))
            _rehome(
                _model("LessonMark"),
                marks,
                "lesson_id",
                ("status", "score"),
                target.pk,
                manifest["rows"],
                counts,
                "marks",
            )
            scores = list(
                _model("ComponentScore").objects.filter(enrollment=enrollment).select_for_update(of=("self",))
            )
            _rehome(
                _model("ComponentScore"),
                scores,
                "component_id",
                ("score",),
                target.pk,
                manifest["rows"],
                counts,
                "scores",
            )
            for share in share_model.objects.filter(enrollments=enrollment).exclude(enrollments=target):
                share.enrollments.add(target)
                manifest["share_links"].append({"share": str(share.pk), "enrollment": str(target.pk)})
                counts["share_links_added"] += 1
            touched |= {enrollment.pk, target.pk}
            _drop_if_empty(enrollment, manifest, counts, "enrollments_kept_has_data")
        elif (enrollment.offering.subject_id, enrollment.offering.period_id) in by_subject:
            _drop_if_empty(enrollment, manifest, counts, "enrollment_other_offering_kept")
        elif enrollment.superseded_by_id or enrollment.pk in superseded_targets:
            counts["enrollment_kept_supersession"] += 1
        else:
            enrollment_model.objects.filter(pk=enrollment.pk).update(student_id=keep.pk, updated_at=timezone.now())
            manifest["moved_enrollments"].append(str(enrollment.pk))
            counts["enrollments_moved"] += 1
            touched.add(enrollment.pk)


def _drop_if_empty(enrollment, manifest, counts, kept_key) -> None:
    if _has_data(enrollment.pk):
        counts[kept_key] += 1
        return
    if enrollment.status == "enrolled":
        _model("Enrollment").objects.filter(pk=enrollment.pk).update(status="dropped", updated_at=timezone.now())
        manifest["dropped"].append(str(enrollment.pk))
        counts["enrollments_dropped"] += 1


def _merge_attempts(duplicate, keep, manifest, counts) -> None:
    attempt_model = django_apps.get_model("exams", "ExamAttempt")
    taken = set(attempt_model.objects.filter(user=keep).values_list("exam_id", flat=True))
    for attempt in attempt_model.objects.filter(user=duplicate).select_for_update(of=("self",)):
        if attempt.exam_id in taken:
            counts["attempts_conflict"] += 1
            continue
        attempt_model.objects.filter(pk=attempt.pk).update(user_id=keep.pk)
        manifest["attempts"].append(attempt.pk)
        counts["attempts_moved"] += 1


def _freeze(organization, duplicate, keep, *, actor, manifest, counts) -> None:
    membership_model = django_apps.get_model("organizations", "Membership")
    for membership in membership_model.objects.filter(organization=organization, user=duplicate, is_active=True):
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        manifest["memberships"].append(str(membership.pk))
        counts["memberships_deactivated"] += 1
    if duplicate.is_active:
        text = block_text(keep.username)
        block_account(
            duplicate,
            actor=actor,
            reason=text,
            reason_code=BLOCK_REASON_CODE,
            contact_code=BLOCK_CONTACT_CODE,
            contact_note=f"Əsas hesabınızla daxil olun: {keep.username}."[:200],
        )
        manifest["blocked"], manifest["block_text"] = True, text
        counts["accounts_blocked"] += 1


def execute(organization, pairs, *, actor, batch: str) -> Counter:
    """Planın cütlərini tətbiq et (çağıranın tranzaksiyasında). Saylar qaytarılır."""
    from apps.registrar.public import gradebook

    counts: Counter = Counter({"pairs_in_file": len(pairs)})
    created = plan_service.delta_created_ids(organization)
    people = plan_service.users({pk for pair in pairs for pk in pair})
    manifests = []
    for duplicate_id, keep_id in pairs:
        duplicate, keep = people.get(duplicate_id), people.get(keep_id)
        verdict = plan_service.check_pair(organization, duplicate, keep, created=created)
        if verdict:
            counts["pairs_skipped"] += 1
            counts[f"skip_{verdict}"] += 1
            continue
        manifest = {"duplicate": duplicate.pk, "keep": keep.pk, "rows": [], "share_links": [], "dropped": [],
                    "moved_enrollments": [], "attempts": [], "memberships": [], "blocked": False, "block_text": ""}  # fmt: skip
        touched: set = set()
        with transaction.atomic():
            _merge_enrollments(organization, duplicate, keep, manifest, counts, touched)
            _merge_attempts(duplicate, keep, manifest, counts)
            if touched:
                gradebook.recompute_absence_hours_many(list(_model("Enrollment").objects.filter(pk__in=touched)))
            _freeze(organization, duplicate, keep, actor=actor, manifest=manifest, counts=counts)
        changed = any(
            manifest[key]
            for key in ("rows", "share_links", "dropped", "moved_enrollments", "attempts", "memberships", "blocked")
        )
        if changed:
            manifests.append(manifest)
            counts["pairs_merged"] += 1
    if manifests:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"counts": {key: counts.get(key, 0) for key in SHOWN}, "pairs": manifests},
            reason=f"merge_duplicate_student {batch}",
            resource_type=BATCH_RESOURCE,
            resource_id=batch,
            resource_repr=batch,
        )
    return counts


def _undo_rows(rows, counts) -> set:
    touched = set()
    by_model: dict = {}
    for row in rows:
        by_model.setdefault(row["model"], []).append(row)
    for name, items in by_model.items():
        model = _model(name)
        key_field = "lesson_id" if name == "LessonMark" else "component_id"
        current = {str(obj.pk): obj for obj in model.objects.filter(pk__in=[row["id"] for row in items])}
        restore, delete = [], []
        for row in items:
            obj = current.get(row["id"])
            if row["moved"]:
                if obj is None or str(obj.enrollment_id) != row["to"]:
                    counts["undo_row_changed"] += 1
                    continue
                delete.append(obj.pk)
            elif obj is not None:
                continue
            values = {f: (None if v is None else (Decimal(v) if f == "score" else v)) for f, v in row["values"].items()}
            restore.append(
                model(id=row["id"], organization_id=None, enrollment_id=row["from"], entered_by_id=row["entered_by"],
                      **{key_field: row["key"]}, **values)  # fmt: skip
            )
            touched |= {row["from"], row["to"]}
        model.objects.filter(pk__in=delete).delete()
        enrollments = _model("Enrollment").objects.in_bulk([obj.enrollment_id for obj in restore])
        for obj in restore:
            obj.organization_id = getattr(enrollments.get(_uuid(obj.enrollment_id)), "organization_id", None)
        model.objects.bulk_create(restore, batch_size=500)
        stamps = {row["id"]: parse_datetime(row["created_at"]) for row in items}
        _restore_created_at(model._meta.db_table, [(obj.pk, stamps[str(obj.pk)]) for obj in restore])
        counts["undo_rows_restored"] += len(restore)
    return touched


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return value


def undo(organization, batch: str, *, actor) -> Counter:
    """Paketi geri qaytar (hələ də paketin vəziyyətində qalanı)."""
    from apps.registrar.public import gradebook

    audit_model = django_apps.get_model("audit", "AuditLog")
    entry = audit_model.objects.filter(
        organization=organization, resource_type=BATCH_RESOURCE, resource_id=batch
    ).first()
    if entry is None:
        raise plan_service.MergePlanError("batch_not_found")
    counts: Counter = Counter()
    enrollment_model = _model("Enrollment")
    user_model = django_apps.get_model("auth", "User")
    for manifest in (entry.new_values or {}).get("pairs") or []:
        # Əvvəl hesab: qeydiyyat qaytarılanda DB qoruyucusu dublikatın aktiv tələbə üzvlüyünü tələb edir.
        counts["undo_memberships_restored"] += (
            django_apps.get_model("organizations", "Membership")
            .objects.filter(pk__in=manifest.get("memberships") or [], is_active=False)
            .update(is_active=True, updated_at=timezone.now())
        )
        duplicate = user_model.objects.select_related("profile").filter(pk=manifest["duplicate"]).first()
        profile = getattr(duplicate, "profile", None)
        if manifest.get("blocked") and duplicate is not None and not duplicate.is_active and profile is not None:
            if profile.block_reason == manifest.get("block_text"):
                unblock_account(duplicate, actor=actor, reason=f"merge_duplicate_student undo {batch}")
                counts["undo_unblocked"] += 1
        touched = _undo_rows(manifest.get("rows") or [], counts)
        for link in manifest.get("share_links") or []:
            share = _model("JournalShare").objects.filter(pk=link["share"]).first()
            if share is not None:
                share.enrollments.remove(link["enrollment"])
                counts["undo_share_links_removed"] += 1
        counts["undo_enrollments_restored"] += enrollment_model.objects.filter(
            pk__in=manifest.get("dropped") or [], status="dropped"
        ).update(status="enrolled", updated_at=timezone.now())
        counts["undo_enrollments_returned"] += enrollment_model.objects.filter(
            pk__in=manifest.get("moved_enrollments") or [], student_id=manifest["keep"]
        ).update(student_id=manifest["duplicate"], updated_at=timezone.now())
        touched |= set(manifest.get("dropped") or []) | set(manifest.get("moved_enrollments") or [])
        counts["undo_attempts_returned"] += (
            django_apps.get_model("exams", "ExamAttempt")
            .objects.filter(pk__in=manifest.get("attempts") or [], user_id=manifest["keep"])
            .update(user_id=manifest["duplicate"])
        )
        if touched:
            gradebook.recompute_absence_hours_many(list(enrollment_model.objects.filter(pk__in=touched)))
    return counts


__all__ = ["BATCH_RESOURCE", "SHOWN", "block_text", "execute", "new_batch", "undo"]
