"""Alt qrupları BİRLƏŞİK qrupun jurnalına yığmaq (sahib qərarı 2026-09-20).

Legacy köçürmədə bəzi axınlar iki qrupa bölünüb («234 K-1», «234 K-2»), TAPŞIRIQ
kitabçası isə dərsi BİRLƏŞİK qrupa («234 K az») verir. Nəticədə birləşik qrupun
açılışları var, amma onun öz tələbəsi YOXDUR — jurnal «0» göstərir. Sahib: «ola
bilsin ki 234K1, 234K2 kimi qalsın uşaqlar sistemdə; onları birləşik bu qrupda
qeyd et».

Tələbələr qruplarını DƏYİŞMİR (reyestr trigger-i qrup yazısını qoruyur — bax
``student_registry_action kind=group_transfer``); onlar birləşik açılışa
«alt qrupdan əlavə» kimi düşür — :func:`apps.registrar.guest_roster.add_guest_student`
provenansı (``source_group``) və audit izini yazır, «Fənlərim»/jurnal çipi isə
mənbə qrupu göstərir. Yəni bu, koordinatorun əl ilə etdiyi əməlin TOPLU halıdır,
yeni yazı yolu deyil.

Namizəd qaydası (fail-closed):
* açılış aktivdir, dövrü verilən dövrdür, qrupu var;
* qrupun AKTİV+ENROLLED akademik qeydi YOXDUR;
* eyni ata (ixtisas) altında ``<baza>-<n>`` adlı alt qruplar var (baza = qrup adı
  sondakı sektor işarəsi «az/ing/ru/en» olmadan; alt qrup adı sektor ilə də ola
  bilər: «234 K az-1»);
* həmin alt qrupların aktiv tələbələri var.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from apps.registrar.models import AcademicStatus, CourseOffering, StudentAcademicRecord

_SECTOR_SUFFIX = re.compile(r"\s+(az|ing|ru|en)$", re.IGNORECASE)
_WS = re.compile(r"\s+")


def _norm(name: str) -> str:
    return _WS.sub(" ", str(name or "")).strip().casefold()


def base_group_name(name: str) -> str:
    """«234 K az» → «234 K»; «234 K-1» → «234 K-1» (dəyişmir)."""
    return _SECTOR_SUFFIX.sub("", _WS.sub(" ", str(name or "")).strip())


def subgroup_pattern(base: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(_norm(base))}(\s+(az|ing|ru|en))?-\d+$")


@dataclass
class Candidate:
    offering: CourseOffering
    subgroups: list = field(default_factory=list)  # OrgUnit-lər
    records: list = field(default_factory=list)  # StudentAcademicRecord-lar (mənbə qrupu ilə)


def _active_records(organization, group):
    return list(
        StudentAcademicRecord.objects.filter(
            organization=organization, group=group, is_active=True, status=AcademicStatus.ENROLLED
        )
        .select_related("student", "group")
        .order_by("student__last_name", "student__first_name")
    )


def find_candidates(organization, period) -> list[Candidate]:
    """Dövrün «tələbəsiz birləşik qrup» açılışları + onların alt qrup tələbələri."""
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    offerings = (
        CourseOffering.objects.filter(organization=organization, period=period, is_active=True, group__isnull=False)
        .select_related("group", "subject", "period")
        .order_by("group__name", "subject__code")
    )
    cache: dict = {}
    out: list[Candidate] = []
    for offering in offerings:
        group = offering.group
        if group.pk not in cache:
            own = StudentAcademicRecord.objects.filter(
                organization=organization, group=group, is_active=True, status=AcademicStatus.ENROLLED
            ).exists()
            subgroups, records = [], []
            if not own and group.parent_id:
                pattern = subgroup_pattern(base_group_name(group.name))
                siblings = OrgUnit.objects.filter(
                    organization=organization, parent_id=group.parent_id, is_active=True, unit_type="group"
                ).exclude(pk=group.pk)
                for sibling in siblings.order_by("name"):
                    if not pattern.match(_norm(sibling.name)):
                        continue
                    rows = _active_records(organization, sibling)
                    if rows:
                        subgroups.append(sibling)
                        records.extend(rows)
            cache[group.pk] = (subgroups, records)
        subgroups, records = cache[group.pk]
        if subgroups:
            out.append(Candidate(offering=offering, subgroups=subgroups, records=records))
    return out


def rollup(organization, period, *, by_user, reason: str, dry: bool = False) -> dict:
    """Namizədləri jurnala «alt qrupdan əlavə» ilə yaz. İdempotent: artıq
    jurnalda olan tələbə ötürülür. Qaytarır hesabat lüğəti."""
    from apps.registrar import guest_roster

    report = {"offerings": 0, "added": 0, "skipped_present": 0, "errors": [], "rows": []}
    for cand in find_candidates(organization, period):
        report["offerings"] += 1
        present = guest_roster.enrolled_student_ids(cand.offering)
        for record in cand.records:
            if record.student_id in present:
                report["skipped_present"] += 1
                continue
            label = (
                f"{cand.offering.group.name} · {cand.offering.subject.code} ← {record.group.name} · {record.student}"
            )
            if dry:
                report["added"] += 1
                report["rows"].append(label)
                continue
            try:
                guest_roster.add_guest_student(
                    offering=cand.offering,
                    student=record.student,
                    by_user=by_user,
                    source_group=record.group,
                    reason=reason,
                )
                report["added"] += 1
                report["rows"].append(label)
            except ValidationError as exc:
                report["errors"].append(f"{label}: {'; '.join(exc.messages)}")
    return report
