"""
projects/views.py
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


@login_required
@require_http_methods(["POST"])
def create_project(request, course_id):
    """Kurs işi yaratma"""
    course = get_object_or_404(Course, id=course_id)
    
    if not request.user.is_teacher or course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
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
        
        # Formdan gələn məlumatlar
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('students[]')
        
        # ════════════════════════════════════════════════════════════
        # ƏSAS MƏNTİQ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # ════════════════════════════════════════════════════════════
        
        if student_ids:
            # Yalnız seçilmiş tələbələri əlavə et
            students = User.objects.filter(id__in=student_ids)
            project.assigned_students.set(students)
        elif group_names:
            # Heç bir tələbə seçilməyib, bütün qrupu əlavə et
            group_students = User.objects.filter(
                course_memberships__course=course,
                course_memberships__group_name__in=group_names,
                course_memberships__role='student'
            ).distinct()
            project.assigned_students.set(group_students)
        
        return JsonResponse({'success': True, 'project_id': project.id})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_project(request, pk):
    """Kurs işini redaktə etmək"""
    project = get_object_or_404(Project, id=pk)
    
    if not request.user.is_teacher or project.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    if request.method == 'GET':
        # Assigned tələbələrin ID-lərini və qrup adlarını al
        assigned_students = list(project.assigned_students.values('id', 'username', 'first_name', 'last_name'))
        assigned_student_ids = [s['id'] for s in assigned_students]
        
        # Bu təl��bələrin hansı qruplarda olduğunu tap
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
            'student_ids': assigned_student_ids,  # Sadəcə ID-lər
            'students': [
                {
                    'id': s['id'],
                    'name': f"{s['first_name']} {s['last_name']}".strip() or s['username']
                }
                for s in assigned_students
            ],
        }
        return JsonResponse({'success': True, 'data': data})
    
    # POST
    try:
        project.title = request.POST.get('title')
        project.description = request.POST.get('description', '')
        project.start_date = request.POST.get('start_date')
        project.deadline = request.POST.get('deadline')
        project.max_attempts = request.POST.get('max_attempts', 1)
        project.max_score = request.POST.get('max_score', 100)
        project.status = request.POST.get('status', 'active')
        project.save()
        
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('students[]')
        
        # ════════════════════════════════════════════════════════════
        # ƏSAS MƏNTİQ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # 3. Heç biri yoxdursa → Boş
        # ════════════════════════════════════════════════════════════
        
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
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_project(request, pk):
    project = get_object_or_404(Project, id=pk)
    
    if not request.user.is_teacher or project.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    project.delete()
    return JsonResponse({'success': True})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, id=pk)
    
    if request.user.is_student:
        if not project.assigned_students.filter(id=request.user.id).exists():
            messages.error(request, 'Bu layihəyə giriş icazəniz yoxdur')
            return redirect('courses:course_dashboard', pk=project.course.id)
    
    user_submissions = project.submissions.filter(student=request.user).order_by('-submitted_at')
    
    return render(request, 'projects/project_detail.html', {
        'project': project,
        'user_submissions': user_submissions,
        'can_submit': project.can_user_submit(request.user),
        'attempts_left': project.max_attempts - project.get_user_attempts(request.user),
    })


@login_required
@require_http_methods(["POST"])
def submit_project(request, pk):
    project = get_object_or_404(Project, id=pk)
    
    if not project.can_user_submit(request.user):
        return JsonResponse({'success': False, 'error': 'Təqdim etmək mümkün deyil'}, status=400)
    
    try:
        submission = ProjectSubmission.objects.create(
            project=project,
            student=request.user,
            content=request.POST.get('content', ''),
        )
        
        if 'file' in request.FILES:
            submission.file = request.FILES['file']
            submission.save()
        
        return JsonResponse({'success': True, 'submission_id': submission.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def review_submissions(request, pk):
    project = get_object_or_404(Project, id=pk)
    
    if not request.user.is_teacher or project.course.owner != request.user:
        messages.error(request, 'İcazəniz yoxdur')
        return redirect('courses:course_dashboard', pk=project.course.id)
    
    return render(request, 'projects/review_submissions.html', {
        'project': project,
        'submissions': project.submissions.select_related('student').order_by('-submitted_at'),
    })


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    submission = get_object_or_404(ProjectSubmission, id=pk)
    
    if not request.user.is_teacher or submission.project.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    submission.grade = request.POST.get('grade')
    submission.feedback = request.POST.get('feedback', '')
    submission.status = 'graded'
    submission.graded_at = timezone.now()
    submission.graded_by = request.user
    submission.save()
    
    return JsonResponse({'success': True})


# ════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@login_required
def api_get_groups(request):
    """Kursdakı qrupları qaytarır"""
    course_id = request.GET.get('course_id')
    
    if not course_id:
        return JsonResponse({'groups': []})
    
    course = get_object_or_404(Course, id=course_id)
    
    groups = CourseMembership.objects.filter(
        course=course,
        role='student'
    ).exclude(group_name='').exclude(group_name__isnull=True).values_list('group_name', flat=True).distinct()
    
    return JsonResponse({
        'groups': [{'id': i, 'name': name} for i, name in enumerate(groups, 1)]
    })


@login_required
def api_get_students(request):
    """Qruplardakı tələbələri qaytarır"""
    course_id = request.GET.get('course_id')
    groups_param = request.GET.get('groups', '')
    
    if not course_id or not groups_param:
        return JsonResponse({'students': []})
    
    course = get_object_or_404(Course, id=course_id)
    group_names = [g.strip() for g in groups_param.split(',') if g.strip()]
    
    if not group_names:
        return JsonResponse({'students': []})
    
    memberships = CourseMembership.objects.filter(
        course=course,
        group_name__in=group_names,
        role='student'
    ).select_related('user').order_by('group_name', 'user__first_name')
    
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