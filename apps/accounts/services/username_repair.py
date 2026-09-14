"""Legacy `myedu.<növ>.<id>` istifadəçi adlarını REAL ad.soyad formasına keçirmək.

Sahibin qərarı (2026-09-14, deploy hazırlığı): «my.edu» izi qalmasın — bu Qərbi
Kaspi Universitetinin real sistemidir. Qayda:

1. **Universitetin verdiyi hesab varsa və `ad.soyad` formasındadırsa, o qalır.**
   Köhnə sistemdə ayrıca username yox idi (giriş e-poçtla idi); universitetin
   özünün verdiyi `…@wcu.edu.az` e-poçtunun yerli hissəsi (`rustem.kerimov`,
   `aygun.akbarova.230k`) məhz həmin şəxsin köhnə kimliyidir → username olur.
   Sərbəst seçilmiş hissə (`asif.66666`, `memmed_gym`) qaydaya uymur → 2-ci bənd.
2. Əks halda **ad.soyad** (Azərbaycan hərfləri ASCII-yə: ə→e, ö→o, ü→u, ğ→g, ş→s,
   ç→c, ı→i, İ→i; boşluq/defis atılır, hər şey kiçik hərf).
3. **Təkrar** olanda sonuna nömrə: `elvin.qurbanov`, `elvin.qurbanov2`,
   `elvin.qurbanov3` … (istifadəçi id-sinə görə sabit sıra — təkrar icra eyni
   nəticəni verir).
4. Ad və soyad boşdursa (4 hesab) → `hesab<id>`.

Unikallıq açarı `canonical_identity` (NFKC + trim + lower) — 0013 miqrasiyasının
ifadə indeksi ilə eynidir, ona görə `Elvin.Qurbanov` / `elvin.qurbanov` toqquşması
əvvəlcədən həll olunur. Yalnız `^myedu\\.(student|worker)\\.\\d+$` hesablar dəyişir;
`qa.*`, `numune.*`, artıq ad-soyad olanlar toxunulmur. E-poçt DƏYİŞMİR.

Planlaşdırma təmiz funksiyadır (DB-siz test olunur); yazı `apply_plan` ilə,
komanda `rename_legacy_usernames --apply` ilə (dry-run defoltdur).
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Iterator

from apps.accounts.identity import canonical_identity

LEGACY_USERNAME_RE = re.compile(r"^myedu\.(student|worker)\.\d+$")
INSTITUTIONAL_DOMAINS = ("wcu.edu.az", "wcu.edu")
#: Universitet hesabı YALNIZ `ad.soyad[...]` formasındadırsa götürülür (`rustem.kerimov`,
#: `aygun.akbarova.230k`); `asif.66666`, `memmed_gym`, `elvin12682` kimi sərbəst
#: seçilmiş hesablar sahibin «ad və soyad birləşməsi» qaydasına uymur → ad.soyad.
_LOCAL_PART_RE = re.compile(r"^[a-z]{2,}\.[a-z]{2,}(?:[._-][a-z0-9]+)*$")
_AZ_MAP = str.maketrans(
    {
        "ə": "e",
        "Ə": "e",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ğ": "g",
        "Ğ": "g",
        "ş": "s",
        "Ş": "s",
        "ç": "c",
        "Ç": "c",
        "ı": "i",
        "I": "i",
        "İ": "i",
        "i": "i",
    }
)
SOURCE_INSTITUTIONAL = "institutional"
SOURCE_NAME = "name"
SOURCE_FALLBACK = "fallback"
SOURCE_KEEP = "keep"


def slug_name(value: object) -> str:
    """«Rüstəm Əli» → `rustemeli`: HTML entity-lər açılır, AZ hərfləri ASCII, yalnız [a-z0-9]."""

    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKC", text).translate(_AZ_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]", "", text)


def institutional_handle(email: object) -> str:
    """`…@wcu.edu.az` e-poçtunun yerli hissəsi (universitetin verdiyi kimlik), yoxdursa ''."""

    value = canonical_identity(email)
    if "@" not in value:
        return ""
    local, _, domain = value.rpartition("@")
    if domain not in INSTITUTIONAL_DOMAINS:
        return ""
    local = re.sub(r"[^a-z0-9._-]", "", local).strip("._-")
    if not local or not _LOCAL_PART_RE.match(local) or LEGACY_USERNAME_RE.match(local):
        return ""
    return local


def name_base(first_name: object, last_name: object) -> str:
    """`ad.soyad`; biri boşdursa o biri; ikisi də boşdursa ''."""

    first, last = slug_name(first_name), slug_name(last_name)
    if first and last:
        return f"{first}.{last}"
    return first or last


@dataclass(frozen=True)
class UsernameCandidate:
    pk: int
    username: str
    first_name: str
    last_name: str
    email: str


@dataclass(frozen=True)
class RenamePlanRow:
    pk: int
    old: str
    new: str
    source: str  # institutional | name | fallback | keep


def _desired(candidate: UsernameCandidate) -> tuple[str, str]:
    handle = institutional_handle(candidate.email)
    if handle:
        return handle, SOURCE_INSTITUTIONAL
    base = name_base(candidate.first_name, candidate.last_name)
    if base:
        return base, SOURCE_NAME
    return f"hesab{candidate.pk}", SOURCE_FALLBACK


def plan_renames(candidates: Iterable[UsernameCandidate], reserved: Iterable[str]) -> list[RenamePlanRow]:
    """Deterministik plan: `reserved` — dəyişməyən bütün mövcud istifadəçi adları.

    Sıra istifadəçi id-sinə görədir; eyni bazanı istəyən ikinci şəxs `2`, üçüncü `3`
    … alır. Artıq istədiyi adı daşıyan hesab (təkrar icra) `keep` ilə qeyd olunur
    və adını əvvəlcədən rezerv edir ki, başqası onu ala bilməsin.
    """

    taken: set[str] = {canonical_identity(name) for name in reserved if name}
    ordered = sorted(candidates, key=lambda item: item.pk)
    desired = {item.pk: _desired(item) for item in ordered}

    rows: list[RenamePlanRow] = []
    pending: list[UsernameCandidate] = []
    for item in ordered:
        base, _source = desired[item.pk]
        if canonical_identity(item.username) == canonical_identity(base):
            taken.add(canonical_identity(base))
            rows.append(RenamePlanRow(item.pk, item.username, item.username, SOURCE_KEEP))
        else:
            pending.append(item)

    for item in pending:
        base, source = desired[item.pk]
        new = base
        suffix = 2
        while canonical_identity(new) in taken:
            new = f"{base}{suffix}"
            suffix += 1
        taken.add(canonical_identity(new))
        rows.append(RenamePlanRow(item.pk, item.username, new, source))
    rows.sort(key=lambda row: row.pk)
    return rows


def load_candidates_and_reserved(user_model) -> tuple[list[UsernameCandidate], list[str]]:
    """DB-dən: dəyişəcək legacy hesablar + toxunulmayan bütün digər istifadəçi adları."""

    candidates: list[UsernameCandidate] = []
    reserved: list[str] = []
    rows = user_model.objects.order_by("pk").values_list("pk", "username", "first_name", "last_name", "email")
    for pk, username, first_name, last_name, email in rows.iterator(chunk_size=2000):
        if LEGACY_USERNAME_RE.match(username or ""):
            candidates.append(UsernameCandidate(pk, username, first_name or "", last_name or "", email or ""))
        else:
            reserved.append(username or "")
    return candidates, reserved


def apply_plan(user_model, rows: Iterable[RenamePlanRow], *, chunk_size: int = 1000) -> int:
    """Planı yaz (`keep` sətirləri atlanır). Çağıran atomic sərhədi qurur."""

    changed = [row for row in rows if row.new != row.old]
    for start in range(0, len(changed), chunk_size):
        chunk = changed[start : start + chunk_size]
        by_pk = {row.pk: row.new for row in chunk}
        users = list(user_model.objects.filter(pk__in=by_pk).only("pk", "username"))
        for user in users:
            user.username = by_pk[user.pk]
        user_model.objects.bulk_update(users, ["username"], batch_size=chunk_size)
    return len(changed)


def iter_report_rows(rows: Iterable[RenamePlanRow]) -> Iterator[tuple[str, str, str, str]]:
    for row in rows:
        yield str(row.pk), row.old, row.new, row.source


__all__ = [
    "LEGACY_USERNAME_RE",
    "RenamePlanRow",
    "UsernameCandidate",
    "apply_plan",
    "institutional_handle",
    "iter_report_rows",
    "load_candidates_and_reserved",
    "name_base",
    "plan_renames",
    "slug_name",
]
