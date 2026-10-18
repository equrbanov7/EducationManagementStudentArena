"""Sənəd yoxlaması URL-ləri — kökdə (``config/urls.py``: ``path("", include(...))``).

* ``/yoxla/`` və ``/yoxla/<kod>/`` — PUBLİK (girişsiz; şəbəkə zonası kənardan açıq saxlayır);
* ``/sened-yoxlamasi/`` — əməkdaş siyahısı (``document_seal.manage``); QƏSDƏN ``/yoxla/`` altında deyil ki,
  publik prefiksin zona istisnası inzibati səhifəyə şamil olunmasın.
"""

from django.urls import path

from . import views_public, views_staff

app_name = "verification"

urlpatterns = [
    path("yoxla/", views_public.verify_home, name="home"),
    path("yoxla/<str:code>/", views_public.verify_detail, name="detail"),
    path("sened-yoxlamasi/", views_staff.seal_list, name="staff_list"),
    path("sened-yoxlamasi/<uuid:pk>/legv/", views_staff.seal_revoke, name="staff_revoke"),
]
