from django.shortcuts import get_object_or_404

from apps.exams.features import without_disabled_practical_exams
from apps.exams.models import Exam
from core.tenancy import (
    get_request_organization,
    request_has_active_organization_context,
    restore_request_organization_from_profile,
    scoped_by_organization,
)


def get_active_organization(request):
    return get_request_organization(request)


def tenant_scoped_exams(request, queryset=None, *, include_deleted=False):
    """Org-scoped imtahan queryset-i — default olaraq YUMŞAQ SİLİNMİŞ
    imtahanları (``is_deleted=True``) çıxarır.

    Bu funksiya bütün imtahan siyahılarının/lookup-larının mərkəzi keçididir,
    ona görə də silinmiş imtahanların gizlədilməsi burada tək yerdə təmin
    olunur. Yalnız "Zibil qutusu" və silinmiş imtahanın nəticələrinə baxış
    kimi xüsusi hallar ``include_deleted=True`` ötürməlidir.
    """
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    scoped = without_disabled_practical_exams(scoped_by_organization(base_queryset, request))
    if not include_deleted:
        scoped = scoped.filter(is_deleted=False)
    return scoped


def ensure_teacher_exam_tenant_context(request):
    """
    Sessiya aktiv org-u itirəndə tenant kontekstini bərpa et.

    ``ensure_student_exam_tenant_context``-in müəllim tərəfi üçün analoqu.
    Bərpa yalnız istifadəçinin həqiqətən aid olduğu YEGANƏ aktiv org üçün
    işləyir (bax: ``restore_request_organization_from_profile``) — tenant
    izolyasiyası pozulmur. Bu olmadan sual edit/delete kimi view-lar
    sessiya org-u düşəndə ``scoped_by_organization → queryset.none()``
    səbəbindən aralıqlı 404 verirdi (RLS GUC da bərpa olunur).
    """
    if request_has_active_organization_context(request):
        return True
    return restore_request_organization_from_profile(
        request,
        profile=getattr(getattr(request, "user", None), "profile", None),
    )


def get_teacher_exam_or_404(request, *, include_deleted=False, **filters):
    ensure_teacher_exam_tenant_context(request)
    teacher_queryset = tenant_scoped_exams(
        request, Exam.objects.filter(author=request.user), include_deleted=include_deleted
    )
    return get_object_or_404(teacher_queryset, **filters)


def get_result_viewable_exam_or_404(request, *, include_deleted=False, **filters):
    """Nəticə görüntüləmə (read-only) üçün imtahanı həll et.

    Müəllim → yalnız öz müəllifi olduğu imtahanlar (``author`` scoped).
    İmtahan mərkəzi rolu → org daxilində İSTƏNİLƏN imtahan (statistika "Bax").
    Hər iki halda tenant/org izolyasiyası ``tenant_scoped_exams`` ilə qorunur.
    İcazə yoxlaması çağıran view-dadır (``_ensure_can_view_attempt_results``).
    """
    from apps.exams.services.access_policy import is_exam_center_user, is_teacher_user

    ensure_teacher_exam_tenant_context(request)
    if is_teacher_user(request.user) and not is_exam_center_user(request.user):
        base_queryset = Exam.objects.filter(author=request.user)
    else:
        # İmtahan mərkəzi (və superadmin) org daxilində bütün imtahanları görür.
        base_queryset = Exam.objects.all()
    return get_object_or_404(tenant_scoped_exams(request, base_queryset, include_deleted=include_deleted), **filters)


def exam_in_active_tenant(request, exam):
    organization = get_active_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return False

    return getattr(exam, "organization", None) == organization
