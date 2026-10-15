"""Tapşırıqdakı RƏSMİ seçmə blok seçimi → qrupun seçimi (2026-10-15).

PROBLEM
-------
TAPŞIRIQ sətri «ATMF IX blok: 1.Fotosintez 2.Virusologiya 3.Parazitologiya» rəsmi
sənəddəki işarə (qalın / «+» / operator override — :mod:`.task_workbook_choice`) ilə
seçilmiş fənni (``row.subject``) daşıyır, amma (ixtisas, fənn) cütü təsdiqlənmiş planda
YALNIZ seçmə olduğu üçün :mod:`.offering_sync` açılış yaratmırdı (``elective_pending``):
jurnal yox idi, cədvəl idxalı hər ATMF xanasını ``subject_not_in_group`` verirdi.

QAYDA
-----
Bu universitetdə seçmə QRUP səviyyəsindədir (``registrar.GroupElectiveChoice``).
Rəsmi tapşırıqdakı seçim qrupun qərarıdır:

* sətir blok mətnidir (``is_block(subject_text)``) və fənni doludur → qrupun hər biri
  üçün planın blokunda (``CurriculumSubject.elective_group``) qərar yazılır —
  ``registrar.services.choose_group_elective`` (rəsmi yol: qərar + qrupun
  qeydiyyatı ``elective``), sonra qrupun qalan aktiv tələbələri də yazılır;
* həmin blok üçün qrupun BAŞQA fənnə qərarı varsa əzilmir → ``elective_choice_conflict``;
* fənn planın seçmə blokunda deyilsə — məcburi fənn kimi açılır (tapşırıq rəsmi
  mənbədir; :mod:`.offering_sync` bunu ``elective_from_task`` kimi sayır);
* blok mətni olmayan (seçimi sənəddən gəlməyən) seçmə sətir əvvəlki kimi gözləyir.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps

from .task_workbook_parsing import is_block


def is_official_choice(rows) -> bool:
    """Hədəfin sətirlərindən biri rəsmi seçmə blok sətridir (fənn sənəddən seçilib)."""
    return any(row.subject_id and is_block(row.subject_text or "") for row in rows)


class BlockIndex:
    """Seçmə bloklar + qrupun mövcud qərarları — toplu SELECT (hədəf sayından asılı deyil)."""

    def __init__(self, organization_id, targets):
        self.organization_id = organization_id
        groups = {entry["group"].pk: entry["group"] for entry in targets.values()}
        specialty_ids = {group.parent_id for group in groups.values() if group.parent_id}
        subject_ids = {key[0] for key in targets}
        period_ids = {key[1] for key in targets}
        self.options = self._options(specialty_ids, subject_ids)
        self.group_curricula = self._group_curricula(groups)
        self.choices = self._choices(groups, period_ids)
        Subject = django_apps.get_model("registrar", "Subject")
        self.subjects = {s.pk: s for s in Subject.objects.filter(organization_id=organization_id, pk__in=subject_ids)}

    def _options(self, specialty_ids, subject_ids) -> dict:
        if not specialty_ids:
            return {}
        CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
        found: dict = {}
        rows = (
            CurriculumSubject.objects.filter(
                organization_id=self.organization_id,
                curriculum__status="approved",
                curriculum__is_active=True,
                curriculum__program__specialty_unit_id__in=specialty_ids,
                subject_id__in=subject_ids,
                is_elective=True,
            )
            .exclude(elective_group="")
            .select_related("curriculum", "curriculum__program")
            .order_by("-curriculum__admission_year", "-curriculum__version", "semester_number")
        )
        for row in rows:
            found.setdefault((row.curriculum.program.specialty_unit_id, row.subject_id), []).append(row)
        return found

    def _group_curricula(self, groups) -> dict:
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        counts: dict = {}
        for group_id, curriculum_id in Record.objects.filter(
            organization_id=self.organization_id, group_id__in=list(groups), is_active=True, curriculum__isnull=False
        ).values_list("group_id", "curriculum_id"):
            counts.setdefault(group_id, Counter())[curriculum_id] += 1
        return {group_id: [cid for cid, _ in counter.most_common()] for group_id, counter in counts.items()}

    def _choices(self, groups, period_ids) -> dict:
        Choice = django_apps.get_model("registrar", "GroupElectiveChoice")
        return {
            (group_id, period_id, block): subject_id
            for group_id, period_id, block, subject_id in Choice.objects.filter(
                organization_id=self.organization_id, group_id__in=list(groups), period_id__in=period_ids
            ).values_list("group_id", "period_id", "elective_group", "chosen_subject_id")
        }

    def block_for(self, group, subject_id):
        """Qrupun planındakı seçmə blok sətri (``CurriculumSubject``) — tələbələrin planı üstündür."""
        options = self.options.get((group.parent_id, subject_id)) or []
        for curriculum_id in self.group_curricula.get(group.pk, ()):
            for option in options:
                if option.curriculum_id == curriculum_id:
                    return option
        return options[0] if options else None

    def existing_choice(self, group_id, period_id, elective_group):
        return self.choices.get((group_id, period_id, elective_group))


def record_group_choice(*, organization, group, period, option, subject, decided_by) -> int:
    """Rəsmi qeydiyyat yolu: ``choose_group_elective`` (qərar + qrupun ``elective`` qeydiyyatı).

    Qeydiyyat pəncərəsi tətbiq olunmur — tapşırıq rəsmi sənəddir (staff override)."""
    from apps.registrar.public import services as registrar_services

    _choice, enrolled = registrar_services.choose_group_elective(
        organization=organization,
        group=group,
        curriculum=option.curriculum,
        period=period,
        elective_group=option.elective_group,
        subject=subject,
        decided_by=decided_by,
        enforce_window=False,
    )
    return int(enrolled or 0)


__all__ = ["BlockIndex", "is_official_choice", "record_group_choice"]
