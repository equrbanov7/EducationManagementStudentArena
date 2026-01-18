"""
courses/views.py
────────────────
Kurs modulu üçün view-lər.

Nə üçün:
- Kurs yaratma (CreateCourseView)
- Kurs dashboard (accordion göstərmə)
- Mövzu əlavə/sil
- Resurs əlavə/sil
- Üzv əlavə/sil

View Tipləri:
- Class-based views (CBV) - Django best practice
- Mixins (LoginRequiredMixin) - Authentikasiya
- get_object_or_404() - Səhv handling
- redirect(), render() - Response

CRUD Əməliyyatlar:
- CREATE: POST, form validation, save(), redirect
- READ: GET, template render
- UPDATE: GET + POST, instance update
- DELETE: POST, delete(), redirect
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, DetailView, UpdateView, View, ListView
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q

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
from django.db import models
from django.db.models import Max
from django.contrib.auth import get_user_model

User = get_user_model()

# ════════════════════════════════════════════════════════════════════════════
# Mixin: Müəllim İcazə Yoxlaması
# ════════════════════════════════════════════════════════════════════════════

class IsTeacherMixin(UserPassesTestMixin):
    """
    Yalnız müəllim (is_teacher) bu view-a girə bilər.
    
    Nə edər:
    - request.user.is_teacher yoxlayır
    - Yoxdursa: 403 Forbidden
    
    Istifadə:
    class CreateCourseView(IsTeacherMixin, CreateView):
        ...
    """
    
    def test_func(self):
        """Müəllim mı?"""
        return getattr(self.request.user, 'is_teacher', False)
    
    def handle_no_permission(self):
        """İcazə yoxdursa nə eləsin."""
        messages.error(self.request, 'Bu əməliyyat yalnız müəllimlər üçün mümkündür.')
        return redirect('home')


class IsCourseOwnerMixin(UserPassesTestMixin):
    """
    Yalnız kursun sahibi (owner) redaktə edə bilər.
    
    Nə edər:
    - course.owner == request.user yoxlayır
    - Yoxdursa: 403 Forbidden
    """
    
    def test_func(self):
        """Kurs sahibimi?"""
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        """Səhifə sahibi deyilsə."""
        messages.error(self.request, 'Bu kursu redaktə etməyə icazəniz yoxdur.')
        return redirect('home')


# ════════════════════════════════════════════════════════════════════════════
# VIEW 1: Kurs Yaratma
# ════════════════════════════════════════════════════════════════════════════

class CreateCourseView(IsTeacherMixin, CreateView):
    """
    Kurs yaratma view-u.
    
    Flow:
    1. GET /courses/create/ → Form göstər
    2. POST /courses/create/ → Form submit
    3. Django model.save() çalışır
    4. Redirect → course_dashboard
    
    Misal:
    - Teacher "Yeni Kurs Yarat" düyməsinə klik edir
    - Form açılır (title, description, cover_image, status)
    - Submit edir
    - Kurs yaradılır, dashboard-a atılır
    """
    
    model = Course
    form_class = CourseForm
    template_name = 'courses/create_course.html'
    
    def form_valid(self, form):
        """Form validdi, kurs yaradıl."""
        # owner otomatik request.user olur
        form.instance.owner = self.request.user
        # status draft olur (default)
        form.instance.status = 'draft'
        
        # Save-dən əvvəl save etmə (commit=False)
        # Tələsmədən əvvəl əlavə məlumat əlavə edə bilərik
        response = super().form_valid(form)
        
        messages.success(
            self.request,
            f'✅ "{form.instance.title}" kursu uğurla yaradıldı!'
        )
        
        return response
    
    def get_success_url(self):
        """Uğur halında hara redirect et?"""
        # Yeni yaradılan kursun dashboard-ına
        return reverse_lazy('courses:course_dashboard', args=[self.object.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW 2: Kurs Dashboard (Accordion)
# ════════════════════════════════════════════════════════════════════════════

class CourseDashboardView(LoginRequiredMixin, DetailView):
    """
    Kurs dashboard səhifəsi (Accordion).
    
    FIX: Context-ə all_users və all_groups əlavə olunub
    (Modal-lar üçün lazımdır)
    """
    
    model = Course
    template_name = 'courses/course_dashboard.html'
    context_object_name = 'course'
    pk_url_kwarg = 'course_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_object()
        
        # Accordion məlumatları
        context['topics'] = course.topics.all().order_by('order')
        context['resources'] = course.resources.all().order_by('-created_at')
        context['members'] = course.memberships.all().order_by('joined_at')
        
        # Formalar (modal-lar üçün)
        context['topic_form'] = CourseTopicForm()
        context['resource_form'] = CourseResourceForm()
        
        # Owner check
        context['is_owner'] = course.owner == self.request.user
        
        # ← FIX: Modal-lar üçün lazımlı məlumatlar
        if context['is_owner']:
            # Kursa hələ əlavə olmamış tələbələr
            course_user_ids = course.memberships.values_list('user_id', flat=True)
            context['all_users'] = (
                User.objects
                .exclude(id__in=course_user_ids)
                .filter(groups__name='student')   # ✅ Yalnız tələbələr (Group ilə)
                .distinct()
                .order_by('username')
)

            
            # Bütün tələbə qrupları (StudentGroup)
        try:
            from blog.models import StudentGroup
            context['all_groups'] = StudentGroup.objects.all().order_by('name')

            # Əgər qruplar müəllimə görə bağlıdırsa, bunu istifadə et:
            # context['all_groups'] = StudentGroup.objects.filter(teacher=self.request.user).order_by('name')

        except ImportError:
            context['all_groups'] = []

        
        return context


# ════════════════════════════════════════════════════════════════════════════
# VIEW 3: Mövzu Əlavə Etmə (AJAX/Modal)
# ════════════════════════════════════════════════════════════════════════════

class AddTopicView(IsCourseOwnerMixin, CreateView):
    """
    Mövzu əlavə etmə (AJAX POST).
    
    Flow:
    1. POST /courses/<id>/topic/add/ (AJAX)
    2. Form validasiyası
    3. Mövzu yaradılır
    4. JSON response (success/error)
    5. JavaScript modal bağlayır, siyahıyı refresh edir
    
    Misal JSON Response:
    {
        "success": true,
        "message": "Mövzu əlavə olundu",
        "topic": {
            "id": 1,
            "title": "Həftə 1",
            "order": 1
        }
    }
    """
    
    model = CourseTopic
    form_class = CourseTopicForm
    
    def dispatch(self, request, *args, **kwargs):
        """View-a gelmədən əvvəl yoxla."""
        self.course = get_object_or_404(Course, id=kwargs['course_id'])
        
        # Kursun sahibi mü?
        if self.course.owner != request.user:
            return HttpResponseForbidden("Bu kursu redaktə etməyə icazəniz yoxdur.")
        
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        """Mövzu yaradıl."""
        form.instance.course = self.course
        
        # Order avtomatik hesablanır
        # max_order = CourseTopic.objects.filter(
        #     course=self.course
        # ).aggregate(models.Max('order'))['order__max'] or 0
        
        max_order = CourseTopic.objects.filter(
            course=self.course).aggregate(Max('order'))['order__max'] or 0

        
        form.instance.order = max_order + 1
        
        response = super().form_valid(form)
        
        # Əgər AJAX idi, JSON return et
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
        
        # Normal POST (form)
        messages.success(
            self.request,
            f'"{form.instance.title}" mövzusu əlavə olundu'
        )
        return response
    
    def form_invalid(self, form):
        """Form validasiyası uğursuzdu."""
        # AJAX error
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'errors': form.errors,
            }, status=400)
        
        # Normal error
        messages.error(self.request, 'Mövzu əlavə olunarkən xəta baş verdi.')
        return redirect('courses:course_dashboard', course_id=self.course.id)
    
    def get_success_url(self):
        """Uğur halında hara atıl?"""
        return reverse_lazy('courses:course_dashboard', args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW 4: Mövzu Silmə (AJAX)
# ════════════════════════════════════════════════════════════════════════════

class DeleteTopicView(IsCourseOwnerMixin, View):
    """
    Mövzu silmə (POST).
    
    Flow:
    1. POST /courses/<id>/topic/<topic_id>/delete/
    2. Mövzu silinir
    3. Redirect dashboard-a
    
    Misal:
    - User accordion-dan mövzünün [Sil] düyməsinə klik edir
    - POST request
    - Mövzu silinir
    - Toast message: "Mövzu silindi"
    - Sayfa refresh olur
    """
    
    def post(self, request, *args, **kwargs):
        """POST: Mövzu sil."""
        course_id = kwargs.get('course_id')
        topic_id = kwargs.get('topic_id')
        
        course = get_object_or_404(Course, id=course_id)
        topic = get_object_or_404(CourseTopic, id=topic_id, course=course)
        
        # Owner mi?
        if course.owner != request.user:
            messages.error(request, 'Bu əməliyyata icazəniz yoxdur.')
            return redirect('courses:course_dashboard', course_id=course_id)
        
        topic_title = topic.title
        topic.delete()
        
        messages.success(request, f'✅ "{topic_title}" mövzusu silindi.')
        
        # AJAX idi?
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        return redirect('courses:course_dashboard', course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW 5: Resurs Əlavə Etmə
# ════════════════════════════════════════════════════════════════════════════

class AddResourceView(IsCourseOwnerMixin, CreateView):
    """
    Resurs əlavə etmə (AJAX/Modal).
    
    AddTopicView-ə bənzərdir.
    """
    
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

"""
courses/views.py – AddMemberView FIX

