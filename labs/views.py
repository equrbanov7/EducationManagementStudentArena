"""
labs/views.py - YENİLƏNMİŞ
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Lab, LabBlock, LabQuestion, LabAssignment, LabSubmission
from courses.models import Course, CourseMembership
from django.contrib.auth import get_user_model

User = get_user_model()


def is_course_teacher(user, course):
    return user.is_teacher and course.owner == user


# ════════════════════════════════════════════════════════════════════════════
# LAB CRUD
# ════════════════════════════════════════════════════════════════════════════

@login_required
@require_http_methods(["POST"])
def create_lab(request, course_id):
    """Lab yaratmaq"""
    course = get_object_or_404(Course, id=course_id)
    
    if not is_course_teacher(request.user, course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        lab = Lab.objects.create(
            course=course,
            created_by=request.user,
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            start_datetime=request.POST.get('start_datetime'),
            end_datetime=request.POST.get('end_datetime'),
            max_score=request.POST.get('max_score', 100),
            status='draft',
            allow_late_submission=request.POST.get('allow_late_submission') == 'on',
            late_penalty_percent=request.POST.get('late_penalty_percent', 0) or 0,
            allow_file_upload=request.POST.get('allow_file_upload') == 'on',
            allow_link_submission=request.POST.get('allow_link_submission') == 'on',
            allowed_extensions=request.POST.get('allowed_extensions', 'zip,pdf,docx'),
            max_file_size_mb=request.POST.get('max_file_size_mb', 50) or 50,
            questions_per_student=request.POST.get('questions_per_student', 0) or 0,
            teacher_instructions=request.POST.get('teacher_instructions', ''),
        )
        
        # Müəllim faylı
        if 'teacher_files' in request.FILES:
            lab.teacher_files = request.FILES['teacher_files']
        
        # Qrup və Tələbə məntiqi
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('student_ids[]')
        
        if student_ids:
            # Yalnız seçilmiş tələbələr
            lab.allowed_groups = ''  # Qrupları sıfırla
            lab.allowed_students = ','.join(student_ids)
        elif group_names:
            # Bütün qrup
            lab.allowed_groups = ','.join(group_names)
            lab.allowed_students = ''
        
        lab.save()
        
        return JsonResponse({'success': True, 'lab_id': lab.id})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_lab(request, pk):
    """Lab redaktə etmək"""
    lab = get_object_or_404(Lab, id=pk)
    
    if not is_course_teacher(request.user, lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    if request.method == 'GET':
        # Allowed students parse
        student_ids = []
        if hasattr(lab, 'allowed_students') and lab.allowed_students:
            student_ids = [int(x) for x in lab.allowed_students.split(',') if x.strip().isdigit()]
        
        data = {
            'id': lab.id,
            'title': lab.title,
            'description': lab.description,
            'start_datetime': lab.start_datetime.strftime('%Y-%m-%dT%H:%M') if lab.start_datetime else '',
            'end_datetime': lab.end_datetime.strftime('%Y-%m-%dT%H:%M') if lab.end_datetime else '',
            'max_score': lab.max_score,
            'status': lab.status,
            'allow_late_submission': lab.allow_late_submission,
            'late_penalty_percent': lab.late_penalty_percent,
            'allow_file_upload': lab.allow_file_upload,
            'allow_link_submission': lab.allow_link_submission,
            'allowed_extensions': lab.allowed_extensions,
            'max_file_size_mb': lab.max_file_size_mb,
            'questions_per_student': lab.questions_per_student,
            'teacher_instructions': lab.teacher_instructions,
            'teacher_files_url': lab.teacher_files.url if lab.teacher_files else None,
            'group_names': lab.get_allowed_groups_list(),
            'student_ids': student_ids,
        }
        return JsonResponse({'success': True, 'data': data})
    
    # POST
    try:
        lab.title = request.POST.get('title')
        lab.description = request.POST.get('description', '')
        lab.start_datetime = request.POST.get('start_datetime')
        lab.end_datetime = request.POST.get('end_datetime')
        lab.max_score = request.POST.get('max_score', 100) or 100
        lab.allow_late_submission = request.POST.get('allow_late_submission') == 'on'
        lab.late_penalty_percent = request.POST.get('late_penalty_percent', 0) or 0
        lab.allow_file_upload = request.POST.get('allow_file_upload') == 'on'
        lab.allow_link_submission = request.POST.get('allow_link_submission') == 'on'
        lab.allowed_extensions = request.POST.get('allowed_extensions', 'zip,pdf,docx')
        lab.max_file_size_mb = request.POST.get('max_file_size_mb', 50) or 50
        lab.questions_per_student = request.POST.get('questions_per_student', 0) or 0
        lab.teacher_instructions = request.POST.get('teacher_instructions', '')
        
        if 'teacher_files' in request.FILES:
            lab.teacher_files = request.FILES['teacher_files']
        
        # Qrup və Tələbə məntiqi
        group_names = request.POST.getlist('group_names[]')
        student_ids = request.POST.getlist('student_ids[]')
        
        if student_ids:
            lab.allowed_groups = ''
            lab.allowed_students = ','.join(student_ids)
        elif group_names:
            lab.allowed_groups = ','.join(group_names)
            lab.allowed_students = ''
        else:
            lab.allowed_groups = ''
            lab.allowed_students = ''
        
        lab.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_lab(request, pk):
    lab = get_object_or_404(Lab, id=pk)
    if not is_course_teacher(request.user, lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    lab.delete()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def publish_lab(request, pk):
    lab = get_object_or_404(Lab, id=pk)
    if not is_course_teacher(request.user, lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    if lab.total_questions == 0:
        return JsonResponse({'success': False, 'error': 'Ən azı 1 sual əlavə edin'}, status=400)
    lab.status = 'published'
    lab.save()
    return JsonResponse({'success': True})


# ════════════════════════════════════════════════════════════════════════════
# BLOCK CRUD
# ════════════════════════════════════════════════════════════════════════════

@login_required
def manage_blocks(request, lab_id):
    lab = get_object_or_404(Lab, id=lab_id)
    if not is_course_teacher(request.user, lab.course):
        messages.error(request, 'İcazəniz yoxdur')
        return redirect('courses:course_dashboard', pk=lab.course.id)
    
    return render(request, 'labs/manage_blocks.html', {
        'lab': lab,
        'blocks': lab.blocks.prefetch_related('questions').all(),
    })


@login_required
@require_http_methods(["POST"])
def create_block(request, lab_id):
    lab = get_object_or_404(Lab, id=lab_id)
    if not is_course_teacher(request.user, lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        max_order = lab.blocks.count() + 1
        block = LabBlock.objects.create(
            lab=lab,
            title=request.POST.get('title', f'Blok {max_order}'),
            description=request.POST.get('description', ''),
            order=max_order,
            questions_to_pick=request.POST.get('questions_to_pick', 0) or 0,
        )
        return JsonResponse({'success': True, 'block': {'id': block.id, 'title': block.title}})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_block(request, pk):
    block = get_object_or_404(LabBlock, id=pk)
    if not is_course_teacher(request.user, block.lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': block.id,
                'title': block.title,
                'description': block.description,
                'order': block.order,
                'questions_to_pick': block.questions_to_pick,
                'question_count': block.question_count,
            }
        })
    
    try:
        block.title = request.POST.get('title')
        block.description = request.POST.get('description', '')
        block.questions_to_pick = request.POST.get('questions_to_pick', 0) or 0
        block.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_block(request, pk):
    block = get_object_or_404(LabBlock, id=pk)
    if not is_course_teacher(request.user, block.lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    block.delete()
    return JsonResponse({'success': True})


# ════════════════════════════════════════════════════════════════════════════
# QUESTION CRUD
# ════════════════════════════════════════════════════════════════════════════

@login_required
@require_http_methods(["POST"])
def create_question(request, block_id):
    block = get_object_or_404(LabBlock, id=block_id)
    if not is_course_teacher(request.user, block.lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        max_num = block.questions.count() + 1
        question = LabQuestion.objects.create(
            block=block,
            question_number=max_num,
            question_text=request.POST.get('question_text'),
            points=request.POST.get('points', 0) or 0,
        )
        if 'attachment' in request.FILES:
            question.attachment = request.FILES['attachment']
            question.save()
        return JsonResponse({'success': True, 'question': {'id': question.id}})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_question(request, pk):
    question = get_object_or_404(LabQuestion, id=pk)
    if not is_course_teacher(request.user, question.block.lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': question.id,
                'question_number': question.question_number,
                'question_text': question.question_text,
                'points': question.points,
                'attachment_url': question.attachment.url if question.attachment else None,
            }
        })
    
    try:
        question.question_text = request.POST.get('question_text')
        question.points = request.POST.get('points', 0) or 0
        if 'attachment' in request.FILES:
            question.attachment = request.FILES['attachment']
        question.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_question(request, pk):
    question = get_object_or_404(LabQuestion, id=pk)
    if not is_course_teacher(request.user, question.block.lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    question.delete()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def import_questions(request, block_id):
    block = get_object_or_404(LabBlock, id=block_id)
    if not is_course_teacher(request.user, block.lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        questions_text = request.POST.get('questions_text', '')
        lines = [line.strip() for line in questions_text.strip().split('\n') if line.strip()]
        
        if not lines:
            return JsonResponse({'success': False, 'error': 'Heç bir sual tapılmadı'}, status=400)
        
        created_count = 0
        start_num = block.questions.count() + 1
        
        for i, line in enumerate(lines):
            LabQuestion.objects.create(
                block=block,
                question_number=start_num + i,
                question_text=line,
            )
            created_count += 1
        
        return JsonResponse({'success': True, 'created_count': created_count, 'message': f'{created_count} sual əlavə edildi'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ════════════════════════════════════════════════════════════════════════════
# STUDENT
# ════════════════════════════════════════════════════════════════════════════

@login_required
def lab_detail(request, pk):
    lab = get_object_or_404(Lab, id=pk)
    
    if request.user.is_student:
        membership = CourseMembership.objects.filter(course=lab.course, user=request.user, role='student').first()
        if not membership:
            messages.error(request, 'Bu laba giriş icazəniz yoxdur')
            return redirect('courses:course_dashboard', pk=lab.course.id)
        
        allowed_groups = lab.get_allowed_groups_list()
        if allowed_groups and membership.group_name not in allowed_groups:
            messages.error(request, 'Bu lab sizin qrupunuz üçün deyil')
            return redirect('courses:course_dashboard', pk=lab.course.id)
    
    assignment = None
    submissions = []
    
    if request.user.is_student and lab.is_open:
        assignment = LabAssignment.get_or_create_for_student(lab, request.user)
        submissions = assignment.submissions.all()
    
    return render(request, 'labs/lab_detail.html', {
        'lab': lab,
        'assignment': assignment,
        'submissions': submissions,
        'assigned_questions': assignment.assigned_questions.all() if assignment else [],
    })


@login_required
@require_http_methods(["POST"])
def submit_lab(request, pk):
    lab = get_object_or_404(Lab, id=pk)
    assignment = get_object_or_404(LabAssignment, lab=lab, student=request.user)
    
    if lab.is_closed and not lab.allow_late_submission:
        return JsonResponse({'success': False, 'error': 'Deadline keçib'}, status=400)
    
    try:
        attempt_num = assignment.submissions.count() + 1
        submission = LabSubmission.objects.create(
            assignment=assignment,
            submission_text=request.POST.get('submission_text', ''),
            submission_link=request.POST.get('submission_link', ''),
            attempt_number=attempt_num,
        )
        if 'submission_file' in request.FILES:
            submission.submission_file = request.FILES['submission_file']
            submission.save()
        return JsonResponse({'success': True, 'submission_id': submission.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ════════════════════════════════════════════════════════════════════════════
# TEACHER: Submissions & Grading
# ════════════════════════════════════════════════════════════════════════════

@login_required
def lab_submissions(request, pk):
    lab = get_object_or_404(Lab, id=pk)
    if not is_course_teacher(request.user, lab.course):
        messages.error(request, 'İcazəniz yoxdur')
        return redirect('courses:course_dashboard', pk=lab.course.id)
    
    submissions = LabSubmission.objects.filter(assignment__lab=lab).select_related('assignment__student').order_by('-submitted_at')
    
    status_filter = request.GET.get('status', '')
    group_filter = request.GET.get('group', '')
    
    if status_filter:
        submissions = submissions.filter(status=status_filter)
    
    if group_filter:
        student_ids = CourseMembership.objects.filter(course=lab.course, group_name=group_filter, role='student').values_list('user_id', flat=True)
        submissions = submissions.filter(assignment__student_id__in=student_ids)
    
    groups = CourseMembership.objects.filter(course=lab.course, role='student').exclude(group_name='').values_list('group_name', flat=True).distinct()
    
    return render(request, 'labs/lab_submissions.html', {
        'lab': lab,
        'submissions': submissions,
        'groups': groups,
        'status_filter': status_filter,
        'group_filter': group_filter,
    })


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    submission = get_object_or_404(LabSubmission, id=pk)
    if not is_course_teacher(request.user, submission.assignment.lab.course):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur'}, status=403)
    
    try:
        submission.score = request.POST.get('score')
        submission.feedback = request.POST.get('feedback', '')
        submission.status = 'graded'
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        submission.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ════════════════════════════════════════════════════════════════════════════
# PREVIEW RANDOMIZATION - FIX
# ════════════════════════════════════════════════════════════════════════════

@login_required
def preview_randomization(request, pk):
    """Müəllim üçün random preview - HTML səhifə"""
    lab = get_object_or_404(Lab, id=pk)
    
    if not is_course_teacher(request.user, lab.course):
        messages.error(request, 'İcazəniz yoxdur')
        return redirect('labs:manage_blocks', lab_id=lab.id)
    
    import hashlib
    import random as rnd
    
    # Test üçün student seç
    student_id = request.GET.get('student_id')
    
    if student_id:
        student = get_object_or_404(User, id=student_id)
    else:
        membership = CourseMembership.objects.filter(course=lab.course, role='student').first()
        student = membership.user if membership else None
    
    if not student:
        return render(request, 'labs/preview_randomization.html', {
            'lab': lab,
            'error': 'Heç bir tələbə yoxdur',
            'students': [],
            'questions': [],
        })
    
    # Random sualları hesabla
    all_questions = []
    
    for block in lab.blocks.all():
        block_questions = list(block.questions.all())
        
        if block.questions_to_pick > 0 and block.questions_to_pick < len(block_questions):
            seed = int(hashlib.md5(f"{lab.id}-{student.id}-{block.id}".encode()).hexdigest(), 16)
            rng = rnd.Random(seed)
            selected = rng.sample(block_questions, block.questions_to_pick)
            all_questions.extend(selected)
        else:
            all_questions.extend(block_questions)
    
    # Lab səviyyəsində limit
    if lab.questions_per_student > 0 and lab.questions_per_student < len(all_questions):
        seed = int(hashlib.md5(f"{lab.id}-{student.id}-total".encode()).hexdigest(), 16)
        rng = rnd.Random(seed)
        all_questions = rng.sample(all_questions, lab.questions_per_student)
    
    # Bütün tələbələr
    students = CourseMembership.objects.filter(course=lab.course, role='student').select_related('user')
    
    return render(request, 'labs/preview_randomization.html', {
        'lab': lab,
        'selected_student': student,
        'questions': all_questions,
        'students': students,
    })


# ════════════════════════════════════════════════════════════════════════════
# API
# ════════════════════════════════════════════════════════════════════════════

@login_required
def api_get_groups(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    groups = CourseMembership.objects.filter(course=course, role='student').exclude(group_name='').exclude(group_name__isnull=True).values_list('group_name', flat=True).distinct()
    return JsonResponse({'groups': [{'name': g} for g in groups]})


@login_required
def api_get_students(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    groups_param = request.GET.get('groups', '')
    
    if not groups_param:
        return JsonResponse({'students': []})
    
    group_names = [g.strip() for g in groups_param.split(',') if g.strip()]
    
    memberships = CourseMembership.objects.filter(course=course, group_name__in=group_names, role='student').select_related('user').order_by('group_name', 'user__first_name')
    
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