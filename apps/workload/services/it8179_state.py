"""Fixed source-row84 workload consolidation; academic history is wholly immutable."""

import hashlib
import os
import stat
import zipfile
from xml.etree import ElementTree

from .sbio235_state import digest  # noqa: F401 — shared state fingerprint surface
from .sbio235_state import RepairError, model, records

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
TASK = "663dbec7-6043-4b12-9f69-9d1278a1b7cb"
CHAIR = "723f5382-82c4-4627-9e69-739b8b3d8325"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SUBJECT = "57f0e160-8371-4974-811d-aa5b68dbacc8"
TEACHER = 8179
KEEP = "ac6d808b-164f-4114-891c-28ee31721bad"
REMOVE = "5dbee7d1-036e-4e5b-ae9d-8ac9a8572b8f"
IT_GROUP = "31bbf1f8-9360-4a12-8c86-ce4d7b40df69"
K_GROUP = "c00a59d4-dbf0-4111-81e0-24baf2c19b2e"
OFFERINGS = ("60845028-cddf-4d4a-b0ad-a722a084ca15", "994ac851-2f8b-488f-ae41-68ffd02806bd")
SOURCE_SHA = "7630be3cbe9bfe7050e2f308fae8c4959c35bd298967f5e3f2b77a0ab4a9cb09"
GROUP_TEXT = "233 K ing\n233 İT ing"
RESOURCE = "workload.it8179_source84_merge"


def load_source(path, sha256):
    if sha256 != SOURCE_SHA:
        raise RepairError("pinned_official_docx_sha_required")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 10_000_000:
            raise RepairError("private_regular_official_docx_required")
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise RepairError("official_docx_changed")
    # Parsing happens only after the entire immutable official file is verified.
    import io

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    row = root.findall(".//w:tbl", ns)[0].findall("w:tr", ns)[83]
    cells = [
        "\n".join("".join(t.text or "" for t in p.findall(".//w:t", ns)) for p in c.findall("w:p", ns)).strip()
        for c in row.findall("w:tc", ns)
    ]
    if (
        len(cells) != 26
        or {i: cells[i] for i in (1, 2, 3, 4, 5, 10, 23, 25)}
        != {1: GROUP_TEXT, 2: "Kompüterlərdə modelləşdirmə", 3: "8", 4: "45", 5: "45", 10: "90", 23: "90", 25: "90"}
        or any(cells[i] for i in (6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24))
    ):
        raise RepairError("official_source_row84_geometry_changed")
    return SOURCE_SHA


def reverse_graph(roots):
    pending, seen, result = {k: set(v) for k, v in roots.items()}, {}, {}
    while pending:
        label, ids = pending.popitem()
        ids = set(map(str, ids)) - seen.get(label, set())
        if not ids:
            continue
        cls = model(label)
        values = records(cls._base_manager.select_for_update().filter(pk__in=ids))
        if any(str(r.get("organization_id", ORG)) != ORG for r in values):
            raise RepairError("reverse_graph_tenant_changed")
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(values)
        if sum(map(len, result.values())) > 30000:
            raise RepairError("fixed_reverse_graph_budget")
        for rel in cls._meta.get_fields(include_hidden=True):
            if rel.auto_created and not rel.concrete and rel.related_model:
                lookup = rel.field.name if rel.many_to_many else rel.field.attname
                children = rel.related_model._base_manager.filter(**{lookup + "__in": ids}).values_list("pk", flat=True)
                pending.setdefault(rel.related_model._meta.label, set()).update(map(str, children))
    return {k: sorted(v, key=lambda r: str(r[model(k)._meta.pk.attname])) for k, v in sorted(result.items()) if v}


def capture():
    rows = model("workload.TeachingTaskRow").objects.filter(task_id=TASK, organization_id=ORG)
    workload = reverse_graph({"workload.TeachingTaskRow": rows.values_list("pk", flat=True)})
    return {
        "academic": reverse_graph({"registrar.CourseOffering": OFFERINGS}),
        "workload": workload,
        "task": records(model("workload.TeachingTask").objects.filter(pk=TASK, organization_id=ORG)),
        "amendments": records(model("workload.WorkloadAmendment").objects.filter(task_id=TASK, organization_id=ORG)),
        "subjects": records(model("registrar.Subject").objects.filter(pk=SUBJECT, organization_id=ORG)),
        "groups": records(
            model("organizations.OrgUnit").objects.filter(pk__in=(IT_GROUP, K_GROUP), organization_id=ORG)
        ),
    }


