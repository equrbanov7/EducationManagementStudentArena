"""Ehtimal olunan DUBLİKAT fənlər (yalnız OXU) — müəllim rəyi Q1, 2026-10-08.

Sual bankının fənn seçicisində eyni fənn iki dəfə görünürdü: «VoIP sistemlərinin …» və
«Vo İP sistemlərinin …» (ayrı kodlar). Bu modul təşkilat daxilində NORMALLAŞDIRILMIŞ adı
eyni olan fənləri qruplaşdırır ki, admin baxıb hansının saxlanacağına qərar versin.
HEÇ NƏ birləşdirilmir/silinmir — birləşdirmə ayrıca, şüurlu əməliyyatdır.

Normallaşdırma: registr qatlanır (türk «İ/I» qaydası ilə), az hərfləri latın əkizinə
(ə→e, ı→i, ö→o, ü→u, ğ→g, ş→s, ç→c), diakritika atılır, hərf/rəqəmdən başqa hər şey
(boşluq, nöqtə, defis, mötərizə) silinir: «Vo İP sistemlərinin» → «voipsistemlerinin».
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count

_FOLD = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ə": "e",
        "ə": "e",
        "Ö": "o",
        "ö": "o",
        "Ü": "u",
        "ü": "u",
        "Ğ": "g",
        "ğ": "g",
        "Ş": "s",
        "ş": "s",
        "Ç": "c",
        "ç": "c",
    }
)


def normalized_subject_key(name: str) -> str:
    """Müqayisə açarı — boşluq/durğu/registr/az hərfinə dözümlü."""
    text = unicodedata.normalize("NFKD", str(name or "").translate(_FOLD))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return "".join(ch for ch in text if ch.isalnum())


@dataclass
class DuplicateGroup:
    organization: object
    key: str
    subjects: list = field(default_factory=list)  # [{"id", "code", "name", "is_active", "offerings"}]


def find_duplicate_subject_groups(*, organizations, include_inactive: bool = False) -> list[DuplicateGroup]:
    """Hər təşkilatda normallaşdırılmış adı eyni olan ≥2 fənn — admin baxışı üçün."""
    from apps.registrar.models import Subject

    groups: list[DuplicateGroup] = []
    for organization in organizations:
        queryset = Subject.objects.filter(organization=organization)
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        rows = queryset.annotate(offering_count=Count("offerings", distinct=True)).order_by("name", "code")
        buckets: dict[str, list] = defaultdict(list)
        for subject in rows:
            key = normalized_subject_key(subject.name)
            if key:
                buckets[key].append(subject)
        for key, subjects in sorted(buckets.items()):
            if len(subjects) < 2:
                continue
            groups.append(
                DuplicateGroup(
                    organization=organization,
                    key=key,
                    subjects=[
                        {
                            "id": str(subject.pk),
                            "code": subject.code,
                            "name": subject.name,
                            "is_active": subject.is_active,
                            "offerings": subject.offering_count,
                        }
                        for subject in subjects
                    ],
                )
            )
    return groups


__all__ = ["DuplicateGroup", "find_duplicate_subject_groups", "normalized_subject_key"]
