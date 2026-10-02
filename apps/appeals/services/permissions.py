"""
Apellyasiya icazə məntiqi — mərkəzi RBAC üzərində.

- create:  student yalnız ÖZ bitmiş, NƏTİCƏSİ DƏRC OLUNMUŞ final/midterm
           attempt-i üçün, pəncərə açıqdırsa, ``appeal.create`` icazəsi ilə.
- respond/decide: apellyasiyalar mərkəzləşdirilmiş qaydada imtahan mərkəzi
           tərəfindən idarə olunur. İmtahan mərkəzi bu platformada imtahan
           məzmununu da mərkəzi olaraq yaradır, ona görə öz yaratdığı imtahana
           gələn apellyasiyaya da qərar verə bilir (müstəqillik qadağası yoxdur
           — imtahan mərkəzi rolu onsuz da tək qərar səlahiyyətidir).
- view:    yuxarıdakılar + tələbənin qrupunu əhatə edən akademik nəzarət
           (dekan, proqram koordinatoru — ``student.registry_view`` scope-u),
           YALNIZ-OXU (Audit 2026-09-28 EXA-03, sahibin 2026-09-07 memo-su).

Bütün hallarda tenant uyğunluğu yoxlanılır (superadmin istisna).
"""

from django.apps import apps as django_apps

from apps.appeals.constants import PERM_APPEAL_CREATE
from apps.exams.public import SECURE_EXAM_CATEGORIES, is_exam_center_user
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization

from .window import attempt_awaiting_grading, is_within_appeal_window

#: Apellyasiya verilə bilən imtahan kateqoriyaları — «Yeni apellyasiya» modalı
#: (``_appeal_eligible_attempts``) ilə EYNİ çoxluq (final + midterm).
APPEALABLE_EXAM_CATEGORIES = frozenset(SECURE_EXAM_CATEGORIES)

#: Akademik nəzarətin (dekan / koordinator) oxu scope-u — tələbə reyestri ilə eyni açar.
PERM_STUDENT_OVERSIGHT_VIEW = "student.registry_view"

# ``appeal_block_reason`` kodları — UI izahı üçün (bax appeal_create.html).
BLOCK_NOT_OWNER = "not_owner"
BLOCK_TRIAL = "trial"
BLOCK_CATEGORY = "category"
BLOCK_NOT_GRADED = "not_graded"
BLOCK_WINDOW = "window"
BLOCK_PERMISSION = "permission"


def _same_tenant(request, appeal):
    if is_superadmin_user(getattr(request, "user", None)):
        return True
    organization = get_request_organization(request)
    return organization is not None and appeal.organization_id == organization.id


def is_appealable_exam(exam):
    """Audit 2026-09-28 EXA-07: yalnız final/midterm imtahanına apellyasiya verilir.

    Əvvəl kateqoriya yalnız UI-da (modal) süzülürdü; quiz/practice cəhdinə
    crafted POST ilə apellyasiya yaradıla bilirdi."""
    category = str(getattr(exam, "exam_type_extended", None) or "").strip()
    return category in APPEALABLE_EXAM_CATEGORIES


