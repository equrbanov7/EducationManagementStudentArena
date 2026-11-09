"""Read-only graph snapshots; apply locks first, dry-run never calls a writer."""

import json

from django.db.models import Q

from apps.syllabus.public import syllabus_for_offering
from apps.workload.public import journal_academic_fingerprint

from .contracts import SCOPE, RestoreError, digest, model


def rows(queryset, *, lock=False):
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    result = list(queryset.order_by("pk")[:30001])
    if len(result) > 30000:
        raise RestoreError("reviewed_state_budget_exceeded")
    return result


def values(objects):
    return [{field.attname: getattr(obj, field.attname) for field in obj._meta.concrete_fields} for obj in objects]


def resolved(offering):
    return syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


def context(org, offerings, syllabi, *, lock=False):
    all_offerings = rows(
        model("registrar.CourseOffering")
        .objects.filter(organization=org)
        .filter(Q(pk__in=[o.pk for o in offerings]) | Q(pk__in=[s.offering_id for s in syllabi if s.offering_id])),
        lock=lock,
    )
    subjects = {o.subject_id for o in all_offerings}
    teachers = {o.instructor_id for o in all_offerings if o.instructor_id} | {
        s.author_id for s in syllabi if s.author_id
    }
    tasks = rows(
        model("workload.TeachingTaskRow").objects.filter(
            organization=org, subject_id__in=subjects, period_id__in={o.period_id for o in all_offerings}
        ),
        lock=lock,
    )
    curriculum = rows(
        model("registrar.CurriculumSubject").objects.filter(organization=org, subject_id__in=subjects), lock=lock
    )
    targets = (
        [str(x) for x in subjects] + [str(x) for x in teachers] + [str(o.group_id) for o in all_offerings if o.group_id]
    )
    remapped = (
        model("legacy_import.LegacyEntityMapVersion")
        .objects.filter(organization=org, target_pk__in=targets)
        .values("entity_map_id")
    )
    mappings = rows(
        model("legacy_import.LegacyEntityMap")
        .objects.filter(organization=org, source_system="myedu_mariadb")
        .filter(Q(target_pk__in=targets) | Q(pk__in=remapped)),
        lock=lock,
    )
    queries = {
        "groups": model("organizations.OrgUnit").objects.filter(
            organization=org, pk__in={o.group_id for o in all_offerings}
        ),
        "subjects": model("registrar.Subject").objects.filter(organization=org, pk__in=subjects),
        "periods": model("organizations.AcademicPeriod").objects.filter(
            organization=org, pk__in={o.period_id for o in all_offerings}
        ),
        "tasks": model("workload.TeachingTask").objects.filter(organization=org, pk__in={r.task_id for r in tasks}),
        "assignments": model("workload.TeacherAssignment").objects.filter(
            organization=org, row_id__in=[r.pk for r in tasks]
        ),
        "row_groups": model("workload.TeachingTaskRow").groups.through.objects.filter(
            teachingtaskrow_id__in=[r.pk for r in tasks]
        ),
        "curricula": model("registrar.Curriculum").objects.filter(
            organization=org, pk__in={r.curriculum_id for r in curriculum}
        ),
        "programs": model("registrar.Program").objects.filter(organization=org),
        "profiles": model("accounts.UserProfile").objects.filter(user_id__in=teachers),
        "memberships": model("organizations.Membership").objects.filter(organization=org, user_id__in=teachers),
        "roles": model("organizations.Role").objects.filter(organization=org),
        "typed_map_versions": model("legacy_import.LegacyEntityMapVersion").objects.filter(
            entity_map_id__in=[row.pk for row in mappings]
        ),
    }
    result = {name: values(rows(query, lock=lock)) for name, query in queries.items()}
    result["typed_maps"] = values(mappings)
    result.update(
        donor_offerings=values(all_offerings), task_rows=values(tasks), curriculum_subjects=values(curriculum)
    )
    return result


def capture(org, ids, *, lock=False):
    offerings = rows(
        model("registrar.CourseOffering")
        .objects.filter(organization=org, pk__in=ids)
        .select_related("organization", "subject", "period", "group", "instructor"),
        lock=lock,
    )
    if {str(o.pk) for o in offerings} != set(ids):
        raise RestoreError("audit_target_missing")
    if any(str(o.period_id) != SCOPE["period_id"] for o in offerings):
        raise RestoreError("audit_period_changed")
    selected = [resolved(o) for o in offerings]
    condition = Q(offering_id__in=ids) | Q(pk__in=[s.pk for s in selected if s])
    for offering in offerings:
        condition |= Q(subject_id=offering.subject_id, author_id=offering.instructor_id)
    syllabus_query = model("syllabus.Syllabus").objects.filter(condition, organization=org)
    syllabi = rows(syllabus_query)
    syllabus_ids = {s.pk for s in syllabi}
    for _ in range(30):
        versions = rows(
            model("syllabus.SyllabusVersion").objects.filter(organization=org, syllabus_id__in=syllabus_ids)
        )
        parents = {s.reused_from_id for s in syllabi if s.reused_from_id}
        source_ids = {v.source_version_id for v in versions if v.source_version_id}
        source_versions = rows(model("syllabus.SyllabusVersion").objects.filter(organization=org, pk__in=source_ids))
        if {v.pk for v in source_versions} != source_ids:
            raise RestoreError("cross_tenant_version_lineage")
        parents.update(v.syllabus_id for v in source_versions)
        extra = parents - syllabus_ids
        if not extra:
            break
        additions = rows(model("syllabus.Syllabus").objects.filter(organization=org, pk__in=extra))
        if {s.pk for s in additions} != extra:
            raise RestoreError("cross_tenant_syllabus_lineage")
        syllabi.extend(additions)
        syllabus_ids |= extra
    else:
        raise RestoreError("syllabus_lineage_budget")
    versions = rows(
        model("syllabus.SyllabusVersion").objects.filter(organization=org, syllabus_id__in=syllabus_ids), lock=lock
    )
    syllabi = rows(model("syllabus.Syllabus").objects.filter(organization=org, pk__in=syllabus_ids), lock=lock)
    sections = rows(
        model("syllabus.SyllabusSection").objects.filter(organization=org, version_id__in=[v.pk for v in versions]),
        lock=lock,
    )
    reviews = rows(
        model("syllabus.SyllabusReview").objects.filter(organization=org, version_id__in=[v.pk for v in versions]),
        lock=lock,
    )
    shares = rows(
        model("syllabus.SyllabusShare")
        .objects.filter(organization=org)
        .filter(Q(offering_id__in=ids) | Q(syllabus_id__in=syllabus_ids)),
        lock=lock,
    )
    cohorts = rows(
        model("registrar.LanguageLevelCohort")
        .objects.filter(organization=org)
        .filter(Q(offering_id__in=ids) | Q(source_offering_id__in=ids)),
        lock=lock,
    )
    graph = {
        "offerings": values(offerings),
        "syllabi": values(syllabi),
        "versions": values(versions),
        "sections": values(sections),
        "reviews": values(reviews),
        "shares": values(shares),
        "cohorts": values(cohorts),
    }
    graph["context"] = context(org, offerings, syllabi, lock=lock)
    # Body values remain in the tenant-bound receipt, never CLI output or repo files.
    graph["protected"] = journal_academic_fingerprint(
        organization_id=org.pk,
        offerings=offerings,
        exclude=("syllabus", "version", "section", "review", "syllabus_share"),
    )
    return json.loads(json.dumps(graph, default=str)), offerings


def fingerprint(graph):
    return digest(graph)
