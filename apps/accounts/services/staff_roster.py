"""Heyət siyahısının (Excel/CSV) oxunması, vəzifə → rol xəritəsi və vahid həlli.

Sahib 2026-09-06-da «kim hansı vəzifədədir» siyahısını verdi (52 struktur
bölməsi, 118 nəfər). Bu modul siyahını MƏNTİQƏ çevirir; yazı əməli
``seed_staff_roster`` komandasındadır (dry-run defolt).

QAYDA: tanınmayan vəzifə UYDURULMUR — `member` rolu + vəzifə mətni yazılır və
hesabatda «xəritələnmədi» kimi göstərilir (sahibin göstərişi: sistemdə olmayan
rollar hələlik olduğu kimi qalsın).

2026-09-06 sahib qərarları (bax `docs/audits/2026-09-05/HEYET_SIYAHISI.md`
bölmə 3): «Baş direktor» → `rector`, «Qəyyumlar şurası» bölməsinin hər üzvü →
`trustee`, qarşılıqsız bölmədəki hər «Müdir» → `admin_unit_head` (əvvəllər
üçü də `member`-ə düşürdü).
"""

from __future__ import annotations

import re
import unicodedata

#: Bölmə başlığını şəxs sətrindən ayıran açar sözlər (kiçik hərflə axtarılır).
_UNIT_KEYWORDS = (
    "şöbə",
    "mərkəz",
    "kafedra",
    "məktəb",
    "şura",
    "laborotoriya",
    "laboratoriya",
    "kitabxana",
    "direktor",
    "prorektor",
    "rektor",
    "magsturatura",
    "magistratura",
    "doktorontura",
    "doktorantura",
    "texnologiyalar",
    "idarə olunması",
    "iş şöbəsi",
    "sənədlər",
    "inkişaf",
    "təminatı",
    "monitorinq",
    "arxiv",
    "audit",
    "mühasibat",
    "innovasiyalar",
    "tədbirlərin",
    "nəşirlərlə",
    "nəşriyyat",
    "imtahan",
    "dəstək",
    "strateji",
    "resusları",
    "resursları",
    "ekologiya",
    "dizayn",
)

#: Vəzifə mətni → təşkilat rolunun adı. Açar KİÇİK hərflə, «başlanğıcına görə»
#: uyğunlaşdırılır (məs. «Baş mütəxəssi(s)» → mutəxəssis qaydası tutmasın deyə
#: daha uzun açar əvvəldədir).
POSITION_ROLE_RULES = (
    ("dekan müavini", "vice_dean"),
    ("dekan müvini", "vice_dean"),
    ("dekan əvəzi", "vice_dean"),
    ("dekan", "dean"),
    ("müavin", "vice_dean"),
    ("icraçı prorektor", "vice_rector"),
    ("prorektor", "vice_rector"),
    # 2026-09-06 sahib qərarı: «Baş direktor» = rektorla eyni səviyyə → `rector`.
    # Siyahıda yazı səhvi var («Baş dirketor») — hər iki yazılış saxlanılır.
    ("baş direktor", "rector"),
    ("baş dirketor", "rector"),
    ("tyutor", "tutor"),
    ("laborant", "lab_assistant"),
    ("müəllim", "teacher"),
)

#: Bölmə adı (kiçik hərflə, açar söz) → həmin bölmədəki «Müdir» üçün rol.
UNIT_HEAD_ROLE_RULES = (
    ("kafedra", "chair_head"),
    ("imtahan mərkəzi", "exam_center_head"),
    ("rəqəmsal inkişaf", "ikt_rehber"),
    ("insan resu", "hr"),
    ("tədrisin təşkili", "teaching_office_head"),
)

#: Bölmə açar sözü → həmin bölmənin ADİ əməkdaşı üçün rol.
UNIT_STAFF_ROLE_RULES = (
    ("imtahan mərkəzi", "exam_center_staff"),
    ("rəqəmsal inkişaf", "rim_staff"),
    ("insan resu", "hr"),
    ("tədrisin təşkili", "teaching_office_staff"),
    ("dövlət nümunəli sənədlər", "student_services"),
    ("tələbə dəstək", "student_services"),
)

#: Heç bir qaydaya düşməyən vəzifə üçün rol (səlahiyyət vermir).
FALLBACK_ROLE = "member"

