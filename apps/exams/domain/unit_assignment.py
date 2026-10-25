"""Reyestr qrupu (`OrgUnit` tipi GROUP) ilə imtahan təyinatı — paylaşılan sorğu parçaları.

2026-09-14 (W4 `w4wizard`, R2). `Exam.allowed_units` M2M-i imtahanı qrup
reyestrindəki akademik qrupa bağlayır. Tələbənin qrupu YEGANƏ mənbədən —
cari aktiv `StudentAcademicRecord.group`-dan — oxunur (klon bazasında 7799
qeyd qrupla, `Membership.scope_unit` isə cəmi 1 sətirdə doludur, yəni
üzvlük vahidi etibarlı mənbə deyil). `is_active=True` + `status=enrolled`:
xaric olunmuş / akademik məzuniyyətdəki tələbə imtahan almır.

2026-10-26 (sahib: «qrupda daha çox tələbə var, amma seçəndə azı görünür»): imtahanın FƏNNİ varsa, həmin
fənnin CARİ dövrdəki jurnalına (açılışın qrupu imtahanın qrupu / alt qrupu) ``enrolled`` yazılmış tələbələr də
qrupla daxildir — İmtahan Mərkəzinin siyahısı jurnaldandır (alt qrupdan əlavə, qrupu dəyişmiş tələbə və s.).

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


def _enrollment_model():
    from django.apps import apps as django_apps

    return django_apps.get_model("registrar", "Enrollment")


def journal_student_ids(subject_id, unit_ids) -> set:
    """*subject_id* fənninin CARİ dövr jurnallarına (açılışın qrupu *unit_ids* içində) yazılmış tələbələr."""
    if not subject_id or not unit_ids:
        return set()
    return set(
        _enrollment_model()
        .objects.filter(
            offering__subject_id=subject_id,
            offering__group_id__in=list(unit_ids),
            offering__period__is_current=True,
            status="enrolled",
        )
        .values_list("student_id", flat=True)
    )


def _journal_pairs(user) -> list:
    """İstifadəçinin cari dövr jurnalları: ``[(fənn id, qrup id)]`` (BİR sorğu; DISTINCT-siz — tutum testi)."""
    rows = (
        _enrollment_model()
        .objects.filter(
            student=user, status="enrolled", offering__period__is_current=True, offering__group__isnull=False
        )
        .order_by()
        .values_list("offering__subject_id", "offering__group_id")
    )
    return sorted(set(rows), key=str)


def _journal_exams_q(user, *, prefix: str = ""):
    """İmtahanın fənni + reyestr qrupu tələbənin cari jurnalına (dəqiq qrup) uyğundur; jurnal yoxdursa ``None``."""
    if user is None or not getattr(user, "pk", None):
        return None
    condition = None
    for subject_id, group_id in _journal_pairs(user):
        part = Q(**{f"{prefix}subject_id": subject_id, f"{prefix}allowed_units": group_id})
        condition = part if condition is None else condition | part
    return condition


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
    journal_q = _journal_exams_q(user, prefix=prefix)
    unit_q = Q(**{f"{prefix}allowed_units__in": ids}) if ids else None
    if unit_q is None and journal_q is None:
        return Q(pk__in=[])
    if unit_q is None or journal_q is None:
        return unit_q if journal_q is None else journal_q
    return unit_q | journal_q


def unit_assigned_student_ids(exam) -> set[int]:
    """İmtahanın reyestr qruplarındakı (alt qruplar daxil) cari tələbələrin `User.id` çoxluğu."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    ids = exam_unit_ids_with_subgroups(exam)
    if not ids:
        return set()
    record_path = "academic_records__"
    registry = set(
        User.objects.filter(
            **{f"{record_path}group__in": ids},
            **unit_student_record_filter(record_path),
        ).values_list("id", flat=True)
    )
    exact = [unit.pk for unit in exam.allowed_units.all()]
    return registry | journal_student_ids(getattr(exam, "subject_id", None), exact)


def user_in_allowed_units(exam, user) -> bool:
    """Tək istifadəçi üçün — model giriş siyasəti (`can_user_see/start`); alt qrup + fənn jurnalı daxil."""
    ids = user_unit_ids_with_parents(user)
    if ids and exam.allowed_units.filter(pk__in=ids).exists():
        return True
    subject_id = getattr(exam, "subject_id", None)
    if not subject_id:
        return False
    units = list(exam.allowed_units.values_list("pk", flat=True))
    return bool(units) and user.pk in journal_student_ids(subject_id, units)


__all__ = [
    "UNIT_STUDENT_RECORD_STATUS",
    "exam_unit_ids_with_subgroups",
    "journal_student_ids",
    "user_unit_ids_with_parents",
    "unit_assigned_exams_q",
    "unit_assigned_student_ids",
    "unit_student_record_filter",
    "user_in_allowed_units",
]


def student_assigned_exams_q(user) -> Q:
    """Tələbəyə təyin olunmuş imtahanlar — hər təyinat yolu ayrıca `pk IN (subquery)`.

    Tutum testi 2026-10-05: OR ilə birləşmiş M2M şərtləri (`allowed_users`,
    `allowed_groups__students`, `allowed_units`, kurs üzvlüyü) LEFT JOIN + DISTINCT
    verirdi — Postgres `user_id = X`-i hər JOIN-ə ayrıca tətbiq edə bilmir və
    2500 tələbəli qrupların bütün sətirlərini birləşdirirdi (kabinetdə hər sorğu
    ~150-200 ms, 10 tələbədə DB 1.3 nüvə). Semi-join sətir çoxaltmır, DISTINCT
    lazım deyil; nəticə çoxluğu əvvəlki şərtlə eynidir.
    """
    from apps.exams.models import Exam

    exams = Exam.objects.order_by()
    condition = (
        Q(pk__in=exams.filter(allowed_users=user).values("pk"))
        | Q(pk__in=exams.filter(allowed_groups__students=user).values("pk"))
        | Q(
            pk__in=exams.filter(
                course__memberships__user=user,
                course__memberships__role="student",
                course__status="published",
            ).values("pk")
        )
    )
    unit_ids = user_unit_ids_with_parents(user)
    if unit_ids:
        condition |= Q(pk__in=exams.filter(allowed_units__in=unit_ids).values("pk"))
    journal_q = _journal_exams_q(user)
    if journal_q is not None:
        condition |= Q(pk__in=exams.filter(journal_q).values("pk"))
    return condition


def student_excluded_exams_q(user) -> Q:
    """`exclude(...)` üçün: tələbə imtahandan xaric edilib (semi-join, DISTINCT-siz)."""
    from apps.exams.models import Exam

    return Q(pk__in=Exam.objects.order_by().filter(excluded_users=user).values("pk"))
