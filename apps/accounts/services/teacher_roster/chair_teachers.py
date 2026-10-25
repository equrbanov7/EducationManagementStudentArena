"""Dərs yükü faylındakı müəllim adı → hesab (yazı səhvinə dözümlü) və ya YENİ FİN-siz müəllim hesabı.

Sahib 2026-10-23 («Tədris şöbəsi dərs yükünü yükləyəndə …»): «orada yazılan müəllim yoxdursa avtomatik onun
müəllim profili açılsın — FİN kod, digər məlumat olmasa da olar; sonra ilkin parol veriləndən sonra bərpa
olunacaq. Bütün hərf səhvlərinə həssas olsun.»

Tutuşdurma Forma 7 tutuşdurmasının (``matching.match_row``) EYNİ qaydasıdır — yeni qayda icad edilmir:

* soyad + ad dəqiq (diakritik/registr/boşluq dözümlü), ata adı eyni və ya bir tərəfdə boş → hesab;
* bir hərf fərqi, ə/a/e · q/g/k · f/v · qoşa hərf variantı və ya tərs sıra + ata adı uyğun → ``fuzzy`` hesab;
* eyni adlı bir neçə hesab → seçilmiş kafedradakı, sonra müəllim rolu olan üstündür; yenə çoxdursa ``ambiguous``
  (TƏXMİN EDİLMİR — sətir vakant qalır, önizləmədə göstərilir);
* «Soyad A.M.» (yalnız inisiallar) — soyad + adın ilk hərfi TƏK hesaba düşürsə qəbul, yoxsa həll olunmur.

Yeni hesab YALNIZ bu hallarda: heç kim tapılmadı (``not_found``), yalnız tələbə/məzun hesabı var (``student_only``
— tələbə müəllim olmur, sahib 2026-09-07), və ya eyni ad + soyadla FƏRQLİ ata adlı şəxs var (``conflict`` — başqa
adamdır; önizləmədə qeyd olunur). Hesab «Müəllim əlavəsi (toplu)»nun FİN-siz yolu ilə yaradılır
(``intake.create.create_account``): istifadəçi adı ``ad.soyad``, placeholder e-poçt, PAROLSUZ (``unusable`` —
birdəfəlik parolu RİM verir), seçilmiş kafedrada müəllim üzvlüyü, audit sətri.

Bloklanmış / silinmiş hesaba uyğun gəlsə yeni hesab AÇILMIR (``blocked`` — RİM hesabı aktivləşdirməlidir).
Çağıran tranzaksiya + tenant konteksti içindədir; ``apply=False`` heç nə yazmır.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .matching import (
    STATUS_AMBIGUOUS,
    STATUS_CONFLICT,
    STATUS_FUZZY,
    STATUS_MATCHED,
    STATUS_NOT_FOUND,
    STATUS_STUDENT_ONLY,
    Account,
    AccountIndex,
    loose,
    match_row,
)
from .parsing import PersonName, fold, key, parse_title_degree

#: Nəticə statusları (önizləmədə göstərilir).
TEACHER_MATCHED = "matched"
TEACHER_FUZZY = "fuzzy"
#: Ad + soyad eyni, ata adı BİR hərf fərqli («Tahir»/«Mahir») — Forma 7 qaydası ilə eyni şəxs sayılır, amma
#: önizləmədə xəbərdarlıqla göstərilir (operator yoxlasın).
TEACHER_PATRONYMIC = "patronymic_similar"
TEACHER_INITIALS = "initials"
TEACHER_CREATED = "created"
TEACHER_CREATED_NAMESAKE = "created_namesake"
TEACHER_AMBIGUOUS = "ambiguous"
TEACHER_REVIEW = "review"
TEACHER_BLOCKED = "blocked"
TEACHER_UNREADABLE = "name_unreadable"
RESOLVED = (
    TEACHER_MATCHED,
    TEACHER_FUZZY,
    TEACHER_PATRONYMIC,
    TEACHER_INITIALS,
    TEACHER_CREATED,
    TEACHER_CREATED_NAMESAKE,
)

EMAIL_PREFIX = "yuk"

#: Ad olmayan sözlər (qatlanmış): elmi dərəcə/ad, vəzifə, ştat qeydi, ata adı şəkilçisi.
_STOPWORDS = frozenset(
    {
        "dos", "dosent", "prof", "professor", "kafedra", "kafedrasi", "mudiri", "mudir", "muellim", "bas",
        "baskicik", "kicik", "elmi", "isci", "stat", "yarimstat", "yarim", "saat", "hesabi", "saathesabi",
        "ilden", "isleyir", "ve", "assistent", "laborant", "dekan", "muavini", "phd", "dr", "akad", "akademik",
        "elmler", "doktoru", "namizedi", "felsefe", "sh",
        # 2026-10-25 kafedra faylları: «Dokturant QKU …», «DİA-nın dissertantı …», «QKU mütəxəssis …»
        "doktorant", "dokturant", "doktrant", "dissertant", "dissertanti", "doktranti", "doktoranti", "qku",
        "dianin", "mutexessis",
    }
)  # fmt: skip
_SUFFIXES = frozenset({"oglu", "ogly", "qizi", "kizi", "gizi"})
_YEAR_CUT_RE = re.compile(r"(?i)\d{4}\s*[-–]?\s*c[iıuü]")


@dataclass(frozen=True)
class _NameRow:
    """``match_row``-un gözlədiyi sətir forması (yalnız ``name``)."""

    name: PersonName
    chair: str = ""


@dataclass
class TeacherResult:
    status: str
    user: object = None
    display: str = ""
    candidates: list = field(default_factory=list)  # [istifadəçi adı] — həll olunmayan hallarda
    flags: list = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.user is not None


def _title_word(word: str) -> str:
    """«MƏMMƏDOV» / «məmmədov» → «Məmmədov» (Azərbaycan İ/i qaydası); qarışıq registr olduğu kimi qalır."""
    word = unicodedata.normalize("NFC", word)
    if not word or not (word.isupper() or word.islower()):
        return word
    head = "İ" if word[0] in "iİ" else word[0].upper()
    tail = word[1:].replace("İ", "i").replace("I", "ı").lower()
    return head + tail


def split_name(text: str) -> tuple[list[str], list[str]]:
    """Müəllim xanası → (ad sözləri, inisiallar). Elmi dərəcə, vəzifə, ştat qeydi, il atılır.

    «b.ü.f.d.  dos.Ağayeva Səltənət Əli qızı» → (["Ağayeva", "Səltənət", "Əli", "qızı"], []);
    «Məmmədov A.M.» → (["Məmmədov"], ["a", "m"]).
    """
    head = _YEAR_CUT_RE.split(str(text or ""))[0]
    head = re.sub(r"\([^)]*\)", " ", head)
    head = re.sub(r"(?<=[a-zəöüğışç.])(?=[A-ZƏÖÜĞŞÇİ][a-zəöüğışç])", " ", head)  # «dos.Ağayeva» → «dos. Ağayeva»
    words, initials = [], []
    for token in re.split(r"[\s,;:/\\]+", head):
        token = token.strip(".-–")
        if not token or re.search(r"\d", token):
            continue
        if "." in token:  # «b.ü.f.d», «A.M» — dərəcə və ya inisiallar
            parts = [part for part in token.split(".") if part]
            if all(len(part) == 1 and part.isalpha() and part.isupper() for part in parts) and words:
                initials.extend(fold(part) for part in parts)
            continue
        folded = key(token)
        if not folded or folded in _STOPWORDS:
            continue
        if len(folded) == 1:
            if token.isupper() and words:
                initials.append(folded)
            continue
        if folded in _SUFFIXES:
            if words:
                words.append(token.lower())
            continue
        words.append(_title_word(token))
    return words, initials


def person_name(words: list[str]) -> PersonName | None:
    core = [word for word in words if key(word) not in _SUFFIXES]
    if len(core) < 2:
        return None
    if len(core) == 2:
        return PersonName(last=core[0], first=core[1], two_part=True)
    return PersonName(last=core[0], first=core[1], patronymic=" ".join(core[2:]))


class ChairTeacherResolver:
    """Bir kafedranın dərs yükü faylı üçün: ad → hesab (keşlə), lazım olsa yeni FİN-siz müəllim hesabı."""

    def __init__(self, organization, chair, *, actor_user, apply: bool, tag: str = ""):
        from .protection import is_student, load_accounts

        self.organization = organization
        self.chair = chair
        self.actor_user = actor_user
        self.apply = apply
        self.tag = tag or "dərs yükü faylı"
        self._is_student = is_student
        self.accounts = load_accounts(organization)
        self.index = AccountIndex(self.accounts, is_student=is_student)
        self._cache: dict = {}
        self._users: dict = {}
        self.created: list = []  # [(user, display)]

    # ── əsas ──────────────────────────────────────────────────────────────
    def resolve(self, text: str) -> TeacherResult:
        words, initials = split_name(text)
        cache_key = (tuple(key(word) for word in words), tuple(initials))
        if cache_key not in self._cache:
            self._cache[cache_key] = self._resolve(text, words, initials)
        return self._cache[cache_key]

    def _resolve(self, text: str, words: list, initials: list) -> TeacherResult:
        name = person_name(words)
        if name is None:
            if len(words) == 1 and initials:
                return self._by_initials(words[0], initials)
            return TeacherResult(TEACHER_UNREADABLE, display=" ".join(words) or str(text or "").strip()[:80])
        match = match_row(_NameRow(name), self.index, getattr(self.chair, "pk", None))
        if match.status in (STATUS_MATCHED, STATUS_FUZZY):
            status = TEACHER_MATCHED if match.status == STATUS_MATCHED else TEACHER_FUZZY
            if "patronymic_spelling" in (match.flags or []):
                status = TEACHER_PATRONYMIC
            return self._found(match.account, status, name.display, match.flags)
        if match.status in (STATUS_NOT_FOUND, STATUS_STUDENT_ONLY, STATUS_CONFLICT):
            status = TEACHER_CREATED_NAMESAKE if match.status == STATUS_CONFLICT else TEACHER_CREATED
            return self._create(name, text, status, [a.username for a in match.candidates])
        status = TEACHER_AMBIGUOUS if match.status == STATUS_AMBIGUOUS else TEACHER_REVIEW
        return TeacherResult(status, display=name.display, candidates=[a.username for a in match.candidates])

    def _by_initials(self, surname: str, initials: list) -> TeacherResult:
        wanted = key(surname)
        pool = [
            account
            for account in self.accounts
            if not self._is_student(account)
            and (account.last_key == wanted or loose(account.last_key) == loose(wanted))
            and account.first_key.startswith(initials[0])
        ]
        display = f"{surname} {'.'.join(i.upper() for i in initials)}."
        in_chair = [account for account in pool if getattr(self.chair, "pk", None) in account.chairs]
        pool = in_chair or pool
        if len(pool) == 1:
            return self._found(pool[0], TEACHER_INITIALS, display, ["initials"])
        status = TEACHER_AMBIGUOUS if pool else TEACHER_REVIEW
        return TeacherResult(status, display=display, candidates=[account.username for account in pool])

    def _found(self, account: Account, status: str, display: str, flags) -> TeacherResult:
        if not account.is_active or account.is_deleted:
            return TeacherResult(TEACHER_BLOCKED, display=display, candidates=[account.username])
        user = self._user(account.user_id)
        if user is None:
            return TeacherResult(TEACHER_REVIEW, display=display, candidates=[account.username])
        return TeacherResult(status, user=user, display=display, flags=list(flags or []))

    def _user(self, user_id):
        from django.contrib.auth import get_user_model

        if user_id not in self._users:
            self._users[user_id] = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        return self._users[user_id]

    # ── yeni hesab ────────────────────────────────────────────────────────
    def _create(self, name: PersonName, raw_text: str, status: str, namesakes: list) -> TeacherResult:
        from django.contrib.auth import get_user_model

        from ..intake.create import create_account, teacher_role
        from ..username_repair import name_base
        from .create import claim_name_username

        title, degree = parse_title_degree(raw_text)
        username = claim_name_username(name_base(name.first, name.last) or "muellim")
        flags = ["namesake"] if status == TEACHER_CREATED_NAMESAKE else []
        if not self.apply:
            preview = get_user_model()(username=username, first_name=name.first, last_name=name.last)
            return TeacherResult(status, user=preview, display=name.display, candidates=namesakes, flags=flags)
        from ...identity import PLACEHOLDER_EMAIL_DOMAIN

        user, _password = create_account(
            organization=self.organization,
            kind="teacher",
            values={
                "username": username,
                "first_name": name.first,
                "last_name": name.last,
                "email": f"{EMAIL_PREFIX}.{username}@{PLACEHOLDER_EMAIL_DOMAIN}",
                "fin": None,  # sahib: FİN olmasa da olar — ilk girişdə «Məcburi profil məlumatları» istəyir
                "patronymic": name.patronymic,
                "gender": "",
                "birth_date": None,
                "phone": "",
                "student_code": "",
                "academic_title": title or "",
                "academic_degree": degree or "",
                "department": getattr(self.chair, "name", "") or "",
            },
            role=teacher_role(self.organization),
            actor=self.actor_user,
            scope_unit=self.chair,
            audit_reason=f"workload_load_upload_teacher_created {self.tag}",
        )
        # Birdəfəlik parolu RİM verir («Parol təyini») — burada heç yerdə göstərilmir və saxlanılmır.
        user.set_unusable_password()
        user.save(update_fields=["password"])
        self.created.append((user, name.display))
        account = Account(
            user_id=user.pk,
            username=user.username,
            last=name.last,
            first=name.first,
            patronymic=name.patronymic,
            is_active=True,
            roles={"teacher"},
            chairs={self.chair.pk} if self.chair is not None else set(),
        )
        self.accounts.append(account)
        self.index = AccountIndex(self.accounts, is_student=self._is_student)
        self._users[user.pk] = user
        return TeacherResult(status, user=user, display=name.display, candidates=namesakes, flags=flags)


__all__ = [
    "RESOLVED",
    "TEACHER_AMBIGUOUS",
    "TEACHER_BLOCKED",
    "TEACHER_CREATED",
    "TEACHER_CREATED_NAMESAKE",
    "TEACHER_FUZZY",
    "TEACHER_INITIALS",
    "TEACHER_MATCHED",
    "TEACHER_PATRONYMIC",
    "TEACHER_REVIEW",
    "TEACHER_UNREADABLE",
    "ChairTeacherResolver",
    "TeacherResult",
    "person_name",
    "split_name",
]
