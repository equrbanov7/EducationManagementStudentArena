from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('technology/', views.technology, name='technology'),
    path('subscribe/', views.subscribe_page, name='subscribe'),
    path('contact/', views.contact, name='contact'),
    path('posts/<int:post_id>/', views.post_detail, name='post_detail'),
    path('posts/create/', views.create_post, name='create_post'),
    path('posts/<int:post_id>/edit/', views.edit_post, name='edit_post')
]