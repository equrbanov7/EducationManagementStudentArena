"""Narrow v2 preflight and canonical source-backed catalogue/access transitions."""

from django.db.models import Count, Q, Sum

from apps.registrar.public import create_reviewed_subject, exact_title_candidates, handover_actions

from .people import is_assignable_teacher, join_chair_as_teacher
from .reviewed_batch_manifest import ORG
from .sbio235_state import RepairError, model, records


def policy(item, name, default=None):
    return item.get("policy", {}).get(name, default)


def has_handovers(plan):
    return any(policy(item, "handover") for item in plan.items)


def membership_q(plan):
    query = Q(pk__in=[])
    for item in plan.items:
        value = policy(item, "join_chair")
        if value:
            query |= Q(user_id=value["teacher_id"], scope_unit_id=value["chair_id"], role__name="teacher")
    return query


def snapshot(plan):
    names = [item["subject"]["name"] for item in plan.items if policy(item, "subject_create")]
    ids = [pk for item in plan.items for pk in policy(item, "handover", {}).get("offering_ids", [])]
    return {
        "catalogue_candidates": (
            [dict(row, id=str(row["id"])) for row in exact_title_candidates(ORG, names)] if names else []
        ),
        "shares": records(model("registrar.JournalShare").objects.filter(organization_id=ORG, offering_id__in=ids)),
        "handovers": records(
            model("registrar.TeachingHandover").objects.filter(organization_id=ORG, offering_id__in=ids)
        ),
    }


def prepare(plan, *, organization, user, actor, batch):
    details = {"created_subject_ids": [], "created_membership_ids": [], "handover_ids": []}
    for item in plan.items:
        identity = policy(item, "subject_create")
        if identity:
            subject = create_reviewed_subject(
                organization=organization,
                user=user,
                identity=identity,
                reason=f"workload.reviewed_source_subject [batch:{batch}]",
            )
            details["created_subject_ids"].append(str(subject.pk))
        join = policy(item, "join_chair")
        if join:
            task = (
                model("workload.TeachingTask")
                .objects.select_related("chair")
                .get(pk=item["task_id"], organization_id=ORG)
            )
            if str(task.chair_id) != join["chair_id"]:
                raise RepairError("reviewed_secondary_membership_task_chair_changed")
            teacher = model("auth.User").objects.get(pk=join["teacher_id"], is_active=True)
            profile = model("accounts.UserProfile").objects.filter(organization_id=ORG, user=teacher).first()
            expected = next(v for v in item["teacher_identity"] if v["id"] == teacher.pk)
            if profile is None or (teacher.first_name, teacher.last_name, profile.patronymic) != (
                expected["first_name"],
                expected["last_name"],
                expected["patronymic"],
            ):
                raise RepairError("reviewed_secondary_membership_full_identity_changed")
            existing = model("organizations.Membership").objects.filter(organization_id=ORG).filter(membership_q(plan))
            if existing.filter(user=teacher, scope_unit=task.chair).exists():
                raise RepairError("reviewed_secondary_membership_already_exists")
            if (
                not model("organizations.Membership")
                .objects.filter(
                    organization_id=ORG,
                    user=teacher,
                    is_active=True,
                    role__is_active=True,
                    role__permissions__contains=["grade.input"],
                )
                .exists()
            ):
                raise RepairError("existing_tenant_teacher_grade_role_required")
            if is_assignable_teacher(organization, task.chair, teacher):
                raise RepairError("reviewed_secondary_membership_not_required")
            join_chair_as_teacher(
                organization=organization,
                user=teacher,
                chair=task.chair,
                actor_user=user,
                reason=f"workload.reviewed_source_secondary_chair [batch:{batch}]",
            )
            details["created_membership_ids"].append(str(existing.get(user=teacher, scope_unit=task.chair).pk))
    return details


def validate_history(item, offering):
    value = next((v for v in policy(item, "legacy_history", []) if v["offering_id"] == str(offering.pk)), None)
    if not value:
        return False
    from .scoped_snapshot.data import offering_counts

    current = offering_counts([offering.pk])[0]
    if any(current[key] != expected for key, expected in value["fingerprints"].items()):
        raise RepairError("reviewed_legacy_snapshot_fingerprint_changed")
    actual_syllabi = list(
        model("syllabus.Syllabus")
        .objects.filter(organization_id=ORG, offering_id=offering.pk)
        .values("id", "author_id", "current_version_id", "approved_version_id")
    )
    actual_syllabi = [
        {key: str(val) if key != "author_id" and val is not None else val for key, val in row.items()}
        for row in actual_syllabi
    ]
    if sorted(actual_syllabi, key=lambda row: row["id"]) != sorted(value["syllabi"], key=lambda row: row["id"]):
        raise RepairError("reviewed_legacy_syllabus_author_version_changed")
    counts = {
        "lessons": offering.lessons.count(),
        "marks": model("registrar.LessonMark").objects.filter(organization_id=ORG, lesson__offering=offering).count(),
        "enrollments": offering.enrollments.count(),
    }
    if any(counts[key] != value[key] for key in counts) or offering.lesson_hours != value["lesson_hours"]:
        raise RepairError("reviewed_legacy_content_counts_or_capacity_changed")
    actual = list(offering.lessons.values("kind", "instructor_id").annotate(hours=Sum("hours"), count=Count("pk")))
    expected = value["recorded"]

    def sort(row):
        return row["kind"], row["instructor_id"] or 0

    if sorted(actual, key=sort) != sorted(expected, key=sort):
        raise RepairError("reviewed_legacy_authorship_or_hours_changed")
    return True