MƏSƏLƏ: Modal açıldıqda bütün users listini göstərmir.

HƏLL: Context-ə bütün mövcud users əlavə et (Form-dan gelen users, 
      group memberships-lər dəhil)
"""

# ════════════════════════════════════════════════════════════════════════════
# VIEW 7: Kurs Üzvləri (Members) - DÜZƏLDİLDİ
# ════════════════════════════════════════════════════════════════════════════

class CourseMembersView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Kurs üzvlüyü səhifəsi.
    FIX: UnboundLocalError həll edildi.
    FIX: StudentGroup modeli düzgün import edildi.
    """
    
    def test_func(self):
        """Yalnız kurs sahibi girə bilər."""
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        messages.error(self.request, 'Bu səhifəyə giriş icazəniz yoxdur.')
        return redirect('home')
    
    def get(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        # 1. Mövcud üzvləri alırıq
        members = course.memberships.all().order_by('joined_at')
        
        # Rollara görə bölürük
        teacher = members.filter(role='teacher').first()
        assistants = members.filter(role='assistant')
        students = members.filter(role='student').order_by('group_name', 'user__username')
        
        # 2. Modal üçün: Kursda OLMAYAN tələbələri tapırıq
        course_user_ids = course.memberships.values_list('user_id', flat=True)
        
        # Burada 'student' qrupuna aid userləri tapırıq (Sənin sisteminə uyğun)
        # Əgər səndə User modelinde is_student fieldi varsa, filter(is_student=True) yaz.
        # İndiki halda qrup adı 'student' olanları axtarır:
        all_users_qs = User.objects.exclude(id__in=course_user_ids)
        
        # Əgər userlərin 'student' qrupu varsa:
        if hasattr(User, 'groups'): 
             all_users = all_users_qs.filter(groups__name='student').distinct().order_by('username')
        else:
             # Sadəcə bütün userləri gətir (ehtiyat variant)
             all_users = all_users_qs.order_by('username')

        
        # 3. Modal üçün: Bütün QRUPLARI tapırıq (StudentGroup)
        # QEYD: 'accounts' və ya qruplar hansı app-dadırsa, oradan import etməlisən.
        # Mən ehtimal edirəm ki, 'accounts' app-ındadır.
        try:
            # Sənin göndərdiyin koda əsasən model adı 'StudentGroup'-dur
            from blog.models import StudentGroup 
            all_groups = StudentGroup.objects.all().order_by('name')
            #all_groups = StudentGroup.objects.filter(teacher=request.user).prefetch_related("students")

        except ImportError:
            # Əgər model tapılmasa boş list qaytar ki, error verməsin
            print("XƏTA: StudentGroup modeli tapılmadı. Zəhmət olmasa importu yoxlayın.")
            all_groups = []
        
        # 4. Context-i İNDİ yaradırıq (Dəyişənlər hazır olandan sonra)
        context = {
            'course': course,
            'members': members,
            'teacher': teacher,
            'assistants': assistants,
            'students': students,
            'all_users': all_users,   # Modal üçün
            'all_groups': all_groups, # Modal üçün
            'is_owner': course.owner == request.user,
        }
        
        return render(request, 'courses/course_members.html', context)


class AvailableStudentsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Kursda olmayan tələbələri JSON kimi qaytarır (modal açılarkən refresh üçün).
    """

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

        data = []
        for u in qs:
            data.append({
                "id": u.id,
                "username": u.username,
                "full_name": (u.get_full_name() or u.username),
            })

        return JsonResponse({"success": True, "users": data})

# ════════════════════════════════════════════════════════════════════════════
# VIEW: Tələbə Əlavə Et (AJAX) - DÜZƏLDİLDİ
# ════════════════════════════════════════════════════════════════════════════

class AddMemberView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Tələbə əlavə etmə (Modal-dan AJAX).
    FIX: 'user_ids' listini qəbul edir (HTML-də name="user_ids" olduğu üçün).
    """
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
    
    def handle_no_permission(self):
        return JsonResponse({
            'success': False, 
            'error': 'Bu əməliyyata icazəniz yoxdur.'
        }, status=403)
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        # FIX: get() əvəzinə getlist() istifadə edirik
        # HTML-də input name="user_ids" olduğu üçün
        user_ids = request.POST.getlist('user_ids')
        group_name = request.POST.get('group_name', '').strip()
        
        if not user_ids:
            return JsonResponse({
                'success': False,
                'error': 'Heç bir tələbə seçilməyib.'
            }, status=400)
        
        added_count = 0
        
        # Seçilən hər bir user üçün dövr edirik
        for uid in user_ids:
            try:
                user = User.objects.get(id=uid)
                
                # Membership yarat və ya update et
                membership, created = CourseMembership.objects.get_or_create(
                    course=course,
                    user=user,
                    defaults={
                        'role': 'student',
                        'group_name': group_name,
                    }
                )
                
                # Əgər artıq üzvdürsə, qrupunu yenilə
                if not created:
                    membership.group_name = group_name
                    membership.save()
                    
                added_count += 1
                
            except User.DoesNotExist:
                continue
        
        # AJAX Response
        return JsonResponse({
            'success': True,
            'message': f'{added_count} tələbə kursa əlavə olundu.'
        })


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Əlavə Et (Bulk) - DÜZƏLDİLDİ
# ════════════════════════════════════════════════════════════════════════════

class AddMembersBulkView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Qrupları toplu şəkildə kursa əlavə et.
    """
    
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
            # Model adını dəqiqləşdirin (StudentGroup)
            from blog.models import StudentGroup
            
            groups = StudentGroup.objects.filter(id__in=group_ids)
            
            added_count = 0
            
            for group in groups:
                # StudentGroup modelində tələbələr necə adlanır? 
                # Adətən: group.students.all()
                students = group.students.all() 
                
                for student in students:
                    membership, created = CourseMembership.objects.get_or_create(
                        course=course,
                        user=student,
                        defaults={
                            'role': 'student',
                            'group_name': group.name, 
                        }
                    )
                    
                    if created:
                        added_count += 1
                    else:
                        # Artıq üzvdürsə, qrup adını yeniləyək
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
        return JsonResponse({
            'success': False,
            'error': 'Bu əməliyyata icazəniz yoxdur.'
        }, status=403)
    
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        member_id = kwargs.get('member_id')
        
        course = get_object_or_404(Course, id=course_id)
        membership = get_object_or_404(CourseMembership, id=member_id, course=course)
        
        username = membership.user.username
        membership.delete()
        
        # AJAX Response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'{username} silindi.'
            })
        
        messages.success(request, f'✅ {username} silindi.')
        return redirect('courses:course_members', course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Silmə (Toplu) - YENİ
# ════════════════════════════════════════════════════════════════════════════

class DeleteGroupFromCourseView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Kursdan müəyyən bir qrup adını daşıyan bütün tələbələri silir.
    Məsələn: '940' qrupunu siləndə, o qrupdakı hər kəs kursdan çıxır.
    """
    
    def test_func(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user
        
    def post(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        # Formdan və ya URL-dən qrup adını alırıq
        group_name = request.POST.get('group_name') 
        
        if not group_name:
             messages.error(request, "Qrup adı tapılmadı.")
             return redirect('courses:course_members', course_id=course_id)

        course = get_object_or_404(Course, id=course_id)
        
        # Həmin qrup adı olan üzvləri tapıb silirik
        deleted_count, _ = CourseMembership.objects.filter(
            course=course, 
            group_name=group_name
        ).delete()
        
        messages.success(request, f'✅ "{group_name}" qrupundan {deleted_count} tələbə kursdan çıxarıldı.')
        
        return redirect('courses:course_members', course_id=course_id)

# ════════════════════════════════════════════════════════════════════════════
# VIEW 10: Kurs Redaksiya Etmə
# ════════════════════════════════════════════════════════════════════════════

class EditCourseView(IsCourseOwnerMixin, UpdateView):
    """
    Kurs məlumatını redaktə etmə (title, description, cover_image, status).
    """
    
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
    
    
"""
courses/views.py içinə əlavə et:

Delete Course View - Kursun tam silinməsi
"""

class DeleteCourseView(IsCourseOwnerMixin, View):
    """
    Kursun tam silinməsi.
    
    Flow:
    1. POST /courses/<id>/delete/
    2. Kurs silinir (cascade: mövzular, resurslar, üzvlər də silinir)
    3. Müəllimin profil səhifəsinə redirect
    
    Misal:
    - Müəllim accordion-dan [Sil] düyməsinə klik edir
    - Confirmation dialogi açılır
    - Confirm edərsə, kurs + bütün məlumatlar silinir
    """
    
    def post(self, request, *args, **kwargs):
        """POST: Kurs sil"""
        course_id = kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        
        # Owner mı?
        if course.owner != request.user:
            messages.error(request, 'Bu kursu silməyə icazəniz yoxdur.')
            return redirect('home')
        
        # Cascade delete:
        # - CourseTopic (mövzular)
        # - CourseResource (resurslar)
        # - CourseMembership (üzvlər)
        # Hamısı otomatik silinir (on_delete=CASCADE)
        
        course_title = course.title
        course.delete()
        
        messages.success(
            request,
            f'✅ "{course_title}" kursu və bütün məlumatları silindi.'
        )
        
        # Müəllimin profil səhifəsinə
        return redirect('profile', username=request.user.username)



class MyCoursesListView(LoginRequiredMixin, ListView):
    template_name = "courses/my_courses.html"
    context_object_name = "courses"
    paginate_by = 12  # istəsən silə bilərsən

    def get_queryset(self):
        # müəllimin yaratdığı kurslar
        return Course.objects.filter(owner=self.request.user).order_by("-created_at")
