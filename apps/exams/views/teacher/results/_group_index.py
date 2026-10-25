"""results paketi — imtahan iştirakçılarının QRUP indeksi (sətir sütunu + süzgəc + say).

2026-10-25 (sahib: «nəticələrə baxanda qrup göstərmirdi, qrupa görə filtrdə gəlmirdi»).

Kök səbəb (prod kopyası, «Js Loop», 28 cəhd):
* cədvəldə qrup sütunu ümumiyyətlə yox idi — qrup yalnız Excel ixracında idi;
* seçicidə imtahana təyin olunmuş ANA qruplar («234 İT az») və cəhdi olmayan alt qruplar
  sayısız görünürdü; tələbələrin akademik qeydi isə ALT qrupdadır («234 K-1»), süzgəc
  qeydin qrupunu birbaşa müqayisə etdiyi üçün ana qrup seçiləndə nəticə 0 gəlirdi, cəhd
  edənlərin ana qrupu («234 K az») isə siyahıda heç yox idi.

Bu modul imtahanın (sınaq olmayan) cəhd edənləri üçün TƏK dəfə (sabit sorğu sayı, sətir
sayından asılı deyil) qurulur və hər üç yerdə eyni qaydanı verir:
* tələbənin qrupu = ən uyğun akademik qeydi: aktiv + «enrolled» → aktiv → digər (xaric
  olunmuşun köhnə qrupu da görünür ki, nəticə «qrupsuz» qalmasın); qrupun reyestr mənbəyi
  ``StudentAcademicRecord.group`` (bax ``unit_assignment``) — sətir, süzgəc, say, ixrac eyni;
* alt qrup ↔ ana qrup: ``settings.parent_group`` izi və ya ad şablonu (registrar
  ``subgroup_rollup.is_subgroup_of``) — ana qrup seçiləndə alt qrupların tələbələri də düşür;
* seçimlər: cəhd edənlərin qrupları + onların ana qrupları + təyin olunmuş qruplar +
  köhnə kohortlar + «Qrupsuz»; hər biri cəhd sayı ilə.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db.models import Count, Q
from django.utils.translation import pgettext

from apps.exams.domain.unit_scope_filters import parse_unit_value, unit_filter_value
from apps.exams.models import StudentGroup
from apps.organizations.models import OrgUnit
from core.constants import OrgUnitType

KIND_COHORT = "cohort"
KIND_UNIT = "unit"
KIND_NONE = "none"
NO_GROUP_VALUE = "none"


@dataclass(frozen=True)
class GroupOption:
    """Seçicinin `id` / `name` cütü + mənbə növü, cəhd sayı və ana/alt qrup izi."""

    id: str
    name: str
    kind: str
    pk: object
    count: int = 0
    #: Ana qrupdursa — onun alt qruplarının adları (seçicidə ipucu).
    subgroup_names: tuple = ()
    #: Yalnız cəhd edənlərin alt qrupundan TÖRƏNMİŞ ana qrup (təyin olunmayıb, öz tələbəsi yoxdur).
    derived: bool = False

    @property
    def is_unit(self) -> bool:
        return self.kind == KIND_UNIT

    @property
    def is_none(self) -> bool:
        return self.kind == KIND_NONE


@dataclass(frozen=True)
class UserGroup:
    """Sətirdə göstərilən qrup: qeydin qrupu + (alt qrupdursa) ana qrupu."""

    unit_pk: object
    name: str
    parent_name: str = ""
    is_active_record: bool = True


@dataclass
class ExamGroupIndex:
    options: list[GroupOption] = field(default_factory=list)
    user_group: dict = field(default_factory=dict)  # user_id → UserGroup
    user_cohorts: dict = field(default_factory=dict)  # user_id → [kohort adı]
    unit_children: dict = field(default_factory=dict)  # ana qrup pk → {alt qrup pk}
    cohort_users: dict = field(default_factory=dict)  # kohort pk → {user_id}
    attempt_users: frozenset = frozenset()

    def option(self, value: str) -> GroupOption | None:
        return next((opt for opt in self.options if opt.id == value), None)

    def user_ids_for(self, option: GroupOption) -> set:
        """Seçimə uyğun cəhd edənlər (ana qrup → alt qrupları da)."""
        if option.is_none:
            return {uid for uid in self.attempt_users if uid not in self.user_group}
        if not option.is_unit:
            return set(self.cohort_users.get(option.pk, ()))
        units = {option.pk, *self.unit_children.get(option.pk, ())}
        return {uid for uid, group in self.user_group.items() if group.unit_pk in units}

    def group_names(self, user_id) -> list[str]:
        """İxrac üçün: reyestr qrupu + kohortlar (ada görə)."""
        names = list(self.user_cohorts.get(user_id, ()))
        group = self.user_group.get(user_id)
        if group is not None:
            names.append(group.name)
        return sorted(set(names), key=str.casefold)

    @property
    def grant_options(self) -> list[GroupOption]:
        """«Qrupa yenidən cəhd» seçicisi: real (törənməmiş) reyestr qrupları + kohortlar."""
        return [opt for opt in self.options if not opt.is_none and not opt.derived]


def _record_model():
    return django_apps.get_model("registrar", "StudentAcademicRecord")


def _subgroup_rollup():
    from apps.registrar.public import subgroup_rollup

    return subgroup_rollup


def _record_rank(row) -> tuple:
    # Aktiv + enrolled → aktiv → qeyri-aktiv; bərabərlikdə ən yeni qeyd.
    enrolled = row["status"] == "enrolled"
    return (bool(row["is_active"]) and enrolled, bool(row["is_active"]), row["created_at"])


def _best_records(user_ids) -> dict:
    """user_id → ən uyğun qrup qeydi (`group_id`, `is_active`) — 1 sorğu."""
    best: dict = {}
    if not user_ids:
        return best
    rows = (
        _record_model()
        .objects.filter(student_id__in=user_ids, group__isnull=False)
        .values("student_id", "group_id", "is_active", "status", "created_at")
    )
    for row in rows:
        current = best.get(row["student_id"])
        if current is None or _record_rank(row) > _record_rank(current):
            best[row["student_id"]] = row
    return best


def _trail_parent(unit) -> str:
    raw = unit.settings if isinstance(unit.settings, dict) else {}
    return str(raw.get("parent_group") or "")


def _is_child_of(child, parent) -> bool:
    if child.pk == parent.pk or child.parent_id != parent.parent_id:
        return False
    return _trail_parent(child) == str(parent.pk) or _subgroup_rollup().is_subgroup_of(parent.name, child.name)


def _unit_family(exam, unit_pks) -> tuple[dict, dict]:
    """(pk → OrgUnit, ana pk → {alt pk}) — verilmiş qruplar + eyni ixtisasdakı qardaşlar (2 sorğu)."""
    only = ("id", "name", "parent_id", "settings", "organization_id")
    base = OrgUnit.objects.filter(unit_type=OrgUnitType.GROUP)
    org_id = getattr(exam, "organization_id", None)
    if org_id:
        base = base.filter(organization_id=org_id)
    units = {unit.pk: unit for unit in base.filter(pk__in=unit_pks).only(*only)} if unit_pks else {}
    parent_ids = {unit.parent_id for unit in units.values() if unit.parent_id}
    siblings = list(base.filter(parent_id__in=parent_ids).only(*only)) if parent_ids else []
    children: dict = {}
    for unit in list(units.values()):
        for sibling in siblings:
            if _is_child_of(unit, sibling):  # unit alt qrupdur, sibling — ana
                children.setdefault(sibling.pk, set()).add(unit.pk)
                units.setdefault(sibling.pk, sibling)
            elif _is_child_of(sibling, unit):  # unit ana qrupdur
                children.setdefault(unit.pk, set()).add(sibling.pk)
    return units, children


def _cohorts(exam, attempt_user_ids) -> tuple[list, dict]:
    """Köhnə kohortlar (`StudentGroup`) + üzv cəhd edənləri (2 sorğu)."""
    qs = StudentGroup.objects.filter(Q(exams=exam) | Q(students__id__in=attempt_user_ids))
    org_id = getattr(exam, "organization_id", None)
    if org_id:
        qs = qs.filter(organization_id=org_id)
    cohorts = list(qs.distinct().order_by("name").only("id", "name"))
    members: dict = {}
    if cohorts and attempt_user_ids:
        through = StudentGroup.students.through
        for cohort_id, user_id in through.objects.filter(
            studentgroup_id__in=[c.pk for c in cohorts], user_id__in=attempt_user_ids
        ).values_list("studentgroup_id", "user_id"):
            members.setdefault(cohort_id, set()).add(user_id)
    return cohorts, members


def build_group_index(exam) -> ExamGroupIndex:
    """İmtahan üçün qrup indeksi — sabit sorğu sayı (cəhd sayından asılı deyil)."""
    attempts_by_user = dict(
        exam.attempts.exclude(is_trial=True).values("user_id").annotate(n=Count("id")).values_list("user_id", "n")
    )
    attempt_users = frozenset(attempts_by_user)
    best = _best_records(attempt_users)
    assigned_pks = set(exam.allowed_units.filter(unit_type=OrgUnitType.GROUP).values_list("pk", flat=True))
    present_pks = {row["group_id"] for row in best.values()}
    units, children = _unit_family(exam, present_pks | assigned_pks)
    parent_of = {child: parent for parent, kids in children.items() for child in kids}

    user_group: dict = {}
    for user_id, row in best.items():
        unit = units.get(row["group_id"])
        if unit is None:  # başqa təşkilatın qrupu — göstərilmir
            continue
        parent = units.get(parent_of.get(unit.pk))
        user_group[user_id] = UserGroup(
            unit_pk=unit.pk,
            name=unit.name,
            parent_name=parent.name if parent is not None else "",
            is_active_record=bool(row["is_active"]),
        )

    unit_counts: Counter = Counter()
    for user_id, group in user_group.items():
        unit_counts[group.unit_pk] += attempts_by_user[user_id]
    option_pks = {pk for pk in present_pks | assigned_pks if pk in units}
    option_pks |= {parent_of[pk] for pk in present_pks if pk in parent_of}

    options = []
    for pk in option_pks:
        unit = units[pk]
        kids = children.get(pk, set())
        count = unit_counts[pk] + sum(unit_counts[kid] for kid in kids)
        options.append(
            GroupOption(
                id=unit_filter_value(pk),
                name=unit.name,
                kind=KIND_UNIT,
                pk=pk,
                count=count,
                subgroup_names=tuple(sorted((units[kid].name for kid in kids if kid in units), key=str.casefold)),
                derived=pk not in present_pks and pk not in assigned_pks,
            )
        )

    cohorts, cohort_users = _cohorts(exam, attempt_users)
    user_cohorts: dict = {}
    for cohort in cohorts:
        members = cohort_users.get(cohort.pk, set())
        for user_id in members:
            user_cohorts.setdefault(user_id, []).append(cohort.name)
        options.append(
            GroupOption(
                id=str(cohort.pk),
                name=cohort.name,
                kind=KIND_COHORT,
                pk=cohort.pk,
                count=sum(attempts_by_user.get(uid, 0) for uid in members),
            )
        )
    options.sort(key=lambda option: (option.name.casefold(), option.kind))

    no_group = [uid for uid in attempt_users if uid not in user_group]
    if no_group:
        options.append(
            GroupOption(
                id=NO_GROUP_VALUE,
                name=pgettext("exams.template.teacher_exam_results", "Qrupsuz"),
                kind=KIND_NONE,
                pk=None,
                count=sum(attempts_by_user[uid] for uid in no_group),
            )
        )
    return ExamGroupIndex(
        options=options,
        user_group=user_group,
        user_cohorts=user_cohorts,
        unit_children=children,
        cohort_users=cohort_users,
        attempt_users=attempt_users,
    )


def normalize_group_value(raw) -> str:
    """GET/POST dəyəri → seçici dəyəri (`"<int>"` / `"unit:<uuid>"` / `"none"`); tanınmayan → ""."""
    value = str(raw or "").strip()
    if not value or value.lower() == "all":
        return ""
    if value.lower() == NO_GROUP_VALUE:
        return NO_GROUP_VALUE
    if value.isdigit():
        return str(int(value))
    unit_id = parse_unit_value(value)
    return unit_filter_value(unit_id) if unit_id else ""


def resolve_group_options(index: ExamGroupIndex, raw_values) -> list[GroupOption]:
    """Yalnız bu imtahanın seçim siyahısındakı dəyərlər (yad id → atılır), sıra saxlanılır."""
    picked: list[GroupOption] = []
    for raw in raw_values or ():
        for part in str(raw or "").split(","):
            option = index.option(normalize_group_value(part))
            if option is not None and option not in picked:
                picked.append(option)
    return picked


__all__ = [
    "ExamGroupIndex",
    "GroupOption",
    "KIND_COHORT",
    "KIND_NONE",
    "KIND_UNIT",
    "NO_GROUP_VALUE",
    "UserGroup",
    "build_group_index",
    "normalize_group_value",
    "resolve_group_options",
]
