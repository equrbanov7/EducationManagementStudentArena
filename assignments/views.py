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


@login_required
@require_http_methods(["POST"])
def create_assignment(request, course_id):
    """Sərbəst iş yaratma"""
    course = get_object_or_404(Course, id=course_id)
    
    if not request.user.is_teacher or course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        assignment = Assignment.objects.create(
            course=course,
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            start_date=request.POST.get('start_date'),
            deadline=request.POST.get('deadline'),
            max_attempts=request.POST.get('max_attempts', 3),
            status=request.POST.get('status', 'active')
        )
        
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('students[]')
        
        # ════════════════════════════════════════════════════════════
        # ƏSAS MƏNTİQ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # ════════════════════════════════════════════════════════════
        
        if student_ids:
            students = User.objects.filter(id__in=student_ids)
            assignment.assigned_students.set(students)
        elif group_names:
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
    """Sərbəst işi redaktə etmək"""
    assignment = get_object_or_404(Assignment, id=pk)
    
    # Yalnız müəllim redaktə edə bilər
    if not request.user.is_teacher or assignment.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    if request.method == 'GET':
        # Assigned tələbələrin ID-lərini al
        assigned_students = list(assignment.assigned_students.values('id', 'username', 'first_name', 'last_name'))
        assigned_student_ids = [s['id'] for s in assigned_students]
        
        # Bu tələbələrin hansı qruplarda olduğunu tap
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
            'student_ids': assigned_student_ids,  # Frontend üçün - hansı tələbələr seçilidir
            'students': [
                {
                    'id': s['id'],
                    'name': f"{s['first_name']} {s['last_name']}".strip() or s['username']
                }
                for s in assigned_students
            ],
        }
        return JsonResponse({'success': True, 'data': data})
    
    # POST - Update
    try:
        assignment.title = request.POST.get('title')
        assignment.description = request.POST.get('description', '')
        assignment.start_date = request.POST.get('start_date')
        assignment.deadline = request.POST.get('deadline')
        assignment.max_attempts = request.POST.get('max_attempts', 3)
        assignment.status = request.POST.get('status', 'active')
        assignment.save()
        
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('students[]')
        
        # ════════════════════════════════════════════════════════════
        # ƏSAS MƏNTİQ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # 3. Heç biri yoxdursa → Boş
        # ════════════════════════════════════════════════════════════
        
        if student_ids:
            # Yalnız seçilmiş tələbələri əlavə et
            students = User.objects.filter(id__in=student_ids)
            assignment.assigned_students.set(students)
        elif group_names:
            # Heç bir tələbə seçilməyib, bütün qrupu əlavə et
            group_students = User.objects.filter(
                course_memberships__course=assignment.course,
                course_memberships__group_name__in=group_names,
                course_memberships__role='student'
            ).distinct()
            assignment.assigned_students.set(group_students)
        else:
            # Heç nə seçilməyib
            assignment.assigned_students.clear()
        
        messages.success(request, 'Sərbəst iş yeniləndi!')
        return JsonResponse({'success': True, 'message': 'Sərbəst iş yeniləndi'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_assignment(request, pk):
    """Sərbəst işi silmək"""
    assignment = get_object_or_404(Assignment, id=pk)
    
    # Yalnız müəllim silə bilər
    if not request.user.is_teacher or assignment.course.owner != request.user:
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        assignment.delete()
        messages.success(request, 'Sərbəst iş silindi!')
        return JsonResponse({'success': True, 'message': 'Silindi'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def assignment_detail(request, pk):
    """Sərbəst işin detalları (tələbə üçün)"""
    assignment = get_object_or_404(Assignment, id=pk)
    
    # Check if student has access
    if request.user.is_student:  # Bu property-dir, işləyir
        has_access = assignment.assigned_students.filter(id=request.user.id).exists()
        if not has_access:
            messages.error(request, 'Bu tapşırığa giriş icazəniz yoxdur')
            return redirect('courses:course_dashboard', pk=assignment.course.id)
    
    # Get user's previous submissions
    user_submissions = assignment.submissions.filter(student=request.user).order_by('-submitted_at')
    
    context = {
        'assignment': assignment,
        'user_submissions': user_submissions,
        'can_submit': assignment.can_user_submit(request.user),
        'attempts_left': assignment.max_attempts - assignment.get_user_attempts(request.user),
    }
    
    return render(request, 'assignments/assignment_detail.html', context)


@login_required
@require_http_methods(["POST"])
def submit_assignment(request, pk):
    """Sərbəst işə cavab göndərmək"""
    assignment = get_object_or_404(Assignment, id=pk)
    
    if not assignment.can_user_submit(request.user):
        return JsonResponse({
            'success': False,
            'error': 'Cavab göndərmək mümkün deyil'
        }, status=400)
    
    try:
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=request.user,
            content=request.POST.get('content', ''),
        )
        
        # Handle file upload if present
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
def review_submissions(request, pk):
    """Cavabları yoxlamaq (müəllim üçün)"""
    assignment = get_object_or_404(Assignment, id=pk)
    
    if not request.user.is_teacher or assignment.course.owner != request.user:
        messages.error(request, 'İcazəniz yoxdur')
        return redirect('courses:course_dashboard', pk=assignment.course.id)
    
    submissions = assignment.submissions.select_related('student').order_by('-submitted_at')
    
    context = {
        'assignment': assignment,
        'submissions': submissions,
    }
    
    return render(request, 'assignments/review_submissions.html', context)


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    """Cavabı qiymətləndirmək"""
    submission = get_object_or_404(AssignmentSubmission, id=pk)
    
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


# AJAX helper views
@login_required
def search_students(request):
    """Tələbə axtarışı"""
    query = request.GET.get('q', '')
    course_id = request.GET.get('course_id')
    
    if not course_id:
        return JsonResponse({'results': []})
    
    course = get_object_or_404(Course, id=course_id)
    
    # CourseMembership-dən tələbələri tap
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
    """Qrup axtarışı - group_name əsasında"""
    query = request.GET.get('q', '')
    course_id = request.GET.get('course_id')
    
    if not course_id:
        return JsonResponse({'results': []})
    
    course = get_object_or_404(Course, id=course_id)
    
    # CourseMembership-dən unique group_name-ləri tap
    group_names = CourseMembership.objects.filter(
        course=course,
        group_name__icontains=query
    ).exclude(
        group_name=''
    ).values_list('group_name', flat=True).distinct()[:10]
    
    results = [{
        'id': name,  # group_name özü ID kimi istifadə olunur
        'text': name
    } for name in group_names]
    
    return JsonResponse({'results': results})


@login_required
def students_by_groups(request):
    """Qruplara görə tələbələri qaytarır"""
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