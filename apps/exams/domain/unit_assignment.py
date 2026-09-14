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


def unit_assigned_exams_q(user, *, prefix: str = "") -> Q:
    """`Exam` queryset-i üçün: istifadəçi icazəli reyestr qrupunun cari üzvüdür.

    ``prefix`` başqa modeldən imtahana gedən yol üçündür (məs. `exam__`).
    Bütün şərtlər TƏK `Q`-dadır ki, eyni `.filter()` çağırışında eyni JOIN-u
    paylaşsın (çoxdəyərli əlaqədə ayrı `filter()` ayrı JOIN yaradar).
    """
    path = f"{prefix}allowed_units__student_records__"
    return Q(**{f"{path}student": user}, **unit_student_record_filter(path))


def unit_assigned_student_ids(exam) -> set[int]:
    """İmtahanın reyestr qruplarındakı cari tələbələrin `User.id` çoxluğu.

    `User` tərəfindən yazılıb (`academic_records` reverse əlaqəsi) ki, çoxdəyərli
    əlaqədə filter + values_list eyni JOIN-da qalsın; nəticə `set` olduğundan
    təkrarlar (bir tələbənin iki qeydi) əhəmiyyət daşımır.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    record_path = "academic_records__"
    return set(
        User.objects.filter(
            **{f"{record_path}group__in": exam.allowed_units.values("pk")},
            **unit_student_record_filter(record_path),
        ).values_list("id", flat=True)
    )


def user_in_allowed_units(exam, user) -> bool:
    """Tək istifadəçi üçün `exists()` — model giriş siyasəti (`can_user_see/start`)."""
    record_path = "student_records__"
    return exam.allowed_units.filter(
        **{f"{record_path}student": user},
        **unit_student_record_filter(record_path),
    ).exists()


__all__ = [
    "UNIT_STUDENT_RECORD_STATUS",
    "unit_assigned_exams_q",
    "unit_assigned_student_ids",
    "unit_student_record_filter",
    "user_in_allowed_units",
]
