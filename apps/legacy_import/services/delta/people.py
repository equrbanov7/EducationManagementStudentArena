"""Legacy müəllim / tələbə → hədəf hesabı; tapılmayanlar üçün hesab YARADILMASI.

Müəllim
    ledger (``worker``) → ``teacher_roster.chair_teachers.ChairTeacherResolver`` (dərs yükü faylının
    ad tutuşdurması: dəqiq / yazı səhvinə dözümlü / ata adı; tapılmasa FİN-siz hesab — sahib 2026-10-11
    qaydası, parolsuz, ``roster.<ad>@placeholder.invalid``). Kafedra = legacy ``department_id``-nin
    ledger vahidi.

Tələbə
    ledger (``student``) → ``institutional_identifier`` = legacy id (əvvəlki delta yaradıbsa) → FİN →
    ad + soyad (tək namizəd; ata adı, qrup və ya doğum tarixi uyğun gəlməlidir). Tapılmasa və AZAD EDİLMƏYİBSƏ,
    qrupu və proqramı həll olunursa — RİM-in ``intake.create.create_account`` yolu ilə hesab (parolsuz,
    ``legacy.<ad>@placeholder.invalid``; ilk girişdə öz e-poçtunu yazır, birdəfəlik parolu RİM verir).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from django.apps import apps as django_apps

from ..legacy_demographics import GENDER_FEMALE, GENDER_MALE, GENDER_UNSPECIFIED, legacy_birth_date, legacy_gender
from .resolve import ledger_map, person_key, text

STUDENT_ROLE_NAMES = ("student", "alumni")
_GENDER_TEXT = {"kisi": GENDER_MALE, "qadin": GENDER_FEMALE}


def worker_display(row: dict) -> str:
    return " ".join(
        part for part in (text(row.get("last_name")), text(row.get("first_name")), text(row.get("father_name"))) if part
    )


class TeacherMapper:
    """legacy ``workers.id`` → ``User`` (keşlə). ``outcome`` sayları hesabata düşür."""

    def __init__(self, run, workers: dict):
        self.run = run
        self.workers = workers
        self.ledger = ledger_map(run.organization, "worker", workers)
        self._users: dict = {}
        self._resolvers: dict = {}
        self._cache: dict = {}
        self.created: list = []  # [(legacy_id, user_pk)]

    def _user(self, pk):
        if pk not in self._users:
            self._users[pk] = django_apps.get_model("auth", "User").objects.filter(pk=pk).first()
        return self._users[pk]

    def _resolver(self, chair):
        from apps.accounts.public import legacy_accounts

        key = getattr(chair, "pk", None)
        if key not in self._resolvers:
            self._resolvers[key] = legacy_accounts.chair_teacher_resolver(
                self.run.organization, chair, actor_user=self.run.actor, apply=True, tag=self.run.tag
            )
        return self._resolvers[key]

    def resolve(self, legacy_id):
        """``(user | None, outcome)``."""

        if legacy_id in self._cache:
            return self._cache[legacy_id]
        result = self._resolve(legacy_id)
        self._cache[legacy_id] = result
        self.run.count(f"teacher.{result[1]}")
        return result

    def _resolve(self, legacy_id):
        from apps.accounts.public import legacy_accounts

        resolved, created = legacy_accounts.teacher_resolution_statuses()
        target = self.ledger.get(str(legacy_id))
        if target:
            user = self._user(int(target))
            if user is not None:
                return (user, "ledger") if user.is_active else (None, "ledger_blocked")
        row = self.workers.get(legacy_id)
        if row is None:
            return None, "source_missing"
        display = worker_display(row)
        if not display:
            return None, "unreadable"
        chair = self.run.catalog.unit_for_department(row.get("department_id"))
        result = self._resolver(chair).resolve(display)
        if result.status in created and result.user is not None:
            self.created.append((legacy_id, result.user.pk))
            self.run.names("teacher_created", display, result.user.username)
            return result.user, "created"
        if result.status in resolved and result.user is not None:
            return result.user, f"matched_{result.status}"
        self.run.names(f"teacher_{result.status}", display, ", ".join(result.candidates or []))
        return None, result.status


class StudentMapper:
    """legacy ``students.id`` → ``User``; tapılmayan aktiv tələbə üçün hesab yaradır."""

    def __init__(self, run, students: dict):
        self.run = run
        self.students = students
        org = run.organization
        self.ledger = ledger_map(org, "student", students)
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        Membership = django_apps.get_model("organizations", "Membership")
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        ids = [str(key) for key in students]
        self.by_inst = dict(
            UserProfile.objects.filter(institutional_identifier__in=ids).values_list(
                "institutional_identifier", "user_id"
            )
        )
        fins = sorted({str(row.get("fincode") or "").strip().upper() for row in students.values()} - {""})
        self.by_fin = {
            fin.upper(): user_id
            for fin, user_id in UserProfile.objects.filter(fin__in=fins).values_list("fin", "user_id")
            if fin
        }
        #: Paket daxilində eyni FİN-li legacy sətirləri (eyni adamın iki legacy qeydi) → EYNİ hesab.
        self.bundle_fin: dict = {}
        self.student_ids = set(
            Membership.objects.filter(organization=org, role__name__in=STUDENT_ROLE_NAMES).values_list(
                "user_id", flat=True
            )
        )
        #: AKTİV «student» üzvlüyü olan AKTİV hesablar — yalnız onlar jurnala yazıla bilər
        #: (``registrar_member_has_permission`` DB qapısı ilə eyni şərt).
        self.active_ids = set(
            Membership.objects.filter(
                organization=org, role__name="student", is_active=True, role__is_active=True, user__is_active=True
            ).values_list("user_id", flat=True)
        )
        self.group_of = dict(
            Record.objects.filter(organization=org, is_active=True).values_list("student_id", "group_id")
        )
        self.by_name: dict = defaultdict(list)
        self.fin_of: dict = {}
        for user_id, first, last, patronymic, birth, fin in UserProfile.objects.filter(
            user_id__in=self.student_ids
        ).values_list("user_id", "user__first_name", "user__last_name", "patronymic", "birth_date", "fin"):
            self.by_name[(person_key(last), person_key(first))].append((user_id, person_key(patronymic), birth))
            if fin:
                self.fin_of[user_id] = fin.strip().upper()
        self._cache: dict = {}
        #: ad ilə tutuşdurulmuş hesab → legacy id: iki legacy adam EYNİ hesaba ad ilə bağlanmır.
        self._name_claims: dict = {}
        #: Paket ``snapshot.create_ambiguous`` — adaşlardan heç biri tutmayan tələbə yaradılır (açıq qərar).
        self.create_ambiguous = bool((run.bundle.get("snapshot") or {}).get("create_ambiguous"))
        self.created: list = []

    def resolve(self, legacy_id, *, create: bool = True):
        """``(user_id | None, outcome)``."""

        if legacy_id in self._cache:
            return self._cache[legacy_id]
        result = self._resolve(legacy_id, create=create)
        self._remember(legacy_id, result)
        return result

    def _remember(self, legacy_id, result) -> None:
        self._cache[legacy_id] = result
        self.run.count(f"student.{result[1]}")
        if result[0] is None:
            return
        # Hər həll hesabı bu legacy id-yə «bağlayır» — başqa legacy adam həmin hesaba yalnız AD ilə
        # bağlana bilməz (qaçışlar arasında nəticə eyni qalsın: yaradılmış hesab növbəti qaçışda
        # «identifikator» ilə tapılır, ad iddiası isə yenə rədd olunur).
        self._name_claims.setdefault(result[0], legacy_id)
        fin = _fin(self.students.get(legacy_id))
        if fin:
            self.bundle_fin.setdefault(fin, result[0])

    def prepare(self) -> None:
        """ÜÇ KEÇİD — nəticə sıradan asılı olmasın (idempotentlik):

        1. hamı YARATMADAN tutuşdurulur (ledger / identifikator / FİN / ad);
        2. tapılmayanlar id sırası ilə yaradılır — hər yaradılandan sonra indekslər yenilənir, ona görə legacy-də
           İKİ sətri olan eyni adam (eyni FİN və ya ad + doğum tarixi) ikinci hesab almır;
        3. FİN-i olub 1-ci keçiddə həll olunmayanlar yenidən yoxlanılır (FİN 2-ci keçiddə yaranmış ola bilər) —
           növbəti qaçışda eyni sətir məhz belə (FİN ilə) tapılacaq.
        """

        create, recheck = [], []
        for legacy_id in sorted(self.students):
            result = self._resolve(legacy_id, create=False)
            if result[0] is None and result[1] == "not_found":
                create.append(legacy_id)
            elif result[0] is None and _fin(self.students.get(legacy_id)):
                recheck.append(legacy_id)
            else:
                self._remember(legacy_id, result)
        for legacy_id in create:
            self.resolve(legacy_id)
        for legacy_id in recheck:
            self.resolve(legacy_id, create=False)

    def _resolve(self, legacy_id, *, create: bool):
        target = self.ledger.get(str(legacy_id))
        if target:
            return int(target), "ledger"
        if str(legacy_id) in self.by_inst:
            return self.by_inst[str(legacy_id)], "identifier"
        row = self.students.get(legacy_id)
        if row is None:
            return None, "source_missing"
        fin = _fin(row)
        if fin and fin in self.by_fin:
            user_id = self.by_fin[fin]
            return (user_id, "fin") if user_id in self.student_ids else (None, "fin_not_student")
        if fin and fin in self.bundle_fin:
            return self.bundle_fin[fin], "fin_same_person"
        group = self._group(row)
        candidates = [
            candidate
            for candidate in self.by_name.get((person_key(row.get("last_name")), person_key(row.get("first_name"))), [])
            if not (fin and self.fin_of.get(candidate[0]) and self.fin_of[candidate[0]] != fin)
        ]
        if candidates and _all_other_people(candidates, row, group, self.group_of):
            # Eyni ad-soyad, amma hər namizədin ata adı (və doğum tarixi) FƏRQLİDİR və heç biri bu qrupda deyil —
            # başqa adamlardır; legacy tələbə sistemdə yoxdur (sahib 2026-10-25: «nə yazmışdısa hamısı orda olsun»).
            if create:
                self.run.count("student.name_other_person")
            candidates = []
        if candidates:
            narrowed = _narrow(candidates, row, group, self.group_of)
            claimed = self._name_claims.get(narrowed[0]) if len(narrowed) == 1 else None
            if claimed is not None and self._same_legacy_person(claimed, row):
                claimed = legacy_id  # legacy-də eyni adamın ikinci sətri (başqa alt qrup) — eyni hesab
            if len(narrowed) == 1 and claimed in (None, legacy_id):
                self._name_claims[narrowed[0]] = legacy_id
                return narrowed[0], "name"
            if not narrowed and self.create_ambiguous:
                # Sahib 2026-10-25 «12 tələbə gəlsin geri»: heç bir adaş bu adam deyil (ata adı / doğum / qrup
                # tutmur) — legacy qrupu ilə yeni hesab; adlı hesabatda ayrıca (RİM birləşdirə bilər).
                if create:
                    self.run.names("student_ambiguous_created", _display(row), str(len(candidates)))
                    self.run.count("student.ambiguous_created")
                candidates = []
            else:
                self.run.names("student_ambiguous", _display(row), str(len(candidates)))
                reason = "claimed_by_other" if claimed is not None else _ambiguity(candidates, row, narrowed)
                return None, f"name_ambiguous.{reason}"
        if not create:
            return None, "not_found"
        if int(row.get("azadedildi") or 0) == 1:
            return None, "expelled_not_created"
        group = group or self._group(row, create=True)
        if group is None:
            return None, "group_unresolved"
        return self._create(legacy_id, row, group, fin)

    def _same_legacy_person(self, other_legacy_id, row) -> bool:
        """İki legacy sətri eyni adamdır: soyad + ad + ata adı eyni, doğum tarixi (hər ikisində varsa) eyni."""

        other = self.students.get(other_legacy_id)
        if other is None or not person_key(row.get("father_name")):
            return False
        for field in ("last_name", "first_name"):
            if person_key(other.get(field)) != person_key(row.get(field)):
                return False
        if not same_father(person_key(other.get("father_name")), person_key(row.get("father_name"))):
            return False
        births = {legacy_birth_date(item.get("birthday") or None) for item in (other, row)} - {None}
        return len(births) <= 1

    def _group(self, row, *, create: bool = False):
        legacy_group = self.run.legacy_groups.get(row.get("group_id"))
        if legacy_group is None:
            return None
        if create:
            from .structure import ensure_group

            return ensure_group(self.run, legacy_group)
        return self.run.catalog.group_for(legacy_group)[0]

    def _program(self, group, row):
        """Qrupun tələbələrinin ən çox proqramı → cutover ledger-i (ixtisas:dərəcə) → ixtisasın tək proqramı."""

        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        Program = django_apps.get_model("registrar", "Program")
        org = self.run.organization
        counts = Counter(
            Record.objects.filter(organization=org, group=group, is_active=True).values_list("program_id", flat=True)
        )
        if counts:
            return Program.objects.filter(pk=counts.most_common(1)[0][0]).first()
        degree = (group.settings or {}).get("degree_level") or "bachelor"
        speciality = row.get("speciality_id") or (self.run.legacy_groups.get(row.get("group_id")) or {}).get(
            "speciality_id"
        )
        target = ledger_map(org, "speciality_program", [f"{speciality}:{degree}"]).get(f"{speciality}:{degree}")
        if target:
            program = Program.objects.filter(pk=target, organization=org).first()
            if program is not None:
                return program
        programs = list(Program.objects.filter(organization=org, specialty_unit_id=group.parent_id, is_active=True))
        matching = [program for program in programs if program.degree_level == degree] or programs
        return matching[0] if len(matching) == 1 else None

    def _create(self, legacy_id, row, group, fin):
        from apps.accounts.public import legacy_accounts

        program = self._program(group, row)
        if program is None:
            return None, "program_unresolved"
        first, last = text(row.get("first_name"), limit=150), text(row.get("last_name"), limit=150)
        if not first or not last:
            return None, "name_unreadable"
        admission_year = _year(row.get("entry_year")) or _year((group.settings or {}).get("admission_year"))
        if admission_year is None:
            return None, "admission_year_unknown"
        user = legacy_accounts.create_legacy_student(
            organization=self.run.organization,
            actor=self.run.actor,
            first_name=first,
            last_name=last,
            patronymic=text(row.get("father_name"), limit=150),
            fin=fin if fin and len(fin) <= 10 else None,
            gender=student_gender(row),
            birth_date=legacy_birth_date(row.get("birthday") or None),
            legacy_code=str(legacy_id),
            group=group,
            program=program,
            admission_year=admission_year,
            education_form="part_time" if "qiyabi" in person_key(row.get("education_type")) else "full_time",
            funding_type="state" if "dovlet" in person_key(row.get("payment_type")) else "paid",
            tag=self.run.tag,
        )
        self.student_ids.add(user.pk)
        self.active_ids.add(user.pk)
        self.group_of[user.pk] = group.pk
        if fin:
            self.by_fin[fin] = user.pk
            self.fin_of[user.pk] = fin
        self.by_inst[str(legacy_id)] = user.pk
        self.by_name[(person_key(last), person_key(first))].append(
            (user.pk, person_key(row.get("father_name")), legacy_birth_date(row.get("birthday") or None))
        )
        self._name_claims[user.pk] = legacy_id
        self.created.append((legacy_id, user.pk))
        self.run.names("student_created", _display(row), f"{user.username} · {group.name}")
        return user.pk, "created"


def _fin(row) -> str:
    return str((row or {}).get("fincode") or "").strip().upper()


_FATHER_SUFFIX = re.compile(r"(qizi|oglu|ogli|kizi|oglu)$")


def same_father(one: str, other: str) -> bool:
    """Ata adı açarları (``person_key``) eyni adamındır: «qızı/oğlu» sonluğu atılır; ilk 5 hərf və ya qısa
    olanın tamamı (≥3 hərf) üst-üstə düşür («ŞAİQ» = «ŞAİQ QIZI», «Əli» = «ƏLİ QIZI»)."""

    one, other = _FATHER_SUFFIX.sub("", one or ""), _FATHER_SUFFIX.sub("", other or "")
    if not one or not other:
        return False
    if one[:5] == other[:5]:
        return True
    short, long_ = sorted((one, other), key=len)
    return len(short) >= 3 and long_.startswith(short)


def _narrow(candidates, row: dict, group, group_of) -> list:
    """Ad + soyad namizədlərindən EYNİ adam olanlar.

    Ata adı (ilk 5 hərf) və ya doğum tarixi üst-üstə düşür; yaxud qrup eynidir VƏ ata adları bir-birini
    TƏKZİB ETMİR (iki tərəfdə də dolu və fərqli ata adı = başqa adamdır, eyni qrupda olsa belə).
    """

    patronymic = person_key(row.get("father_name"))
    birth = legacy_birth_date(row.get("birthday") or None)
    out = []
    for user_id, their_patronymic, their_birth in candidates:
        same_patronymic = same_father(patronymic, their_patronymic)
        contradicts = bool(patronymic and their_patronymic and not same_patronymic)
        same_birth = birth is not None and birth == their_birth
        same_group = group is not None and group_of.get(user_id) == group.pk
        if same_patronymic or same_birth or (same_group and not contradicts):
            out.append(user_id)
    if len(out) > 1 and group is not None:
        # Bir neçə adaş ata adı ilə uyğun gəlir — legacy qrupunda olan TƏK namizəd üstündür.
        in_group = [user_id for user_id in out if group_of.get(user_id) == group.pk]
        if len(in_group) == 1:
            return in_group
    return out


def _all_other_people(candidates, row: dict, group, group_of) -> bool:
    """HƏR namizəd başqa adamdır: ata adı iki tərəfdə dolu və fərqli, doğum tarixi eyni deyil, qrup başqadır."""

    patronymic = person_key(row.get("father_name"))
    if not patronymic:
        return False
    birth = legacy_birth_date(row.get("birthday") or None)
    for user_id, their_patronymic, their_birth in candidates:
        if not their_patronymic or same_father(patronymic, their_patronymic):
            return False
        if birth is not None and birth == their_birth:
            return False
        if group is not None and group_of.get(user_id) == group.pk:
            return False
    return True


def _ambiguity(candidates, row: dict, narrowed) -> str:
    """Hesabat üçün ambiqülüyün növü (qərar dəyişmir)."""

    if len(narrowed) > 1:
        return "many_match"
    if len(candidates) > 1:
        return "many_candidates"
    if person_key(row.get("father_name")) and candidates[0][1]:
        return "patronymic_differs"
    return "no_patronymic_other_group"


def student_gender(row: dict) -> str:
    sex = row.get("sex")
    gender = legacy_gender(sex) if isinstance(sex, int) else GENDER_UNSPECIFIED
    if gender != GENDER_UNSPECIFIED:
        return gender
    return _GENDER_TEXT.get(person_key(row.get("gender")), GENDER_UNSPECIFIED)


def _year(value):
    digits = str(value or "").strip()[:4]
    return int(digits) if digits.isdigit() and 1950 < int(digits) < 2100 else None


def _display(row: dict) -> str:
    return " ".join(
        part for part in (text(row.get("last_name")), text(row.get("first_name")), text(row.get("father_name"))) if part
    )


__all__ = ["StudentMapper", "TeacherMapper", "student_gender", "worker_display"]
