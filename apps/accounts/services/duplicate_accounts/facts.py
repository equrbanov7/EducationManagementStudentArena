"""Dublikat axtarışı üçün hesab FAKTLARI (toplu sorğular, YAZMIR; ``bypass_rls`` altında çağırılır).

Əhali: təşkilatda tələbə rolundan başqa (aktiv və ya deaktiv) üzvlüyü olan, AKTİV tələbə/məzun üzvlüyü olmayan,
silinməmiş hesablar. Hər hesab üçün:

* **jurnal** — cari semestr(lər)də (``AcademicPeriod.is_current``) ``CourseOffering.instructor`` (aktiv açılış),
  ``Lesson.instructor`` və ya ``LessonMark.entered_by`` olduğu açılışların sayı;
* **yük** — tədris ilinin ``TeacherAssignment`` bölgüləri (ləğv edilmiş tapşırıq xaric);
* aktiv üzvlüklər (rol + bölmə), rəhbəri olduğu bölmələr, kafedralar, son giriş, FİN-in olub-olmaması.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from ..teacher_roster.matching import loose
from ..teacher_roster.parsing import key, patronymic_key
from ..teacher_roster.protection import STUDENT_ROLE_NAMES, _chair_resolver

CANCELLED_TASK = "cancelled"

#: Saxlanılacaq hesabın seçimində rolun çəkisi (sahib: «sonra rol (dekan/kafedra müdiri) olan»).
ROLE_RANK = {"dean": 5, "vice_dean": 4, "chair_head": 3}
#: Bu rollar «müəllim» sayılır — rəhbər/inzibati rol çəkisi vermir.
PLAIN_ROLES = frozenset({"teacher", "assistant", "assistant_teacher", "instructor", "collaborator", "member"})

#: Köçürmədən qalmış «saxta» ata adları («---», «xxx», «AAAA») — ata adı YOXDUR sayılır.
_PLACEHOLDERS = frozenset({"xxx", "yox", "nan", "none", "test"})


def clean_patronymic(value: str) -> str:
    text = patronymic_key(value)
    if text and (len(set(text)) <= 1 or text in _PLACEHOLDERS):
        return ""
    return text


@dataclass
class Person:
    user_id: int
    username: str
    last: str
    first: str
    patronymic: str
    is_active: bool
    last_login: datetime.datetime | None
    has_fin: bool
    protected: str = ""  # superuser / staff / owner — heç vaxt dondurulmur
    memberships: list = field(default_factory=list)  # aktiv üzvlüklər: dict(id, role_id, role, unit, title, primary)
    chairs: set = field(default_factory=set)  # kafedralar (aktiv və deaktiv üzvlüklərdən — dondurulandan sonra da)
    heads: list = field(default_factory=list)  # rəhbəri olduğu bölmə id-ləri
    owned: list = field(default_factory=list)  # cari semestrin aktiv açılışları (instructor) — təhvil olunacaq
    journals: int = 0
    history: int = 0  # cari semestrdə yazdığı dərs + qiymət sətri (köçmür, tarixdir)
    load: int = 0

    @property
    def last_key(self) -> str:
        return key(self.last)

    @property
    def first_key(self) -> str:
        return key(self.first)

    @property
    def patronymic_key(self) -> str:
        return clean_patronymic(self.patronymic)

    @property
    def partial(self) -> bool:
        return not (self.last_key and self.first_key)

    @property
    def exact_key(self) -> tuple:
        return tuple(sorted((self.last_key, self.first_key)))

    @property
    def loose_key(self) -> tuple:
        return tuple(sorted((loose(self.last_key), loose(self.first_key))))

    @property
    def single_key(self) -> str:
        return loose(self.last_key or self.first_key)

    @property
    def role_rank(self) -> int:
        ranks = [ROLE_RANK.get(row["role"], 0 if row["role"] in PLAIN_ROLES else 1) for row in self.memberships]
        return max(ranks, default=0)

    @property
    def display(self) -> str:
        return " ".join(part for part in (self.last, self.first, self.patronymic) if part) or self.username

    def sort_key(self):
        """Saxlanılacaq hesabın sırası: jurnal → yük → son giriş → rol → üzvlük sayı → köhnə hesab."""
        login = self.last_login.timestamp() if self.last_login else 0.0
        return (
            self.journals > 0,
            self.journals,
            self.load > 0,
            self.load,
            self.last_login is not None,
            login,
            self.role_rank,
            len(self.memberships),
            -self.user_id,
        )


def _model(app_label, name):
    return django_apps.get_model(app_label, name)


def _population(organization) -> set:
    Membership = _model("organizations", "Membership")
    staff, students = set(), set()
    for user_id, role_name, active in (
        Membership.objects.filter(organization=organization)
        .values_list("user_id", "role__name", "is_active")
        .order_by()
    ):
        if role_name in STUDENT_ROLE_NAMES:
            if active:
                students.add(user_id)
        else:
            staff.add(user_id)
    return staff - students


def load_people(organization, *, academic_year: str, period_ids) -> dict:
    """``{user_id: Person}`` — dublikat axtarışının əhalisi və faktları."""
    from django.contrib.auth import get_user_model

    ids = _population(organization)
    people = {}
    owner_id = getattr(organization, "owner_id", None)
    fields = ("id", "username", "first_name", "last_name", "is_active", "is_superuser", "is_staff", "last_login")
    profile = ("profile__patronymic", "profile__fin", "profile__is_deleted")
    for row in get_user_model().objects.filter(pk__in=list(ids)).values_list(*fields, *profile):
        user_id, username, first, last, active, superuser, staff, last_login, patronymic, fin, deleted = row
        if deleted:
            continue
        first_tokens = (first or "").split()
        if len(first_tokens) == 2 and not (patronymic or "").strip():
            first, patronymic = first_tokens[0], first_tokens[1]
        person = Person(
            user_id=user_id,
            username=username,
            last=last or "",
            first=first or "",
            patronymic=patronymic or "",
            is_active=bool(active),
            last_login=last_login,
            has_fin=bool((fin or "").strip()),
        )
        if not (person.last_key or person.first_key):
            continue
        if superuser or staff:
            person.protected = "superuser"
        elif user_id == owner_id:
            person.protected = "org_owner"
        people[user_id] = person
    _attach_facts(organization, people, academic_year=academic_year, period_ids=list(period_ids or []))
    return people


def _attach_facts(organization, people: dict, *, academic_year: str, period_ids: list) -> None:
    ids = list(people)
    chair_of = _chair_resolver(organization)
    for row in (
        _model("organizations", "Membership")
        .objects.filter(organization=organization, user_id__in=ids)
        .values("id", "user_id", "role_id", "role__name", "scope_unit_id", "title", "is_primary", "is_active")
        .order_by("created_at")
    ):
        person = people[row["user_id"]]
        chair = chair_of(row["scope_unit_id"]) if row["scope_unit_id"] else None
        if chair is not None:
            person.chairs.add(str(chair))
        if not row["is_active"]:
            continue
        person.memberships.append(
            {
                "id": str(row["id"]),
                "role_id": str(row["role_id"]),
                "role": row["role__name"],
                "unit": str(row["scope_unit_id"]) if row["scope_unit_id"] else None,
                "title": row["title"] or "",
                "primary": bool(row["is_primary"]),
            }
        )
    for unit_id, head_id in (
        _model("organizations", "OrgUnit")
        .objects.filter(organization=organization, head_id__in=ids)
        .values_list("id", "head_id")
        .order_by("name")
    ):
        people[head_id].heads.append(str(unit_id))

    journals = defaultdict(set)
    history = defaultdict(int)
    Offering = _model("registrar", "CourseOffering")
    for offering_id, instructor_id in Offering.objects.filter(
        organization=organization, period_id__in=period_ids, is_active=True, instructor_id__in=ids
    ).values_list("id", "instructor_id"):
        people[instructor_id].owned.append(str(offering_id))
        journals[instructor_id].add(offering_id)
    for offering_id, instructor_id in (
        _model("registrar", "Lesson")
        .objects.filter(organization=organization, offering__period_id__in=period_ids, instructor_id__in=ids)
        .values_list("offering_id", "instructor_id")
    ):
        journals[instructor_id].add(offering_id)
        history[instructor_id] += 1
    for offering_id, author_id in (
        _model("registrar", "LessonMark")
        .objects.filter(organization=organization, lesson__offering__period_id__in=period_ids, entered_by_id__in=ids)
        .values_list("lesson__offering_id", "entered_by_id")
    ):
        journals[author_id].add(offering_id)
        history[author_id] += 1
    for user_id, offerings in journals.items():
        people[user_id].journals = len(offerings)
        people[user_id].history = history.get(user_id, 0)
    for teacher_id in (
        _model("workload", "TeacherAssignment")
        .objects.filter(organization=organization, teacher_id__in=ids, row__task__academic_year=academic_year)
        .exclude(row__task__status=CANCELLED_TASK)
        .values_list("teacher_id", flat=True)
    ):
        people[teacher_id].load += 1


__all__ = ["Person", "clean_patronymic", "load_people"]
