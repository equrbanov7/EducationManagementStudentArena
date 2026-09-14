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


#: Yazılı imtahan balı köçürməsi — vərəq/protokol skanına baxış açarı
#: (``apps.registrar.exam_score_entry.ENTRY_PERMISSION`` ilə eyni sətir;
#: ``core`` app modullarını import etmir).
EXAM_SCORE_ENTRY_PERMISSION = "final_score.entry"


def check_exam_score_sheet_access(user, path: str) -> bool:
    """``exam_score_sheets/`` — köçürmə partiyasının skan edilmiş protokolu/vərəqi.

    2026-09-12 (imtahan balı köçürmə paneli): partiya sənədi BÜTÜN qrupun
    ballarını daşıyır, ona görə «aid tələbə» qapısı YOXDUR — tələbə öz balının
    sətrini görür, qrup yoldaşlarının vərəqini yox. İcazəlilər: sənədin
    təşkilatında aktiv üzvlüklə ``final_score.entry`` daşıyan aktor (imtahan
    mərkəzi), açılışın müəllimi, yaxud düzəliş səlahiyyətli inzibati aktor
    (``journal.correct`` / org-admin səviyyəsi). Media qatı onsuz da deny-by-
    default-dur — bu checker icazəli girişin AÇIQ qaydasıdır (fail-closed).
    """
    ExamScoreSheet = django_apps.get_model("registrar", "ExamScoreSheet")
    sheet = _get_single(ExamScoreSheet.objects.select_related("organization", "offering"), evidence=path)
    if sheet is None:
        return False
    if _is_offering_instructor(user, sheet.offering) and user_has_org_membership(user, sheet.organization):
        return True
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    for permission in (EXAM_SCORE_ENTRY_PERMISSION, CORRECT_PERMISSION):
        scope = OrgUnit.user_permission_scope(user, sheet.organization, permission)
        if not scope.has_structure_access:
            continue
        if scope.is_org_wide:
            return True
        if (
            sheet.offering.group_id
            and OrgUnit.objects.filter(organization=sheet.organization, pk=sheet.offering.group_id)
            .filter(scope.unit_subtree_q())
            .exists()
        ):
            return True
    return False


def check_guest_roster_document_access(user, path: str) -> bool:
    """``guest_roster_documents/`` — alt qrupdan əlavənin təqdimatı/sərəncamı.

    Aid olduğu tələbə, açılışın müəllimi, yaxud inzibati aktor (``journal.correct``
    / org-admin səviyyəsi). Koordinator/dekanlıq sənədi jurnal səthindən görür."""
    GuestRosterDocument = django_apps.get_model("registrar", "GuestRosterDocument")
    document = _get_single(
        GuestRosterDocument.objects.select_related("organization", "enrollment__offering"),
        document=path,
    )
    if document is None:
        return False
    if getattr(document.enrollment, "student_id", None) == user.id:
        return True
    if _is_offering_instructor(user, getattr(document.enrollment, "offering", None)):
        return True
    if user_has_org_permission(user, document.organization, "journal.roster"):
        return True
    return _is_correction_reviewer(user, document.organization)


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


# ---------------------------------------------------------------------------

#: Dərs yükünə baxış açarı (``apps.workload.constants.PERM_VIEW`` ilə eyni
#: sətir; ``core`` app modullarını import etmir).
WORKLOAD_VIEW_PERMISSION = "workload.view"


def check_workload_amendment_access(user, path: str) -> bool:
    """``workload_amendments/`` — dərs yükü düzəlişinin RƏSMİ sənədi (PDF).

    2026-09-10 auditinin P0 tapıntısı: prefiks nə ``PRIVATE_PREFIXES``-də, nə
    də reyestrdə yox idi, yəni ``/media/workload_amendments/<org>/<task>/<fayl>``
    AUTENTİFİKASİYASIZ və ``Cache-Control: public`` ilə verilirdi. Fayl adı
    təsadüfiləşdirilmir (``əmr.pdf`` kimi ola bilir); məzmun isə kafedra
    yükünün rəsmi düzəliş əsasıdır.

    İcazəlilər: sənədin aid olduğu TƏŞKİLATDA ``workload.view`` açarını daşıyan
    aktor. Düzəliş qeydi append-only reyestrdir — sənəd yükün auditinin bir
    hissəsidir, ona görə yükü görə bilən onu da görür.
    """
    WorkloadAmendment = django_apps.get_model("workload", "WorkloadAmendment")
    amendment = _get_single(WorkloadAmendment.objects.select_related("organization"), document=path)
    if amendment is None:
        return False
    return user_has_org_permission(user, amendment.organization, WORKLOAD_VIEW_PERMISSION)


# ---------------------------------------------------------------------------
# Kurs tapşırığı təhvili və sistem bildirişinin qoşması (2026-09-13, audit F-02)
# ---------------------------------------------------------------------------
#
# Hər iki prefiks model ``FileField`` ilə deyil, ``default_storage.save`` ilə
# yazılır (``assignments.models.Submission.attach_uploaded_file`` → JSON
# ``files[].path``; ``accounts.services.profile_actions`` → bildiriş
# ``metadata.image_url`` / ``metadata.attachments[].url``). Ona görə heç bir
# ``upload_to`` inventarında görünmür və reyestrə düşməmişdi: deny-by-default
# (2026-09-10 ağ siyahı qaydası) sayəsində sızma YOX idi, amma qiymətləndirmə
# növbəsindəki ``/media/assignments/submissions/…`` linki və bildiriş qoşması
# superadmin-dən başqa HƏR KƏSƏ 404 verirdi (funksional, fail-closed).

