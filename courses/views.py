"""
courses/views.py
────────────────
Kurs modulu üçün view-lər.

Labs app inteqrasiyası əlavə edilib.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, DetailView, UpdateView, View, ListView
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q, Max

from .models import (
    Course,
    CourseMembership,
    CourseTopic,
    CourseResource,
)
from .forms import (
    CourseForm,
    CourseTopicForm,
    CourseResourceForm,
)
from django.contrib.auth import get_user_model

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Mixin: Müəllim İcazə Yoxlaması
# ════════════════════════════════════════════════════════════════════════════

class IsTeacherMixin(UserPassesTestMixin):
    """Yalnız müəllim (is_teacher) bu view-a girə bilər."""
    
    def test_func(self):
        return getattr(self.request.user, 'is_teacher', False)
    
    def handle_no_permission(self):
        messages.error(self.request, 'Bu əməliyyat yalnız müəllimlər üçün mümkündür.')
        return redirect('home')


class IsCourseOwnerMixin(UserPassesTestMixin):
    """Yalnız kursun sahibi (owner) redaktə edə bilər."""
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        messages.error(self.request, 'Bu kursu redaktə etməyə icazəniz yoxdur.')
        return redirect('home')


# ════════════════════════════════════════════════════════════════════════════
# VIEW 1: Kurs Yaratma
# ════════════════════════════════════════════════════════════════════════════

class CreateCourseView(IsTeacherMixin, CreateView):
    """Kurs yaratma view-u."""
    
    model = Course
    form_class = CourseForm
    template_name = 'courses/create_course.html'
    
    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.status = 'draft'
        response = super().form_valid(form)
        messages.success(self.request, f'✅ "{form.instance.title}" kursu uğurla yaradıldı!')
        return response
    
    def get_success_url(self):
        return reverse_lazy('courses:course_dashboard', args=[self.object.id])


# ═══���════════════════════════════════════════════════════════════════════════
# VIEW 2: Kurs Dashboard (Accordion) - LABS ƏLAVƏSİ
# ════════════════════════════════════════════════════════════════════════════

class CourseDashboardView(LoginRequiredMixin, DetailView):
    """
    Kurs dashboard view-u.
    Labs app inteqrasiyası əlavə edilib.
    """
    model = Course
    template_name = 'courses/course_dashboard.html'
    context_object_name = 'course'
    pk_url_kwarg = 'course_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_object()
        user = self.request.user

        # ════════════════════════════════════════════════════════════════
        # Accordion məlumatları
        # ════════════════════════════════════════════════════════════════
        context['topics'] = course.topics.all().order_by('order')
        context['resources'] = course.resources.all().order_by('-created_at')
        context['members'] = course.memberships.all().order_by('joined_at')

        # ════════════════════════════════════════════════════════════════
        # LABS - YENİ
        # ════════════════════════════════════════════════════════════════
        if user.is_teacher and course.owner == user:
            # Müəllim bütün labları görür
            context['labs'] = course.labs.all().order_by('-created_at')
        elif hasattr(user, 'is_student') and user.is_student:
            # Tələbə yalnız published labları görür
            # + Qrup filtri varsa, yalnız öz qrupuna aid labları
            membership = course.memberships.filter(user=user, role='student').first()
            
            labs_qs = course.labs.filter(status='published')
            
            if membership:
                student_group = membership.group_name
                # Qrup filtri olan labları yoxla
                filtered_labs = []
                for lab in labs_qs:
                    allowed_groups = lab.get_allowed_groups_list()
                    if not allowed_groups or student_group in allowed_groups:
                        filtered_labs.append(lab)
                context['labs'] = filtered_labs
            else:
                context['labs'] = labs_qs
        else:
            context['labs'] = course.labs.filter(status='published')

        # ════════════════════════════════════════════════════════════════
        # Formalar (modal-lar üçün)
        # ════════════════════════════════════════════════════════════════
        context['topic_form'] = CourseTopicForm()
        context['resource_form'] = CourseResourceForm()

        # Owner check
        context['is_owner'] = course.owner == user

        # ════════════════════════════════════════════════════════════════
        # ASSIGNMENT MODAL üçün: Kursdakı real qruplar
        # ════════════════════════════════════════════════════════════════
        context['assignment_groups'] = list(
            course.memberships
            .filter(role='student')
            .exclude(group_name__isnull=True)
            .exclude(group_name__exact='')
            .values_list('group_name', flat=True)
            .distinct()
            .order_by('group_name')
        )

        # ════════════════════════════════════════════════════════════════
        # Modal-lar üçün owner-ə məxsus şeylər
        # ════════════════════════════════════════════════════════════════
        if context['is_owner']:
            course_user_ids = course.memberships.values_list('user_id', flat=True)
            context['all_users'] = (
                User.objects
                .exclude(id__in=course_user_ids)
                .filter(groups__name='student')
                .distinct()
                .order_by('username')
            )

            try:
                from blog.models import StudentGroup
                context['all_groups'] = StudentGroup.objects.all().order_by('name')
            except ImportError:
                context['all_groups'] = []
        else:
            context['all_users'] = []
            context['all_groups'] = []

        return context


# ════════════════════════════════════════════════════════════════════════════
# VIEW 3: Mövzu Əlavə Etmə (AJAX/Modal)
# ════════════════════════════════════════════════════════════════════════════

class AddTopicView(IsCourseOwnerMixin, CreateView):
    """Mövzu əlavə etmə (AJAX POST)."""
    
    model = CourseTopic
    form_class = CourseTopicForm
    
    def dispatch(self, request, *args, **kwargs):
        self.course = get_object_or_404(Course, id=kwargs['course_id'])
        if self.course.owner != request.user:
            return HttpResponseForbidden("Bu kursu redaktə etməyə icazəniz yoxdur.")
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.course = self.course
        max_order = CourseTopic.objects.filter(
            course=self.course
        ).aggregate(Max('order'))['order__max'] or 0
        form.instance.order = max_order + 1
        
        response = super().form_valid(form)
        
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'"{form.instance.title}" mövzusu əlavə olundu',
                'topic': {
                    'id': form.instance.id,
                    'title': form.instance.title,
                    'order': form.instance.order,
                },
            })
        
        messages.success(self.request, f'"{form.instance.title}" mövzusu əlavə olundu')
        return response
    
    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        messages.error(self.request, 'Mövzu əlavə olunarkən xəta baş verdi.')
        return redirect('courses:course_dashboard', course_id=self.course.id)
    
    def get_success_url(self):
        return reverse_lazy('courses:course_dashboard', args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW 4: Mövzu Silmə (AJAX)
# ════════════════════════════════════════════════════════════════════════════

class DeleteTopicView(IsCourseOwnerMixin, View):
    """Mövzu silmə (POST)."""
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        topic_id = kwargs.get('topic_id')
        
        course = get_object_or_404(Course, id=course_id)
        topic = get_object_or_404(CourseTopic, id=topic_id, course=course)
        
        if course.owner != request.user:
            messages.error(request, 'Bu əməliyyata icazəniz yoxdur.')
            return redirect('courses:course_dashboard', course_id=course_id)
        
        topic_title = topic.title
        topic.delete()
        
        messages.success(request, f'✅ "{topic_title}" mövzusu silindi.')
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        return redirect('courses:course_dashboard', course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW 5: Resurs Əlavə Etmə
# ════════════════════════════════════════════════════════════════════════════

class AddResourceView(IsCourseOwnerMixin, CreateView):
    """Resurs əlavə etmə (AJAX/Modal)."""
    
    model = CourseResource
    form_class = CourseResourceForm
    
    def dispatch(self, request, *args, **kwargs):
        self.course = get_object_or_404(Course, id=kwargs['course_id'])
        if self.course.owner != request.user:
            return HttpResponseForbidden("Bu kursu redaktə etməyə icazəniz yoxdur.")
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.course = self.course
        response = super().form_valid(form)
        
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'"{form.instance.title}" resursu əlavə olundu',
                'resource': {
                    'id': form.instance.id,
                    'title': form.instance.title,
                    'type': form.instance.get_resource_type_display(),
                },
            })
        
        messages.success(self.request, f'"{form.instance.title}" resursu əlavə olundu')
        return response
    
    def get_success_url(self):
        return reverse_lazy('courses:course_dashboard', args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW 6: Resurs Silmə
# ════════════════════════════════════════════════════════════════════════════

class DeleteResourceView(IsCourseOwnerMixin, View):
    """Resurs silmə."""
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        resource_id = kwargs.get('resource_id')
        
        course = get_object_or_404(Course, id=course_id)
        resource = get_object_or_404(CourseResource, id=resource_id, course=course)
        
        if course.owner != request.user:
            messages.error(request, 'Bu əməliyyata icazəniz yoxdur.')
            return redirect('courses:course_dashboard', course_id=course_id)
        
        resource_title = resource.title
        resource.delete()
        
        messages.success(request, f'✅ "{resource_title}" resursu silindi.')
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        return redirect('courses:course_dashboard', course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW 7: Kurs Üzvləri (Members)
# ════════════════════════════════════════════════════════════════════════════

class CourseMembersView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Kurs üzvlüyü səhifəsi."""
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        messages.error(self.request, 'Bu səhifəyə giriş icazəniz yoxdur.')
        return redirect('home')
    
    def get(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        members = course.memberships.all().order_by('joined_at')
        teacher = members.filter(role='teacher').first()
        assistants = members.filter(role='assistant')
        students = members.filter(role='student').order_by('group_name', 'user__username')
        
        course_user_ids = course.memberships.values_list('user_id', flat=True)
        
        if hasattr(User, 'groups'): 
            all_users = User.objects.exclude(id__in=course_user_ids).filter(
                groups__name='student'
            ).distinct().order_by('username')
        else:
            all_users = User.objects.exclude(id__in=course_user_ids).order_by('username')
        
        try:
            from blog.models import StudentGroup 
            all_groups = StudentGroup.objects.all().order_by('name')
        except ImportError:
            all_groups = []
        
        context = {
            'course': course,
            'members': members,
            'teacher': teacher,
            'assistants': assistants,
            'students': students,
            'all_users': all_users,
            'all_groups': all_groups,
            'is_owner': course.owner == request.user,
        }
        
        return render(request, 'courses/course_members.html', context)


class AvailableStudentsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Kursda olmayan tələbələri JSON kimi qaytarır."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def get(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)

        course_user_ids = course.memberships.values_list("user_id", flat=True)

        qs = (
            User.objects
            .exclude(id__in=course_user_ids)
            .filter(groups__name="student")
            .distinct()
            .order_by("username")
        )

        data = [
            {"id": u.id, "username": u.username, "full_name": u.get_full_name() or u.username}
            for u in qs
        ]

        return JsonResponse({"success": True, "users": data})


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Tələbə Əlavə Et (AJAX)
# ════════════════════════════════════════════════════════════════════════════

class AddMemberView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Tələbə əlavə etmə (Modal-dan AJAX)."""
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        return JsonResponse({'success': False, 'error': 'Bu əməliyyata icazəniz yoxdur.'}, status=403)
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        user_ids = request.POST.getlist('user_ids')
        group_name = request.POST.get('group_name', '').strip()
        
        if not user_ids:
            return JsonResponse({'success': False, 'error': 'Heç bir tələbə seçilməyib.'}, status=400)
        
        added_count = 0
        
        for uid in user_ids:
            try:
                user = User.objects.get(id=uid)
                membership, created = CourseMembership.objects.get_or_create(
                    course=course,
                    user=user,
                    defaults={'role': 'student', 'group_name': group_name}
                )
                if not created:
                    membership.group_name = group_name
                    membership.save()
                added_count += 1
            except User.DoesNotExist:
                continue
        
        return JsonResponse({'success': True, 'message': f'{added_count} tələbə kursa əlavə olundu.'})


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Əlavə Et (Bulk)
# ════════════════════════════════════════════════════════════════════════════

class AddMembersBulkView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Qrupları toplu şəkildə kursa əlavə et."""
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        return JsonResponse({'success': False, 'error': 'İcazəniz yoxdur.'}, status=403)
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        group_ids = request.POST.getlist('group_ids')
        
        if not group_ids:
            return JsonResponse({'success': False, 'error': 'Qrup seçilməyib.'}, status=400)
        
        try:
            from blog.models import StudentGroup
            groups = StudentGroup.objects.filter(id__in=group_ids)
            
            added_count = 0
            
            for group in groups:
                students = group.students.all() 
                
                for student in students:
                    membership, created = CourseMembership.objects.get_or_create(
                        course=course,
                        user=student,
                        defaults={'role': 'student', 'group_name': group.name}
                    )
                    if created:
                        added_count += 1
                    else:
                        if not (membership.group_name or "").strip():
                            membership.group_name = group.name
                            membership.save(update_fields=["group_name"])
            
            return JsonResponse({
                'success': True,
                'message': f'{added_count} tələbə kursa əlavə olundu.',
                'added_count': added_count
            })
            
        except ImportError:
            return JsonResponse({'success': False, 'error': 'StudentGroup modeli tapılmadı.'}, status=500)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Üzv Silmə (AJAX)
# ════════════════════════════════════════════════════════════════════════════

class DeleteMemberView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Tələbə və ya köməkçi silmə."""
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        return JsonResponse({'success': False, 'error': 'Bu əməliyyata icazəniz yoxdur.'}, status=403)
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        member_id = kwargs.get('member_id')
        
        course = get_object_or_404(Course, id=course_id)
        membership = get_object_or_404(CourseMembership, id=member_id, course=course)
        
        username = membership.user.username
        membership.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f'{username} silindi.'})
        
        messages.success(request, f'✅ {username} silindi.')
        return redirect('courses:course_members', course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Silmə (Toplu)
# ════════════════════════════════════════════════════════════════════════════

class DeleteGroupFromCourseView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Kursdan müəyyən bir qrup adını daşıyan bütün tələbələri silir."""
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
        
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        group_name = request.POST.get('group_name') 
        
        if not group_name:
            messages.error(request, "Qrup adı tapılmadı.")
            return redirect('courses:course_members', course_id=course_id)

        course = get_object_or_404(Course, id=course_id)
        
        deleted_count, _ = CourseMembership.objects.filter(
            course=course, 
            group_name=group_name
        ).delete()
        
        messages.success(request, f'✅ "{group_name}" qrupundan {deleted_count} tələbə kursdan çıxarıldı.')
        return redirect('courses:course_members', course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Kurs Redaksiya Etmə
# ════════════════════════════════════════════════════════════════════════════

class EditCourseView(IsCourseOwnerMixin, UpdateView):
    """Kurs məlumatını redaktə etmə."""
    
    model = Course
    form_class = CourseForm
    template_name = 'courses/edit_course.html'
    context_object_name = 'course'
    pk_url_kwarg = 'course_id'
    
    def form_valid(self, form):
        messages.success(self.request, f'✅ "{form.instance.title}" kursu yeniləndi.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('courses:course_dashboard', args=[self.object.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Kurs Silmə
# ════════════════════════════════════════════════════════════════════════════

class DeleteCourseView(IsCourseOwnerMixin, View):
    """Kursun tam silinməsi."""
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        if course.owner != request.user:
            messages.error(request, 'Bu kursu silməyə icazəniz yoxdur.')
            return redirect('home')
        
        course_title = course.title
        course.delete()
        
        messages.success(request, f'✅ "{course_title}" kursu və bütün məlumatları silindi.')
        return redirect('profile', username=request.user.username)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Mənim Kurslarım
# ════════════════════════════════════════════════════════════════════════════

class MyCoursesListView(LoginRequiredMixin, ListView):
    template_name = "courses/my_courses.html"
    context_object_name = "courses"
    paginate_by = 12

    def get_queryset(self):
        return Course.objects.filter(owner=self.request.user).order_by("-created_at")