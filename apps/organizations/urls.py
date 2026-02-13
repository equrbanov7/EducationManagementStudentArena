"""
URL configuration for organizations app.
"""

from django.urls import path

from . import views

app_name = "organizations"

urlpatterns = [
    path("select/", views.select_organization, name="select"),
    path("switch/<slug:slug>/", views.switch_organization, name="switch"),
    # Placeholder URLs - to be implemented in Sprint 6
    # path('', views.organization_list, name='list'),
    # path('<slug:slug>/', views.organization_detail, name='detail'),
]
