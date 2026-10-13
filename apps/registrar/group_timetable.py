"""«Starosta» bölməsi — qrupun HƏFTƏLİK CƏDVƏLİ (birləşmiş dərslərlə) + YAXIN İMTAHANLAR, 2026-10-13 (gecə).

Adi tələbənin «Cədvəlim»-i yalnız ÖZ qeydiyyatlarını göstərir; starosta isə QRUPUN cədvəlini görür:

* qrupun öz açılışlarının slotları + qrup tələbələrinin oxuduğu BAŞQA qrup jurnallarının slotları
  (alt qrup birləşməsi, seçmə) — ``group_academic.group_subjects`` müəyyən etdiyi açılışlar;
* AXIN (birləşmiş mühazirə): eyni gün + başlama vaxtı + fənn + effektiv müəllim, hər ikisi mühazirə
  (``schedule.is_joint_lecture`` qaydası) olan BAŞQA qrupların adları slotun yanında;
* qrupun bir HİSSƏSİNİN getdiyi dərs (seçmə / alt qrup) — «N tələbə» qeydi.

İmtahanlar: aktiv, silinməmiş, arxivlənməmiş, başlama vaxtı İNDİDƏN sonra olan imtahanlar ki, ya qrupa
(və ya ana qrupuna) təyin olunub (``Exam.allowed_units``), ya da qrupun açılışlarının LMS kursuna bağlıdır —
eyni əlaqə :func:`apps.registrar.schedule.get_week_exams`-dadır. Yalnız ad / fənn / vaxt (nəticə yox).
Modul sərhədi: ``Exam`` app registry ilə açılır (registrar exams-ı statik import etmir). Heç nə YAZMIR.
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils import timezone

from apps.registrar.models import ScheduleSlot, SlotKind
from apps.registrar.schedule import WEEKDAYS, effective_instructor_id

#: Yaxın imtahan pəncərəsi və siyahı həddi (kabinet paneli — tam siyahı «İmtahanlar» bölməsindədir).
EXAM_WINDOW_DAYS = 90
EXAM_LIMIT = 12


def _person(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def _slot_key(slot):
    return (slot.weekday, slot.start_time, slot.offering.subject_id, effective_instructor_id(slot))


def group_timetable(group, *, period, subjects) -> list:
    """``[{"weekday", "label", "slots": [...]}]`` — yalnız dərsi olan günlər.

    ``subjects`` — ``group_academic.group_subjects`` nəticəsi (açılışlar + iştirakçılar).
    """
    if group is None or period is None or not subjects.get("offering_ids"):
        return []
    by_offering = {item["offering_id"]: item for item in subjects["subjects"]}
    slots = list(
        ScheduleSlot.objects.filter(
            organization_id=group.organization_id,
            offering_id__in=list(subjects["offering_ids"]),
            offering__period=period,
            is_parked=False,
        )
        .select_related("offering", "offering__subject", "offering__group", "offering__instructor", "instructor")
        .order_by("weekday", "start_time", "end_time")
    )
    if not slots:
        return []

    # Axın: eyni dövrdə BAŞQA açılışların mühazirə slotları (eyni fənlər, eyni günlər) — TƏK sorğu.
    lecture_slots = [slot for slot in slots if slot.kind == SlotKind.LECTURE]
    joint: dict = {}
    if lecture_slots:
        candidates = (
            ScheduleSlot.objects.filter(
                organization_id=group.organization_id,
                offering__period=period,
                is_parked=False,
                kind=SlotKind.LECTURE,
                offering__subject_id__in={slot.offering.subject_id for slot in lecture_slots},
                weekday__in={slot.weekday for slot in lecture_slots},
            )
            .exclude(offering_id__in=list(subjects["offering_ids"]))
            .select_related("offering", "offering__group")
        )
        for other in candidates:
            name = getattr(other.offering.group, "name", "") or ""
            if name and name != group.name:
                joint.setdefault(_slot_key(other), set()).add(name)

    week_labels = dict(WEEKDAYS)
    days: dict = {}
    for slot in slots:
        subject = by_offering.get(slot.offering_id, {})
        teacher = slot.instructor if slot.instructor_id else slot.offering.instructor
        other_groups = set(subject.get("other_groups") or [])
        if slot.kind == SlotKind.LECTURE:
            other_groups |= joint.get(_slot_key(slot), set())
        other_groups.discard(group.name)
        days.setdefault(slot.weekday, []).append(
            {
                "start": slot.start_time,
                "end": slot.end_time,
                "subject": subject.get("name") or slot.offering.subject.name,
                "kind": slot.kind,
                "kind_label": slot.get_kind_display(),
                "week_type": slot.week_type,
                "week_type_label": slot.get_week_type_display() if slot.week_type != "all" else "",
                "room": slot.room or "",
                "teacher": _person(teacher),
                "other_groups": sorted(other_groups, key=str.lower),
                "partial": bool(subject.get("partial")),
                "takers": subject.get("takers", 0),
                "is_elective": subject.get("kind") == "elective",
            }
        )
    return [
        {"weekday": weekday, "label": week_labels.get(weekday, str(weekday)), "slots": items}
        for weekday, items in sorted(days.items())
    ]


def group_upcoming_exams(group, *, period, subjects, unit_ids, now=None) -> list:
    """Qrupun yaxın imtahanları: ``[{"title", "start", "end", "subject", "kind_label"}]``."""
    if group is None:
        return []
    now = now or timezone.now()
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    course_ids = []
    if subjects.get("offering_ids"):
        course_ids = list(
            CourseOffering.objects.filter(pk__in=list(subjects["offering_ids"]), course__isnull=False)
            .values_list("course_id", flat=True)
            .distinct()
        )
    scope = Q(allowed_units__in=list(unit_ids or [group.pk]))
    if course_ids:
        scope |= Q(course_id__in=course_ids)
    Exam = django_apps.get_model("exams", "Exam")
    # M2M (`allowed_units`) JOIN-u təkrar sətir verə bilər — DISTINCT əvəzinə id alt-sorğusu (TƏK sorğu).
    matching = Exam.objects.filter(
        organization_id=group.organization_id,
        is_active=True,
        is_deleted=False,
        is_archived=False,
        start_datetime__isnull=False,
        start_datetime__gte=now,
        start_datetime__lte=now + datetime.timedelta(days=EXAM_WINDOW_DAYS),
    ).filter(scope)
    exams = (
        Exam.objects.filter(pk__in=matching.values("pk"))
        .select_related("subject", "course")
        .order_by("start_datetime", "pk")[:EXAM_LIMIT]
    )
    out = []
    for exam in exams:
        subject = getattr(exam.subject, "name", "") or getattr(exam.course, "title", "") or ""
        kind = exam.get_exam_type_extended_display() if exam.exam_type_extended else ""
        out.append(
            {
                "title": exam.title,
                "start": timezone.localtime(exam.start_datetime),
                "end": timezone.localtime(exam.end_datetime) if exam.end_datetime else None,
                "subject": subject,
                "kind_label": kind,
            }
        )
    return out


__all__ = ["EXAM_LIMIT", "EXAM_WINDOW_DAYS", "group_timetable", "group_upcoming_exams"]
