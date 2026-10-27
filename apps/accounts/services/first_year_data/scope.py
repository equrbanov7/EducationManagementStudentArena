"""1-ci kurs əhatəsi: qəbul ili verilmiş AKTİV qeydi olan AKTİV tələbə hesabları."""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from ..teacher_roster.parsing import key as name_key
from ..teacher_roster.parsing import patronymic_key

__all__ = ["first_year_records", "name_key", "new_batch", "patronymic_key", "person_key"]


def first_year_records(organization, admission_year: int, counts: Counter) -> list:
    """``admission_year`` qəbulunun aktiv qeydləri (tələbə başına BİR qeyd; iki aktiv qeydli tələbə ötürülür).

    ``select_related``: tələbə + profil + qrup + proqram — sonrakı addımlar əlavə sorğu atmasın.
    """

    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    rows = list(
        Record.objects.filter(
            organization=organization,
            admission_year=admission_year,
            is_active=True,
            student__is_active=True,
        )
        .select_related("student", "student__profile", "group", "program")
        .order_by("student_id", "pk")
    )
    per_student = Counter(record.student_id for record in rows)
    out = []
    for record in rows:
        if per_student[record.student_id] > 1:
            counts["skip_multi_record"] += 1
            continue
        if getattr(record.student, "profile", None) is None:
            counts["skip_no_profile"] += 1
            continue
        out.append(record)
    return out


def person_key(last, first, patronymic) -> tuple[str, str, str]:
    """Soyad + ad + ata adı açarı (registr/diakritik/ayırıcı dözümlü; «oğlu/qızı» atılır)."""

    return name_key(last), name_key(first), patronymic_key(patronymic)


def new_batch(prefix: str) -> str:
    return f"{prefix}-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
