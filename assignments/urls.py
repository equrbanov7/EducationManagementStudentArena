from django.urls import path
from . import views

app_name = 'assignments'

urlpatterns = [
    # Assignment CRUD
    path('create/<int:course_id>/', views.create_assignment, name='create_assignment'),
    path('<int:pk>/edit/', views.edit_assignment, name='edit_assignment'),
    path('<int:pk>/delete/', views.delete_assignment, name='delete_assignment'),
    path('<int:pk>/detail/', views.assignment_detail, name='assignment_detail'),
    
    # Submissions
    path('<int:pk>/submit/', views.submit_assignment, name='submit_assignment'),
    path('<int:pk>/submissions/', views.review_submissions, name='review_assignment_submissions'),
    path('submission/<int:pk>/grade/', views.grade_submission, name='grade_submission'),
    
    # AJAX endpoints
    path('search-students/', views.search_students, name='search_students'),
    path('search-groups/', views.search_groups, name='search_groups'),
]