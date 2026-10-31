"""Teacher's single contact-kind journal over source-proven physical groups."""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from . import gradebook, joint_journal, schedule
from .audit_write import AuditWriteFailed, audit_failure_message
from .journal_shares import journal_scope
from .models import Lesson, ScheduleSlot
from .practical_label import kind_choices


def _session_key(lesson):
    # Different historical topics/hours/authors remain separate columns. Never
    # reinterpret an imported lesson or manufacture marks for another group.
    return (lesson.date, lesson.start_time, lesson.end_time, lesson.topic, lesson.hours, lesson.instructor_id)


def _grid(joint, user):
    locked = any(gradebook.journal_is_locked(offering) for offering in joint.offerings)
    fields = ("date", "start_time", "end_time", "topic", "hours", "instructor_id")
    # Determine ambiguity over ALL historical lessons, before either member or
    # combined windows. An ordinal among truncated duplicates is not identity.
    ambiguous = {
        tuple(row[field] for field in fields)
        for row in Lesson.objects.filter(offering_id__in=joint.offering_ids, kind=joint.kind)
        .values("offering_id", *fields)
        .annotate(count=Count("pk"))
        .filter(count__gt=1)
    }
    journals = [
        (
            offering,
            gradebook.get_offering_journal(
                offering=offering,
                newest_first=True,
                lesson_limit=12,
                lesson_kind=joint.kind,
                scope=journal_scope(user, offering),
            ),
        )
        for offering in joint.offerings
    ]
    columns = {}
    lesson_keys = {}
    for _offering, journal in journals:
        for lesson in journal["lessons"]:
            signature = _session_key(lesson)
            key = (*signature, str(lesson.pk) if signature in ambiguous else "")
            lesson_keys[lesson.pk] = key
            columns.setdefault(key, lesson)
    keys = sorted(columns, key=lambda key: (key[0], str(key[1]), str(key[2]), str(key[3])), reverse=True)[:12]
    rows = []
    for offering, journal in journals:
        for row in journal["rows"]:
            for cell in row["cells"]:
                if locked or (cell["mark"] and cell["mark"].status not in ("present", "absent")):
                    cell["writable"] = False
            own = {lesson_keys[cell["lesson"].pk]: cell for cell in row["cells"]}
            rows.append({**row, "group": offering.group, "cells": [own.get(key) for key in keys]})
    return [columns[key] for key in keys], rows


def _entries(post):
    entries = []
    for key, status in post.items():
        if not key.startswith("att__"):
            continue
        parts = key.split("__")
        if len(parts) != 3:
            raise joint_journal.JointJournalError("Xana açarı düzgün deyil.")
        lesson_id, enrollment_id = parts[1:]
        score = post.get(f"score__{lesson_id}__{enrollment_id}", "")
        if status == "":
            if not score.strip():
                continue
            status = "present"
        entries.append(
            dict(
                lesson_id=lesson_id,
                enrollment_id=enrollment_id,
                status=status,
                score=score,
            )
        )
    return entries


@login_required
def detail(request, source_row_id, kind):
    organization = getattr(request, "organization", None)
    if organization is None:
        raise Http404
    args = dict(organization=organization, user=request.user, source_row_id=source_row_id, kind=kind)
    joint = joint_journal.resolve(**args)
    url = reverse("registrar:joint_journal", args=[source_row_id, kind])
    if request.method == "POST":
        try:
            if request.POST.get("action") == "add_lesson":
                slot = ScheduleSlot.objects.filter(
                    organization=organization,
                    offering_id__in=joint.offering_ids,
                    kind=kind,
                    is_parked=False,
                    pk=uuid.UUID(request.POST.get("slot_id", "")),
                ).first()
                if slot is None:
                    raise joint_journal.JointJournalError("Cədvəl dərsi düzgün seçilməyib.")
                joint_journal.create_lessons(
                    **args,
                    date=request.POST.get("date"),
                    topic=request.POST.get("topic", ""),
                    slot_signature=joint_journal._signature(slot),
                )
                messages.success(request, "Birgə dərs bütün qrupların jurnalına əlavə edildi.")
            elif request.POST.get("action") == "save_marks":
                report = joint_journal.save_marks(**args, entries=_entries(request.POST), request=request)
                messages.success(request, f"Birgə jurnal yadda saxlanıldı ({report['written']} xana).")
            else:
                raise joint_journal.JointJournalError("Jurnal əməliyyatı düzgün deyil.")
        except gradebook.LessonRuleError as exc:
            messages.error(request, str(exc))
        except (ValueError, TypeError):
            messages.error(request, "Dərsin tarix və cədvəl seçimi düzgün deyil.")
        except AuditWriteFailed:
            messages.error(request, audit_failure_message())
        return redirect(url)
    columns, rows = _grid(joint, request.user)
    slots = list(
        ScheduleSlot.objects.filter(
            organization=organization,
            offering=joint.offerings[0],
            kind=kind,
            is_parked=False,
        )
    )
    for slot in slots:
        slot.weekday_label = dict(schedule.WEEKDAYS).get(slot.weekday, slot.weekday)
    return render(
        request,
        "registrar/joint_journal.html",
        {
            "joint": joint,
            "offering": joint.offerings[0],
            "columns": columns,
            "rows": rows,
            "kind_label": dict(kind_choices(joint.offerings[0]))[kind],
            "slots": slots,
            "today": timezone.localdate(),
            "joint_locked": any(gradebook.journal_is_locked(offering) for offering in joint.offerings),
            "active_main_nav": "journal",
        },
    )