def journal_hours(item, offering_id):
    history = next((v for v in policy(item, "legacy_history", []) if v["offering_id"] == str(offering_id)), None)
    return history["lesson_hours"] if history and history["retain_capacity"] else item["contacts"]


def forward_handovers(plan, *, organization, user, batch, details):
    for item in plan.items:
        value = policy(item, "handover")
        if not value:
            continue
        for pk in value["offering_ids"]:
            offering = model("registrar.CourseOffering").objects.get(organization_id=ORG, pk=pk)
            if offering.instructor_id != value["from_instructor_id"]:
                raise RepairError("reviewed_handover_from_teacher_changed")
            try:
                result = handover_actions.reassign(
                    actor=user,
                    organization=organization,
                    offering_id=pk,
                    new_instructor_id=value["to_instructor_id"],
                    reason=f"Rəsmi kafedra yükü üzrə baxılmış müəllim təhvili [batch:{batch}]",
                )
            except handover_actions.HandoverError as exc:
                raise RepairError("canonical_handover_rejected:" + exc.code) from exc
            details["handover_ids"].extend(result["handover_ids"])


def retain_capacities(plan):
    for item in plan.items:
        for value in policy(item, "legacy_history", []):
            if value["retain_capacity"]:
                offering = model("registrar.CourseOffering").objects.get(pk=value["offering_id"], organization_id=ORG)
                offering.lesson_hours = value["lesson_hours"]
                offering.save(update_fields=["lesson_hours", "updated_at"])


def undo(plan, *, details, user, organization, batch):
    for pk in reversed(details.get("handover_ids", [])):
        handover_actions.revert(
            actor=user,
            organization=organization,
            handover_id=pk,
            reason=f"Baxılmış mənbə dəstinin geri qaytarılması [batch:{batch}]",
        )
    model("organizations.Membership").objects.filter(
        organization_id=ORG, pk__in=details.get("created_membership_ids", []), is_primary=False
    ).delete()
    subjects = model("registrar.Subject").objects.filter(
        organization_id=ORG, pk__in=details.get("created_subject_ids", [])
    )
    for subject in subjects:
        # No cascade may remove a later user's unrelated catalogue reference.
        if subject.offerings.exists():
            raise RepairError("undo_created_subject_still_referenced")
        subject.delete()


def handover_targets(plan):
    from .reviewed_named_transitions import owner_targets

    return {
        **owner_targets(plan),
        **{
            pk: value["to_instructor_id"]
            for item in plan.items
            if (value := policy(item, "handover"))
            for pk in value["offering_ids"]
        },
    }


def preserved(plan, before, after, details):
    """Explicit additions may not modify any previous identity or access row."""
    from .reviewed_batch_guards import _same_except

    for name, created in (
        ("subjects", details.get("created_subject_ids", [])),
        ("memberships", details.get("created_membership_ids", [])),
    ):
        current = {row["id"]: row for row in after[name]}
        previous = {row["id"]: row for row in before[name]}
        if set(current) - set(previous) != set(created) or not set(previous) <= set(current):
            raise RepairError("unreviewed_" + name + "_identity_change")
        for pk, row in previous.items():
            if current[pk] != row:
                raise RepairError("existing_" + name + "_changed")
        if name == "memberships":
            allowed = {
                str(value["teacher_id"]) + ":" + value["chair_id"]
                for item in plan.items
                if (value := policy(item, "join_chair"))
            }
            for pk in created:
                row = current[pk]
                if (
                    row["is_primary"]
                    or not row["is_active"]
                    or str(row["user_id"]) + ":" + row["scope_unit_id"] not in allowed
                ):
                    raise RepairError("unreviewed_primary_or_secondary_membership")
    previous, current = before["extensions"], after["extensions"]
    old_events = {row["id"]: row for row in previous["handovers"]}
    new_events = {row["id"]: row for row in current["handovers"]}
    if set(new_events) - set(old_events) != set(details.get("handover_ids", [])) or any(
        new_events.get(pk) != row for pk, row in old_events.items()
    ):
        raise RepairError("unreviewed_handover_history_change")
    targets = handover_targets(plan)
    deactivated = set()
    for pk in details.get("handover_ids", []):
        row = new_events[pk]
        if targets.get(row["offering_id"]) != row["to_instructor_id"]:
            raise RepairError("unreviewed_handover_target")
        deactivated.update(row["deactivated_share_ids"])
    shares = {row["id"]: row for row in current["shares"]}
    for old in previous["shares"]:
        pk = old["id"]
        if pk not in shares:
            raise RepairError("historical_journal_share_deleted")
        allowed = {"is_active", "updated_at"} if pk in deactivated else set()
        _same_except(old, shares[pk], allowed, "unreviewed_journal_share_change")
        if pk in deactivated and (not old["is_active"] or shares[pk]["is_active"]):
            raise RepairError("unreviewed_share_deactivation")
    old_share_ids = {row["id"] for row in previous["shares"]}
    for pk, share in shares.items():
        if pk not in old_share_ids and (share["source"] != "workload" or share["offering_id"] not in targets):
            raise RepairError("unreviewed_handover_new_access")
