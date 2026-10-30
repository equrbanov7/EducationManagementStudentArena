"""233KE dar bərpası üçün exact scope, bütün-sahə izləri və canlı qapılar."""

from django.db.models import Q

from . import ke233_alias_spec as spec
from .sbio235_state import RepairError, digest, model, records


def offering_ids():
    return sorted(
        {r["id"] for r in spec.MOVES}
        | {item["id"] for item in retained_items()}
        | {r[k] for r in spec.COLLISIONS for k in ("source", "target")}
    )


def retained_items():
    return (spec.RETAINED, *spec.PRESERVED)


def row_ids():
    return [r["id"] for r in spec.ROWS]


def references(label, ids, *, lock=False, exclude=None):
    """Bütün real reverse FK/M2M-lər; yeni relation əlavə ediləndə inventara avtomatik düşür."""
    result = {}
    for relation in model(label)._meta.get_fields():
        if not relation.auto_created or relation.concrete or not relation.related_model:
            continue
        field = relation.field
        lookup = field.name if relation.many_to_many else field.attname
        qs = relation.related_model._default_manager.filter(**{f"{lookup}__in": ids})
        key = f"{relation.related_model._meta.label}.{field.name}"
        qs = qs.exclude(pk__in=(exclude or {}).get(key, ()))
        result[key] = records(qs, lock=lock)
    return result


def fingerprint(data):
    return {k: {"count": len(v), "sha256": digest(v)} for k, v in sorted(data.items())}


def academic(*, lock=False):
    """Offering və yeni share/enrollment ayrıca müqayisə olunur; mövcud məzmunun hamısı qalır."""
    from .repair_fingerprints import academic_fingerprint

    offerings = list(model("registrar.CourseOffering").objects.filter(organization_id=spec.ORG, pk__in=offering_ids()))
    result = academic_fingerprint(organization_id=spec.ORG, offerings=offerings, lock=lock)
    for key in ("offering", "enrollment", "syllabus_share"):
        result.pop(key)
    return result


def workload(*, exclude=False, lock=False):
    qs = model("workload.TeachingTaskRow").objects.filter(organization_id=spec.ORG)
    qs = qs.exclude(pk__in=row_ids()) if exclude else qs.filter(pk__in=row_ids())
    result = records(qs, lock=lock)
    for row in result:
        row["groups"] = sorted(str(v) for v in qs.get(pk=row["id"]).groups.values_list("pk", flat=True))
    return result


def state(*, lock=False):
    tasks = sorted({r["task_id"] for r in spec.ROWS})
    return {
        "groups": records(
            model("organizations.OrgUnit").objects.filter(organization_id=spec.ORG, pk__in=(spec.SOURCE, spec.TARGET)),
            lock=lock,
        ),
        "rows": workload(lock=lock),
        "assignments": records(
            model("workload.TeacherAssignment").objects.filter(organization_id=spec.ORG, row_id__in=row_ids()),
            lock=lock,
        ),
        "tasks": records(
            model("workload.TeachingTask").objects.filter(organization_id=spec.ORG, pk__in=tasks), lock=lock
        ),
        "offerings": records(
            model("registrar.CourseOffering").objects.filter(organization_id=spec.ORG, pk__in=offering_ids()), lock=lock
        ),
        "academic": academic(lock=lock),
        "offering_references": fingerprint(references("registrar.CourseOffering", offering_ids(), lock=lock)),
        "source_references": fingerprint(references("organizations.OrgUnit", [spec.SOURCE], lock=lock)),
        "row_references": fingerprint(references("workload.TeachingTaskRow", row_ids(), lock=lock)),
        "history": records(
            model("workload.WorkloadAmendment").objects.filter(organization_id=spec.ORG, task_id__in=tasks), lock=lock
        ),
        "memberships": fingerprint(
            {
                "memberships": records(
                    model("organizations.Membership").objects.filter(organization_id=spec.ORG), lock=lock
                )
            }
        ),
        "target_records": fingerprint(
            {
                "records": records(
                    model("registrar.StudentAcademicRecord").objects.filter(
                        organization_id=spec.ORG, group_id=spec.TARGET
                    ),
                    lock=lock,
                )
            }
        ),
    }


