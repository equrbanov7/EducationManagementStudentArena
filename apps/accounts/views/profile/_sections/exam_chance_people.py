"""«Yenidən imtahan cəhdi» bölməsi — tələbə kimliyi (ata adı + qrup) və ön-doldurma köməkçiləri (2026-10-24).

Sahib: «Eyni qrupda eyni adlı iki tələbəni ayırmaq çətindir» — çiplərdə və «Son verilən cəhd hüquqları»
cədvəlində ata adı (``UserProfile.patronymic``) və cari qrup göstərilir. Hamısı TOPLU sorğudur (N+1 yox):

* :func:`identity_map` — ``{user_id: {"patronymic", "group"}}``; qrup = cari aktiv akademik qeydin qrupu
  (``StudentAcademicRecord`` — reyestr), yoxdursa təşkilatdakı kohort (``StudentGroup``) adları;
* :func:`selected_student_ids` — ``chance_student`` parametri (vergüllə id siyahısı, ≤ 20);
* :func:`selected_students` — həmin id-lər yalnız təşkilat üzvləri arasından (yad id səssizcə atılır).
"""

from __future__ import annotations

MAX_SELECTED = 20


def selected_student_ids(raw) -> list[int]:
    ids: list[int] = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
        if len(ids) >= MAX_SELECTED:
            break
    return ids


def selected_students(organization, ids) -> list:
    if not ids or organization is None:
        return []
    from django.contrib.auth import get_user_model

    from apps.organizations.public import organization_user_queryset

    User = get_user_model()
    by_id = {
        user.pk: user for user in organization_user_queryset(organization, queryset=User.objects.filter(pk__in=ids))
    }
    return [by_id[pk] for pk in ids if pk in by_id]


def identity_map(organization, user_ids) -> dict:
    """``{user_id: {"patronymic": str, "group": str}}`` — ata adı və cari qrup (toplu, 3 sorğu)."""
    from django.apps import apps as django_apps

    from apps.accounts.models import UserProfile
    from apps.exams.public import unit_student_record_filter
    from core.person_names import clean_name_part

    user_ids = sorted({uid for uid in user_ids if uid})
    result = {uid: {"patronymic": "", "group": ""} for uid in user_ids}
    if not user_ids:
        return result
    for user_id, patronymic in UserProfile.objects.filter(user_id__in=user_ids).values_list("user_id", "patronymic"):
        result[user_id]["patronymic"] = clean_name_part(patronymic)
    if organization is None:
        return result

    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    rows = (
        record_model.objects.filter(
            organization=organization,
            student_id__in=user_ids,
            group__isnull=False,
            **unit_student_record_filter(""),
        )
        .order_by("student_id", "-created_at")
        .values_list("student_id", "group__name")
    )
    for student_id, group_name in rows:
        if not result[student_id]["group"]:
            result[student_id]["group"] = group_name or ""

    missing = [uid for uid, info in result.items() if not info["group"]]
    if missing:
        group_model = django_apps.get_model("exams", "StudentGroup")
        names: dict = {}
        for student_id, name in (
            group_model.objects.filter(organization=organization, students__in=missing)
            .order_by("name")
            .values_list("students", "name")
        ):
            names.setdefault(student_id, []).append(name)
        for student_id, group_names in names.items():
            result[student_id]["group"] = ", ".join(group_names[:2])
    return result


__all__ = ["MAX_SELECTED", "identity_map", "selected_student_ids", "selected_students"]