def protected(value):
    workload = dict(value["workload"])
    workload["workload.TeachingTaskRow"] = [
        {k: v for k, v in r.items() if not (str(r["id"]) == KEEP and k in ("groups_text", "updated_at"))}
        for r in workload["workload.TeachingTaskRow"]
        if str(r["id"]) != REMOVE
    ]
    workload["workload.TeacherAssignment"] = [
        r for r in workload["workload.TeacherAssignment"] if str(r["row_id"]) != REMOVE
    ]
    through = model("workload.TeachingTaskRow").groups.through._meta.label
    workload[through] = [r for r in workload[through] if str(r["teachingtaskrow_id"]) not in (KEEP, REMOVE)]
    # Empty labels disappear from traversal after deletion, so normalize them.
    workload = {k: v for k, v in workload.items() if v}
    return {
        **{k: v for k, v in value.items() if k not in ("workload", "task", "amendments")},
        "workload": workload,
        "task": [{k: v for k, v in r.items() if k not in ("updated_at", "status")} for r in value["task"]],
    }


def reject_history(row):
    allowed = {"workload.TeacherAssignment", row.groups.through._meta.label}
    for label, values in reverse_graph({"workload.TeachingTaskRow": [row.pk]}).items():
        if label not in allowed | {"workload.TeachingTaskRow"} and values:
            raise RepairError("duplicate_row_has_history_" + model(label)._meta.model_name)
    if model("workload.WorkloadAmendment").objects.filter(task_id=TASK, target_id=row.pk).exists():
        raise RepairError("duplicate_row_has_prior_amendment")


def validate(*, corrected):
    rows = (
        model("workload.TeachingTaskRow").objects.select_for_update().filter(pk__in=(KEEP, REMOVE), organization_id=ORG)
    )
    expected = {KEEP} if corrected else {KEEP, REMOVE}
    if {str(r.pk) for r in rows} != expected:
        raise RepairError("reviewed_row_set_changed")
    for row in rows:
        if (
            str(row.task_id),
            str(row.subject_id),
            str(row.period_id),
            row.season,
            row.row_kind,
            row.degree_level,
            row.education_form,
            str(row.credits),
            row.union_count,
            row.subgroup_count,
            row.lecture_plan,
            row.lecture_total,
            row.seminar_plan,
            row.seminar_total,
            row.total_hours,
        ) != (TASK, SUBJECT, PERIOD, "fall", "teaching", "bachelor", "eyani", "7", 1, 1, 45, 45, 45, 45, 90) or any(
            getattr(row, k)
            for k in (
                "lab_plan",
                "lab_total",
                "consult_hours",
                "exam_hours",
                "postgrad_hours",
                "practice_production_hours",
                "practice_research_hours",
                "thesis_hours",
            )
        ):
            raise RepairError("reviewed_contact_credit_or_other_hours_changed")
        groups = {str(g) for g in row.groups.values_list("pk", flat=True)}
        wanted = {IT_GROUP, K_GROUP} if corrected else ({IT_GROUP} if str(row.pk) == KEEP else {K_GROUP})
        if groups != wanted or (corrected and row.groups_text != GROUP_TEXT):
            raise RepairError("reviewed_physical_groups_changed")
        if sorted((a.teacher_id, a.activity, a.hours, a.is_hourly_paid) for a in row.assignments.all()) != [
            (TEACHER, "lecture", 45, False),
            (TEACHER, "seminar", 45, False),
        ]:
            raise RepairError("reviewed_assignments_changed")
        if str(row.pk) == REMOVE:
            reject_history(row)
    offerings = (
        model("registrar.CourseOffering").objects.select_for_update().filter(pk__in=OFFERINGS, organization_id=ORG)
    )
    if {str(o.pk) for o in offerings} != set(OFFERINGS):
        raise RepairError("reviewed_offering_set_changed")
    if {
        (str(o.group_id), str(o.subject_id), str(o.period_id), o.instructor_id, o.is_active, o.lesson_hours)
        for o in offerings
    } != {(g, SUBJECT, PERIOD, TEACHER, True, 90) for g in (IT_GROUP, K_GROUP)}:
        raise RepairError("reviewed_offering_owner_or_metadata_changed")
    return rows.get(pk=KEEP)
