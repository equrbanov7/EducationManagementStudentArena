"""«Təşkilatın mövcud üzvləri» — əhatə və «Struktur bölməsi» / «Qrup» süzgəcləri.

Sahib (2026-10-14, dekan kimi baxış): «Bölmə» süzgəcində əslində QRUPLAR
(«0055 / (A)») görünürdü — seçici təşkilatın BÜTÜN aktiv vahidlərini (fakültə,
kafedra, ixtisas, qrup …) bir siyahıda verirdi, üstəlik dekana başqa
fakültələrin vahidləri də düşürdü. İndi:

* «Struktur bölməsi» (``hm_unit``) — qrupdan BAŞQA vahidlər (fakültə, kafedra,
  şöbə …); üzvlüyün ``scope_unit``-i ilə uyğunlaşır (əvvəlki davranış);
* «Qrup» (``hm_group``) — akademik qruplar; tələbənin AKTİV akademik qeydinin
  (``StudentAcademicRecord.group``) qrupu ilə uyğunlaşır — tələbə üzvlüyünün
  ``scope_unit``-i boşdur, ona görə köhnə «Bölmə» seçimi qrupda heç kimi tapmırdı.

Hər iki seçim aktorun ``member.view`` əhatəsi ilə məhdudlaşır (dekan → öz
fakültə alt-ağacı). Unit-əhatəli aktor əhatəsindəki TƏLƏBƏLƏRİ də görür:
qrupu və ya ixtisas bölməsi alt-ağacda olan aktiv akademik qeydin sahibləri
(qrup reyestri ilə eyni meyar — ``student_record_scope_q``).
"""

from django.apps import apps as django_apps
from django.db.models import Q

from apps.organizations.public import student_record_scope_q

#: Qrup süzgəcinə düşən vahid tipi (struktur seçicisindən çıxarılır).
GROUP_UNIT_TYPE = "group"


def _records(organization):
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    return StudentAcademicRecord.objects.filter(organization=organization, is_active=True)


def scoped_student_user_ids(organization, unit_scope) -> set:
    """Unit əhatəsindəki tələbələr (aktiv akademik qeyd üzrə); org əhatəsi üçün çağırılmır."""
    if not unit_scope.is_unit_scoped:
        return set()
    return set(_records(organization).filter(student_record_scope_q(unit_scope)).values_list("student_id", flat=True))


def membership_scope_q(*, scoped_unit_ids, scoped_student_ids, student_role_names) -> Q:
    """Üzvlük sətirləri üçün əhatə filtri: bölmə alt-ağacı + əhatədəki tələbələrin tələbə üzvlüyü."""
    q = Q(scope_unit_id__in=scoped_unit_ids)
    if scoped_student_ids:
        q |= Q(
            scope_unit__isnull=True,
            user_id__in=list(scoped_student_ids),
            role__name__in=list(student_role_names),
        )
    return q


def split_unit_options(unit_index, allowed_ids=None) -> tuple[list, list]:
    """(struktur bölmələri, qruplar) seçimləri — ``allowed_ids`` verilərsə yalnız onlar."""
    structure, groups = [], []
    for unit_id, (name, unit_type, _parent) in unit_index.units.items():
        if allowed_ids is not None and unit_id not in allowed_ids:
            continue
        (groups if unit_type == GROUP_UNIT_TYPE else structure).append((name.lower(), str(unit_id), name))
    return (
        [{"value": value, "label": label} for _key, value, label in sorted(structure)],
        [{"value": value, "label": label} for _key, value, label in sorted(groups)],
    )


def group_student_user_ids(organization, group_id) -> set:
    """Seçilmiş qrupun aktiv akademik qeydli tələbələri."""
    return set(_records(organization).filter(group_id=group_id).values_list("student_id", flat=True))


def page_student_groups(organization, user_ids) -> dict:
    """Səhifədəki tələbələrin qrupu (``user_id → group_id``) — «Bölmə» sütunu üçün TƏK sorğu."""
    if not user_ids:
        return {}
    out = {}
    rows = _records(organization).filter(student_id__in=user_ids, group__isnull=False).order_by("-created_at")
    for student_id, group_id in rows.values_list("student_id", "group_id"):
        out.setdefault(student_id, group_id)
    return out


__all__ = [
    "GROUP_UNIT_TYPE",
    "group_student_user_ids",
    "membership_scope_q",
    "page_student_groups",
    "scoped_student_user_ids",
    "split_unit_options",
]
