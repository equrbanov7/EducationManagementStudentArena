"""Ad hissələrində idxal «boşluq doldurucuları» — göstərmədə boş sayılır (QA-1 F15).

Köhnə sistemdən gələn siyahılarda ata adı olmayanda ``-`` yazılırdı; jurnal sətri «Soyadov Ad -» kimi görünürdü.
Saxlanan dəyər dəyişmir — yalnız çıxışda atılır (jurnal adı, kadr/tələbə siyahıları, ``full_name_with_patronymic``).
"""

from __future__ import annotations

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


__all__ = ["clean_name_part", "user_display_name_with_patronymic"]
