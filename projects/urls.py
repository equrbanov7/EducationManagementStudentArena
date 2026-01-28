from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    # ═══════════════════════════════════════════════════════════════════════
    # CRUD
    # ═══════════════════════════════════════════════════════════════════════
    path('create/<int:course_id>/', views.create_project, name='create_project'),
    path('<int:pk>/edit/', views.edit_project, name='edit_project'),
    path('<int:pk>/delete/', views.delete_project, name='delete_project'),
    
    # ═══════════════════════════════════════════════════════════════════════
    # TƏLƏBƏ
    # ═══════════════════════════════════════════════════════════════════════
    path('<int:pk>/', views.project_detail, name='project_detail'),
    path('<int:pk>/submit/', views.submit_project, name='submit_project'),
    path('<int:pk>/my-submissions/', views.my_submissions, name='my_submissions'),
    
    # ═══════════════════════════════════════════════════════════════════════
    # MÜƏLLİM
    # ═══════════════════════════════════════════════════════════════════════
    path('<int:pk>/submissions/', views.review_submissions, name='review_project_submissions'),
    path('submission/<int:pk>/grade/', views.grade_submission, name='grade_submission'),
    
    # ═══════════════════════════════════════════════════════════════════════
    # API
    # ═══════════════════════════════════════════════════════════════════════
    path('api/groups/', views.api_get_groups, name='api_get_groups'),
    path('api/students/', views.api_get_students, name='api_get_students'),
]