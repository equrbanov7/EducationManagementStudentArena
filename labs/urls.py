from django.urls import path
from . import views

app_name = 'labs'

urlpatterns = [
    # Lab CRUD
    path('create/<int:course_id>/', views.create_lab, name='create_lab'),
    path('<int:pk>/edit/', views.edit_lab, name='edit_lab'),
    path('<int:pk>/delete/', views.delete_lab, name='delete_lab'),
    path('<int:pk>/publish/', views.publish_lab, name='publish_lab'),
    
    # Block CRUD
    path('<int:lab_id>/blocks/', views.manage_blocks, name='manage_blocks'),
    path('<int:lab_id>/blocks/create/', views.create_block, name='create_block'),
    path('blocks/<int:pk>/edit/', views.edit_block, name='edit_block'),
    path('blocks/<int:pk>/delete/', views.delete_block, name='delete_block'),
    
    # Question CRUD
    path('blocks/<int:block_id>/questions/create/', views.create_question, name='create_question'),
    path('questions/<int:pk>/edit/', views.edit_question, name='edit_question'),
    path('questions/<int:pk>/delete/', views.delete_question, name='delete_question'),
    path('blocks/<int:block_id>/questions/import/', views.import_questions, name='import_questions'),
    
    # Submissions & Grading
    path('<int:pk>/submissions/', views.lab_submissions, name='lab_submissions'),
    path('submissions/<int:pk>/grade/', views.grade_submission, name='grade_submission'),
    
    # Preview
    path('<int:pk>/preview/', views.preview_randomization, name='preview_randomization'),
    
    # Student
    path('<int:pk>/', views.lab_detail, name='lab_detail'),
    path('<int:pk>/submit/', views.submit_lab, name='submit_lab'),
    
    # API
    path('api/groups/<int:course_id>/', views.api_get_groups, name='api_get_groups'),
    path('api/students/<int:course_id>/', views.api_get_students, name='api_get_students'),
]