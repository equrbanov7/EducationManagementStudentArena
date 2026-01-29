"""
═══════════════════════════════════════════════════════════════════════════════
PROJECTS VIEWS
═══════════════════════════════════════════════════════════════════════════════
Kurs işləri üçün bütün view-lar:
- CRUD əməliyyatları (create, edit, delete)
- Tələbə görünüşü (detail, submit, my_submissions)
- Müəllim görünüşü (review, grade)
- API helper view-lar (get groups, get students)
═══════════════════════════════════════════════════════════════════════════════
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Project, ProjectSubmission
from courses.models import Course, CourseMembership
from django.contrib.auth import get_user_model

User = get_user_model()


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD ƏMƏLİYYATLARI
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_http_methods(["POST"])
def create_project(request, course_id):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işi yaratma                                                        │
    │ POST /projects/create/<course_id>/                                      │
    │                                                                         │
    │ Tələb olunan fieldlər: title, start_date, deadline                      │
    │ Opsional: description, max_attempts, max_score, status                  │
    │ Təyin etmə: group_names[] və ya students[]                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course = get_object_or_404(Course, id=course_id)
    
    # İcazə yoxlaması - yalnız kurs sahibi
    if not request.user.is_teacher or course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        # Project yarat
        project = Project.objects.create(
            course=course,
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            start_date=request.POST.get('start_date'),
            deadline=request.POST.get('deadline'),
            max_attempts=request.POST.get('max_attempts', 1),
            max_score=request.POST.get('max_score', 100),
            status=request.POST.get('status', 'active')
        )
        
        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('students[]')
        
        if student_ids:
            # Konkret tələbələr seçilib
            students = User.objects.filter(id__in=student_ids)
            project.assigned_students.set(students)
        elif group_names:
            # Qrup seçilib - qrupdakı bütün tələbələri əlavə et
            group_students = User.objects.filter(
                course_memberships__course=course,
                course_memberships__group_name__in=group_names,
                course_memberships__role='student'
            ).distinct()
            project.assigned_students.set(group_students)
        
        messages.success(request, 'Kurs işi uğurla yaradıldı!')
        return JsonResponse({'success': True, 'project_id': project.id})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini redaktə etmək                                                │
    │ GET  /projects/<pk>/edit/ → JSON data qaytarır                          │
    │ POST /projects/<pk>/edit/ → Yeniləyir                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = get_object_or_404(Project, id=pk)
    
    # İcazə yoxlaması
    if not request.user.is_teacher or project.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    # ─────────────────────────────────────────────────────────────────────────
    # GET - Mövcud məlumatları JSON olaraq qaytar
    # ─────────────────────────────────────────────────────────────────────────
    if request.method == 'GET':
        assigned_students = list(project.assigned_students.values(
            'id', 'username', 'first_name', 'last_name'
        ))
        assigned_student_ids = [s['id'] for s in assigned_students]
        
        # Tələbələrin qruplarını tap
        assigned_groups = list(
            CourseMembership.objects.filter(
                course=project.course,
                user_id__in=assigned_student_ids,
                role='student'
            ).exclude(group_name='').values_list('group_name', flat=True).distinct()
        )
        
        data = {
            'id': project.id,
            'title': project.title,
            'description': project.description,
            'start_date': project.start_date.strftime('%Y-%m-%dT%H:%M') if project.start_date else '',
            'deadline': project.deadline.strftime('%Y-%m-%dT%H:%M') if project.deadline else '',
            'max_attempts': project.max_attempts,
            'max_score': project.max_score,
            'status': project.status,
            'group_names': assigned_groups,
            'student_ids': assigned_student_ids,
            'students': [
                {
                    'id': s['id'],
                    'name': f"{s['first_name']} {s['last_name']}".strip() or s['username']
                }
                for s in assigned_students
            ],
        }
        return JsonResponse({'success': True, 'data': data})
    
    # ─────────────────────────────────────────────────────────────────────────
    # POST - Yenilə
    # ─────────────────────────────────────────────────────────────────────────
    try:
        project.title = request.POST.get('title')
        project.description = request.POST.get('description', '')
        project.start_date = request.POST.get('start_date')
        project.deadline = request.POST.get('deadline')
        project.max_attempts = request.POST.get('max_attempts', 1)
        project.max_score = request.POST.get('max_score', 100)
        project.status = request.POST.get('status', 'active')
        project.save()
        
        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # 3. Heç biri yoxdursa → Boş
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('students[]')
        
        if student_ids:
            students = User.objects.filter(id__in=student_ids)
            project.assigned_students.set(students)
        elif group_names:
            group_students = User.objects.filter(
                course_memberships__course=project.course,
                course_memberships__group_name__in=group_names,
                course_memberships__role='student'
            ).distinct()
            project.assigned_students.set(group_students)
        else:
            project.assigned_students.clear()
        
        messages.success(request, 'Kurs işi yeniləndi!')
        return JsonResponse({'success': True, 'message': 'Kurs işi yeniləndi'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini silmək                                                       │
    │ POST /projects/<pk>/delete/                                             │
    └─────────────────────────────��───────────────────────────────────────────┘
    """
    project = get_object_or_404(Project, id=pk)
    
    if not request.user.is_teacher or project.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        project.delete()
        messages.success(request, 'Kurs işi silindi!')
        return JsonResponse({'success': True, 'message': 'Silindi'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ═══════════════════════════════════════════════════════════════════════════════
# TƏLƏBƏ GÖRÜNÜŞÜ
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def project_detail(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinin detalları (tələbə üçün)                                     │
    │ GET /projects/<pk>/                                                     │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Project məlumatlarını görür                                           │
    │ - Əvvəlki cavablarını görür                                             │
    │ - Yeni cavab göndərə bilir (cəhd varsa)                                 │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = get_object_or_404(Project, id=pk)
    
    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - tələbə yalnız özünə təyin olunmuşlara baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if getattr(request.user, 'is_student', False):
        has_access = project.assigned_students.filter(id=request.user.id).exists()
        if not has_access:
            messages.error(request, 'Bu kurs işinə giriş icazəniz yoxdur')
            return redirect('courses:course_dashboard', course_id=project.course.id)
    
    # İstifadəçinin əvvəlki cavablarını al
    user_submissions = project.submissions.filter(student=request.user).order_by('-submitted_at')
    user_attempts = user_submissions.count()
    
    context = {
        'project': project,
        'user_submissions': user_submissions,
        'user_attempts': user_attempts,
        'can_submit': project.can_user_submit(request.user),
        'attempts_left': project.max_attempts - user_attempts,
    }
    
    return render(request, 'projects/project_detail.html', context)


@login_required
@require_http_methods(["POST"])
def submit_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinə cavab göndərmək                                              │
    │ POST /projects/<pk>/submit/                                             │
    │                                                                         │
    │ Form data: content (text), file (optional)                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = get_object_or_404(Project, id=pk)
    
    # Cavab göndərə bilərmi yoxla
    if not project.can_user_submit(request.user):
        return JsonResponse({
            'success': False,
            'error': 'Təqdim etmək mümkün deyil. Cəhd limitiniz bitib və ya müddət keçib.'
        }, status=400)
    
    try:
        submission = ProjectSubmission.objects.create(
            project=project,
            student=request.user,
            content=request.POST.get('content', ''),
        )
        
        # Fayl yükləmə
        if 'file' in request.FILES:
            submission.file = request.FILES['file']
            submission.save()
        
        messages.success(request, 'Layihəniz təqdim edildi!')
        return JsonResponse({
            'success': True,
            'message': 'Layihə təqdim edildi',
            'submission_id': submission.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def my_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Tələbənin öz cavablarını görmək                                         │
    │ GET /projects/<pk>/my-submissions/                                      │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Bütün göndərdiyi cavabları görür                                      │
    │ - Qiymətlərini görür                                                    │
    │ - Müəllim rəyini görür                                                  │
    │ - Qalan cəhd sayını görür                                               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = get_object_or_404(Project, id=pk)
    
    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - yalnız özünə təyin olunmuş project-lərə baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if not project.assigned_students.filter(id=request.user.id).exists():
        messages.error(request, 'Bu kurs işinə giriş icazəniz yoxdur')
        return redirect('courses:course_dashboard', course_id=project.course.id)
    
    # İstifadəçinin cavablarını al
    submissions = project.submissions.filter(student=request.user).order_by('-submitted_at')
    user_attempts = submissions.count()
    
    context = {
        'project': project,
        'submissions': submissions,
        'user_attempts': user_attempts,
        'can_submit': project.can_user_submit(request.user),
        'attempts_left': project.max_attempts - user_attempts,
    }
    
    return render(request, 'projects/my_submissions.html', context)


# ═══════════════════════════════════════════════════════════════════════════════
# MÜƏLLİM GÖRÜNÜŞÜ
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def review_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabları yoxlamaq (müəllim üçün)                                       │
    │ GET /projects/<pk>/submissions/                                         │
    │                                                                         │
    │ Müəllim burada:                                                         │
    │ - Bütün tələbə cavablarını görür                                        │
    │ - Qiymət verə bilir                                                     │
    │ - Rəy yaza bilir                                                        │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = get_object_or_404(Project, id=pk)
    
    # İcazə yoxlaması
    if not request.user.is_teacher or project.course.owner != request.user:
        messages.error(request, 'İcazəniz yoxdur')
        return redirect('courses:course_dashboard', course_id=project.course.id)
    
    submissions = project.submissions.select_related('student').order_by('-submitted_at')
    
    context = {
        'project': project,
        'submissions': submissions,
    }
    
    return render(request, 'projects/review_submissions.html', context)


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabı qiymətləndirmək                                                  │
    │ POST /projects/submission/<pk>/grade/                                   │
    │                                                                         │
    │ Form data: grade, feedback (optional)                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    submission = get_object_or_404(ProjectSubmission, id=pk)
    
    # İcazə yoxlaması
    if not request.user.is_teacher or submission.project.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        submission.grade = request.POST.get('grade')
        submission.feedback = request.POST.get('feedback', '')
        submission.status = 'graded'
        submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save()
        
        messages.success(request, 'Qiymət verildi!')
        return JsonResponse({
            'success': True,
            'message': 'Qiymətləndirildi'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ═══════════════════════════════════════════════════════════════════════════════
# API HELPER VIEW-LAR (AJAX üçün)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def api_get_groups(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kursdakı qrupları qaytarır (AJAX)                                       │
    │ GET /projects/api/groups/?course_id=<id>                                │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course_id = request.GET.get('course_id')
    
    if not course_id:
        return JsonResponse({'groups': []})
    
    course = get_object_or_404(Course, id=course_id)
    
    # Unique qrup adlarını tap
    groups = CourseMembership.objects.filter(
        course=course,
        role='student'
    ).exclude(
        group_name=''
    ).exclude(
        group_name__isnull=True
    ).values_list('group_name', flat=True).distinct().order_by('group_name')
    
    return JsonResponse({
        'groups': [{'id': i, 'name': name} for i, name in enumerate(groups, 1)]
    })


@login_required
def api_get_students(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Qruplardakı tələbələri qaytarır (AJAX)                                  │
    │ GET /projects/api/students/?course_id=<id>&groups=<g1,g2>               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course_id = request.GET.get('course_id')
    groups_param = request.GET.get('groups', '')
    
    if not course_id or not groups_param:
        return JsonResponse({'students': []})
    
    course = get_object_or_404(Course, id=course_id)
    group_names = [g.strip() for g in groups_param.split(',') if g.strip()]
    
    if not group_names:
        return JsonResponse({'students': []})
    
    # Qruplardakı tələbələri tap
    memberships = CourseMembership.objects.filter(
        course=course,
        group_name__in=group_names,
        role='student'
    ).select_related('user').order_by('group_name', 'user__first_name')
    
    # Dublikatları çıxar
    students = []
    seen = set()
    for m in memberships:
        if m.user.id not in seen:
            seen.add(m.user.id)
            students.append({
                'id': m.user.id,
                'name': m.user.get_full_name() or m.user.username,
                'group_name': m.group_name
            })
    
    return JsonResponse({'students': students})