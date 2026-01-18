"""
courses/urls.py
───────────────
Kurs modulu üçün URL routları.

Nə üçün:
- /courses/create/ → Kurs yaratma
- /courses/<id>/dashboard/ → Kurs dashboard (accordion)
- /courses/<id>/topic/add/ → Mövzu əlavə et (modal)
- /courses/<id>/resource/add/ → Resurs əlavə et (modal)
- ... və s.

Namespace: courses:
- reverse('courses:create_course') → /courses/create/
- reverse('courses:course_dashboard', args=[1]) → /courses/1/dashboard/
"""

from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    # ════════════════════════════════════════════════════════════════════════
    # Kurs Yaratma & Görüntüləmə
    # ════════════════════════════════════════════════════════════════════════
    
    # GET /courses/create/ → Kurs yaratma forması
    # POST /courses/create/ → Kurs yaradılır → Redirect dashboard-a
    path(
        'create_course/',
        views.CreateCourseView.as_view(),
        name='create_course'
    ),
    path("my-courses/", views.MyCoursesListView.as_view(), name="my_courses"),
    
    # GET /courses/<id>/dashboard/ → Kurs profil səhifəsi (accordion)
    path(
        '<int:course_id>/dashboard/',
        views.CourseDashboardView.as_view(),
        name='course_dashboard'
    ),
    
    # GET /courses/<id>/edit/ → Kurs redaksiya
    path(
        '<int:course_id>/edit/',
        views.EditCourseView.as_view(),
        name='edit_course'
    ),
    
    # POST /courses/<id>/delete/ → Kurs sil
    path(
        '<int:course_id>/delete/',
        views.DeleteCourseView.as_view(),
        name='delete_course'
    ),
    
    # ════════════════════════════════════════════════════════════════════════
    # Mövzular (Topics)
    # ════════════════════════════════════════════════════════════════════════
    
    # POST /courses/<id>/topic/add/ (AJAX/Modal)
    # Mövzu əlavə etmə
    path(
        '<int:course_id>/topic/add/',
        views.AddTopicView.as_view(),
        name='add_topic'
    ),
    
    # POST /courses/<id>/topic/<topic_id>/delete/ (AJAX)
    # Mövzu silmə
    path(
        '<int:course_id>/topic/<int:topic_id>/delete/',
        views.DeleteTopicView.as_view(),
        name='delete_topic'
    ),
    
    # ════════════════════════════════════════════════════════════════════════
    # Resurslar (Resources)
    # ════════════════════════════════════════════════════════════════════════
    
    # POST /courses/<id>/resource/add/ (AJAX/Modal)
    # Resurs əlavə et
    path(
        '<int:course_id>/resource/add/',
        views.AddResourceView.as_view(),
        name='add_resource'
    ),
    
    # POST /courses/<id>/resource/<resource_id>/delete/ (AJAX)
    # Resurs sil
    path(
        '<int:course_id>/resource/<int:resource_id>/delete/',
        views.DeleteResourceView.as_view(),
        name='delete_resource'
    ),
    
    # ════════════════════════════════════════════════════════════════════════
    # Üzvlük & Qruplar (Membership & Groups)
    # ════════════════════════════════════════════════════════════════════════
    
  # Kurs üzvləri
    path('<int:course_id>/members/', 
         views.CourseMembersView.as_view(), 
         name='course_members'),
    
    path("<int:course_id>/available-students/",
         views.AvailableStudentsView.as_view(), 
         name="available_students"),

    # Tələbə əlavə et (AJAX)
    path('<int:course_id>/members/add/', 
         views.AddMemberView.as_view(), 
         name='add_member'),
    
    # Qrup əlavə et (Bulk)
    path('<int:course_id>/members/add-bulk/', 
         views.AddMembersBulkView.as_view(), 
         name='add_members_bulk'),
    
    # Üzv sil
    path('<int:course_id>/members/<int:member_id>/delete/', 
         views.DeleteMemberView.as_view(), 
         name='delete_member'),  
    path('<int:course_id>/members/delete-group/', 
         views.DeleteGroupFromCourseView.as_view(), 
         name='delete_group_from_course'),
]