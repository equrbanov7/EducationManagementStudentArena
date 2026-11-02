"""Fresh tenant, identity, allocation and full reverse academic graph guards."""

from types import SimpleNamespace

from apps.registrar.public import offering_is_practical, schedule_lock
from apps.syllabus.public import approved_version_for, section_data_map, syllabus_for_offering
from apps.workload.public import reviewed_catalog_graph as e

from . import exact_syllabus_recovery as core
from . import own_base_syllabus_spec as spec
from .blank_draft_syllabus_state import actor_scope
from .own_base_syllabus_source import require


def pins(query, expected, code, key="id"):
    values = e.bounded(query, cap=max(len(expected), 1))
    by_id = {str(r[key]): r for r in values}
    require(
        len(values) == len(expected)
        and all(str(p[key]) in by_id and all(by_id[str(p[key])].get(k) == v for k, v in p.items()) for p in expected),
        code,
    )
    return values


def digest_rows(query, cap=20000):
    rows = e.bounded(query, cap=cap)
    return {"count": len(rows), "sha256": e.digest(rows)}


def scope(org, actor, rows):
    actor_scope(org, actor)
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)
    objects = []
    for row in rows:
        obj = core.scope(
            org,
            actor,
            SimpleNamespace(
                organization=spec.ORG,
                period=spec.PERIOD,
                offering=row["offering_id"],
                author=row["teacher_id"],
                allowed_owners=(row["teacher_id"],),
                subject_code=row["subject_code"],
                subject_id=row["subject_id"],
                group_id=row["group_id"],
                require_current_period=True,
            ),
        )
        require(
            not obj.is_intensive
            and obj.subject.name == row["subject_name"]
            and obj.lesson_hours == row["hours"]
            and obj.period.locked_at is None
            and obj.period.academic_year == "2026/2027"
            and obj.period.name == "Payız",
            "current_regular_plan_required",
        )
        if row["source_contact_hours"] != row["contact_hours"]:
            require(
                row["source_id"] in (4164, 8473)
                and row["source_contact_hours"] == [0, 0, 60, 0]
                and row["contact_hours"] == [0, 60, 0, 0]
                and offering_is_practical(obj),
                "fixed_design_practical_alias_required",
            )
        for entity, source_id, label, target in (
            ("worker", row["source_author"], "auth.user", str(row["teacher_id"])),
            ("lesson_subject", row["source_subject"], "registrar.subject", row["subject_id"]),
        ):
            links = e.bounded(
                e.model("legacy_import.LegacyEntityMap").objects.filter(
                    organization=org,
                    source_system="myedu_mariadb",
                    entity_type=entity,
                    legacy_pk=str(source_id),
                    state="migrated",
                ),
                cap=5,
            )
            require(
                not links or all(r["target_model_label"] == label and r["target_pk"] == target for r in links),
                "contradictory_typed_identity",
            )
        user = e.model("auth.User").objects.select_for_update().get(pk=row["teacher_id"])
        profile = e.model("accounts.UserProfile").objects.select_for_update().get(user=user, organization=org)
        require(
            user.username == row["username"]
            and " ".join((user.first_name, user.last_name, profile.patronymic)).strip() == row["teacher"],
            "reviewed_full_teacher_identity_changed",
        )
        group = e.model("organizations.OrgUnit").objects.select_for_update().get(pk=obj.group_id, organization=org)
        require(
            group.is_active and all(group.settings.get(k) == v for k, v in row["group_settings"].items()),
            "group_scope_changed",
        )
        require(group.settings.get("education_form") == "full_time", "full_time_only")
        rowids = [r["id"] for r in row["rows"]]
        pins(
            e.model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=rowids),
            row["rows"],
            "official_rows_changed",
        )
        pins(
            e.model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=rowids),
            row["assignments"],
            "official_assignments_changed",
        )
        pins(
            e.model("workload.TeachingTask").objects.filter(organization=org, pk__in=[t["id"] for t in row["tasks"]]),
            row["tasks"],
            "official_tasks_changed",
        )
        groups = sorted(
            (str(r.pk), str(g))
            for r in e.model("workload.TeachingTaskRow").objects.filter(pk__in=rowids)
            for g in r.groups.values_list("pk", flat=True)
        )
        require(groups == sorted((r["id"], r["groups__id"]) for r in row["row_groups"]), "official_row_groups_changed")
        objects.append(obj)
    return objects


