from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.exams.forms import StudentGroupForm
from apps.exams.models import StudentGroup
from apps.exams.services.attempts import _ensure_teacher


# --- 1. SİYAHI VƏ MODAL ÜÇÜN FORM ---
@login_required
def teacher_group_list(request):
    # Bu funksiya yəqin ki sizdə var (müəllim olduğunu yoxlayan)
    # _ensure_teacher(request.user)

    # Müəllimin mövcud qrupları
    groups = StudentGroup.objects.filter(teacher=request.user).prefetch_related(
        "students"
    )

    # DÜZƏLİŞ: Formu yaradarkən 'teacher' parametrini ötürürük
    # Bu, formun __init__ metodunda işlənəcək və tələbə siyahısını filterləyəcək
    form = StudentGroupForm(teacher=request.user)

    context = {"groups": groups, "form": form}
    return render(request, "exams/teacher/teacher_group_list.html", context)


# --- 2. YENİ QRUP YARATMAQ (POST) ---
@login_required
@require_POST
def teacher_create_group(request):
    # _ensure_teacher(request.user)

    # DÜZƏLİŞ: POST sorğusunu qəbul edərkən də 'teacher' ötürürük
    form = StudentGroupForm(request.POST, teacher=request.user)

    if form.is_valid():
        group = form.save(commit=False)
        group.teacher = request.user  # Qrupu bu müəllimə bağlayırıq
        group.save()
        form.save_m2m()  # ManyToMany (tələbələr) üçün vacibdir

    return redirect("exams:teacher_group_list")


# --- 3. QRUPU YENİLƏMƏK (UPDATE - POST) ---
@login_required
@require_POST
def teacher_update_group(request, group_id):
    # _ensure_teacher(request.user)

    # Yalnız bu müəllimin qrupunu tapırıq
    group = get_object_or_404(StudentGroup, id=group_id, teacher=request.user)

    # DÜZƏLİŞ: 'instance=group' və 'teacher=request.user'
    form = StudentGroupForm(request.POST, instance=group, teacher=request.user)

    if form.is_valid():
        form.save()

    return redirect("exams:teacher_group_list")


# --- 4. QRUPU SİLMƏK (DELETE) ---
@login_required
def teacher_delete_group(request, group_id):
    # _ensure_teacher(request.user)

    group = get_object_or_404(StudentGroup, id=group_id, teacher=request.user)
    group.delete()

    return redirect("exams:teacher_group_list")


@login_required
def create_student_group(request):
    _ensure_teacher(request.user)

    if request.method == "POST":
        form = StudentGroupForm(request.POST, teacher=request.user)
        if form.is_valid():
            group = form.save(commit=False)
            group.teacher = request.user
            group.save()
            form.save_m2m()
            messages.success(request, "Qrup uğurla yaradıldı.")
            return redirect("exams:teacher_group_list")
    else:
        form = StudentGroupForm(teacher=request.user)

    return render(request, "exams/teacher/create_student_group.html", {"form": form})
