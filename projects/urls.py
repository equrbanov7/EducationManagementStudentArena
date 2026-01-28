from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    # CRUD
    path('create/<int:course_id>/', views.create_project, name='create_project'),
    path('<int:pk>/edit/', views.edit_project, name='edit_project'),
    path('<int:pk>/delete/', views.delete_project, name='delete_project'),
    path('<int:pk>/detail/', views.project_detail, name='project_detail'),
    
    # Submissions
    path('<int:pk>/submit/', views.submit_project, name='submit_project'),
    path('<int:pk>/submissions/', views.review_submissions, name='review_project_submissions'),
    path('submission/<int:pk>/grade/', views.grade_submission, name='grade_submission'),
    
    # API
    path('api/groups/', views.api_get_groups, name='api_get_groups'),
    path('api/students/', views.api_get_students, name='api_get_students'),
]