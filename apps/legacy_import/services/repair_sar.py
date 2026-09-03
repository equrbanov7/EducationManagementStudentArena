"""R-9 təmiri: təmirlə yaradılmış tələbələr üçün akademik qeyd (SAR).

Qüsur (2026-09-02 reqressiya qaçışı).  ``legacy_repair_missing_accounts`` 100
tələbə hesabı yaratdı, amma **akademik qeyd yaratmadı**: hədəfdə 7 816 tələbə
hesabı, cəmi 7 703 SAR var idi (qalan 13 sətir qrupu həll olunmadığı üçün
QƏSDƏN ``staged``-dir — bax HANDOFF §2/28).  SAR olmadan tələbə nə «Fənlərim»
bölməsini, nə transkriptini görür: ``registrar.public.build_student_subjects_context``
ilk addımda ``StudentAcademicRecord`` axtarır və tapmayanda boş vəziyyət qaytarır.

Niyə faza kodunu birbaşa çağırmırıq.  ``rehearsal_sar_phase`` qərarını LEDGER
üzərindən (``run_id``-yə bağlı observation-lar) qurur və hər sətri derivation
hash-ı ilə möhürləyir; təmir anında nə run var, nə də möhür yenidən yazıla bilər
(``legacy_entity_identity_conflict``).  Ona görə bu modul EYNİ qərar qaydasını
**hədəf tərəfdən** yenidən qurur:

* qrup — ``OrgUnit(unit_type='group')``, ``settings['legacy']['id']`` açarı ilə;
* proqram — ``(specialty_unit, degree_level)`` cütü ilə (fazadakı
  ``program_index`` ilə eyni açar);
* qəbul ili — ``students.entry_year`` (4 rəqəm və attestasiya olunmuş
  diapazonda), yoxsa qrupun ``settings['admission_year']``-i, yoxsa
  ``FALLBACK_ADMISSION_YEAR`` sentineli (bax ``rehearsal_sar_phase`` A2-fix:
  «il bilinmir» ≠ «məzun»);
* kurikulum — əvvəlcə DƏQİQ ``(program, admission_year)``; yoxdursa həmin
  proqramın ən yaxın mövcud kurikulumu (``substituted``); heç biri yoxdursa
  yenisi yaradılır (``created``), çünki ``SAR.curriculum`` NOT NULL-dur.

Yerləşdirmə qərarının özü (``resolve_placement``) fazadan **olduğu kimi** idxal
olunur — iki yerdə iki fərqli qayda olmasın deyə.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction

from .legacy_text import clean_code
from .rehearsal_placement_phase import ENTRY_YEAR_MAX_LENGTH, ENTRY_YEAR_PATTERN, _apply_fin, _legacy_fin
from .rehearsal_sar_archive import FALLBACK_ADMISSION_YEAR
from .rehearsal_structure_source import MAX_ADMISSION_YEAR, MIN_ADMISSION_YEAR

AUDIT_REASON = "legacy_repair:student_record"
TABLE_HEADERS = ("legacy", "username", "qrup", "proqram", "qəbul ili", "kurikulum", "qərar")


@dataclass(frozen=True)
class SarDecision:
    legacy_pk: int
    username: str
    user_pk: int
    group_slug: str
    program_code: str
    admission_year: int
    curriculum_source: str
    action: str

    def as_row(self):
        return (
            self.legacy_pk,
            self.username,
            self.group_slug or "—",
            self.program_code or "—",
            self.admission_year or "—",
            self.curriculum_source,
            self.action,
        )


@dataclass(frozen=True)
class _Ctx:
    """``_apply_fin`` yalnız ``organization``-a baxır."""

    organization: object


def group_index(organization) -> dict[str, dict]:
    """Legacy ``groups.id`` → hədəfdəki qrup vahidinin oxunmuş atributları."""

    index: dict[str, dict] = {}
    for row in (
        django_apps.get_model("organizations", "OrgUnit")
        .objects.filter(organization=organization, unit_type="group")
        .values("id", "slug", "parent_id", "settings")
    ):
        settings = row["settings"] if isinstance(row["settings"], dict) else {}
        legacy = settings.get("legacy") if isinstance(settings.get("legacy"), dict) else {}
        legacy_id = legacy.get("id")
        if type(legacy_id) is not int:
            continue
        index[str(legacy_id)] = {
            "pk": row["id"],
            "slug": str(row["slug"] or ""),
            "specialty_unit_id": str(row["parent_id"] or ""),
            "degree_level": str(settings.get("degree_level") or ""),
            "admission_year": settings.get("admission_year"),
        }
    return index


def program_index(organization) -> dict[tuple[str, str], dict]:
    """``(specialty_unit, degree_level)`` → proqram (faza ilə eyni açar)."""

    return {
        (str(row["specialty_unit_id"]), str(row["degree_level"])): {"pk": row["id"], "code": str(row["code"])}
        for row in django_apps.get_model("registrar", "Program")
        .objects.filter(organization=organization)
        .values("id", "specialty_unit_id", "degree_level", "code")
    }


def curriculum_index(organization) -> dict[str, dict[int, object]]:
    """``program_pk`` → {qəbul ili: kurikulum pk}."""

    index: dict[str, dict[int, object]] = {}
    for row in (
        django_apps.get_model("registrar", "Curriculum")
        .objects.filter(organization=organization)
        .values("id", "program_id", "admission_year")
    ):
        index.setdefault(str(row["program_id"]), {})[int(row["admission_year"])] = row["id"]
    return index


def resolve_admission_year(entry_year_value, group: dict | None) -> int:
    """``entry_year`` → qrupun ili → sentinel (faza ilə EYNİ pilləkən)."""

    text, _truncated = clean_code(entry_year_value, max_length=ENTRY_YEAR_MAX_LENGTH)
    if ENTRY_YEAR_PATTERN.fullmatch(text) and MIN_ADMISSION_YEAR <= int(text) <= MAX_ADMISSION_YEAR:
        return int(text)
    if group is not None and type(group.get("admission_year")) is int:
        return int(group["admission_year"])
    return FALLBACK_ADMISSION_YEAR


def resolve_curriculum(organization, *, program_pk, admission_year, curricula) -> tuple[object, str]:
    """DƏQİQ il → həmin proqramın ən yaxın ili → yeni sətir (NOT NULL tələbi)."""

    by_year = curricula.setdefault(str(program_pk), {})
    if admission_year in by_year:
        return by_year[admission_year], "exact"
    if by_year:
        nearest = min(by_year, key=lambda year: (abs(year - admission_year), year))
        return by_year[nearest], "substituted"
    curriculum = django_apps.get_model("registrar", "Curriculum").objects.create(
        organization=organization, program_id=program_pk, admission_year=admission_year
    )
    by_year[admission_year] = curriculum.pk
    return curriculum.pk, "created"


def plan_records(organization, rows, *, groups=None, programs=None, curricula=None) -> list[SarDecision]:
    """``rows`` = (legacy_pk, user_pk, username, projected_row) — yazmadan qərar."""

    groups = group_index(organization) if groups is None else groups
    programs = program_index(organization) if programs is None else programs
    curricula = curriculum_index(organization) if curricula is None else curricula
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    existing = set(
        record_model.objects.filter(
            organization=organization, student_id__in=[user_pk for _pk, user_pk, _u, _r in rows]
        ).values_list("student_id", flat=True)
    )
    decisions: list[SarDecision] = []
    for legacy_pk, user_pk, username, row in rows:
        group_legacy = row["group_id"]
        group = groups.get(str(group_legacy)) if type(group_legacy) is int and group_legacy else None
        program = None
        if group is not None:
            program = programs.get((group["specialty_unit_id"], group["degree_level"]))
        admission_year = resolve_admission_year(row["entry_year"], group)
        if user_pk in existing:
            action, source = "already_present", "—"
        elif group is None:
            action, source = "skip_group_unresolved", "—"
        elif program is None:
            action, source = "skip_program_unresolved", "—"
        else:
            action, source = "create", "pending"
        decisions.append(
            SarDecision(
                legacy_pk=int(legacy_pk),
                username=username,
                user_pk=int(user_pk),
                group_slug="" if group is None else group["slug"],
                program_code="" if program is None else program["code"],
                admission_year=admission_year,
                curriculum_source=source,
                action=action,
            )
        )
    return decisions


def materialise(organization, rows, *, fin_occurrences=None) -> tuple[int, Counter]:
    """Qərarı tətbiq et: qrup + proqram + kurikulum + qəbul ili ilə SAR yaz."""

    groups = group_index(organization)
    programs = program_index(organization)
    curricula = curriculum_index(organization)
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    context = _Ctx(organization=organization)
    created = 0
    sources: Counter[str] = Counter()
    for decision, (_legacy_pk, _user_pk, _username, row) in zip(
        plan_records(organization, rows, groups=groups, programs=programs, curricula=curricula), rows
    ):
        if decision.action != "create":
            sources[decision.action] += 1
            continue
        group = groups[str(row["group_id"])]
        program = programs[(group["specialty_unit_id"], group["degree_level"])]
        with transaction.atomic():
            curriculum_pk, source = resolve_curriculum(
                organization,
                program_pk=program["pk"],
                admission_year=decision.admission_year,
                curricula=curricula,
            )
            record_model.objects.create(
                organization=organization,
                student_id=decision.user_pk,
                program_id=program["pk"],
                curriculum_id=curriculum_pk,
                group_id=group["pk"],
                admission_year=decision.admission_year,
                is_active=True,
            )
            if fin_occurrences is not None:
                _apply_fin(context, str(decision.user_pk), _legacy_fin(row["fincode"]), fin_occurrences)
        created += 1
        sources[f"curriculum_{source}"] += 1
    return created, sources


__all__ = [
    "AUDIT_REASON",
    "TABLE_HEADERS",
    "SarDecision",
    "curriculum_index",
    "group_index",
    "materialise",
    "plan_records",
    "program_index",
    "resolve_admission_year",
    "resolve_curriculum",
]
