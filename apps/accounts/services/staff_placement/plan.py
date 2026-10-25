"""Yerləşdirmə PLANI — kim hansı kafedrada olmalıdır, sistemdə harada görünür, nə dəyişəcək (YAZMIR).

Qaydalar (sahib 2026-10-25):

* **Gözlənilən ştat (əsas) kafedrası**: struktur siyahısında kafedranın müdiri/laborantı/müəllimi → həmin kafedra;
  yoxsa Forma 7-də ştat (ştat / yarım ştat) sətrinin TƏK kafedrası; yoxsa Forma 7-nin TƏK kafedrası (saathesabı).
  Bir neçə ştat kafedrası → avtomatik seçilmir (qərar siyahısı).
* **Gözlənilən tədris kafedraları** = Forma 7 + kafedranın dərs yükü faylı. Hər birində aktiv müəllim-rollu üzvlük
  olmalıdır — yoxdursa ``JOIN`` (``workload.join_chair_as_teacher`` — ƏLAVƏ, ``is_primary=False``). Dərs yükü olan
  dekan / tədris şöbəsi / imtahan mərkəzi əməkdaşı belə «Müəllimlər» siyahısına düşür.
* **Ştat kafedrası səhvdirsə** və əsas (``is_primary``) üzvlük səhv kafedradakı MÜƏLLİM üzvlüyüdürsə → ``PRIMARY``
  (əsaslıq düzgün kafedradakı müəllim üzvlüyünə keçir; dekan/inzibati əsas üzvlüyə toxunulmur).
* **Başqa kafedraya düşmə**: Forma 7-də olan şəxsin siyahıda/yük faylında OLMAYAN kafedradakı sırf ``teacher``
  üzvlüyü, həmin kafedrada bu il dərs yükü və cari jurnalı yoxdursa → ``DEACTIVATE`` (sonra yenidən aktivləşə bilər).
  Kafedrası məlum olmayan cari jurnal varsa heç nə deaktiv edilmir (ehtiyat).
* Siyahılarda kafedra kimi OLMAYAN kafedra tipli bölmə — ``unlisted_chairs`` (YALNIZ hesabat: üzv / tapşırıq /
  açılış sayı; bölmənin birləşdirilməsi və ya arxivi sahibin qərarıdır).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from ..people.constants import TEACHER_ROLE_NAMES
from ..teacher_roster.matching import MATCHED_STATUSES, AccountIndex, match_row
from ..teacher_roster.protection import is_student, load_accounts
from . import facts as facts_mod
from .sources import KIND_HOURLY, SOURCE_FORMA7, SOURCE_LOAD, SOURCE_STRUCTURE

JOIN = "join"
PRIMARY = "primary"
DEACTIVATE = "deactivate"

#: Struktur siyahısındakı bu rollar şəxsin kafedrasını (ştatını) göstərir.
CHAIR_STAFF_ROLES = frozenset({"chair_head", "lab_assistant", "teacher"})
#: «Köhnəlmiş rol» yoxlaması — bu rollar struktur siyahısı ilə tam üst-üstə düşməlidir.
CHECKED_ROLES = ("dean", "vice_dean", "chair_head", "lab_assistant", "tutor")
PURE_TEACHER_ROLE = "teacher"


@dataclass
class Action:
    kind: str
    user_id: int
    unit_id: str | None = None
    membership_id: str | None = None
    note: str = ""


@dataclass
class PersonPlan:
    account: object
    evidence: list = field(default_factory=list)
    expected_home: str | None = None
    home_reason: str = ""
    home_options: list = field(default_factory=list)
    expected_chairs: set = field(default_factory=set)
    current_home: str | None = None
    final_home: str | None = None
    actions: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)  # [Account] — eyni adlı digər heyət hesabları

    @property
    def user_id(self):
        return self.account.user_id

    @property
    def sources(self) -> set:
        return {item.source for item in self.evidence}


@dataclass
class Plan:
    organization: object
    academic_year: str
    kafedra_types: tuple
    sources: object
    facts: object
    people: dict  # user_id → PersonPlan
    unmatched: list  # [(Evidence, RowMatch)]
    listed_chairs: set
    unlisted_chairs: list  # [{"id", "name", "members", "tasks", "offerings", "archive"}]
    roles_missing: list  # [(PersonPlan|None, Evidence)]
    roles_stale: list  # [(user_id, rol, bölmə id)]
    incomplete_accounts: list  # [dict]
    actions: list = field(default_factory=list)
    dormant_ids: set = field(default_factory=set)  # yalnız deaktiv üzvlüyü olan (tutuşmuş) hesablar
    accounts: dict = field(default_factory=dict)  # user_id → Account (hesabat üçün)


def _home(rows, kafedra_types):
    from apps.workload.public import home_chair_rank

    chairs = [row for row in rows if row["scope_unit__unit_type"] in kafedra_types]
    if not chairs:
        return None
    return min(chairs, key=lambda row: home_chair_rank(row, kafedra_types))["scope_unit_id"]


def _expected_home(person: PersonPlan, kafedra_types) -> None:
    structure = {
        item.unit_id
        for item in person.evidence
        if item.source == SOURCE_STRUCTURE and item.kind in CHAIR_STAFF_ROLES and item.unit_type in kafedra_types
    }
    staff = {item.unit_id for item in person.evidence if item.source == SOURCE_FORMA7 and item.kind != KIND_HOURLY} - {
        None
    }
    any_forma7 = {item.unit_id for item in person.evidence if item.source == SOURCE_FORMA7} - {None}
    for reason, options in (("structure", structure), ("forma7_staff", staff), ("forma7", any_forma7)):
        if len(options) == 1:
            person.expected_home, person.home_reason = next(iter(options)), reason
            return
        if len(options) > 1:
            person.home_options, person.home_reason = sorted(options), f"{reason}_multiple"
            return


def _teaching_units(rows) -> set:
    return {row["scope_unit_id"] for row in rows if row["role__name"] in TEACHER_ROLE_NAMES and row["scope_unit_id"]}


def _plan_person(person: PersonPlan, facts, kafedra_types, listed) -> None:
    user_id = person.user_id
    rows = [dict(row) for row in facts.memberships.get(user_id, [])]
    person.current_home = _home(rows, kafedra_types)
    _expected_home(person, kafedra_types)
    person.expected_chairs = {
        item.unit_id for item in person.evidence if item.source in (SOURCE_FORMA7, SOURCE_LOAD) and item.unit_id
    }
    if person.expected_home:
        person.expected_chairs.add(person.expected_home)
    teaching = _teaching_units(rows)

    # 1) Gözlənilən hər tədris kafedrasında müəllim üzvlüyü.
    for unit_id in sorted(person.expected_chairs):
        if facts.unit_types.get(unit_id) not in kafedra_types:
            continue
        if unit_id not in teaching:
            person.actions.append(Action(JOIN, user_id, unit_id))
            rows.append(
                {
                    "id": None,
                    "user_id": user_id,
                    "role__name": PURE_TEACHER_ROLE,
                    "role__level": 50,
                    "scope_unit_id": unit_id,
                    "scope_unit__unit_type": facts.unit_types.get(unit_id),
                    "is_primary": False,
                    "created_at": None,
                }
            )
            teaching.add(unit_id)

    if person.expected_home and person.current_home != person.expected_home:
        primary = next((row for row in rows if row["is_primary"]), None)
        if (
            primary is not None
            and primary["role__name"] in TEACHER_ROLE_NAMES
            and primary["scope_unit__unit_type"] in kafedra_types
            and primary["scope_unit_id"] != person.expected_home
        ):
            target = next(
                (
                    row
                    for row in rows
                    if row["scope_unit_id"] == person.expected_home and row["role__name"] in TEACHER_ROLE_NAMES
                ),
                None,
            )
            if target is not None:
                person.actions.append(
                    Action(PRIMARY, user_id, person.expected_home, str(target["id"]) if target["id"] else None)
                )
                primary["is_primary"] = False
                target["is_primary"] = True

    # 3) Başqa kafedraya düşmə — yalnız Forma 7-də olan şəxs üçün (yeri sənədlə məlumdur).
    #    Kafedrası məlum olmayan cari jurnal varsa YALNIZ siyahıda olmayan / arxivlənmiş kafedradakı üzvlük düşür
    #    (jurnalın kafedrası onda ştat kafedrasından — düzgün kafedradan — həll olunur).
    if SOURCE_FORMA7 in person.sources:
        journal = facts.journal_chairs.get(user_id, set())
        unknown = None in journal
        if unknown:
            person.notes.append("journal_chair_unknown")
        keep = person.expected_chairs | set(facts.load_chairs.get(user_id, {})) | (journal - {None})
        for row in rows:
            unit_id = row["scope_unit_id"]
            if (
                row["id"] is None
                or row["role__name"] != PURE_TEACHER_ROLE
                or row["scope_unit__unit_type"] not in kafedra_types
                or unit_id in keep
            ):
                continue
            if unknown and unit_id in listed and unit_id not in facts.inactive_units:
                continue
            if row["is_primary"]:
                person.notes.append("stray_primary_kept")  # əsaslıq köçmədisə əsas üzvlük deaktiv edilmir
                continue
            person.actions.append(Action(DEACTIVATE, user_id, unit_id, str(row["id"])))
            row["_gone"] = True
    remaining = [row for row in rows if not row.get("_gone")]
    person.final_home = _home(remaining, kafedra_types)
    if person.expected_home and person.final_home != person.expected_home:
        person.notes.append("home_unresolved")
    if person.home_options and person.final_home not in person.home_options:
        person.notes.append("home_ambiguous")


def _dormant_accounts(organization, known_ids) -> list:
    """Təşkilatda YALNIZ deaktiv müəllim üzvlüyü qalmış hesablar (məs. arxivlənmiş kafedradan düşənlər) — tutuşdurmaya
    qatılır ki, Forma 7-dəki adam «hesab yoxdur» sayılıb ikinci hesab açılmasın; tapılarsa kafedraya qaytarılır."""
    from django.contrib.auth import get_user_model

    from apps.organizations.models import Membership

    from ..teacher_roster.matching import Account

    roles = defaultdict(set)
    for user_id, role_name in (
        Membership.objects.filter(organization=organization, is_active=False, role__name__in=TEACHER_ROLE_NAMES)
        .exclude(user_id__in=list(known_ids))
        .values_list("user_id", "role__name")
        .order_by()
    ):
        roles[user_id].add(role_name)
    accounts = []
    fields = ("id", "username", "first_name", "last_name", "is_active", "is_superuser", "is_staff")
    profile_fields = ("profile__patronymic", "profile__role", "profile__is_deleted")
    for row in get_user_model().objects.filter(pk__in=list(roles)).values_list(*fields, *profile_fields):
        user_id, username, first, last, active, superuser, staff, patronymic, role, deleted = row
        accounts.append(
            Account(
                user_id=user_id,
                username=username,
                last=last or "",
                first=first or "",
                patronymic=patronymic or "",
                is_active=bool(active),
                is_superuser=bool(superuser),
                is_staff=bool(staff),
                is_deleted=bool(deleted),
                profile_role=role or "",
                roles=roles[user_id],
            )
        )
    return accounts


def _match_all(sources, index, kafedra_types):
    matched, unmatched, candidates = defaultdict(list), [], defaultdict(set)
    for item in sources.all:
        # ``Account.chairs`` UUID saxlayır (``protection.load_accounts``) — ipucu da UUID olmalıdır.
        chair_hint = uuid.UUID(item.unit_id) if item.unit_id and item.unit_type in kafedra_types else None
        result = match_row(item, index, chair_hint)
        if result.status in MATCHED_STATUSES:
            matched[result.account.user_id].append(item)
            for other in result.candidates:
                if other.user_id != result.account.user_id:
                    candidates[result.account.user_id].add(other.user_id)
        else:
            unmatched.append((item, result))
    return matched, unmatched, candidates


def _roles(people, sources, facts, by_id):
    missing, stale = [], []
    expected = set()
    covered_units = {item.unit_id for item in sources.structure if item.unit_id}
    by_evidence = {}
    for person in people.values():
        for item in person.evidence:
            if item.source == SOURCE_STRUCTURE:
                by_evidence[id(item)] = person
    for item in sources.structure:
        person = by_evidence.get(id(item))
        if item.unit_id is None or item.kind in ("member", ""):
            continue
        if person is None:
            missing.append((None, item))
            continue
        expected.add((person.user_id, item.kind, item.unit_id))
        rows = facts.memberships.get(person.user_id, [])
        if not any(row["role__name"] == item.kind and row["scope_unit_id"] == item.unit_id for row in rows):
            missing.append((person, item))
    for user_id, rows in facts.memberships.items():
        for row in rows:
            if row["role__name"] in CHECKED_ROLES and row["scope_unit_id"] in covered_units:
                if (user_id, row["role__name"], row["scope_unit_id"]) not in expected:
                    stale.append((user_id, row["role__name"], row["scope_unit_id"]))
    return missing, stale


def _unlisted(organization, people, facts, listed, kafedra_types, memberships_by_unit) -> list:
    """Siyahılarda kafedra kimi olmayan kafedra tipli aktiv bölmələr + köçürmədən sonra qalan yük/üzvlük."""
    from apps.organizations.models import OrgUnit

    moved_out = defaultdict(set)
    for person in people.values():
        for action in person.actions:
            if action.kind == DEACTIVATE:
                moved_out[action.unit_id].add(action.membership_id)
    rows = []
    units = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=kafedra_types)
    for unit_id, name in units.order_by("name").values_list("id", "name"):
        unit_id = str(unit_id)
        if unit_id in listed:
            continue
        members = memberships_by_unit.get(unit_id, set())
        left = members - moved_out.get(unit_id, set())
        row = {
            "id": unit_id,
            "name": name,
            "members": len(members),
            "members_left": len(left),
            "tasks": int(unit_id in facts.task_chairs),
            "offerings": facts.offering_chairs.get(unit_id, 0),
        }
        row["archivable"] = not left and not row["tasks"] and not row["offerings"]
        rows.append(row)
    return rows


def _memberships_by_unit(organization) -> dict:
    from apps.organizations.models import Membership

    result = defaultdict(set)
    for membership_id, unit_id in (
        Membership.objects.filter(organization=organization, is_active=True, scope_unit__isnull=False)
        .values_list("id", "scope_unit_id")
        .order_by()
    ):
        result[str(unit_id)].add(str(membership_id))
    return result


_TEST_MARKERS = ("numune", "nümunə", "test", "demo", "sample", "example", "monitoring", "center", "konullu")


def _incomplete(accounts, facts, teacher_ids) -> list:
    """Natamam / sınaq görünüşlü müəllim hesabları (soyad yoxdur, ad = soyad, rəqəm, sınaq sözləri) — YALNIZ hesabat."""
    from ..teacher_roster.parsing import fold

    rows = []
    for account in accounts:
        if account.user_id not in teacher_ids:
            continue
        last, first = (account.last or "").strip(), (account.first or "").strip()
        text = fold(f"{account.username} {first} {last}")
        reasons = []
        if not last or not first:
            reasons.append("name_incomplete")
        elif fold(first) == fold(last):
            reasons.append("first_equals_last")
        if any(char.isdigit() for char in f"{first}{last}"):
            reasons.append("digits_in_name")
        if any(fold(marker) in text for marker in _TEST_MARKERS):
            reasons.append("test_marker")
        if not reasons:
            continue
        rows.append(
            {
                "account": account,
                "reasons": reasons,
                "load_hours": sum(facts.load_chairs.get(account.user_id, {}).values()),
                "journals": facts.journal_count.get(account.user_id, 0),
                "suggest_block": "test_marker" in reasons
                and account.is_active
                and not facts.teaching_now(account.user_id),
            }
        )
    return rows


def build(organization, sources, *, academic_year: str, period_ids=None) -> Plan:
    """Mənbələri hesablarla tutuşdurur və düzəliş planını qurur — YAZMIR."""
    from apps.organizations.public import kafedra_unit_types

    kafedra_types = kafedra_unit_types(organization)
    period_ids = facts_mod.current_period_ids(organization) if period_ids is None else period_ids
    active_accounts = load_accounts(organization)
    dormant = _dormant_accounts(organization, {account.user_id for account in active_accounts})
    accounts = [*active_accounts, *dormant]
    by_id = {account.user_id: account for account in accounts}
    index = AccountIndex(accounts, is_student=is_student)
    matched, unmatched, candidates = _match_all(sources, index, kafedra_types)
    teacher_ids = facts_mod.teacher_role_user_ids(organization)
    wanted = set(matched) | teacher_ids | {pk for group in candidates.values() for pk in group}
    wanted |= facts_mod.role_user_ids(organization, CHECKED_ROLES)
    facts = facts_mod.collect(organization, wanted, academic_year=academic_year, period_ids=period_ids)

    # Adı natamam hesab (soyad/ad boş — «Minayə», «Ramilə») tam adla tutuşmur; eyni kafedrada adı uyğun gələn —
    # ehtimal dublikat (yük bəzən məhz onun üzərindədir) → qərar siyahısı.
    partial = [account for account in accounts if not (account.last_key and account.first_key)]
    listed = set(sources.structure_chairs)
    listed |= {item.unit_id for item in [*sources.forma7, *sources.loads] if item.unit_id}
    people = {}
    for user_id, evidence in matched.items():
        person = PersonPlan(account=by_id[user_id], evidence=evidence)
        person.duplicates = [
            by_id[pk]
            for pk in sorted(candidates.get(user_id, ()))
            if pk in by_id
            and by_id[pk].last_key == person.account.last_key
            and by_id[pk].first_key == person.account.first_key
        ]
        person.duplicates += [
            account
            for account in partial
            if (account.first_key or account.last_key) in {person.account.first_key, person.account.last_key}
            and {str(chair) for chair in account.chairs} & {item.unit_id for item in evidence if item.unit_id}
        ]
        _plan_person(person, facts, kafedra_types, listed)
        people[user_id] = person
    plan = Plan(
        organization=organization,
        academic_year=academic_year,
        kafedra_types=kafedra_types,
        sources=sources,
        facts=facts,
        people=people,
        unmatched=unmatched,
        listed_chairs=listed,
        unlisted_chairs=_unlisted(
            organization, people, facts, listed, kafedra_types, _memberships_by_unit(organization)
        ),
        roles_missing=[],
        roles_stale=[],
        incomplete_accounts=_incomplete(accounts, facts, teacher_ids),
    )
    plan.roles_missing, plan.roles_stale = _roles(people, sources, facts, by_id)
    plan.dormant_ids = {account.user_id for account in dormant} & set(people)
    plan.accounts = by_id
    plan.actions = [action for person in people.values() for action in person.actions]
    return plan


def protect_ids(plan: Plan) -> set:
    """Bloklamadan QORUNANLAR: struktur/yük faylında adı olanlar və onların adaş (dublikat) hesabları."""
    ids = {pk for pk, person in plan.people.items() if person.sources & {SOURCE_STRUCTURE, SOURCE_LOAD}}
    for person in plan.people.values():
        ids |= {account.user_id for account in person.duplicates}
    for _item, result in plan.unmatched:
        ids |= {account.user_id for account in result.candidates}
    return ids


__all__ = [
    "DEACTIVATE",
    "JOIN",
    "PRIMARY",
    "Action",
    "PersonPlan",
    "Plan",
    "build",
    "protect_ids",
]
