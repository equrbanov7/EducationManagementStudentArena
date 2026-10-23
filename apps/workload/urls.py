"""Dərs yükü JSON endpoint-ləri — ``/ders-yuku/…`` (namespace: ``workload``).

Bunlar SƏHİFƏ deyil: ekranlar profil bölməsi kimi açılır (sol sidebar qalır),
bu URL-lər yalnız bölmənin data/yazma səthidir.
"""

from django.urls import path

from . import views
from .actions import workload_action
from .load_actions import load_template

app_name = "workload"

urlpatterns = [
    # Oxu
    path("setirler/", views.rows, name="rows"),
    # WP9a (2026-10-10): `kafedralar/` silindi — kafedra siyahısı bölmə konteksti ilə gəlir (public.py).
    path("muellimler/", views.teachers, name="teachers"),
    path("secimler/", views.options, name="options"),
    path("tedris-plani/", views.curriculum, name="curriculum"),
    # Yazma
    path("tapsiriq/", views.task, name="task"),
    path("setir/yadda-saxla/", views.row_save, name="row_save"),
    path("setir/sil/", views.row_delete, name="row_delete"),
    path("bolgu/", views.assign, name="assign"),
    path("bolgu/sil/", views.unassign_view, name="unassign"),
    path("bolgu/tesdiq/", views.confirm, name="confirm"),
    path("duzelis/", views.amend, name="amend"),
    # Mərhələ 4 — zəncirin bütün mutasiyaları (tək endpoint)
    path("emel/", workload_action, name="action"),
    # Sahib 2026-10-23: Tədris şöbəsinin «Dərs yükü faylı» Excel şablonu
    path("yuk-sablonu/", load_template, name="load_template"),
    # Müəllim səthi
    path("mene/setirler/", views.my_rows, name="my_rows"),
    path("mene/ixrac/", views.my_export, name="my_export"),
]
