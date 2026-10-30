"""Source-bound opt-in elective policies and immutable group-choice receipts."""

from django.db.models import Q

from .reviewed_batch_manifest import ORG, uid
from .sbio235_state import RepairError, model, records


def parse(entry, item, values, *, empty=False, direct=False):
    expected = {
        "source_sha",
        "source_line",
        "source_subject",
        "subject_id",
        "group_id",
        "period_id",
        "option_id",
        "curriculum_id",
        "elective_group",
    }
    if empty or direct:
        expected -= {"option_id", "curriculum_id", "elective_group"}
    if direct:
        expected.add("options")
    if item["mode"] != "create" or item["existing_journals"] or not isinstance(values, list) or not values:
        raise RepairError("reviewed_elective_create_only_required")
    result, seen = [], set()
    for value in values:
        if not isinstance(value, dict) or set(value) != expected:
            raise RepairError("reviewed_elective_exact_identity_required")
        clean = {
            **value,
            **{
                k: uid(value[k])
                for k in (
                    ("subject_id", "group_id", "period_id")
                    if empty or direct
                    else ("subject_id", "group_id", "period_id", "option_id", "curriculum_id")
                )
            },
        }
        if (
            clean["subject_id"] != item["subject_id"]
            or clean["period_id"] != item["period_id"]
            or clean["group_id"] not in item["group_ids"]
            or clean["group_id"] in seen
            or clean["source_sha"] != item["source_sha"]
            or type(clean["source_line"]) is not int
            or clean["source_line"] != item["source_line"]
            or clean["source_subject"] != entry["source_reference"]["values"].get("subject")
            or not isinstance(clean["source_subject"], str)
            or not clean["source_subject"].strip()
            or (
                not empty
                and not direct
                and (not isinstance(clean["elective_group"], str) or not 1 <= len(clean["elective_group"]) <= 50)
            )
        ):
            raise RepairError("reviewed_elective_source_key_mismatch")
        if direct:
            options = clean["options"]
            if not isinstance(options, list) or not 2 <= len(options) <= 100:
                raise RepairError("reviewed_direct_option_set_required")
            parsed = []
            for op in options:
                if not isinstance(op, dict) or set(op) != {"option_id", "curriculum_id", "elective_group"}:
                    raise RepairError("reviewed_direct_option_identity_required")
                if not isinstance(op["elective_group"], str) or not 1 <= len(op["elective_group"]) <= 50:
                    raise RepairError("reviewed_direct_option_block_invalid")
                parsed.append({**op, "option_id": uid(op["option_id"]), "curriculum_id": uid(op["curriculum_id"])})
            if len({op["option_id"] for op in parsed}) != len(parsed):
                raise RepairError("reviewed_direct_option_set_duplicate")
            clean["options"] = parsed
        seen.add(clean["group_id"])
        result.append(
            {
                **clean,
                **({"empty_group_journal_only": True} if empty else {}),
                **({"source_course_without_curriculum_decision": True} if direct else {}),
            }
        )
    return result


def policies(plan):
    return [value for item in plan.items for value in item.get("policy", {}).get("elective_choices", [])]


def empty_policies(plan):
    return [value for item in plan.items for value in item.get("policy", {}).get("empty_group_journals", [])]


def direct_policies(plan):
    return [value for item in plan.items for value in item.get("policy", {}).get("direct_elective_courses", [])]


def choice_q(plan):
    query = Q(pk__in=[])
    for value in policies(plan):
        query |= Q(group_id=value["group_id"], period_id=value["period_id"], elective_group=value["elective_group"])
    for value in direct_policies(plan):
        query |= Q(
            group_id=value["group_id"],
            period_id=value["period_id"],
            elective_group__in=[op["elective_group"] for op in value["options"]],
        )
    for value in empty_policies(plan):
        query |= Q(group_id=value["group_id"], period_id=value["period_id"])
    return query


def snapshot(plan, *, lock=False):
    values = policies(plan) + [op for value in direct_policies(plan) for op in value["options"]]
    return {
        "choices": records(
            model("registrar.GroupElectiveChoice").objects.filter(organization_id=ORG).filter(choice_q(plan)), lock=lock
        ),
        "options": records(
            model("registrar.CurriculumSubject").objects.filter(
                organization_id=ORG, pk__in=[v["option_id"] for v in values]
            ),
            lock=lock,
        ),
        "curricula": records(
            model("registrar.Curriculum").objects.filter(
                organization_id=ORG, pk__in=[v["curriculum_id"] for v in values]
            ),
            lock=lock,
        ),
    }


def preserved(plan, before, after, details):
    previous = {v["id"]: v for v in before["choices"]}
    current = {v["id"]: v for v in after["choices"]}
    if any(current.get(pk) != value for pk, value in previous.items()):
        raise RepairError("existing_group_elective_choice_changed")
    if before["options"] != after["options"] or before["curricula"] != after["curricula"]:
        raise RepairError("elective_curriculum_metadata_changed")
    allowed = {(v["group_id"], v["period_id"], v["elective_group"], v["subject_id"]) for v in policies(plan)}
    new_ids = []
    for pk, value in current.items():
        if pk not in previous:
            if (
                value["group_id"],
                value["period_id"],
                value["elective_group"],
                value["chosen_subject_id"],
            ) not in allowed:
                raise RepairError("unreviewed_group_elective_choice_created")
            new_ids.append(pk)
    details["created_elective_choice_ids"] = sorted(new_ids)


def for_rows(plan, rows):
    keys = {(str(row.subject_id), str(row.period_id), str(group.pk)) for row in rows for group in row.groups.all()}
    from uuid import UUID

    return {
        tuple(UUID(v[k]) for k in ("subject_id", "period_id", "group_id")): v
        for v in policies(plan) + empty_policies(plan) + direct_policies(plan)
        if (v["subject_id"], v["period_id"], v["group_id"]) in keys
    }


def undo(details):
    model("registrar.GroupElectiveChoice").objects.filter(
        organization_id=ORG, pk__in=details.get("created_elective_choice_ids", [])
    ).delete()
