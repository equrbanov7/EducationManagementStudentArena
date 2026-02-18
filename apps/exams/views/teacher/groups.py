from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.exams.forms import StudentGroupForm
from apps.exams.models import StudentGroup
from apps.exams.services.attempts import _ensure_teacher
from apps.organizations.services import get_user_organization


def _get_current_organization(request):
    """
    Resolve active organization from middleware/session first, then profile fallback.
    """
    return getattr(request, "organization", None) or get_user_organization(request.user)


# --- 1. SİYAHI VƏ MODAL ÜÇÜN FORM ---
@login_required
def teacher_group_list(request):
    # Bu funksiya yəqin ki sizdə var (müəllim olduğunu yoxlayan)
    # _ensure_teacher(request.user)

    organization = _get_current_organization(request)
    if organization is None:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    # Müəllimin mövcud qrupları (yalnız aktiv tenant daxilində)
    groups = StudentGroup.objects.filter(teacher=request.user, organization=organization).prefetch_related("students")

    # DÜZƏLİŞ: Formu yaradarkən 'teacher' parametrini ötürürük
    # Bu, formun __init__ metodunda işlənəcək və tələbə siyahısını filterləyəcək
    form = StudentGroupForm(teacher=request.user, organization=organization)

    context = {"groups": groups, "form": form, "organization": organization}
    return render(request, "exams/teacher/teacher_group_list.html", context)


# --- 2. YENİ QRUP YARATMAQ (POST) ---
@login_required
@require_POST
def teacher_create_group(request):
    # _ensure_teacher(request.user)

    organization = _get_current_organization(request)
    if organization is None:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    # DÜZƏLİŞ: POST sorğusunu qəbul edərkən də tenant kontekstini ötürürük
    form = StudentGroupForm(request.POST, teacher=request.user, organization=organization)

    if form.is_valid():
        group = form.save(commit=False)
        group.teacher = request.user  # Qrupu bu müəllimə bağlayırıq
        group.organization = organization
        group.save()
        form.save_m2m()  # ManyToMany (tələbələr) üçün vacibdir

    return redirect("exams:teacher_group_list")


# --- 3. QRUPU YENİLƏMƏK (UPDATE - POST) ---
@login_required
@require_POST
def teacher_update_group(request, group_id):
    # _ensure_teacher(request.user)

    # Yalnız bu müəllimin qrupunu tapırıq
    organization = _get_current_organization(request)
    if organization is None:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    group = get_object_or_404(StudentGroup, id=group_id, teacher=request.user, organization=organization)

    # DÜZƏLİŞ: 'instance=group' və 'teacher=request.user'
    form = StudentGroupForm(request.POST, instance=group, teacher=request.user, organization=organization)

    if form.is_valid():
        form.save()

    return redirect("exams:teacher_group_list")


# --- 4. QRUPU SİLMƏK (DELETE) ---
@login_required
def teacher_delete_group(request, group_id):
    # _ensure_teacher(request.user)

    organization = _get_current_organization(request)
    if organization is None:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    group = get_object_or_404(StudentGroup, id=group_id, teacher=request.user, organization=organization)
    group.delete()

    return redirect("exams:teacher_group_list")


@login_required
def create_student_group(request):
    _ensure_teacher(request.user)
    organization = _get_current_organization(request)
    if organization is None:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    if request.method == "POST":
        form = StudentGroupForm(request.POST, teacher=request.user, organization=organization)
        if form.is_valid():
            group = form.save(commit=False)
            group.teacher = request.user
            group.organization = organization
            group.save()
            form.save_m2m()
            messages.success(request, "Qrup uğurla yaradıldı.")
            return redirect("exams:teacher_group_list")
    else:
        form = StudentGroupForm(teacher=request.user, organization=organization)

    return render(request, "exams/teacher/create_student_group.html", {"form": form, "organization": organization})
