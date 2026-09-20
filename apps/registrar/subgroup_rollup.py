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
* eyni ata (ixtisas) altında ``<baza><ayırıcı><n>`` adlı alt qruplar var — baza =
  qrup adı sondakı sektor işarəsi «az/ing/ru/en» olmadan, BOŞLUQLARA HƏSSAS DEYİL
  («233KE» ↔ «233 KE-1»); ayırıcı «-», «/» və ya boşluq («534 TB 1»); sektor
  nömrədən əvvəl və ya sonra ola bilər («234 K ing-1», «235 İT-1 az»); baza
  rəqəmlə bitirsə ayırıcı MÜTLƏQDİR («036» ↔ «0361» toqquşmasın);
* alt qrupun sektoru birləşik qrupun sektoru ilə EYNİDİR (yazılmayan = az) —
  «234 K ing» «234 K-1»-i götürmür;
* həmin alt qrupların aktiv tələbələri var.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from apps.registrar.models import AcademicStatus, CourseOffering, StudentAcademicRecord

_SECTOR = "(az|ing|ru|en)"
_SECTOR_SUFFIX = re.compile(rf"\s+{_SECTOR}$", re.IGNORECASE)
_WS = re.compile(r"\s+")
DEFAULT_SECTOR = "az"


def _norm(name: str) -> str:
    return _WS.sub(" ", str(name or "")).strip().casefold()


def base_group_name(name: str) -> str:
    """«234 K az» → «234 K»; «234 K-1» → «234 K-1» (dəyişmir)."""
    return _SECTOR_SUFFIX.sub("", _WS.sub(" ", str(name or "")).strip())


def group_sector(name: str) -> str:
    """Birləşik qrupun sektoru: «234 K ing» → ing; «234 K» → az (susmaya görə)."""
    match = _SECTOR_SUFFIX.search(_WS.sub(" ", str(name or "")).strip())
    return match.group(1).casefold() if match else DEFAULT_SECTOR


def subgroup_pattern(base: str) -> re.Pattern:
    """Bazaya görə alt qrup şablonu (ad ``_norm``-dan keçmiş olmalıdır).

    Baza boşluqlara həssas deyil (hər simvol arasında ``\\s*``); nömrədən əvvəl
    sektor və/və ya ayırıcı («-», «/», boşluq), sonra isə sektor ola bilər.
    Baza rəqəmlə bitirsə nömrədən əvvəl sektor və ya ayırıcı mütləqdir.
    """
    key = _WS.sub("", str(base or "")).casefold()
    loose = r"\s*".join(re.escape(ch) for ch in key)
    sep = r"[-/\s]"
    before = (
        rf"(?:\s*(?P<sec1>{_SECTOR})\s*{sep}?|{sep})"
        if key[-1:].isdigit()
        else rf"(?:\s*(?P<sec1>{_SECTOR}))?\s*{sep}?"
    )
    return re.compile(rf"^{loose}{before}\s*(?P<num>\d+)(?:\s*(?P<sec2>{_SECTOR}))?$")


def is_subgroup_of(combined_name: str, candidate_name: str) -> bool:
    """«234 K az» ↔ «234 K-1» ✓, «534 TB az» ↔ «534 TB 1» ✓, «233KE» ↔ «233 KE-1» ✓,
    «234 K ing» ↔ «234 K-1» ✗ (sektor fərqli), «036» ↔ «0361» ✗."""
    match = subgroup_pattern(base_group_name(combined_name)).match(_norm(candidate_name))
    if not match:
        return False
    sector = (match.group("sec1") or match.group("sec2") or DEFAULT_SECTOR).casefold()
    return sector == group_sector(combined_name)


def _sibling_groups(organization, parent_ids):
    """Verilmiş ata vahidlərin altındakı aktiv qruplar (bir sorğu)."""
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return list(
        OrgUnit.objects.filter(
            organization=organization, parent_id__in=parent_ids, is_active=True, unit_type="group"
        ).only("id", "name", "parent_id", "settings")
    )


def _trail_parent(unit) -> str:
    raw = unit.settings if isinstance(unit.settings, dict) else {}
    return str(raw.get("parent_group") or "")


def subgroup_map(organization, parents) -> dict:
    """``{ana_qrup_pk: [alt qruplar]}`` — reyestr bölməsinin ``settings.parent_group``
    izi VƏ YA ad şablonu (`is_subgroup_of`) ilə, eyni ata (ixtisas) altında.
    İmtahan təyinatı: «234 K az» seçiləndə 234 K-1 / 234 K-2 də düşür."""
    parents = [p for p in parents if getattr(p, "parent_id", None)]
    if not parents:
        return {}
    siblings = _sibling_groups(organization, {p.parent_id for p in parents})
    out: dict = {}
    for parent in parents:
        found = []
        for sibling in siblings:
            if sibling.pk == parent.pk or sibling.parent_id != parent.parent_id:
                continue
            if _trail_parent(sibling) == str(parent.pk) or is_subgroup_of(parent.name, sibling.name):
                found.append(sibling)
        if found:
            out[parent.pk] = sorted(found, key=lambda u: _norm(u.name))
    return out


def subgroup_units(organization, parents) -> list:
    """Verilmiş qrupların bütün alt qrupları (təkrarsız siyahı)."""
    seen: set = set()
    out: list = []
    for units in subgroup_map(organization, parents).values():
        for unit in units:
            if unit.pk not in seen:
                seen.add(unit.pk)
                out.append(unit)
    return out


def parent_group_candidates(organization, group) -> list:
    """Alt qrupun ANA qrup namizədləri (eyni ata altında): ``settings.parent_group``
    izi və ya ad şablonu — «234 K-1» → [«234 K az»]. Tələbənin imtahan görünürlüyü
    üçün: ana qrupa təyin olunmuş imtahan alt qrupun tələbəsinə də açıqdır."""
    if group is None or not getattr(group, "parent_id", None):
        return []
    trail = _trail_parent(group)
    out = []
    for sibling in _sibling_groups(organization, {group.parent_id}):
        if sibling.pk == group.pk:
            continue
        if trail == str(sibling.pk) or is_subgroup_of(sibling.name, group.name):
            out.append(sibling)
    return out


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
                siblings = OrgUnit.objects.filter(
                    organization=organization, parent_id=group.parent_id, is_active=True, unit_type="group"
                ).exclude(pk=group.pk)
                for sibling in siblings.order_by("name"):
                    if not is_subgroup_of(group.name, sibling.name):
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