def validate(*, after=False):
    groups = {
        str(g.pk): g
        for g in model("organizations.OrgUnit").objects.filter(
            organization_id=spec.ORG, pk__in=(spec.SOURCE, spec.TARGET)
        )
    }
    if len(groups) != 2:
        raise RepairError("group_missing")
    source, target = groups[spec.SOURCE], groups[spec.TARGET]
    if source.unit_type != "group" or target.unit_type != "group" or not target.is_active:
        raise RepairError("group_type_or_active_mismatch")
    if source.is_active == after or source.parent_id != target.parent_id:
        raise RepairError("group_identity_mismatch")
    if source.name != "233KE" or target.name != "233 KE az":
        raise RepairError("group_name_mismatch")
    for key, expected in (("degree_level", "bachelor"), ("education_form", "full_time"), ("sector", "az")):
        if source.settings.get(key) != expected or target.settings.get(key) != expected:
            raise RepairError("group_sector_or_program_mismatch")
    if source.settings.get("parent_group") or target.settings.get("parent_group"):
        raise RepairError("parent_child_not_alias")
    if after and source.settings.get("canonical_group") != spec.TARGET:
        raise RepairError("canonical_pointer_missing")
    if source.settings.get("canonical_group") not in (None, "", spec.TARGET):
        raise RepairError("canonical_pointer_conflict")
    refs = references("organizations.OrgUnit", [spec.SOURCE])
    allowed = {"registrar.CourseOffering.group", "workload.TeachingTaskRow.groups"}
    if any(rows for key, rows in refs.items() if key not in allowed):
        raise RepairError("outside_group_reference_in_use")
    expected_old = {item["id"] for item in retained_items()} | (
        {r["source"] for r in spec.COLLISIONS}
        if after
        else {r["id"] for r in spec.MOVES} | {r["source"] for r in spec.COLLISIONS}
    )
    if {r["id"] for r in refs.get("registrar.CourseOffering.group", [])} != expected_old:
        raise RepairError("outside_alias_offering")
    if {r["id"] for r in refs.get("workload.TeachingTaskRow.groups", [])} != (
        {item["row_id"] for item in retained_items()} if after else set(row_ids())
    ):
        raise RepairError("outside_alias_workload")
    rows = {
        str(r.pk): r
        for r in model("workload.TeachingTaskRow")
        .objects.filter(organization_id=spec.ORG, pk__in=row_ids())
        .select_related("task", "period")
    }
    if len(rows) != len(spec.ROWS):
        raise RepairError("row_missing")
    for expected in spec.ROWS:
        row = rows[expected["id"]]
        if (
            str(row.task_id) != expected["task_id"]
            or str(row.subject_id) != expected["subject_id"]
            or str(row.period_id) != expected["period_id"]
        ):
            raise RepairError("row_scope_mismatch")
        if row.task.academic_year != spec.YEAR or row.task.status not in ("distributed", "amended"):
            raise RepairError("task_scope_or_status_mismatch")
        if row.period.academic_year != spec.YEAR or row.period.locked_at is not None or not row.period.is_active:
            raise RepairError("period_locked_or_wrong_year")
        wanted = set(expected["after_groups"] if after else expected["before_groups"])
        if {str(v) for v in row.groups.values_list("pk", flat=True)} != wanted:
            raise RepairError("row_groups_changed")
    offerings = {
        str(o.pk): o
        for o in model("registrar.CourseOffering").objects.filter(organization_id=spec.ORG, pk__in=offering_ids())
    }
    if len(offerings) != len(offering_ids()):
        raise RepairError("offering_missing")
    for item in spec.MOVES:
        _offering(offerings[item["id"]], item, group=spec.TARGET if after else spec.SOURCE, active=True)
        guarded = {
            "registrar.Enrollment.offering",
            "registrar.Lesson.offering",
            "registrar.AssessmentScheme.offering",
            "registrar.ScheduleSlot.offering",
            "registrar.AssessmentComponent.offering",
            "registrar.SelfWorkTopic.offering",
        }
        if not after and any(
            values for key, values in references("registrar.CourseOffering", [item["id"]]).items() if key in guarded
        ):
            raise RepairError("move_identity_now_has_evidence")
    for item in retained_items():
        _offering(offerings[item["id"]], item, group=spec.SOURCE, active=True)
        if offerings[item["id"]].instructor_id and offerings[item["id"]].lesson_hours:
            if (
                not model("registrar.AssessmentScheme")
                .objects.filter(organization_id=spec.ORG, offering_id=item["id"])
                .exists()
            ):
                raise RepairError("retained_scheme_missing")
    for item in spec.COLLISIONS:
        _offering(offerings[item["source"]], item, group=spec.SOURCE, active=not after)
        _offering(offerings[item["target"]], item, group=spec.TARGET, active=True)
        source_refs = references("registrar.CourseOffering", [item["source"]])
        # Sillabus və boş qiymətləndirmə sxemi qalır; başqa tarixçə/əlaqə gizlədilmir.
        allowed = {"syllabus.Syllabus.offering", "registrar.AssessmentScheme.offering"}
        if any(values for key, values in source_refs.items() if key not in allowed):
            raise RepairError("collision_source_has_content")
    if (
        not model("registrar.StudentAcademicRecord")
        .objects.filter(organization_id=spec.ORG, group_id=spec.TARGET, is_active=True, status="enrolled")
        .exists()
    ):
        raise RepairError("canonical_roster_empty")
    return rows, offerings


def _offering(offering, expected, *, group, active):
    if (
        str(offering.subject_id),
        str(offering.period_id),
        str(offering.group_id),
        offering.instructor_id,
        offering.is_active,
    ) != (expected["subject_id"], expected["period_id"], group, expected["teacher_id"], active):
        raise RepairError("offering_identity_changed")


def outside():
    return {
        "rows": digest(workload(exclude=True)),
        "offerings": digest(
            records(
                model("registrar.CourseOffering")
                .objects.filter(organization_id=spec.ORG)
                .exclude(pk__in=offering_ids())
            )
        ),
        "memberships": digest(records(model("organizations.Membership").objects.filter(organization_id=spec.ORG))),
    }


def enrollment_rows(*, exclude_ids=()):
    return records(
        model("registrar.Enrollment")
        .objects.filter(organization_id=spec.ORG, offering_id__in=offering_ids())
        .exclude(pk__in=exclude_ids)
    )


def share_rows(*, exclude_ids=()):
    return records(
        model("syllabus.SyllabusShare")
        .objects.filter(
            Q(offering_id__in=offering_ids()) | Q(syllabus_id=spec.SHARE_SYLLABUS), organization_id=spec.ORG
        )
        .exclude(pk__in=exclude_ids)
    )
