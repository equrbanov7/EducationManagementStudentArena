"""Exact current account/SAR resolution; all family extras remain protected."""

from collections import defaultdict

from apps.registrar.public import validate_active_student_member

from . import bi_mu536_roster_plan as contract
from . import tspx_roster_state as shared
from .repair_fingerprints import queryset_database_fingerprint
from .sbio235_state import RepairError, model
from .tspx_roster_plan import Plan as FamilyPlan


def groups_and_period(organization, *, lock=False):
    query = model("organizations.OrgUnit").objects.filter(
        organization=organization, pk__in=[gid for f in contract.FAMILIES for gid in f.group_ids]
    )
    if lock:
        query = query.select_for_update()
    groups = {str(g.pk): g for g in query}
    if len(groups) != 6:
        raise RepairError("bi_mu_registered_families_missing")
    for family in contract.FAMILIES:
        spec = contract.GEOMETRY[family.name]
        for number, gid in enumerate(family.group_ids):
            group = groups[gid]
            settings = group.settings or {}
            if (
                not group.is_active
                or group.unit_type != "group"
                or group.name != spec["names"][number]
                or str(group.parent_id) != spec["specialty"]
                or str(settings.get("sector") or "az").casefold() != "az"
                or str(settings.get("language_sector") or "az").casefold() != "az"
                or settings.get("degree_level", "bachelor") != "bachelor"
                or settings.get("education_form", "full_time") not in {"full_time", "eyani"}
                or (number and str(settings.get("parent_group")) != family.parent)
            ):
                raise RepairError("bi_mu_registered_family_metadata_changed")
    period = model("organizations.AcademicPeriod").objects.get(organization=organization, pk=contract.PERIOD)
    if not period.is_current or not period.is_active or period.locked_at or period.academic_year != "2026/2027":
        raise RepairError("bi_mu_current_open_period_required")
    return groups, period


def resolve(plan, organization, *, lock=False, allow_targets=False):
    groups, period = groups_and_period(organization, lock=lock)
    names = [p["current_username"] for p in plan.candidates]
    users = {u.username: u for u in model("auth.User").objects.filter(username__in=names)}
    profiles = {
        p.user_id: p
        for p in model("accounts.UserProfile").objects.filter(organization=organization, user__in=users.values())
    }
    query = (
        model("registrar.StudentAcademicRecord")
        .objects.filter(organization=organization, student__in=users.values(), is_active=True, status="enrolled")
        .select_related("student", "program", "curriculum", "group")
    )
    if lock:
        query = query.select_for_update(of=("self",))
    by_user = defaultdict(list)
    for record in query:
        by_user[record.student_id].append(record)
    maps = defaultdict(list)
    for row in model("legacy_import.LegacyEntityMap").objects.filter(
        organization=organization,
        source_system="myedu_mariadb",
        entity_type__in=("student", "student_record"),
        legacy_pk__in=[str(p["legacy_student_id"]) for p in plan.candidates],
    ):
        maps[(row.entity_type, row.legacy_pk)].append(row)
    selected, records_by_id = defaultdict(list), {}
    for person in plan.candidates:
        user = users.get(person["current_username"])
        profile = profiles.get(user.pk) if user else None
        found = by_user.get(user.pk, []) if user else []
        if not user or not user.is_active or not profile or profile.access_state != "active" or len(found) != 1:
            raise RepairError("bi_mu_unique_active_current_account_and_record_required")
        record = found[0]
        family = contract.BI if person["source_home_group_id"] == 966 else contract.MU
        spec = contract.GEOMETRY[family.name]
        target = family.targets[person["source_home_group_id"]]
        actual = {"first_name": user.first_name, "last_name": user.last_name, "patronymic": profile.patronymic}
        if (
            contract.identity(actual) != contract.identity(person["source_identity"])
            or contract.identity(actual) != contract.identity(person["current_identity"])
            or str(record.group_id) not in ({family.parent, target} if allow_targets else {family.parent})
            or record.admission_year != 2026
            or not record.program_id
            or not record.curriculum_id
            or str(record.program.organization_id) != str(organization.pk)
            or not record.program.is_active
            or record.program.official_code_current != spec["program"]
            or str(record.program.specialty_unit_id) != spec["specialty"]
            or record.program.degree_level != "bachelor"
            or str(record.curriculum.organization_id) != str(organization.pk)
            or record.curriculum.program_id != record.program_id
        ):
            raise RepairError("bi_mu_current_full_identity_program_year_or_group_changed")
        validate_active_student_member(organization=organization, user=user)
        for kind, label, pk in (
            ("student", "auth.user", user.pk),
            ("student_record", "registrar.studentacademicrecord", record.pk),
        ):
            existing = maps.get((kind, str(person["legacy_student_id"])), [])
            if existing and (
                len(existing) != 1
                or any(
                    m.state != "migrated" or m.target_model_label != label or m.target_pk != str(pk) for m in existing
                )
            ):
                raise RepairError("bi_mu_existing_immutable_mapping_conflict")
        runtime = {**person, "target_user_id": user.pk, "expected_record_id": str(record.pk), "target_group_id": target}
        selected[family.name].append(runtime)
        records_by_id[str(record.pk)] = record
    scopes = tuple(FamilyPlan(plan.sha256, selected[f.name], [], f) for f in contract.FAMILIES)
    return scopes, groups, period, records_by_id


def capture(scopes, *, lock=False):
    return {p.family.name: shared.capture(p, lock=lock) for p in scopes}


def private_protection(scopes):
    # Opaque full-field fingerprints protect account/profile data (including
    # credential fields) without exporting their values into Python/audit JSON.
    record_users = (
        model("registrar.StudentAcademicRecord")
        .objects.filter(organization_id=contract.ORG, group_id__in=[g for p in scopes for g in p.family.group_ids])
        .values("student_id")
    )
    return {
        "users": queryset_database_fingerprint(model("auth.User").objects.filter(pk__in=record_users)),
        "profiles": queryset_database_fingerprint(
            model("accounts.UserProfile").objects.filter(organization_id=contract.ORG, user_id__in=record_users)
        ),
    }


def preserve(scopes, before, after, moved, source_enrollments):
    for scope in scopes:
        name = scope.family.name
        shared.preserved(scope, before[name], after[name], moved, source_enrollments)
        # Even a newly-created child journal cannot receive invented content.
        if before[name]["academic"] != after[name]["academic"]:
            raise RepairError("bi_mu_academic_content_or_authorship_changed")
        old = {e["id"]: e for e in before[name]["enrollments"]}
        current = {e["id"]: e for e in after[name]["enrollments"]}
        allowed = {current[pk]["superseded_by_id"] for pk in source_enrollments if pk in current}
        if set(current) - set(old) - allowed:
            raise RepairError("bi_mu_unexpected_new_enrollment")
        old_offers = {o["id"]: o for o in before[name]["offerings"]}
        targets = {p["target_user_id"]: p["target_group_id"] for p in scope.candidates}
        allowed_keys = {
            (old_offers[e["offering_id"]]["subject_id"], contract.PERIOD, targets[e["student_id"]])
            for e in old.values()
            if e["id"] in source_enrollments
        }
        for offering in after[name]["offerings"]:
            if (
                offering["id"] not in old_offers
                and (offering["subject_id"], offering["period_id"], offering["group_id"]) not in allowed_keys
            ):
                raise RepairError("bi_mu_unreviewed_new_journal")
