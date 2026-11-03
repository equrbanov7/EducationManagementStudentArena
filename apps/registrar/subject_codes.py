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
SITE_CODE_RE = re.compile(r"^SAYT-(\d{1,6})$")
#: ``merge_subjects`` / prod-data-ops-da qəbul olunan kodlar: saxlanılan YALNIZ ``QKU-N``, mənbə ``QKU-N`` və ya ``SAYT-N``.
KEEPER_CODE_RE = QKU_CODE_RE
SOURCE_CODE_RE = re.compile(r"^(QKU|SAYT)-\d{1,6}$")


def qku_code(number: int) -> str:
    return f"{QKU_PREFIX}-{number}"


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
    "next_qku_number",
    "qku_code",
]
