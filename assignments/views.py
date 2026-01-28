"""
═══════════════════════════════════════════════════════════════════════════════
ASSIGNMENTS VIEWS
═══════════════════════════════════════════════════════════════════════════════
Sərbəst işlər üçün bütün view-lar:
- CRUD əməliyyatları (create, edit, delete)
- Tələbə görünüşü (detail, submit, my_submissions)
- Müəllim görünüşü (review, grade)
- API helper view-lar (search students, groups)
═══════════════════════════════════════════════════════════════════════════════
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.http import require_http_methods

from .models import Assignment, AssignmentSubmission
from courses.models import Course, CourseMembership
from django.contrib.auth import get_user_model

User = get_user_model()


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD ƏMƏLİYYATLARI
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_http_methods(["POST"])
def create_assignment(request, course_id):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Sərbəst iş yaratma                                                      │
    │ POST /assignments/create/<course_id>/                                   │
    │                                                                         │
    │ Tələb olunan fieldlər: title, deadline                                  │
    │ Opsional: description, start_date, max_attempts, status                 │
    │ Təyin etmə: group_names[] və ya students[]                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course = get_object_or_404(Course, id=course_id)
    
    # İcazə yoxlaması - yalnız kurs sahibi
    if not request.user.is_teacher or course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        # Assignment yarat
        assignment = Assignment.objects.create(
            course=course,
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            start_date=request.POST.get('start_date'),
            deadline=request.POST.get('deadline'),
            max_attempts=request.POST.get('max_attempts', 3),
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
            assignment.assigned_students.set(students)
        elif group_names:
            # Qrup seçilib - qrupdakı bütün tələbələri əlavə et
            group_students = User.objects.filter(
                course_memberships__course=course,
                course_memberships__group_name__in=group_names,
                course_memberships__role='student'
            ).distinct()
            assignment.assigned_students.set(group_students)
        
        messages.success(request, 'Sərbəst iş uğurla yaradıldı!')
        return JsonResponse({'success': True, 'assignment_id': assignment.id})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_assignment(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Sərbəst işi redaktə etmək                                               │
    │ GET  /assignments/<pk>/edit/ → JSON data qaytarır                       │
    │ POST /assignments/<pk>/edit/ → Yeniləyir                                │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = get_object_or_404(Assignment, id=pk)
    
    # İcazə yoxlaması
    if not request.user.is_teacher or assignment.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    # ─────────────────────────────────────────────────────────────────────────
    # GET - Mövcud məlumatları JSON olaraq qaytar
    # ─────────────────────────────────────────────────────────────────────────
    if request.method == 'GET':
        assigned_students = list(assignment.assigned_students.values(
            'id', 'username', 'first_name', 'last_name'
        ))
        assigned_student_ids = [s['id'] for s in assigned_students]
        
        # Tələbələrin qruplarını tap
        assigned_groups = list(
            CourseMembership.objects.filter(
                course=assignment.course,
                user_id__in=assigned_student_ids,
                role='student'
            ).exclude(group_name='').values_list('group_name', flat=True).distinct()
        )
        
        data = {
            'id': assignment.id,
            'title': assignment.title,
            'description': assignment.description,
            'start_date': assignment.start_date.strftime('%Y-%m-%dT%H:%M') if assignment.start_date else '',
            'deadline': assignment.deadline.strftime('%Y-%m-%dT%H:%M') if assignment.deadline else '',
            'max_attempts': assignment.max_attempts,
            'status': assignment.status,
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
    
    # ───────────────��─────────────────────────────────────────────────────────
    # POST - Yenilə
    # ─────────────────────────────────────────────────────────────────────────
    try:
        assignment.title = request.POST.get('title')
        assignment.description = request.POST.get('description', '')
        assignment.start_date = request.POST.get('start_date')
        assignment.deadline = request.POST.get('deadline')
        assignment.max_attempts = request.POST.get('max_attempts', 3)
        assignment.status = request.POST.get('status', 'active')
        assignment.save()
        
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
            assignment.assigned_students.set(students)
        elif group_names:
            group_students = User.objects.filter(
                course_memberships__course=assignment.course,
                course_memberships__group_name__in=group_names,
                course_memberships__role='student'
            ).distinct()
            assignment.assigned_students.set(group_students)
        else:
            assignment.assigned_students.clear()
        
        messages.success(request, 'Sərbəst iş yeniləndi!')
        return JsonResponse({'success': True, 'message': 'Sərbəst iş yeniləndi'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_assignment(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Sərbəst işi silmək                                                      │
    │ POST /assignments/<pk>/delete/                                          │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = get_object_or_404(Assignment, id=pk)
    
    if not request.user.is_teacher or assignment.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        assignment.delete()
        messages.success(request, 'Sərbəst iş silindi!')
        return JsonResponse({'success': True, 'message': 'Silindi'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ���══════════════════════════════════════════════════════════════════════════════
# TƏLƏBƏ GÖRÜNÜŞÜ
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def assignment_detail(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Sərbəst işin detalları (tələbə üçün)                                    │
    │ GET /assignments/<pk>/                                                  │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Assignment məlumatlarını görür                                        │
    │ - Əvvəlki cavablarını görür                                             │
    │ - Yeni cavab göndərə bilir (cəhd varsa)                                 │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = get_object_or_404(Assignment, id=pk)
    
    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - tələbə yalnız özünə təyin olunmuşlara baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if getattr(request.user, 'is_student', False):
        has_access = assignment.assigned_students.filter(id=request.user.id).exists()
        if not has_access:
            messages.error(request, 'Bu tapşırığa giriş icazəniz yoxdur')
            return redirect('courses:course_dashboard', course_id=assignment.course.id)
    
    # İstifadəçinin əvvəlki cavablarını al
    user_submissions = assignment.submissions.filter(student=request.user).order_by('-submitted_at')
    user_attempts = user_submissions.count()
    
    context = {
        'assignment': assignment,
        'user_submissions': user_submissions,
        'user_attempts': user_attempts,
        'can_submit': assignment.can_user_submit(request.user),
        'attempts_left': assignment.max_attempts - user_attempts,
    }
    
    return render(request, 'assignments/assignment_detail.html', context)


@login_required
@require_http_methods(["POST"])
def submit_assignment(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Sərbəst işə cavab göndərmək                                             │
    │ POST /assignments/<pk>/submit/                                          │
    │                                                                         │
    │ Form data: content (text), file (optional)                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = get_object_or_404(Assignment, id=pk)
    
    # Cavab göndərə bilərmi yoxla
    if not assignment.can_user_submit(request.user):
        return JsonResponse({
            'success': False,
            'error': 'Cavab göndərmək mümkün deyil. Cəhd limitiniz bitib və ya müddət keçib.'
        }, status=400)
    
    try:
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=request.user,
            content=request.POST.get('content', ''),
        )
        
        # Fayl yükləmə
        if 'file' in request.FILES:
            submission.file = request.FILES['file']
            submission.save()
        
        messages.success(request, 'Cavabınız göndərildi!')
        return JsonResponse({
            'success': True,
            'message': 'Cavab göndərildi',
            'submission_id': submission.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def my_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Tələbənin öz cavablarını görmək                                         │
    │ GET /assignments/<pk>/my-submissions/                                   │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Bütün göndərdiyi cavabları görür                                      │
    │ - Qiymətlərini görür                                                    │
    │ - Müəllim rəyini görür                                                  │
    │ - Qalan cəhd sayını görür                                               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = get_object_or_404(Assignment, id=pk)
    
    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - yalnız özünə təyin olunmuş assignment-lara baxa bilər
    # ──────────────────��──────────────────────────────────────────────────────
    if not assignment.assigned_students.filter(id=request.user.id).exists():
        messages.error(request, 'Bu tapşırığa giriş icazəniz yoxdur')
        return redirect('courses:course_dashboard', course_id=assignment.course.id)
    
    # İstifadəçinin cavablarını al
    submissions = assignment.submissions.filter(student=request.user).order_by('-submitted_at')
    user_attempts = submissions.count()
    
    context = {
        'assignment': assignment,
        'submissions': submissions,
        'user_attempts': user_attempts,
        'can_submit': assignment.can_user_submit(request.user),
        'attempts_left': assignment.max_attempts - user_attempts,
    }
    
    return render(request, 'assignments/my_submissions.html', context)


# ═══════════════════════════════════════════════════════════════════════════════
# MÜƏLLİM GÖRÜNÜŞÜ
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def review_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabları yoxlamaq (müəllim üçün)                                       │
    │ GET /assignments/<pk>/submissions/                                      │
    │                                                                         │
    │ Müəllim burada:                                                         │
    │ - Bütün tələbə cavablarını görür                                        │
    │ - Qiymət verə bilir                                                     │
    │ - Rəy yaza bilir                                                        │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = get_object_or_404(Assignment, id=pk)
    
    # İcazə yoxlaması
    if not request.user.is_teacher or assignment.course.owner != request.user:
        messages.error(request, 'İcazəniz yoxdur')
        return redirect('courses:course_dashboard', course_id=assignment.course.id)
    
    submissions = assignment.submissions.select_related('student').order_by('-submitted_at')
    
    context = {
        'assignment': assignment,
        'submissions': submissions,
    }
    
    return render(request, 'assignments/review_submissions.html', context)


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabı qiymətləndirmək                                                  │
    │ POST /assignments/submission/<pk>/grade/                                │
    │                                                                         │
    │ Form data: grade, feedback (optional)                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    submission = get_object_or_404(AssignmentSubmission, id=pk)
    
    # İcazə yoxlaması
    if not request.user.is_teacher or submission.assignment.course.owner != request.user:
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
def search_students(request):
    """
    ┌────────────────���────────────────────────────────────────────────────────┐
    │ Tələbə axtarışı (AJAX)                                                  │
    │ GET /assignments/api/students/?q=<query>&course_id=<id>                 │
    │                                                                         │
    │ Select2 dropdown üçün istifadə olunur                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    query = request.GET.get('q', '')
    course_id = request.GET.get('course_id')
    
    if not course_id:
        return JsonResponse({'results': []})
    
    course = get_object_or_404(Course, id=course_id)
    
    # Kursda olan tələbələri axtar
    student_memberships = course.memberships.filter(
        role='student'
    ).filter(
        Q(user__username__icontains=query) |
        Q(user__first_name__icontains=query) |
        Q(user__last_name__icontains=query)
    ).select_related('user')[:10]
    
    results = [{
        'id': m.user.id,
        'text': f"{m.user.get_full_name()} ({m.user.username})" if m.user.first_name else m.user.username,
        'group_name': m.group_name or ''
    } for m in student_memberships]
    
    return JsonResponse({'results': results})


@login_required
def search_groups(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Qrup axtarışı (AJAX)                                                    │
    │ GET /assignments/api/groups/?q=<query>&course_id=<id>                   │
    │                                                                         │
    │ Kursdakı unique group_name-ləri qaytarır                                │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    query = request.GET.get('q', '')
    course_id = request.GET.get('course_id')
    
    if not course_id:
        return JsonResponse({'results': []})
    
    course = get_object_or_404(Course, id=course_id)
    
    # Unique qrup adlarını tap
    group_names = CourseMembership.objects.filter(
        course=course,
        group_name__icontains=query
    ).exclude(
        group_name=''
    ).values_list('group_name', flat=True).distinct()[:10]
    
    results = [{
        'id': name,
        'text': name
    } for name in group_names]
    
    return JsonResponse({'results': results})


@login_required
def students_by_groups(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Qruplara görə tələbələri qaytarır (AJAX)                                │
    │ GET /assignments/api/students-by-groups/?course_id=<id>&groups=<g1,g2>  │
    │                                                                         │
    │ Modal-da qrup seçildikdə tələbə listini yeniləmək üçün                  │
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