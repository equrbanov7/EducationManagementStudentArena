"""Sillabuslar — TƏSDİQLƏNMİŞ (``approval_source=migration``) kimi; müəllimə iş yaranmır.

1. **Açılışa bağlı**: tam semestr jurnalının ``sillabus_id``-si (fənni jurnalın fənni ilə EYNİ olmalıdır)
   → ilk dilim açılışına ``import_migrated_version(offering=…, period=…, status=approved)``. Açılışın
   artıq sillabusu varsa (açılış, paylaşım və ya fənn+semestr pilləsi — müəllim yeni sistemdə yazıb / bağlayıb)
   TOXUNULMUR. Jurnal banneri «Təsdiqlənib» görünür, müəllimdən heç nə tələb olunmur.
   **Bir sillabus** (sahib 2026-10-27): eyni köhnə sillabusu işlədən DİGƏR dilim/jurnal açılışları (eyni müəllim)
   surət almır — həmin dosyeyə ``SyllabusShare(source=legacy)`` ilə bağlanır (potok dərsi: təsdiq və plan birdir).
   Başqa müəllimin açılışı öz surətini alır (müəllim yalnız öz sillabusunu görür).
2. **Baza sillabus** (semestrsiz, fənn + müəllim): baseline-dan sonra yaranan, açılışa bağlanmayan aktiv
   sillabus — həmin (fənn, müəllim) üçün baza dosye YOXDURSA (cutover qaydası, spec §2).

Məzmun cutover-in ÖZ çeviricisi ilə qurulur (``rehearsal_syllabus_targets.build_section_data``): HTML
entity-lər açılır, həftəlik mövzular saatları ilə, peyk bölmələr öz yerinə.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

from ..rehearsal_syllabus_documents import SyllabusDocument
from ..rehearsal_syllabus_source import (
    SyllabusHeaderRow,
    _distilled_week_row,
    distilled_section_row,
    legacy_language,
)
from ..rehearsal_syllabus_targets import build_section_data
from ..syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS
from .resolve import subject_key

NOTE = "Köhnə sistemdən köçürülüb (delta {tag})"


def document_for(row: dict) -> SyllabusDocument:
    hours = row.get("ders_saati")
    header = SyllabusHeaderRow(
        legacy_pk=int(row["id"]),
        uniqid=str(row.get("uniqid") or ""),
        lesson_id=int(row.get("lesson_id") or 0),
        teacher_id=int(row.get("teacher_id") or 0),
        lesson_hours=int(hours) if isinstance(hours, int) and 0 <= hours < 1000 else 0,
        language=legacy_language(row.get("language"))[0],
        active=bool(row.get("active")),
        issues=(),
    )
    week = tuple(_distilled_week_row(int(item["id"]), item) for item in row.get("week") or ())
    sections = tuple(
        (
            table,
            tuple(distilled_section_row(int(pk), value) for pk, value in (row.get("sections") or {}).get(table, ())),
        )
        for table in SYLLABUS_SECTION_CONTRACTS
    )
    return SyllabusDocument(header=header, week=week, sections=sections)


def _chair_for(subject, author, organization):
    if subject.chair_unit_id:
        return subject.chair_unit
    if author is None:
        return None
    Membership = django_apps.get_model("organizations", "Membership")
    membership = (
        Membership.objects.filter(organization=organization, user=author, is_active=True, scope_unit__unit_type="chair")
        .select_related("scope_unit")
        .first()
    )
    return membership.scope_unit if membership else None


def _same_subject(run, syllabus_lesson_id, journal_lesson_id) -> bool:
    """Eyni legacy fənn və ya kataloqdakı DUBLİKAT (eyni adlı başqa ``lessons.id``)."""

    if syllabus_lesson_id == journal_lesson_id:
        return True
    left, right = run.legacy_subjects.get(syllabus_lesson_id), run.legacy_subjects.get(journal_lesson_id)
    return bool(left and right) and subject_key(left.get("name")) == subject_key(right.get("name"))


def import_syllabi(run, slices: dict) -> None:
    from apps.syllabus.public import import_migrated_version, link_legacy_share, syllabus_for_offering

    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    by_id = {row["id"]: row for row in run.bundle["syllabi"]}
    used: set = set()
    #: ``(legacy sillabus id, müəllim)`` → bu qaçışda köçmüş dosye — eyni cütün növbəti açılışı ona paylaşılır.
    imported: dict = {}
    stamp = timezone.now()
    note = NOTE.format(tag=run.tag)
    for entry in slices.values():
        legacy = by_id.get(entry.journal.get("sillabus_id"))
        if legacy is None:
            run.count("syllabus.journal_without_syllabus")
            continue
        used.add(legacy["id"])
        if not _same_subject(run, legacy.get("lesson_id"), entry.journal.get("lesson_id")):
            run.count("syllabus.subject_mismatch_skipped")
            continue
        section_data, _codes = build_section_data(document_for(legacy))
        for offering in entry.offerings:
            if offering.pk not in entry.writable:
                run.count("syllabus.offering_closed")
                continue
            if syllabus_for_offering(
                organization=run.organization,
                offering_id=offering.pk,
                subject_id=offering.subject_id,
                period_id=offering.period_id,
                instructor_id=offering.instructor_id,
            ):
                run.count("syllabus.offering_has_syllabus")
                continue
            author = offering.instructor
            anchor = imported.get((legacy["id"], offering.instructor_id)) if offering.instructor_id else None
            if anchor is not None:
                outcome = link_legacy_share(syllabus=anchor, offering=offering, user=run.actor)
                run.count(f"syllabus.offering_shared_{outcome}")
                if outcome == "linked":
                    run.created("syllabus_shares", offering.pk)
                    continue
            syllabus, version = import_migrated_version(
                organization=run.organization,
                subject=offering.subject,
                approved_at=stamp,
                period=offering.period,
                offering=offering,
                chair_unit=_chair_for(offering.subject, author, run.organization),
                author=author,
                section_data=section_data,
                note=note,
            )
            if offering.instructor_id:
                imported.setdefault((legacy["id"], offering.instructor_id), syllabus)
            run.created("syllabus_versions", version.pk)
            run.count("syllabus.offering_imported")
    for legacy in run.bundle["syllabi"]:
        if legacy["id"] in used or not legacy.get("is_new") or not legacy.get("active"):
            continue
        subject_row = run.legacy_subjects.get(legacy.get("lesson_id"))
        subject = run.catalog.subject_for(subject_row)[0] if subject_row else None
        author, _outcome = run.teachers.resolve(legacy.get("teacher_id"))
        if subject is None or author is None:
            run.count("syllabus.base_unresolved")
            continue
        if Syllabus.objects.filter(
            organization=run.organization, subject=subject, author=author, offering__isnull=True, period__isnull=True
        ).exists():
            run.count("syllabus.base_exists")
            continue
        section_data, _codes = build_section_data(document_for(legacy))
        _syllabus, version = import_migrated_version(
            organization=run.organization,
            subject=subject,
            approved_at=stamp,
            chair_unit=_chair_for(subject, author, run.organization),
            author=author,
            section_data=section_data,
            note=note,
        )
        run.created("syllabus_versions", version.pk)
        run.count("syllabus.base_imported")


__all__ = ["document_for", "import_syllabi"]
