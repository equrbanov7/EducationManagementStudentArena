"""Dərs cədvəli .docx idxalı — qrup / fənn / müəllim / dərs növü TUTUŞDURMASI (yalnız oxuyur).

Heç nə YARADILMIR (açılış, qrup, fənn, istifadəçi): tapılmayan hüceyrə hesabata səbəb kodu ilə düşür.

QRUP: başlıq «233 İTex ing» → (rəqəm, kod, sektor, alt qrup). Kod müqayisəsi diakritikasız və
İ/I fərqsizdir; cədvəlin uzun kodları sistem kodlarına xəritələnir: «İTex» → «İT» (İnformasiya
texnologiyaları), «İTəh» → «İ» (İnformasiya təhlükəsizliyi). Sektor yazılmayıbsa «az»dır. Əvvəl EYNİ
adlı ana qrup(lar) yoxlanır; onda bu fənnin açılışı yoxdursa alt qruplar («235 İT-1 az», «235 İT-2 az»)
— onda dərs hər alt qrupun öz açılışına yazılır (birgə dərs). Eyni adlı iki qrup («235 K» ×2) varsa
yalnız fənnin açılışı OLAN götürülür; ikisində də varsa — ``group_ambiguous``.

FƏNN: yalnız HƏMİN qrupun HƏMİN semestrdəki aktiv açılışları arasında (başqa fənnə «sürüşmə» olmasın).
Ad diakritikasız + durğusuz müqayisə olunur; sistem adının mötərizə hissəsi («(Database security)»)
atılır; nömrələr («-2», «– 3») ikisində də varsa bərabər olmalıdır; sözlərin ≥75%-i hər iki istiqamətdə
oxşar sözlə qarşılanmalıdır (fərqli fənn «sürüşməsin»). Oxşarlıq < 0.80 → tapılmadı;
ikinci namizəd 0.04-dən yaxındırsa → ``subject_ambiguous``; fayldakı ad sistem adının yalnız
HİSSƏSİdirsə («Xətti cəbr» ⊂ «Xətti cəbr və analitik həndəsə») → ``subject_partial`` (yazılmır, yoxlanılsın).
Qrupun bu semestrdə heç açılışı yoxdursa → ``group_no_offerings``.

MÜƏLLİM («Soyad İ.»; magistratura cədvəlində TAM AD «Ad Soyad» — hər iki sıra, diakritikasız, 2026-10-17):
(1) açılışın slotuna təyin oluna bilənlər —
``schedule_slot_teachers.allowed_teacher_ids`` (jurnal sahibi + jurnal dərsləri + kafedra yükü
bölgüsü; əvvəl dəqiq soyad, sonra kiçik yazı xətası — ``teacher_fuzzy``); (2) fənnin kafedrasının müəllimləri; (3) təşkilatın
bütün aktiv müəllimləri (yalnız dəqiq soyad + baş hərf). Hamısı aktiv ``grade.input`` üzvüdür (slot
müəllimi üçün DB qoruyucusu ilə eyni qayda). Bir mənalı deyilsə slot müəllimi YAZILMIR (jurnal sahibi
qalır) və səbəb hesabata düşür.

NÖV: hüceyrədə yoxdursa — açılışın saat bölgüsündə TƏK növ varsa o; yoxsa müəllimin bu açılış üzrə
yük bölgüsündə TƏK fəaliyyəti varsa o; yoxsa ``kind_unknown`` (yazılmır). Magistratura hüceyrəsi (növ
işarəsi yoxdur) bu halda mühazirədir (``kind_default_lecture``).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

from apps.registrar import schedule_slot_teachers
from apps.registrar.models import AcademicStatus, CourseOffering, Enrollment, StudentAcademicRecord
from apps.registrar.schedule_docx_parse import GroupLabel, fold, parse_group_label

#: Cədvəlin qrup kodu → sistemin qrup kodu (fold edilmiş).
CODE_ALIASES = {"itex": "it", "iteh": "i"}
SUBJECT_MIN_SCORE = 0.8
SUBJECT_MARGIN = 0.04
TEACHER_FUZZY = 0.85
_CANCELLED_TASK = "cancelled"
_ACTIVITIES = ("lecture", "seminar", "lab")


def code_key(code: str) -> str:
    key = fold(code).replace(" ", "")
    return CODE_ALIASES.get(key, key)


def label_key(label: GroupLabel) -> tuple:
    return (label.digits, code_key(label.code), label.sector)


def subject_norm(name: str, *, drop_parenthetical: bool = True) -> str:
    text = str(name or "")
    if drop_parenthetical:
        text = re.sub(r"\([^)]*(\)|$)", " ", text)
    text = fold(text)
    text = re.sub(r"[«»\"'.,:;()\-–—/]", " ", text)
    return " ".join(text.split())


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+", text)


def _coverage(tokens_a: list[str], tokens_b: list[str]) -> float:
    """``tokens_a``-nın neçə faizi ``tokens_b``-də oxşar (≥0.75) sözlə qarşılanır (qısa sözlər sayılmır)."""
    long_a = [token for token in tokens_a if len(token) >= 3]
    if not long_a:
        return 1.0
    hits = sum(
        1
        for token in long_a
        if any(difflib.SequenceMatcher(None, token, other).ratio() >= 0.75 for other in tokens_b if len(other) >= 3)
    )
    return hits / len(long_a)


def subject_score(file_name: str, system_name: str) -> float:
    """0..1 oxşarlıq; söz örtüyü (hər iki istiqamətdə ≥75%) şərtdir — «Müasir Veb proqramlaşdırma
    vasitələri» «Müasir proqramlaşdırma dilləri»-nə BƏRABƏR SAYILMIR (simvol oxşarlığı yüksək olsa da)."""
    a = subject_norm(file_name)
    best = 0.0
    for b in {subject_norm(system_name), subject_norm(system_name, drop_parenthetical=False)}:
        if not a or not b:
            continue
        nums_a, nums_b = _numbers(a), _numbers(b)
        if nums_a and nums_b and nums_a != nums_b:
            continue
        if a == b or a.replace(" ", "") == b.replace(" ", ""):
            return 1.0
        words_a = [w for w in a.split() if not w.isdigit()]
        words_b = [w for w in b.split() if not w.isdigit()]
        if min(_coverage(words_a, words_b), _coverage(words_b, words_a)) < 0.75:
            continue
        score = difflib.SequenceMatcher(None, a, b).ratio()
        if bool(nums_a) != bool(nums_b):
            score -= 0.03
        best = max(best, score)
    return best


def subject_contains(system_name: str, file_name: str) -> bool:
    """Fayldakı ad sistem adının HİSSƏSİdir («Xətti cəbr» ⊂ «Xətti cəbr və analitik həndəsə») — yazılmır,
    yalnız ``subject_partial`` kimi hesabata düşür (əl ilə yoxlanılsın)."""
    words_file = [w for w in subject_norm(file_name).split() if len(w) >= 3]
    words_system = subject_norm(system_name).split()
    return len(words_file) >= 1 and _coverage(words_file, words_system) == 1.0


def surname_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(value))


def split_teacher(token: str) -> tuple[str, str]:
    """«Məmmədova L.» → («memmedova», «l»); «Əkbərli» → («ekberli», «»)."""
    parts = str(token or "").replace(".", " ").split()
    if not parts:
        return "", ""
    initial = fold(parts[1])[:1] if len(parts) > 1 else ""
    return surname_key(parts[0]), initial


def is_full_name(token: str) -> bool:
    """«Günel Rəhimli» / «Qasımzadə Nail» (magistratura, 2026-10-17) — iki tam söz, nöqtəsiz (inisial yox)."""
    words = str(token or "").split()
    return "." not in str(token or "") and len(words) == 2 and all(len(surname_key(w)) > 1 for w in words)


def _first_word(value: str) -> str:
    words = str(value or "").split()
    return surname_key(words[0]) if words else ""


def teacher_matches(users, token: str, *, fuzzy: bool) -> list:
    """Nişana uyğun hesablar. «Soyad İ.»: dəqiq soyad (``fuzzy`` — yalnız ≥ ``TEACHER_FUZZY`` yazı xətası)
    + baş hərf. TAM AD: (ad, soyad) cütü hər iki sırada; ``fuzzy`` — hər iki söz ≥ ``TEACHER_FUZZY``."""
    out: dict = {}
    if is_full_name(token):
        a, b = (surname_key(word) for word in str(token).split())
        for user in users:
            first, last = _first_word(user.first_name), surname_key(user.last_name)
            if not first or not last:
                continue
            exact = (first, last) in ((a, b), (b, a))
            if fuzzy:
                ratio = difflib.SequenceMatcher
                same = not exact and any(
                    ratio(None, x, first).ratio() >= TEACHER_FUZZY and ratio(None, y, last).ratio() >= TEACHER_FUZZY
                    for x, y in ((a, b), (b, a))
                )
            else:
                same = exact
            if same:
                out[user.pk] = user
        return list(out.values())
    surname, initial = split_teacher(token)
    for user in users:
        last = surname_key(user.last_name)
        if not last or not surname:
            continue
        if fuzzy:
            same = last != surname and difflib.SequenceMatcher(None, last, surname).ratio() >= TEACHER_FUZZY
        else:
            same = last == surname
        if same and (not initial or fold(user.first_name)[:1] == initial):
            out[user.pk] = user
    return list(out.values())


@dataclass
class Target:
    offering: object
    score: float
    via: str  # "group" | "duplicate" | "subgroup"


@dataclass
class Resolution:
    targets: list[Target] = field(default_factory=list)
    reason: str = ""
    notes: list[str] = field(default_factory=list)


class Resolver:
    """Bir təşkilat + semestr üçün yaddaşda indekslər (hər hüceyrəyə ayrıca sorğu yoxdur)."""

    def __init__(self, organization, period):
        self.organization = organization
        self.period = period
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        self.units: dict[tuple, list] = {}
        for unit in OrgUnit.objects.filter(organization=organization, unit_type="group", is_active=True):
            label = parse_group_label(unit.name)
            if label is not None:
                self.units.setdefault(label_key(label) + (label.sub,), []).append(unit)
        self.offerings: dict = {}
        for offering in CourseOffering.objects.filter(
            organization=organization, period=period, is_active=True, group__isnull=False
        ).select_related("subject", "group", "instructor"):
            self.offerings.setdefault(offering.group_id, []).append(offering)
        self._allowed: dict = {}
        self._hours: dict = {}
        self._teachers = None
        self.group_seen: dict[str, str] = {}

    # ── qrup + fənn ────────────────────────────────────────────────────────
    def _unit_tiers(self, label: GroupLabel) -> list[tuple[str, list]]:
        key = label_key(label)
        if label.sub:
            exact = self.units.get(key + (label.sub,), [])
            tiers = [("group", exact)] if exact else []
            base = GroupLabel(raw=label.raw, digits=label.digits, code=label.code, sector=label.sector)
            return tiers + [(via, units) for via, units in self._unit_tiers(base)]
        base_units = self.units.get(key + ("",), [])
        subs = [unit for (d, c, s, sub), units in self.units.items() if (d, c, s) == key and sub for unit in units]
        tiers = []
        if base_units:
            tiers.append(("duplicate" if len(base_units) > 1 else "group", base_units))
        if subs:
            tiers.append(("subgroup", sorted(subs, key=lambda unit: unit.name)))
        return tiers

    def group_units(self, label: GroupLabel) -> list:
        """Başlığın həll olunduğu BÜTÜN qrup vahidləri (öz qrupu, eyni adlı ana qrup(lar), alt qruplar) —
        açılışdan asılı olmayan oxu (``workload.assign_task_rows_from_timetable`` tapşırıq sətirlərini
        bu qruplar üzrə axtarır). Sıra :meth:`_unit_tiers` ilə eynidir, təkrarlar atılır."""
        seen: dict = {}
        for _via, units in self._unit_tiers(label):
            for unit in units:
                seen.setdefault(unit.pk, unit)
        return list(seen.values())

    def _best(self, offerings, name):
        scored = sorted(((subject_score(name, o.subject.name), o) for o in offerings), key=lambda item: -item[0])
        if not scored or scored[0][0] < SUBJECT_MIN_SCORE:
            partial = [o for o in offerings if subject_contains(o.subject.name, name)]
            return None, ("subject_partial" if partial else "subject_not_in_group")
        best_score, best = scored[0]
        for score, other in scored[1:]:
            if other.subject_id != best.subject_id and best_score - score < SUBJECT_MARGIN:
                return None, "subject_ambiguous"
        return (best, best_score), ""

    def resolve(self, label: GroupLabel, subject_name: str) -> Resolution:
        tiers = self._unit_tiers(label)
        if not tiers:
            return Resolution(reason="group_not_found")
        self.group_seen[label.display] = ", ".join(unit.name for _via, units in tiers for unit in units)
        if not subject_name:
            return Resolution(reason="subject_missing")
        if not any(self.offerings.get(unit.pk) for _via, units in tiers for unit in units):
            return Resolution(reason="group_no_offerings")
        reasons = set()
        for via, units in tiers:
            found = []
            for unit in units:
                offerings = self.offerings.get(unit.pk, [])
                if not offerings:
                    continue
                match, reason = self._best(offerings, subject_name)
                if match is None:
                    reasons.add(reason)
                    continue
                found.append(Target(offering=match[0], score=round(match[1], 3), via=via))
            if not found:
                continue
            if via == "duplicate" and len(found) > 1:
                return Resolution(reason="group_ambiguous")
            notes = ["subgroup_expanded"] if via == "subgroup" else []
            if label.sub and via != "group":
                notes.append("subgroup_unit_missing")
            return Resolution(targets=found, notes=notes)
        for reason in ("subject_ambiguous", "subject_partial"):
            if reason in reasons:
                return Resolution(reason=reason)
        return Resolution(reason="subject_not_in_group")

    # ── müəllim ────────────────────────────────────────────────────────────
    def _teacher_pool(self) -> dict:
        """Təşkilatın aktiv ``grade.input`` müəllimləri: {user_id: (user, {scope_unit_id, …})}."""
        if self._teachers is None:
            Membership = django_apps.get_model("organizations", "Membership")
            rows = Membership.objects.filter(
                organization=self.organization, is_active=True, user__is_active=True, role__is_active=True
            ).values_list("user_id", "scope_unit_id")
            scopes: dict = {}
            for user_id, scope_id in rows:
                scopes.setdefault(user_id, set()).add(scope_id)
            allowed = schedule_slot_teachers.authorized_teacher_ids(self.organization, scopes.keys())
            users = get_user_model().objects.filter(pk__in=allowed)
            self._teachers = {user.pk: (user, scopes.get(user.pk, set())) for user in users}
        return self._teachers

    def _allowed_ids(self, offering) -> set:
        if offering.pk not in self._allowed:
            self._allowed[offering.pk] = schedule_slot_teachers.allowed_teacher_ids(offering)
        return self._allowed[offering.pk]

    def teacher(self, offering, token: str):
        """→ (user | None, səbəb). Səbəb boşdursa açılışın öz müəllimləri arasında dəqiq tapılıb."""
        if not split_teacher(token)[0]:
            return None, "teacher_missing"
        pool = self._teacher_pool()
        allowed = [pool[pk][0] for pk in self._allowed_ids(offering) if pk in pool]
        chair_id = getattr(offering.subject, "chair_unit_id", None)
        for users, fuzzy, reason in (
            (allowed, False, ""),
            (allowed, True, "teacher_fuzzy"),
            ([user for user, scopes in pool.values() if chair_id and chair_id in scopes], False, "teacher_chair_match"),
            ([user for user, _scopes in pool.values()], False, "teacher_org_match"),
        ):
            found = {user.pk: user for user in teacher_matches(users, token, fuzzy=fuzzy)}
            if len(found) == 1:
                return next(iter(found.values())), reason
            if len(found) > 1:
                return None, "teacher_ambiguous"
        return None, "teacher_not_found"

    # ── dərs növü ──────────────────────────────────────────────────────────
    def infer_kind(self, offering, teacher, *, default: str = "") -> tuple[str, str]:
        """``default`` — magistratura hüceyrəsində növ işarəsi yoxdur: bölgüdən çıxmırsa mühazirə (2026-10-17)."""
        from apps.registrar.plan_hours import plan_hours_for_offering

        if offering.pk not in self._hours:
            self._hours[offering.pk] = plan_hours_for_offering(offering) or {}
        kinds = [kind for kind in _ACTIVITIES if self._hours[offering.pk].get(kind)]
        if len(kinds) == 1:
            return kinds[0], "kind_from_hours"
        if teacher is not None:
            Assignment = django_apps.get_model("workload", "TeacherAssignment")
            activities = set(
                Assignment.objects.filter(
                    organization_id=offering.organization_id,
                    row__subject_id=offering.subject_id,
                    row__period_id=offering.period_id,
                    row__groups=offering.group_id,
                    teacher=teacher,
                    activity__in=_ACTIVITIES,
                )
                .exclude(row__task__status=_CANCELLED_TASK)
                .values_list("activity", flat=True)
            )
            if len(activities) == 1:
                return activities.pop(), "kind_from_load"
        if default:
            return default, f"kind_default_{default}"
        return "", "kind_unknown"

    # ── görünmə ────────────────────────────────────────────────────────────
    def visible_students(self, offering) -> int:
        """Bu açılışın slotunu «Dərs cədvəli»ndə görəcək tələbə sayı (öz qrupu + alt qrupdan əlavə)."""
        own = StudentAcademicRecord.objects.filter(
            organization=self.organization, group_id=offering.group_id, status=AcademicStatus.ENROLLED
        ).count()
        guests = Enrollment.objects.filter(
            offering=offering, status=Enrollment.Status.ENROLLED, source_group__isnull=False
        ).count()
        return own + guests


__all__ = [
    "CODE_ALIASES",
    "SUBJECT_MARGIN",
    "SUBJECT_MIN_SCORE",
    "TEACHER_FUZZY",
    "Resolution",
    "Resolver",
    "Target",
    "code_key",
    "is_full_name",
    "split_teacher",
    "subject_contains",
    "subject_score",
    "surname_key",
    "teacher_matches",
]