#: Kurs üzvlüyündə təhvili görə bilən rollar (``task_submission_core.access``
#: ``can_user_access_course_roster`` ilə eyni siyahı; ``core`` app import etmir).
_COURSE_STAFF_ROLES: tuple[str, ...] = ("teacher", "assistant")


def check_assignment_submission_access(user, path: str) -> bool:
    """``assignments/submissions/`` — tapşırıq təhvilinin yüklənmiş faylı.

    İcazəlilər: təhvili GÖNDƏRƏN tələbə, kursun sahibi (``Course.owner``), yaxud
    kursda ``teacher``/``assistant`` üzvlüyü olan aktor. Fayl yolu JSON
    ``files[].path`` sahəsindədir — ``contains`` axtarışı ilə tapılır; eyni
    yol bir neçə təhvildə görünsə (nəzəri) hər biri ayrıca yoxlanır."""
    from django.db.models import Q

    Submission = django_apps.get_model("assignments", "Submission")
    # Köhnə sətirlərdə açar ``url`` ola bilər (``Submission.file`` xüsusiyyəti hər ikisini oxuyur).
    lookup = Q(files__contains=[{"path": path}]) | Q(files__contains=[{"url": f"/media/{path}"}])
    submissions = Submission.objects.filter(lookup).select_related("assignment__course")
    if not submissions:
        return False
    CourseMembership = django_apps.get_model("courses", "CourseMembership")
    for submission in submissions:
        if submission.user_id == user.id:
            return True
        course = submission.assignment.course
        if course.owner_id == user.id:
            return True
        if CourseMembership.objects.filter(course=course, user=user, role__in=_COURSE_STAFF_ROLES).exists():
            return True
    return False


def _notification_file_urls(path: str) -> list[str]:
    """Bildiriş metadata-sında saxlanılan URL formaları (``default_storage.url`` + ``/media/``)."""
    from django.core.files.storage import default_storage

    candidates = [f"/media/{path}"]
    try:
        storage_url = default_storage.url(path)
    except Exception:  # storage URL qura bilmirsə — yalnız yerli forma
        storage_url = ""
    if storage_url and storage_url not in candidates:
        candidates.insert(0, storage_url)
    return candidates


def check_notification_file_access(user, path: str) -> bool:
    """``notifications/files/`` və ``notifications/images/`` — sistem bildirişinin qoşması.

    Fayl bildirişin ÖZÜNDƏ (``InAppNotification.metadata``) URL kimi saxlanılır;
    eyni fayl bütün alıcıların sətirlərində təkrarlanır. İcazəlilər: bildirişin
    ALICISI (silinmiş/oxunmuş olsa da — qoşma onun poçtudur), yaxud bildirişin
    təşkilatında müəllim səviyyəli (≥50) aktiv üzv — dərc edən şəxs ayrıca
    saxlanmır, dərc səlahiyyəti isə müəllim/əməkdaş səviyyəsindən başlayır.
    Təşkilatsız (qlobal) bildirişdə yalnız alıcı qapısı işləyir."""
    from django.db.models import Q

    InAppNotification = django_apps.get_model("notifications", "InAppNotification")
    lookup = Q()
    for url in _notification_file_urls(path):
        lookup |= Q(metadata__image_url=url) | Q(metadata__attachments__contains=[{"url": url}])
    matching = InAppNotification.objects.filter(lookup)
    if not matching.exists():
        return False
    if matching.filter(recipient_id=user.id).exists():
        return True
    organization_ids = set(matching.exclude(organization_id=None).values_list("organization_id", flat=True))
    return any(user_has_org_membership(user, org_id, min_level=TEACHER_MIN_LEVEL) for org_id in organization_ids)


#: ``media_views._PRIVATE_PREFIXES``-ə qatılan prefikslər.
PRIVATE_PREFIXES: tuple[str, ...] = (
    "journal_corrections/",
    "journal_lesson_corrections/",
    "journal_selfwork_corrections/",
    "journal_coursework_corrections/",
    "journal_component_corrections/",
    "exam_score_entries/",
    "exam_score_sheets/",
    "guest_roster_documents/",
    "legacy_excuse_documents/",
    "student_movements/",
    "applications/",
    "workload_amendments/",
    "assignments/submissions/",
    "notifications/files/",
    "notifications/images/",
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
    "exam_score_sheets/": check_exam_score_sheet_access,
    "guest_roster_documents/": check_guest_roster_document_access,
    "legacy_excuse_documents/": check_legacy_excuse_document_access,
    "applications/": check_application_attachment_access,
    "workload_amendments/": check_workload_amendment_access,
    "assignments/submissions/": check_assignment_submission_access,
    "notifications/files/": check_notification_file_access,
    "notifications/images/": check_notification_file_access,
}