def disposition(org, obj):
    selected = syllabus_for_offering(
        organization=org,
        offering_id=obj.pk,
        subject_id=obj.subject_id,
        period_id=obj.period_id,
        instructor_id=obj.instructor_id,
    )
    if selected is not None:
        e.bounded(e.model("syllabus.Syllabus").objects.filter(organization=org, pk=selected.pk), cap=1)
        if (
            selected.is_active
            and selected.subject_id == obj.subject_id
            and selected.period_id == obj.period_id
            and approved_version_for(selected)
        ):
            return "skip_approved", selected.pk
        return "skip_existing", selected.pk
    direct = list(e.model("syllabus.Syllabus").objects.select_for_update().filter(organization=org, offering=obj))
    if direct:
        # Even an incomplete teacher draft remains theirs; never silently replace it.
        return "skip_existing", direct[0].pk
    return "ready", None


def snapshot(org, actor, children=(), shares=(), rows=None):
    rows = spec.ROWS if rows is None else rows
    objects = scope(org, actor, rows)
    dispositions, selected_ids = {}, []
    for obj in objects:
        status, selected = disposition(org, obj)
        dispositions[str(obj.pk)] = status
        if selected:
            selected_ids.append(selected)
    roots = {
        "registrar.CourseOffering": [r["offering_id"] for r in rows],
        "workload.TeachingTaskRow": sorted({r["id"] for c in rows for r in c["rows"]}),
        "syllabus.Syllabus": list(set(selected_ids) | {c["syllabus"] for c in children}),
    }
    raw = e.graph(spec.ORG, roots)
    created = {}
    for c in children:
        for label, ids in (
            ("syllabus.Syllabus", [c["syllabus"]]),
            ("syllabus.SyllabusVersion", [c["version"]]),
            ("syllabus.SyllabusSection", c["sections"]),
        ):
            created.setdefault(label, set()).update(str(v) for v in ids)
    created["syllabus.SyllabusShare"] = {s["id"] for s in shares}
    protected, owned = {}, {}
    for label, values in raw.items():
        pk = e.model(label)._meta.pk.attname
        old = [v for v in values if str(v[pk]) not in created.get(label, set())]
        new = [v for v in values if str(v[pk]) in created.get(label, set())]
        if old:
            protected[label] = {"count": len(old), "sha256": e.digest(old)}
        if new:
            owned[label] = {"count": len(new), "sha256": e.digest(new)}
    teachers = {r["teacher_id"] for r in rows}
    memberships = e.bounded(e.model("organizations.Membership").objects.filter(organization=org, user_id__in=teachers))
    authority_queries = {
        "teachers": e.model("auth.User").objects.filter(pk__in=teachers),
        "profiles": e.model("accounts.UserProfile").objects.filter(organization=org, user_id__in=teachers),
        "roles": e.model("organizations.Role").objects.filter(pk__in=[m["role_id"] for m in memberships]),
        "groups": e.model("organizations.OrgUnit").objects.filter(
            organization=org, pk__in={o.group_id for o in objects}
        ),
        "subjects": e.model("registrar.Subject").objects.filter(
            organization=org, pk__in={o.subject_id for o in objects}
        ),
        "period": e.model("organizations.AcademicPeriod").objects.filter(organization=org, pk=spec.PERIOD),
        "source_bridges": e.model("legacy_import.LegacyEntityMap").objects.filter(
            organization=org,
            source_system="myedu_mariadb",
            legacy_pk__in={str(v) for r in rows for v in (r["source_author"], r["source_subject"])},
            entity_type__in=("worker", "lesson_subject"),
        ),
        "tasks": e.model("workload.TeachingTask").objects.filter(
            organization=org, pk__in={r["task_id"] for c in rows for r in c["rows"]}
        ),
    }
    protected["authority"] = {k: digest_rows(q) for k, q in authority_queries.items()}
    protected["authority"]["memberships"] = {"count": len(memberships), "sha256": e.digest(memberships)}
    return {"protected": protected, "owned": owned, "dispositions": dispositions}, objects


def created_child(org, obj, syllabus, version):
    rows = e.bounded(e.model("syllabus.SyllabusSection").objects.filter(organization=org, version=version), cap=10)
    require(
        len(rows) == 10 and version.approval_source == "migration" and version.approved_by_id is None,
        "migration_approval_truth",
    )
    return {
        "offering": str(obj.pk),
        "syllabus": str(syllabus.pk),
        "version": str(version.pk),
        "sections": [str(r["id"]) for r in rows],
        "body": core.digest(section_data_map(version)),
    }
