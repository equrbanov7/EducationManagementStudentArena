# from django.urls import path
# from . import views

# urlpatterns = [
#     path('', views.home, name='home'),
#     path('about/', views.about, name='about'),
#     path('technology/', views.technology, name='technology'),
#     path('subscribe/', views.subscribe_page, name='subscribe'),
#     path('contact/', views.contact, name='contact'),
#     path('posts/<int:post_id>/', views.post_detail, name='post_detail'),
#     path('posts/create/', views.create_post, name='create_post'),
#     path('posts/<int:post_id>/edit/', views.edit_post, name='edit_post')
# ]

from django.urls import path
from django.contrib.auth import views as auth_views  # 👈 auth view-lər üçün
from . import views

urlpatterns = [
    # Ana səhifə və mövcud səhifələr
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('technology/', views.technology, name='technology'),
    path('subscribe/', views.subscribe_page, name='subscribe'),
    path('contact/', views.contact, name='contact'),

    # --- Auth (istifadəçi qeydiyyatı və giriş) ---
    path('register/', views.register_view, name='register'),
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='blog/login.html'),
        name='login'
    ),
  path('logout/', views.logout_view, name='logout'),

    
    

    # --- User profil səhifəsi ---
    # Məs: /blog/users/elvin/
    path('users/<str:username>/', views.user_profile, name='user_profile'),

    # --- Postlarla bağlı URL-lər ---
    path('posts/<int:post_id>/', views.post_detail, name='post_detail'),
    path('posts/create/', views.create_post, name='create_post'),
    path('posts/<int:post_id>/edit/', views.edit_post, name='edit_post'),
]