#: Heyət siyahısındakı adam BU rolları daşıyan hesab OLA BİLMƏZ. Eyni ad-soyadlı
#: bir neçə hesab tapılanda tələbə/məzun/valideyn hesabları kənarlaşdırılır —
#: 2026-09-06 klon yoxlamasında «Babayeva Nigar» adına PROREKTOR rolu tələbə
#: hesabına yapışdırılmışdı, çünki uyğunlaşdırma yalnız ada baxırdı.
NON_STAFF_ROLE_NAMES = frozenset({"student", "alumni", "lead_student", "parent"})

_PERSON_STOPWORDS = {"və", "üzrə", "ilə", "üçün"}


#: Türk/Azərbaycan «İ» kiçildikdə `i` + birləşən nöqtə verir (U+0307) və adi
#: `in` axtarışı tutmur — «Rəqəmsal İnkişaf» → «rəqəmsal i̇nkişaf». Müqayisə
#: üçün İ/I/ı hamısı sadə `i`-yə yığılır (uyğunlaşdırma onsuz da qeyri-dəqiqdir).
_FOLD = str.maketrans({"İ": "i", "I": "i", "ı": "i", "\u0307": ""})


def _norm(value: str) -> str:
    """Kiçik hərf + artıq boşluqsuz + İ/ı folding — müqayisə üçün."""
    text = unicodedata.normalize("NFC", str(value or "")).strip().translate(_FOLD).lower()
    text = unicodedata.normalize("NFD", text).replace("\u0307", "")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text))


#: `_norm()`-dan keçmiş «Qəyyumlar şurası» — sondakı «ı» folding-dən sonra
#: «i»-ə düşür (məs. «şurasi»), ona görə literalı əl ilə yazmaq əvəzinə
#: `_norm()`-un özündən alırıq (2026-09-06 sahib qərarı: bax `role_for`).
_QƏYYUMLAR_ŞURASI = _norm("Qəyyumlar şurası")


def looks_like_person(text: str) -> bool:
    """Sətir ŞƏXS adıdır, yoxsa bölmə başlığı?

    Şəxs: 2–4 söz, hamısı böyük hərflə başlayır, bağlayıcı və struktur açar
    sözləri yoxdur. «Babayeva Nigar Mais» → şəxs; «Elmi Kitabxana» → bölmə.
    """
    raw = str(text or "").strip()
    if not raw:
        return False
    lowered = _norm(raw)
    if any(keyword in lowered for keyword in _UNIT_KEYWORDS):
        return False
    tokens = raw.split()
    if not 2 <= len(tokens) <= 4:
        return False
    if any(token.lower() in _PERSON_STOPWORDS for token in tokens):
        return False
    return all(token[:1].isupper() for token in tokens if token)


def parse_rows(rows):
    """[(ad, vəzifə)] → [{"name", "position", "section"}] (başlıqlar süzülür)."""
    people, section = [], ""
    for raw_name, raw_position in rows:
        name = str(raw_name or "").strip()
        position = str(raw_position or "").strip()
        if not name:
            continue
        if not position and not looks_like_person(name):
            section = name
            continue
        people.append({"name": name, "position": position, "section": section})
    return people


