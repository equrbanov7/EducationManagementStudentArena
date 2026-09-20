"""Reyestr qrupu (`OrgUnit` tipi GROUP) ilə imtahan təyinatı — paylaşılan sorğu parçaları.

2026-09-14 (W4 `w4wizard`, R2). `Exam.allowed_units` M2M-i imtahanı qrup
reyestrindəki akademik qrupa bağlayır. Tələbənin qrupu YEGANƏ mənbədən —
cari aktiv `StudentAcademicRecord.group`-dan — oxunur (klon bazasında 7799
qeyd qrupla, `Membership.scope_unit` isə cəmi 1 sətirdə doludur, yəni
üzvlük vahidi etibarlı mənbə deyil). `is_active=True` + `status=enrolled`:
xaric olunmuş / akademik məzuniyyətdəki tələbə imtahan almır.

Bütün oxuyanlar (giriş siyasəti, tələbə siyahıları, kabinet sayğacları, PIN
provizionu, bildiriş alıcıları) EYNİ şərti işlətməlidir ki, «siyahıda görünür,
amma başlaya bilmir» kimi uyğunsuzluq yaranmasın — ona görə şərt burada
tək yerdədir.
"""

from django.db.models import Q

#: Reyestr qrupu ilə imtahan almağa hüquq verən akademik qeyd statusu.
UNIT_STUDENT_RECORD_STATUS = "enrolled"


def unit_student_record_filter(prefix: str) -> dict:
    """`prefix` — `StudentAcademicRecord`-a gedən lookup yolu (sonu `__` ilə)."""
    return {
        f"{prefix}is_active": True,
        f"{prefix}status": UNIT_STUDENT_RECORD_STATUS,
    }


def _record_model():
    from django.apps import apps as django_apps

    return django_apps.get_model("registrar", "StudentAcademicRecord")


def _subgroup_service():
    from apps.registrar.public import subgroup_rollup

    return subgroup_rollup


def user_unit_ids_with_parents(user) -> list:
    """İstifadəçinin cari (enrolled) qrupları + onların ANA qrup namizədləri.

    SAHİB (2026-09-21): ana qrupa («234 K az») təyin olunmuş imtahan alt qrupun
    («234 K-1») tələbəsinə də açıqdır — alt qrup əlaqəsi reyestr bölməsinin
    `settings.parent_group` izi və ya ad şablonu ilə tanınır."""
    if user is None or not getattr(user, "pk", None):
        return []
    records = (
        _record_model()
        .objects.filter(student=user, group__isnull=False, **unit_student_record_filter(""))
        .select_related("group", "organization")
    )
    ids: list = []
    service = _subgroup_service()
    for record in records:
        for unit in [record.group, *service.parent_group_candidates(record.organization, record.group)]:
            if unit.pk not in ids:
                ids.append(unit.pk)
    return ids


def exam_unit_ids_with_subgroups(exam) -> list:
    """İmtahanın reyestr qrupları + onların alt qrupları (bax `user_unit_ids_with_parents`)."""
    units = list(exam.allowed_units.select_related("parent"))
    if not units:
        return []
    ids = [unit.pk for unit in units]
    for unit in _subgroup_service().subgroup_units(exam.organization, units):
        if unit.pk not in ids:
            ids.append(unit.pk)
    return ids


def unit_assigned_exams_q(user, *, prefix: str = "") -> Q:
    """`Exam` queryset-i üçün: istifadəçi icazəli reyestr qrupunun (və ya onun
    ana qrupunun) cari üzvüdür. ``prefix`` başqa modeldən imtahana gedən yol
    üçündür (məs. `exam__`)."""
    ids = user_unit_ids_with_parents(user)
    if not ids:
        return Q(pk__in=[])
    return Q(**{f"{prefix}allowed_units__in": ids})


def unit_assigned_student_ids(exam) -> set[int]:
    """İmtahanın reyestr qruplarındakı (alt qruplar daxil) cari tələbələrin `User.id` çoxluğu."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    ids = exam_unit_ids_with_subgroups(exam)
    if not ids:
        return set()
    record_path = "academic_records__"
    return set(
        User.objects.filter(
            **{f"{record_path}group__in": ids},
            **unit_student_record_filter(record_path),
        ).values_list("id", flat=True)
    )


def user_in_allowed_units(exam, user) -> bool:
    """Tək istifadəçi üçün — model giriş siyasəti (`can_user_see/start`); alt qrup daxil."""
    ids = user_unit_ids_with_parents(user)
    return bool(ids) and exam.allowed_units.filter(pk__in=ids).exists()


__all__ = [
    "UNIT_STUDENT_RECORD_STATUS",
    "exam_unit_ids_with_subgroups",
    "user_unit_ids_with_parents",
    "unit_assigned_exams_q",
    "unit_assigned_student_ids",
    "unit_student_record_filter",
    "user_in_allowed_units",
]
