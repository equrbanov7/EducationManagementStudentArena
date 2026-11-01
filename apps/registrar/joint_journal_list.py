"""Teacher-only virtual entries, projected before pagination and after ORM filters."""

from copy import copy
from urllib.parse import urlencode

from django.db.models import Count
from django.urls import reverse

from .joint_journal import selections
from .models import Enrollment
from .practical_label import kind_choices


def project(queryset, *, organization, user, selected_kind, observer=None, observer_request=None):
    joints = selections(organization=organization, user=user)
    if observer is not None:
        from .joint_journal_observation import allowed

        joints = allowed(joints, observer, request=observer_request)
    if not joints:
        return queryset
    # The already-authorized and filtered set remains the outer boundary. A
    # joint candidate cannot restore a group removed by year/season/kind/scope.
    offerings = list(queryset)
    allowed_ids = {offering.pk for offering in offerings if observer is not None or offering.journal_is_current_load}
    joints = [
        joint
        for joint in joints
        if joint.offering_ids <= allowed_ids and (not selected_kind or joint.kind == selected_kind)
    ]
    if not joints:
        return offerings
    by_pair = {(pk, joint.kind): joint for joint in joints for pk in joint.offering_ids}
    affected = set().union(*(joint.offering_ids for joint in joints))
    if observer is not None:
        from .teacher_journal_list import project as project_teacher

        current = {
            offering.pk: offering for offering in project_teacher(queryset.filter(pk__in=affected), user, organization)
        }
        if not affected <= current.keys():
            return offerings
        offerings = [current.get(offering.pk, offering) for offering in offerings]
    emitted, entries = set(), []
    for offering in offerings:
        if offering.pk not in affected:
            entries.append(offering)
            continue
        kinds = [kind for kind in ("lecture", "seminar", "lab") if getattr(offering, f"journal_current_{kind}", False)]
        for kind in kinds:
            if selected_kind and kind != selected_kind:
                continue
            joint = by_pair.get((offering.pk, kind))
            key = (joint.source_row_id, kind) if joint else (offering.pk, kind)
            if key in emitted:
                continue
            emitted.add(key)
            entry = copy(offering)
            entry.journal_entry_kind = kind
            entry.joint_selection = joint
            if observer is not None:
                entry.joint_observed_teacher = user
            entry.journal_entry_url = (
                reverse("registrar:joint_journal", args=[joint.source_row_id, kind])
                if joint
                else f"{reverse('registrar:journal_detail', args=[offering.pk])}?kind={kind}"
            )
            if joint and observer is not None:
                entry.journal_entry_url += "?" + urlencode({"teacher": user.pk, "observe": "1"})
            entries.append(entry)
    return entries


def attach(entries, *, user=None):
    joints = [entry.joint_selection for entry in entries if getattr(entry, "joint_selection", None)]
    ids = set().union(*(joint.offering_ids for joint in joints)) if joints else set()
    counts = (
        {
            row["offering_id"]: row["count"]
            for row in Enrollment.objects.filter(offering_id__in=ids, status=Enrollment.Status.ENROLLED)
            .values("offering_id")
            .annotate(count=Count("pk"))
        }
        if ids
        else {}
    )
    for entry in entries:
        kind = getattr(entry, "journal_entry_kind", None)
        if not kind:
            continue
        entry.kind_label = str(dict(kind_choices(entry))[kind])
        entry.slot_kinds = [kind]
        entry.next_lesson = None  # a different physical kind's occurrence is not this entry
        joint = entry.joint_selection
        if joint:
            entry.journal_group_name = joint.group_label
            entry.student_count = sum(counts.get(pk, 0) for pk in joint.offering_ids)
    if user is not None:
        from .teacher_journal_list import attach as attach_teacher

        observed = {}
        for entry in entries:
            teacher = getattr(entry, "joint_observed_teacher", None)
            if teacher is not None:
                observed.setdefault(teacher, []).append(entry)
        for teacher, rows in observed.items():
            attach_teacher(teacher, rows)
        from .joint_journal_records import attach as attach_records

        attach_records(entries, user)