def role_for(section: str, position: str) -> tuple[str, bool]:
    """(rol adı, xəritələndi?) — tanınmayan vəzifə `member`-ə düşür.

    Sıra: (1) prorektor bloku, (1b) Qəyyumlar Şurası, (2) dekanlıq (fakültə/
    məktəb), (3) bölmə RƏHBƏRİ, (4) bölmə MÜAVİNİ, (5) ümumi vəzifə qaydaları,
    (6) bölmənin adi əməkdaşı.
    """
    unit = _norm(section)
    title = _norm(position)
    is_faculty = any(word in unit for word in ("məktəb", "fakültə"))

    # (1) «Prorektor» bölməsindəki hər kəs prorektordur — vəzifə mətni portfeldir
    #     («Elmi işlər üzrə», «Ümumi İşlər üzrə», boş...).
    if unit.startswith("prorektor"):
        return "vice_rector", True

    # (1b) Qəyyumlar Şurası — NƏZARƏT orqanıdır, vəzifə mətni («Sədr», üzv...)
    #      əhəmiyyətsizdir; prorektor qaydası ilə EYNİ naxış (bölmə həll edir).
    #      2026-09-06 sahib qərarı, bax `default_roles_oversight.py`.
    if unit.startswith(_QƏYYUMLAR_ŞURASI):
        return "trustee", True

    # (2) Dekanlıq.
    if title.startswith(("dekan müavini", "dekan müvini", "dekan əvəzi")):
        return "vice_dean", True
    if title.startswith("dekan"):
        return "dean", True
    if is_faculty and title.startswith("müavin"):
        return "vice_dean", True

    # (3) Bölmə rəhbəri («Müdir», «Müdir əvəzi»). Qarşılığı olan (akademik/
    #     mərkəz) bölmələrdə domen-spesifik rol; qalanlarında (mühasibatlıq,
    #     kadrlar, arxiv...) 2026-09-06-dan `admin_unit_head` — əvvəllər bura
    #     `member`-ə düşürdü (bax HEYET_SIYAHISI.md bölmə 3, sahib qərarı).
    if title.startswith("müdir") and not title.startswith("müdir müavini"):
        for keyword, role in UNIT_HEAD_ROLE_RULES:
            if keyword in unit:
                return role, True
        return "admin_unit_head", True

    # (4) Bölmə müavini rəhbər DEYİL: varsa həmin bölmənin əməkdaş rolu.
    if title.startswith(("müdir müavini", "müavin")):
        for keyword, role in UNIT_STAFF_ROLE_RULES:
            if keyword in unit:
                return role, True
        return FALLBACK_ROLE, False

    # (5) Ümumi vəzifələr (tyutor, laborant, müəllim...).
    for prefix, role in POSITION_ROLE_RULES:
        if title.startswith(prefix):
            return role, True

    # (6) Bölmənin adi əməkdaşı.
    for keyword, role in UNIT_STAFF_ROLE_RULES:
        if keyword in unit:
            return role, True
    return FALLBACK_ROLE, False


def match_unit(section: str, units):
    """Bölmə adına ən yaxın `OrgUnit` (tam → başlanğıc → söz kəsişməsi)."""
    target = _norm(section)
    if not target:
        return None
    by_name = {_norm(unit.name): unit for unit in units}
    if target in by_name:
        return by_name[target]
    for name, unit in by_name.items():
        if name and (target.startswith(name) or name.startswith(target)):
            return unit
    target_words = {word for word in target.split() if len(word) > 3}
    best, best_score = None, 0
    for name, unit in by_name.items():
        score = len(target_words & {word for word in name.split() if len(word) > 3})
        if score > best_score:
            best, best_score = unit, score
    if best_score >= 2:
        return best
    # Siyahıda yazı səhvləri var («Azərbbaycan», «Magsturatura») — söz kəsişməsi
    # tutmayanda simvol-səviyyəli oxşarlığa baxırıq (0.72 empirik həddir:
    # yazı səhvini tutur, fərqli kafedraları qarışdırmır).
    from difflib import SequenceMatcher

    best, best_ratio = None, 0.0
    for name, unit in by_name.items():
        ratio = SequenceMatcher(None, target, name).ratio()
        if ratio > best_ratio:
            best, best_ratio = unit, ratio
    return best if best_ratio >= 0.72 else None


def split_name(full_name: str) -> tuple[str, str]:
    """«Soyad Ad Ata adı» → (ad, soyad). Siyahı bu sıradadır."""
    tokens = str(full_name or "").split()
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[1], tokens[0]


def username_seed(full_name: str) -> str:
    """Addan latın hərfli istifadəçi adı özəyi (`n.novruzova`)."""
    first, last = split_name(full_name)
    table = str.maketrans({"ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c"})
    first = unicodedata.normalize("NFKD", first.lower().translate(table))
    last = unicodedata.normalize("NFKD", last.lower().translate(table))
    clean = lambda text: re.sub(r"[^a-z]", "", text.encode("ascii", "ignore").decode())  # noqa: E731
    return f"{clean(first)[:1]}.{clean(last)}".strip(".") or "isci"


__all__ = [
    "FALLBACK_ROLE",
    "POSITION_ROLE_RULES",
    "UNIT_HEAD_ROLE_RULES",
    "UNIT_STAFF_ROLE_RULES",
    "looks_like_person",
    "match_unit",
    "parse_rows",
    "role_for",
    "split_name",
    "username_seed",
]