def appeal_block_reason(request, attempt, *, at_time=None):
    """Apellyasiya YARADILA BİLMİRSƏ səbəb kodu, yoxsa ``None``."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False) or attempt.user_id != getattr(user, "id", None):
        return BLOCK_NOT_OWNER
    # 2026-09-14 (W3 `w3sweep` brauzer süpürgəsi): müəllimin «Sınaq keç» cəhdi
    # (`is_trial`) heç bir nəticəyə yazılmır, amma nəticə səhifəsində
    # «Apellyasiya et» düyməsi çıxırdı və real apellyasiya yaradıla bilirdi
    # (statistikanı çirkləndirir). Sınaq cəhdi apellyasiya olunmur.
    if getattr(attempt, "is_trial", False):
        return BLOCK_TRIAL
    if not is_appealable_exam(getattr(attempt, "exam", None)):
        return BLOCK_CATEGORY
    # Audit 2026-09-28 EXA-02: yoxlanmamış yazılı/praktiki cəhdə apellyasiya yoxdur.
    if attempt_awaiting_grading(attempt):
        return BLOCK_NOT_GRADED
    if not is_within_appeal_window(attempt, at_time=at_time):
        return BLOCK_WINDOW
    if not request_has_permission(request, PERM_APPEAL_CREATE):
        return BLOCK_PERMISSION
    return None


def appeal_applicable(attempt):
    """Cəhd növü apellyasiyaya aiddirmi (2026-10-02): sınaq deyil və imtahan kateqoriyası apellyasiya olunur.

    Nəticə səhifəsi apellyasiya panelini yalnız bu halda göstərir — əvvəl quiz/sınaqda da
    «apellyasiya pəncərəsi bağlıdır» yazılırdı (EXAMQA R6).
    """
    return not getattr(attempt, "is_trial", False) and is_appealable_exam(getattr(attempt, "exam", None))


def can_create_appeal(request, attempt, *, at_time=None):
    return appeal_block_reason(request, attempt, at_time=at_time) is None


def can_review_appeal(request, appeal):
    """Apellyasiyaya baxıb item-lərə cavab verə bilərmi (imtahan mərkəzi).

    İmtahan mərkəzi istifadəçisi (və superadmin) təşkilatının bütün
    apellyasiyalarına — öz yaratdığı imtahanlar daxil — baxa bilir.
    """
    if not _same_tenant(request, appeal):
        return False
    return is_exam_center_user(getattr(request, "user", None))


def can_decide_appeal(request, appeal):
    """Yekun status qərarı / override verə bilərmi (imtahan mərkəzi).

    İmtahan mərkəzi bu platformada mərkəzi qərar səlahiyyətidir; imtahan
    müəllifi eyni zamanda mərkəz istifadəçisidirsə də qərar verə bilir.
    """
    if not _same_tenant(request, appeal):
        return False
    return is_exam_center_user(getattr(request, "user", None))


def oversight_covers_student(user, organization, student_id):
    """Aktorun ``student.registry_view`` scope-u tələbənin qrupunu əhatə edirmi (fail-closed)."""
    if organization is None or not getattr(user, "is_authenticated", False):
        return False
    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    scope = org_unit_model.user_permission_scope(user, organization, PERM_STUDENT_OVERSIGHT_VIEW)
    if not scope.has_structure_access:
        return False
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    records = record_model.objects.filter(organization=organization, student_id=student_id)
    if not scope.is_org_wide:
        records = records.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    return records.exists()


def can_view_appeal(request, appeal):
    """YALNIZ-OXU baxış: reviewer və ya tələbəni əhatə edən dekan/koordinator.

    Audit 2026-09-28 EXA-03 (sahibin 2026-09-07 memo-su: «apellyasiya nəticəsi
    koordinator/dekanlıq tərəfindən görünməlidir»): əvvəl apellyasiyanı yalnız
    imtahan mərkəzi görürdü. Qərar/redaktə hüququ VERİLMİR (``can_review_appeal``
    / ``can_decide_appeal`` dəyişməyib)."""
    if can_review_appeal(request, appeal):
        return True
    if not _same_tenant(request, appeal):
        return False
    return oversight_covers_student(getattr(request, "user", None), appeal.organization, appeal.student_id)


__all__ = [
    "APPEALABLE_EXAM_CATEGORIES",
    "BLOCK_CATEGORY",
    "BLOCK_NOT_GRADED",
    "BLOCK_NOT_OWNER",
    "BLOCK_PERMISSION",
    "BLOCK_TRIAL",
    "BLOCK_WINDOW",
    "appeal_block_reason",
    "can_create_appeal",
    "can_decide_appeal",
    "can_review_appeal",
    "can_view_appeal",
    "appeal_applicable",
    "is_appealable_exam",
    "oversight_covers_student",
]
