"""Qorunan media üçün jurnal/düzəliş/müraciət prefikslərinin icazə siyasətləri.

``core.media_views`` bu moduldan ``PRIVATE_PREFIXES`` və ``ACCESS_CHECKERS``
lüğətlərini götürüb öz reyestrinə qatır.  Bölgünün səbəbi ikiqatdır:

1. **Modul-ölçü büdcəsi** (``scripts/check_module_size.py``, SOFT_CAP=600) —
   ``media_views.py`` artıq tavana yaxın idi.
2. **Sərhəd** — burada yalnız *domen* siyasətləri var (registrar düzəliş
   sənədləri, imtahan bal sübutu, köhnə üzrlü qayıb sənədləri, müraciət
   qoşmaları); fayl təhvili/verilməsi məntiqi ``media_views``-da qalır.

Asılılıq istiqaməti BİR TƏRƏFLİDİR: ``media_views`` → ``media_policies``.
Modellər ``django.apps.apps.get_model`` ilə gec (lazy) həll olunur ki, app
sərhədləri (``scripts/module_deps.py``) pozulmasın.

Təhlükəsizlik müqaviləsi
------------------------
* Hər checker imzası ``(user, path) -> bool``; **default DENY**.
* Sətir tapılmasa (``DoesNotExist``) və ya dublikat uyğunluq olsa → ``False``.
* Anonim istifadəçi checker-ə heç çatmır (``media_views`` login-ə yönləndirir).

2026-09-02 auditinin P0-1 tapıntısı: bu prefikslərin **heç biri** private
sayılmırdı, yəni tibbi arayışlar və bal-düzəliş sübutları autentifikasiyasız
verilirdi.  Reyestrə əlavə DEYİL, prefiks siyahısına əlavə də vacibdir —
``media_views._is_private`` məhz həmin siyahıya baxır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils.module_loading import import_string

#: lab_assistant = 50, teacher = 60 → müəllim səviyyəsi.
TEACHER_MIN_LEVEL = 50

#: Təşkilat-admin səviyyəsi — düzəliş sənədləri həssasdır (tibbi arayış və s.).
ORG_ADMIN_MIN_LEVEL = 80

#: Sənədli düzəliş səlahiyyəti (İKT Rəhbəri / RİM, rektor, owner).
CORRECT_PERMISSION = "journal.correct"

#: Müraciət modulunun görünüş siyasəti — NÖQTƏLİ YOL ilə GEC həll olunur.
#: Səbəb: ``scripts/module_deps.py`` shared-kernel qaydası ``core/`` içindən
#: statik ``apps.*`` idxalını qadağan edir (baseline ``core_to_apps: []``).
#: Modul istəsə öz ``AppConfig.ready()``-sindən ``register_media_policy()``
#: çağırıb bu default-u əvəz edə bilər.
APPLICATIONS_CAN_VIEW_PATH = "apps.applications.services.access.can_view"

#: Runtime reyestr — app-ların ``AppConfig.ready()``-dən qeyd etdiyi siyasətlər.
#: Buradakı qeyd modul-daxili ``ACCESS_CHECKERS`` default-undan ÜSTÜNDÜR.
_RUNTIME_POLICIES: dict[str, object] = {}


def register_media_policy(prefix: str, checker) -> None:
    """Bir private media prefiksi üçün icazə siyasətini qeyd et.

    App-lar (``AppConfig.ready()``) bunu çağıraraq ``core``-a öz siyasətini
    verir — beləliklə shared kernel app modullarını İDXAL ETMİR.
    Çağırış idempotentdir; sonuncu qeyd qüvvədədir.
    """
    if not prefix.endswith("/"):
        raise ValueError("Media prefiksi '/' ilə bitməlidir.")
    _RUNTIME_POLICIES[prefix] = checker


def registered_prefixes() -> tuple[str, ...]:
    """Runtime-da qeyd olunmuş prefikslər (``_is_private`` üçün)."""
    return tuple(_RUNTIME_POLICIES)


def resolve_checker(prefix: str, default=None):
    """Prefiks üçün qüvvədə olan checker (runtime qeyd → default)."""
    return _RUNTIME_POLICIES.get(prefix) or default or ACCESS_CHECKERS.get(prefix)


def user_has_org_membership(user, organization, *, min_level: int = 0) -> bool:
    """*user*-in *organization*-da aktiv üzvlüyü varmı (rol səviyyəsi ≥ min)."""
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    return user.memberships.filter(
        organization=organization,
        is_active=True,
        role__level__gte=min_level,
    ).exists()


def user_has_org_permission(user, organization, permission: str) -> bool:
    """Aktiv üzvlüklərin rol icazələrində *permission* varmı (wildcard daxil).

    ``core.permissions.request_has_permission``-dan fərqli olaraq ``request``
    tələb etmir: media endpoint-ində aktiv-təşkilat konteksti yoxdur, hədəf
    təşkilat faylın sahibi olan sətirdən gəlir.
    """
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    from core.permissions import has_permission

    Membership = django_apps.get_model("organizations", "Membership")
    permissions: set[str] = set()
    for membership in Membership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
        role__is_active=True,
    ).select_related("role"):
        permissions.update(membership.role.permissions or [])
    return has_permission(list(permissions), permission)


def _is_correction_reviewer(user, organization) -> bool:
    """Düzəliş sənədini oxuya bilən inzibati aktor.

    ``journal.correct`` daşıyan (İKT Rəhbəri/RİM) VƏ YA org-admin səviyyəli
    (≥80: rektor, prorektor, owner) üzv.  Sırf müəllim səviyyəsi kifayət
    etmir — sənəd tibbi/rəsmi ola bilər.
    """
    if user_has_org_permission(user, organization, CORRECT_PERMISSION):
        return True
    return user_has_org_membership(user, organization, min_level=ORG_ADMIN_MIN_LEVEL)


def _is_offering_instructor(user, offering) -> bool:
    """Aktor bu açılışın (CourseOffering) jurnal sahibi müəllimidirmi."""
    if offering is None or user is None:
        return False
    return getattr(offering, "instructor_id", None) == user.id


def _is_enrolled_student(user, offering) -> bool:
    """Aktor bu açılışda qeydiyyatlı tələbədirmi (dərs-səviyyə düzəlişi üçün)."""
    if offering is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    return Enrollment.objects.filter(offering_id=offering.pk, student_id=user.id).exists()


def _get_single(queryset, **lookup):
    """Tək uyğun sətri qaytarır; tapılmasa/dublikat olsa ``None`` (fail-closed)."""
    model = queryset.model
    try:
        return queryset.get(**lookup)
    except (model.DoesNotExist, model.MultipleObjectsReturned):
        return None


# ---------------------------------------------------------------------------
# Jurnal düzəliş sənədləri (PDF — tibbi arayış / rəsmi akt)
# ---------------------------------------------------------------------------


def check_journal_correction_access(user, path: str) -> bool:
    """``journal_corrections/`` — xana (davamiyyət/bal) düzəlişinin sənədi.

    Sənədin aid olduğu TƏLƏBƏ, yaxud düzəliş səlahiyyətli inzibati aktor oxuya
    bilər.  Açılışın müəllimi QƏSDƏN daxil deyil — sənəd tibbi/rəsmi arayışdır
    (əvvəlki müqavilə, ``test_corrections_bridge.CorrectionMediaAccessTest``)."""
    JournalCorrection = django_apps.get_model("registrar", "JournalCorrection")
    correction = _get_single(
        JournalCorrection.objects.select_related(
            "organization",
            "lesson_mark__enrollment",
            "lesson_mark__lesson__offering",
        ),
        document=path,
    )
    if correction is None:
        return False
    mark = correction.lesson_mark
    if mark is not None and getattr(mark.enrollment, "student_id", None) == user.id:
        return True
    return _is_correction_reviewer(user, correction.organization)


def check_lesson_correction_access(user, path: str) -> bool:
    """``journal_lesson_corrections/`` — DƏRS sətrinə (tarix/tip/saat) düzəliş.

    Dərs sətri bütün qrupa aiddir, ona görə «aid olan tələbə» = həmin açılışda
    qeydiyyatlı istənilən tələbə (jurnalında sarı xana kimi görünür)."""
    LessonCorrection = django_apps.get_model("registrar", "LessonCorrection")
    correction = _get_single(
        LessonCorrection.objects.select_related("organization", "lesson__offering"),
        document=path,
    )
    if correction is None:
        return False
    offering = getattr(correction.lesson, "offering", None) if correction.lesson_id else None
    if _is_offering_instructor(user, offering):
        return True
    if _is_enrolled_student(user, offering):
        return True
    return _is_correction_reviewer(user, correction.organization)


def check_selfwork_correction_access(user, path: str) -> bool:
    """``journal_selfwork_corrections/`` — sərbəst iş təhvil düzəlişi."""
    SelfWorkCorrection = django_apps.get_model("registrar", "SelfWorkCorrection")
    correction = _get_single(
        SelfWorkCorrection.objects.select_related("organization", "enrollment", "topic__offering"),
        document=path,
    )
    if correction is None:
        return False
    if getattr(correction.enrollment, "student_id", None) == user.id:
        return True
    if _is_offering_instructor(user, getattr(correction.topic, "offering", None)):
        return True
    return _is_correction_reviewer(user, correction.organization)


def check_coursework_correction_access(user, path: str) -> bool:
    """``journal_coursework_corrections/`` — kurs işi düzəlişi."""
    CourseWorkCorrection = django_apps.get_model("registrar", "CourseWorkCorrection")
    correction = _get_single(
        CourseWorkCorrection.objects.select_related("organization", "enrollment__offering"),
        document=path,
    )
    if correction is None:
        return False
    if getattr(correction.enrollment, "student_id", None) == user.id:
        return True
    if _is_offering_instructor(user, getattr(correction.enrollment, "offering", None)):
        return True
    return _is_correction_reviewer(user, correction.organization)


def check_component_correction_access(user, path: str) -> bool:
    """``journal_component_corrections/`` — komponent (kollokvium/SDF) balı."""
    ComponentScoreCorrection = django_apps.get_model("registrar", "ComponentScoreCorrection")
    correction = _get_single(
        ComponentScoreCorrection.objects.select_related("organization", "enrollment", "component__offering"),
        document=path,
    )
    if correction is None:
        return False
    if getattr(correction.enrollment, "student_id", None) == user.id:
        return True
    if _is_offering_instructor(user, getattr(correction.component, "offering", None)):
        return True
    return _is_correction_reviewer(user, correction.organization)


def check_exam_score_evidence_access(user, path: str) -> bool:
    """``exam_score_entries/`` — imtahan vərəqinin şəkli/PDF-i (sübut).

    Balı daşıyan tələbə, açılışın müəllimi, yaxud düzəliş səlahiyyətli aktor."""
    ExamScoreEntry = django_apps.get_model("registrar", "ExamScoreEntry")
    entry = _get_single(
        ExamScoreEntry.objects.select_related("organization", "enrollment__offering"),
        evidence=path,
    )
    if entry is None:
        return False
    if getattr(entry.enrollment, "student_id", None) == user.id:
        return True
    if _is_offering_instructor(user, getattr(entry.enrollment, "offering", None)):
        return True
    return _is_correction_reviewer(user, entry.organization)


def check_legacy_excuse_document_access(user, path: str) -> bool:
    """``legacy_excuse_documents/`` — köhnə sistemdən gələn üzrlü qayıb aktı.

    Sətirdə açılış/fənn YOXDUR (tarix aralığı + tələbə), ona görə «müəllim»
    əhatəsi hesablana bilmir: sənədi yalnız AİD OLDUĞU TƏLƏBƏ və düzəliş
    səlahiyyətli inzibati aktor (dekanlıq/RİM səviyyəsi) oxuyur."""
    LegacyExcuseDocument = django_apps.get_model("registrar", "LegacyExcuseDocument")
    document = _get_single(
        LegacyExcuseDocument.objects.select_related("organization"),
        document=path,
    )
    if document is None:
        return False
    if document.student_id is not None and document.student_id == user.id:
        return True
    return _is_correction_reviewer(user, document.organization)


def check_application_attachment_access(user, path: str) -> bool:
    """``applications/`` — müraciət qoşması.

    Qərar ``apps.applications`` modulunun ÖZ ``can_view`` siyasətinə həvalə
    olunur (göndərən, cari şöbənin əhatəli emalçısı, izləyən şöbə,
    ``application.manage`` daşıyan, superuser/təşkilat sahibi)."""
    ApplicationAttachment = django_apps.get_model("applications", "ApplicationAttachment")
    attachment = _get_single(
        ApplicationAttachment.objects.select_related(
            "application__organization",
            "application__current_unit",
            "application__current_scope_unit",
        ),
        file=path,
    )
    if attachment is None:
        return False
    try:
        can_view = import_string(APPLICATIONS_CAN_VIEW_PATH)
    except ImportError:  # modul quraşdırılmayıbsa — fail-closed
        return False
    return bool(can_view(user, attachment.application))


# ---------------------------------------------------------------------------
# Tələbə hərəkəti əmrinin sənədi (ərizə / arayış / protokol)
# ---------------------------------------------------------------------------

#: Rəsmi reyestrə baxış açarı (``apps.accounts.services.people.permissions``
#: ilə eyni sətir; ``core`` app modullarını import etmir).
REGISTRY_VIEW_PERMISSION = "student.registry_view"


def check_student_movement_access(user, path: str) -> bool:
    """``student_movements/`` — köçürmə/məzuniyyət/xaric əmrinin əsas sənədi.

    2026-09-03 auditinin P0 tapıntısı: prefiks nə ``PRIVATE_PREFIXES``-də, nə
    də reyestrdə yox idi, yəni ``/media/student_movements/<org>/<fayl>``
    AUTENTİFİKASİYASIZ verilirdi.  Fayl adı təsadüfiləşdirilmir (``ərizə.pdf``
    kimi ola bilir), ona görə yol praktikada təxmin edilə bilən idi; məzmun
    isə tibbi arayış / intizam əmri ola bilər.

    İcazəlilər: əmrin aid olduğu TƏLƏBƏ, yaxud əmri yazan təşkilatda
    ``student.registry_view`` açarını daşıyan aktor.  Struktur əhatəsi ilə
    daralmış tam yoxlama ``accounts.views.student_registry
    .student_registry_document``-dədir — bu, sonuncu qapıdır (default DENY).
    """
    StudentMovement = django_apps.get_model("registrar", "StudentMovement")
    movement = _get_single(
        StudentMovement.objects.select_related("organization", "record"),
        document=path,
    )
    if movement is None:
        return False
    if getattr(movement.record, "student_id", None) == getattr(user, "id", None):
        return True
    return user_has_org_permission(user, movement.organization, REGISTRY_VIEW_PERMISSION)


#: ``media_views._PRIVATE_PREFIXES``-ə qatılan prefikslər.
PRIVATE_PREFIXES: tuple[str, ...] = (
    "journal_corrections/",
    "journal_lesson_corrections/",
    "journal_selfwork_corrections/",
    "journal_coursework_corrections/",
    "journal_component_corrections/",
    "exam_score_entries/",
    "legacy_excuse_documents/",
    "student_movements/",
    "applications/",
)

#: ``media_views._ACCESS_CHECKERS``-ə qatılan checker-lər (eyni açarlarla).
ACCESS_CHECKERS: dict[str, object] = {
    "student_movements/": check_student_movement_access,
    "journal_corrections/": check_journal_correction_access,
    "journal_lesson_corrections/": check_lesson_correction_access,
    "journal_selfwork_corrections/": check_selfwork_correction_access,
    "journal_coursework_corrections/": check_coursework_correction_access,
    "journal_component_corrections/": check_component_correction_access,
    "exam_score_entries/": check_exam_score_evidence_access,
    "legacy_excuse_documents/": check_legacy_excuse_document_access,
    "applications/": check_application_attachment_access,
}
