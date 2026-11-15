"""Ad hissələrində idxal «boşluq doldurucuları» — göstərmədə boş sayılır (QA-1 F15).

Köhnə sistemdən gələn siyahılarda ata adı olmayanda ``-`` yazılırdı; jurnal sətri «Soyadov Ad -» kimi görünürdü.
Saxlanan dəyər dəyişmir — yalnız çıxışda atılır (jurnal adı, kadr/tələbə siyahıları, ``full_name_with_patronymic``).
"""

from __future__ import annotations

import html
import unicodedata

_PUNCTUATION_ONLY = frozenset("-–—−_.?/*,;:'\"`~ ")
_WORD_PLACEHOLDERS = frozenset({"n/a", "na", "none", "null", "yoxdur", "yox"})


def clean_name_part(value) -> str:
    """Kənar boşluqlar atılır; yalnız durğu işarəsindən ibarət («-», «--», «.») və ya «yoxdur» → ``""``."""
    text = (value or "").strip() if isinstance(value, str) or value is None else str(value).strip()
    if not text:
        return ""
    if all(char in _PUNCTUATION_ONLY for char in text) or text.casefold() in _WORD_PLACEHOLDERS:
        return ""
    return text


def user_display_name_with_patronymic(user) -> str:
    """«Ad Soyad Ata adı» — istifadəçi obyekti üçün (sahib 2026-10-26: ata adı axtarış/PIN siyahılarında da görünsün).

    Profil (``user.profile``) yoxdursa və ya ata adı boşdursa «Ad Soyad»; ad da boşdursa username.
    Sorğu açmamaq üçün çağıran ``select_related("profile")`` etməlidir.
    """
    profile = getattr(user, "profile", None)  # RelatedObjectDoesNotExist ⊂ AttributeError
    parts = (
        (getattr(user, "first_name", "") or "").strip(),
        (getattr(user, "last_name", "") or "").strip(),
        clean_name_part(getattr(profile, "patronymic", "") if profile is not None else ""),
    )
    return " ".join(part for part in parts if part) or getattr(user, "username", "") or ""


def person_label_from_parts(last_name="", first_name="", patronymic="", username="") -> str:
    """«Soyad Ad Ata adı» — ayrı sahələrdən (``values()`` sətirləri, annotasiya, JSON üçün).

    Sahib 2026-11-15: axtarış/seçicilərdə insan HƏMİŞƏ eyni sırada — jurnal qridindəki «SOYAD AD ATA ADI» kimi —
    görünsün ki, eyni adlı iki nəfəri ata adı ilə ayırmaq olsun. Ata adı yer tutucusu («-», «yoxdur») atılır;
    hamısı boşdursa ``username``.
    """
    parts = (str(last_name or "").strip(), str(first_name or "").strip(), clean_name_part(patronymic))
    return " ".join(part for part in parts if part) or (username or "")


_UNSET = object()


def person_label(user, patronymic=_UNSET) -> str:
    """«Soyad Ad Ata adı» — axtarış nəticəsi, autocomplete və seçici option-ları üçün vahid etiket.

    Ata adı ``user.profile.patronymic``-dən oxunur — N+1 olmasın deyə çağıran ``select_related("profile")`` etməlidir;
    ata adı artıq əldədirsə (annotasiya, xəritə) ``patronymic=`` ilə verilir və profilə toxunulmur.
    ``None`` → ``""``.
    """
    if user is None:
        return ""
    if patronymic is _UNSET:
        profile = getattr(user, "profile", None)  # RelatedObjectDoesNotExist ⊂ AttributeError
        patronymic = getattr(profile, "patronymic", "") if profile is not None else ""
    return person_label_from_parts(
        getattr(user, "last_name", ""),
        getattr(user, "first_name", ""),
        patronymic,
        getattr(user, "username", "") or "",
    )


#: ``select_related``/``values`` üçün ata adı yolu (``auth.User`` → ``UserProfile.patronymic``).
PATRONYMIC_LOOKUP = "profile__patronymic"


def name_key(value) -> str:
    """Ad hissəsinin müqayisə açarı (PR #266 qaydası): HTML varlıqları («&Uuml;»), böyük/kiçik, İ/ı, diakritika və
    boşluq fərqi sayılmır — «CƏFƏRLİ» = «Cəfərli», «G&Uuml;LÜSTAN» = «Gülüstan»."""
    text = html.unescape(str(value or "")).replace("İ", "I").replace("ı", "i").casefold()
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return " ".join(text.split())


def same_person_name(last_name, first_name, other_last_name, other_first_name) -> bool:
    """Soyad VƏ ad (:func:`name_key` ilə) eynidir; hər iki hissə dolu olmalıdır.

    FİN tutuşdurmasının təsdiqi (sahib 2026-11-08): köhnə sistemdə bir neçə tələbə sətrinə BAŞQA tələbənin FİN-i
    yazılıb — FİN eyni, ad başqadırsa bu FİN sahibi deyil (bir adamın bal və qeydiyyatları başqasına yazılırdı).
    """
    last, first = name_key(last_name), name_key(first_name)
    return bool(last and first) and last == name_key(other_last_name) and first == name_key(other_first_name)


__all__ = [
    "PATRONYMIC_LOOKUP",
    "clean_name_part",
    "name_key",
    "person_label",
    "person_label_from_parts",
    "same_person_name",
    "user_display_name_with_patronymic",
]
