"""Fənn kartının KODU — vahid ``QKU-N`` fəzası (sahib 2026-11-04).

Sahib: «SAYT deyə başına yazılan kodlar QKU olmalıdı, SAYT hardan gəlib bilmirəm, ona görə fənlərdə təkrarlanır hələ».
2026-09-09 sayt planlarının importu (``import_curriculum_plans --create-subjects``) yeni kartları ``SAYT-####`` kimi
açmışdı; kataloqun qalanı sonra ``QKU-N``-ə keçdi. Bundan sonra HƏR yeni kart növbəti boş ``QKU-N`` alır
(təşkilat daxilində ən böyük ``QKU-N`` + 1; arxivlənmiş kartlar da sayılır — kod unikallığı arxivə baxmır).
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps

QKU_PREFIX = "QKU"
SITE_PREFIX = "SAYT"
QKU_CODE_RE = re.compile(r"^QKU-(\d{1,6})$")
#: VAHİD STANDART (sahib 2026-11-11: «fənn kodu səhv düşənləri də … standart olsun bir»): ``QKU-N`` — N başında sıfır
#: olmayan müsbət ədəd. ``SAYT-0012``, ``QKU-L2670``, ``QKU-MR085``, ``QKU-SRC-…`` standart DEYİL.
STANDARD_CODE_RE = re.compile(r"^QKU-[1-9]\d{0,5}$")
SITE_CODE_RE = re.compile(r"^SAYT-(\d{1,6})$")
#: ``merge_subjects`` / prod-data-ops-da qəbul olunan kodlar: saxlanılan YALNIZ ``QKU-N``, mənbə ``QKU-N`` və ya ``SAYT-N``.
KEEPER_CODE_RE = QKU_CODE_RE
SOURCE_CODE_RE = re.compile(r"^(QKU|SAYT)-\d{1,6}$")


def qku_code(number: int) -> str:
    return f"{QKU_PREFIX}-{number}"


def is_standard_code(code) -> bool:
    return bool(STANDARD_CODE_RE.match(str(code or "")))


def code_shape(code) -> str:
    """Kodun forması (inventar üçün): ``standard`` / ``blank`` / ``site`` / ``whitespace`` / ``case`` / ``other``."""
    text = str(code or "")
    if not text.strip():
        return "blank"
    if is_standard_code(text):
        return "standard"
    if text != text.strip() or "  " in text:
        return "whitespace"
    if SITE_CODE_RE.match(text):
        return "site"
    if STANDARD_CODE_RE.match(text.upper()):
        return "case"
    return "other"


def uses_standard(organization) -> bool:
    """Təşkilat ``QKU-N`` fəzasındadırmı (ən azı bir standart kodlu kart) — qapı yalnız belə təşkilatda işləyir."""
    Subject = django_apps.get_model("registrar", "Subject")
    codes = Subject._base_manager.filter(organization=organization, code__startswith=f"{QKU_PREFIX}-")
    return any(is_standard_code(code) for code in codes.values_list("code", flat=True)[:50])


def allocate_code(organization) -> str:
    """Yeni kartın kodu — növbəti boş ``QKU-N`` (çağıran ``Subject`` cədvəlini eyni tranzaksiyada yazır)."""
    return qku_code(next_qku_number(organization))


def next_qku_number(organization) -> int:
    """Təşkilatda növbəti boş ``QKU-N`` nömrəsi (ən böyük + 1)."""

    Subject = django_apps.get_model("registrar", "Subject")
    highest = 0
    for code in Subject._base_manager.filter(organization=organization, code__startswith=f"{QKU_PREFIX}-").values_list(
        "code", flat=True
    ):
        match = QKU_CODE_RE.match(code or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


__all__ = [
    "KEEPER_CODE_RE",
    "QKU_CODE_RE",
    "QKU_PREFIX",
    "SITE_CODE_RE",
    "SITE_PREFIX",
    "SOURCE_CODE_RE",
    "STANDARD_CODE_RE",
    "allocate_code",
    "code_shape",
    "is_standard_code",
    "next_qku_number",
    "qku_code",
    "uses_standard",
]
