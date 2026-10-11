"""Siyahı sətirlərinin mövcud hesablarla TUTUŞDURULMASI (sahib 2026-10-11).

Hesab indeksi təşkilatda AKTİV üzvlüyü olan bütün hesablardan qurulur (müəllim, inzibati heyət, tələbə):

* ad açarı: ``User.last_name`` + ``User.first_name`` + ``UserProfile.patronymic`` (diakritik/registr/boşluq
  dözümlü, «oğlu/qızı» atılır); ``first_name`` iki sözdürsə və ata adı boşdursa ikinci söz ata adı sayılır;
* kafedra: üzvlüyün ``scope_unit``-indən yuxarı ilk ``chair``/``department`` bölməsi.

Qayda (UYDURMA YOXDUR):

1. Soyad + ad DƏQİQ (qatlanmış) uyğun, ata adı ya eyni, ya bir tərəfdə boş → namizəd. Ata adı HƏR İKİ
   tərəfdə var və fərqlidirsə → ``conflict`` (eyni adlı başqa adam ola bilər).
2. Tələbə/məzun hesabları müəllim sətrinə HEÇ VAXT bağlanmır (``student_only``).
3. Bir neçə namizəd → ata adı tam uyğun olanlar, sonra eyni kafedradakılar üstün; yenə çoxdursa ``ambiguous``.
4. Dəqiq namizəd yoxdursa: soyad və ya adda BİR hərf fərqi, yazılış variantı (ə/a/e, q/g/k, f/v, qoşa hərf)
   və ya tərs sıra («Ad Soyad») + ata adı eyni/oxşar → ``fuzzy`` (tək namizəddirsə uyğun sayılır,
   hesabatda ayrıca göstərilir). Ata adında bir hərf/yazılış fərqi («Rəhim»/«Rahim») ``similar`` sayılır —
   uyğunluq qəbul olunur, amma ``patronymic_spelling`` qeydi ilə.

Hər sətrin BÜTÜN namizədləri (``ambiguous``/``conflict``/``review`` daxil) bloklama siyahısından çıxarılır —
yazı səhvinə görə işləyən müəllim bloklanmasın.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .parsing import fold, key, patronymic_key

STATUS_MATCHED = "matched"
STATUS_FUZZY = "fuzzy"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_CONFLICT = "conflict"
STATUS_REVIEW = "review"
STATUS_STUDENT_ONLY = "student_only"
STATUS_NOT_FOUND = "not_found"

MATCHED_STATUSES = (STATUS_MATCHED, STATUS_FUZZY)

CHAIR_UNIT_TYPES = ("chair", "department")
_CHAIR_STOPWORDS = frozenset({"kafedrasi", "kafedra", "ve", "uzre", "merkezi"})
CHAIR_MIN_SCORE = 0.45


@dataclass
class Account:
    user_id: int
    username: str
    last: str
    first: str
    patronymic: str
    is_active: bool
    is_superuser: bool = False
    is_staff: bool = False
    is_deleted: bool = False
    profile_role: str = ""
    staff_position: str = ""
    title: str = ""
    degree: str = ""
    roles: set = field(default_factory=set)  # bu təşkilatdakı aktiv rol adları
    foreign_roles: set = field(default_factory=set)  # başqa təşkilatlardakı aktiv rol adları
    membership_titles: set = field(default_factory=set)
    chairs: set = field(default_factory=set)  # kafedra OrgUnit id-ləri
    is_unit_head: bool = False

    @property
    def last_key(self) -> str:
        return key(self.last)

    @property
    def first_key(self) -> str:
        return key(self.first)

    @property
    def patronymic_key(self) -> str:
        return patronymic_key(self.patronymic)

    @property
    def display(self) -> str:
        return " ".join(part for part in (self.last, self.first, self.patronymic) if part) or self.username


@dataclass
class RowMatch:
    row: object
    status: str
    account: Account | None = None
    candidates: list = field(default_factory=list)
    chair_unit_id: object = None
    flags: list = field(default_factory=list)


# ── Kafedra adları ────────────────────────────────────────────────────────────


def _chair_tokens(name: str) -> list:
    return [token for token in fold(name).split() if token not in _CHAIR_STOPWORDS and len(token) > 1]


def _tokens_match(left: str, right: str) -> bool:
    """Söz kökü uyğunluğu: eyni söz və ya ortaq prefiks ≥3 hərf və qısa sözün ≥60 %-i («dili»/«dilçiliyi»)."""
    if left == right:
        return True
    common = 0
    for a, b in zip(left, right):
        if a != b:
            break
        common += 1
    return common >= 3 and common >= 0.6 * min(len(left), len(right))


def chair_score(file_name: str, unit_name: str) -> float:
    left, right = _chair_tokens(file_name), _chair_tokens(unit_name)
    if not left or not right:
        return 0.0
    pool, matched = list(right), 0
    for token in left:
        hit = next((candidate for candidate in pool if _tokens_match(token, candidate)), None)
        if hit is not None:
            pool.remove(hit)
            matched += 1
    dice = 2 * matched / (len(left) + len(right))
    ratio = SequenceMatcher(None, " ".join(left), " ".join(right)).ratio()
    return round(0.7 * dice + 0.3 * ratio, 3)


def match_chairs(file_chairs, units, overrides=None) -> dict:
    """Fayldakı kafedra adı → ``{"unit": (id, ad)|None, "score": float, "source": "override|fuzzy|none"}``.

    ``units`` — ``[(id, ad)]`` (yalnız kafedra tipli bölmələr). ``overrides`` — ``{fayl adı: bölmə adı}``.
    """
    overrides = {fold(name): target for name, target in (overrides or {}).items()}
    by_name = {fold(name): (unit_id, name) for unit_id, name in units}
    result = {}
    for chair in file_chairs:
        forced = overrides.get(fold(chair))
        if forced is not None:
            unit = by_name.get(fold(forced))
            result[chair] = {"unit": unit, "score": 1.0 if unit else 0.0, "source": "override" if unit else "none"}
            continue
        scored = sorted(((chair_score(chair, name), unit_id, name) for unit_id, name in units), reverse=True)
        best = scored[0] if scored else (0.0, None, "")
        if best[0] >= CHAIR_MIN_SCORE:
            result[chair] = {"unit": (best[1], best[2]), "score": best[0], "source": "fuzzy"}
        else:
            result[chair] = {"unit": None, "score": best[0], "source": "none"}
    return result


# ── Hesab indeksi ─────────────────────────────────────────────────────────────

_LOOSE = str.maketrans({"e": "a", "q": "g", "k": "g", "f": "v"})


def loose(value: str) -> str:
    """Yazılış variantlarına dözümlü açar (``key`` üzərində): ə/a/e, q/g/k, f/v bir sinif, qoşa hərf tək."""
    return re.sub(r"(.)\1+", r"\1", (value or "").translate(_LOOSE))


def _levenshtein_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    short, long_ = (left, right) if len(left) < len(right) else (right, left)
    for index in range(len(long_)):
        if long_[:index] + long_[index + 1 :] == short:
            return True
    return False


class AccountIndex:
    """Ad açarları üzrə axtarış. ``is_student`` funksiyası ``protection`` modulundan verilir."""

    def __init__(self, accounts, *, is_student):
        self.accounts = list(accounts)
        self.is_student = is_student
        self.by_name: dict = {}
        self.by_loose: dict = {}
        for account in self.accounts:
            self.by_name.setdefault((account.last_key, account.first_key), []).append(account)
            self.by_loose.setdefault((loose(account.last_key), loose(account.first_key)), []).append(account)

    def exact(self, last_key: str, first_key: str) -> list:
        return list(self.by_name.get((last_key, first_key), []))

    def variants(self, last_key: str, first_key: str) -> list:
        """Yazılış variantı (``loose``) və ya tərs sıra ilə uyğun gələn hesablar (dəqiq uyğunluqlar çıxılır)."""
        found = list(self.by_loose.get((loose(last_key), loose(first_key)), []))
        found += self.by_loose.get((loose(first_key), loose(last_key)), [])
        exact = {id(account) for account in self.exact(last_key, first_key)}
        unique = {id(account): account for account in found if id(account) not in exact}
        return list(unique.values())

    def near(self, last_key: str, first_key: str) -> list:
        found = []
        for account in self.accounts:
            same_last, same_first = account.last_key == last_key, account.first_key == first_key
            if same_last and same_first:
                continue
            if (same_last and _levenshtein_at_most_one(account.first_key, first_key)) or (
                same_first and _levenshtein_at_most_one(account.last_key, last_key)
            ):
                found.append(account)
        return found


def _patronymic_state(row_key: str, account: Account) -> str:
    """``same`` / ``similar`` (bir hərf və ya yazılış fərqi) / ``missing`` (bir tərəfdə yoxdur) / ``different``."""
    account_key = account.patronymic_key
    if not row_key or not account_key:
        return "missing"
    if row_key == account_key or row_key.startswith(account_key) or account_key.startswith(row_key):
        return "same"
    if loose(row_key) == loose(account_key) or (
        min(len(row_key), len(account_key)) >= 4 and _levenshtein_at_most_one(row_key, account_key)
    ):
        return "similar"
    return "different"


def _prefer(candidates: list, row_patronymic: str, chair_unit_id) -> list:
    strong = [account for account in candidates if _patronymic_state(row_patronymic, account) == "same"]
    pool = strong or candidates
    if len(pool) > 1 and chair_unit_id is not None:
        same_chair = [account for account in pool if chair_unit_id in account.chairs]
        pool = same_chair or pool
    if len(pool) > 1:
        teaching = [account for account in pool if account.roles & TEACHING_HINT_ROLES]
        pool = teaching or pool
    return pool


#: Bir neçə namizəd arasında müəllim rolu olanı üstün tut (``protection.TEACHING_ROLE_NAMES`` ilə eyni).
TEACHING_HINT_ROLES = frozenset(
    {"teacher", "assistant", "assistant_teacher", "instructor", "collaborator", "lab_assistant", "professor"}
)


def match_row(row, index: AccountIndex, chair_unit_id=None) -> RowMatch:
    name = row.name
    row_patronymic = name.patronymic_key
    keys = [(name.last_key, name.first_key)]
    if name.two_part:
        keys.append((name.first_key, name.last_key))  # «Ad Soyad» yazılışı

    exact = []
    for last_key, first_key in keys:
        exact.extend(index.exact(last_key, first_key))
    staff = [account for account in exact if not index.is_student(account)]
    if exact and not staff:
        return RowMatch(row, STATUS_STUDENT_ONLY, candidates=exact, chair_unit_id=chair_unit_id)
    compatible = [account for account in staff if _patronymic_state(row_patronymic, account) != "different"]
    if staff and not compatible:
        return RowMatch(row, STATUS_CONFLICT, candidates=staff, chair_unit_id=chair_unit_id)
    if compatible:
        pool = _prefer(compatible, row_patronymic, chair_unit_id)
        if len(pool) == 1:
            state = _patronymic_state(row_patronymic, pool[0])
            flags = {"same": [], "similar": ["patronymic_spelling"]}.get(state, ["patronymic_unverified"])
            return RowMatch(row, STATUS_MATCHED, pool[0], candidates=staff, chair_unit_id=chair_unit_id, flags=flags)
        return RowMatch(row, STATUS_AMBIGUOUS, candidates=staff, chair_unit_id=chair_unit_id)

    near = index.near(name.last_key, name.first_key) + index.variants(name.last_key, name.first_key)
    near = list({account.user_id: account for account in near if not index.is_student(account)}.values())
    if not near:
        return RowMatch(row, STATUS_NOT_FOUND, chair_unit_id=chair_unit_id)
    verified = [account for account in near if _patronymic_state(row_patronymic, account) in ("same", "similar")]
    if len(verified) == 1:
        return RowMatch(row, STATUS_FUZZY, verified[0], candidates=near, chair_unit_id=chair_unit_id, flags=["typo"])
    return RowMatch(row, STATUS_REVIEW, candidates=near, chair_unit_id=chair_unit_id)


__all__ = [
    "CHAIR_UNIT_TYPES",
    "MATCHED_STATUSES",
    "STATUS_AMBIGUOUS",
    "STATUS_CONFLICT",
    "STATUS_FUZZY",
    "STATUS_MATCHED",
    "STATUS_NOT_FOUND",
    "STATUS_REVIEW",
    "STATUS_STUDENT_ONLY",
    "Account",
    "AccountIndex",
    "RowMatch",
    "chair_score",
    "match_chairs",
    "match_row",
]
