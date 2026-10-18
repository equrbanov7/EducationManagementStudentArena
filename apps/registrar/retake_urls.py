"""25% / alt qrup müraciəti URL-ləri — ``/tekrar-imtahan/`` (``config/urls.py``, namespace ``retake``).

``/jurnal/`` altında DEYİL: şəbəkə zonası ``/jurnal/``-u kənardan bağlayır, tələbə isə evdən müraciət edir.
"""

from django.urls import path

from . import retake_admin_views, retake_views

app_name = "retake"

urlpatterns = [
    path("muraciet/", retake_views.apply, name="apply"),
    path("<uuid:application_id>/qebz/", retake_views.upload_receipt, name="receipt"),
    path("<uuid:application_id>/geri-gotur/", retake_views.withdraw, name="withdraw"),
    path("<uuid:application_id>/odenis/", retake_views.payment, name="payment"),
    path("<uuid:application_id>/qerar/", retake_views.decision, name="decision"),
    path("<uuid:application_id>/netice/", retake_views.result, name="result"),
    # 2026-10-19 (sahib): ödənişin qaytarılması — qərar (Tədris şöbəsi / RİM) və icra qeydi (Mühasibatlıq).
    path("<uuid:application_id>/qaytarma/", retake_views.refund, name="refund"),
    path("iz/<int:student_id>/", retake_views.trail, name="trail"),
    # 2026-10-19 (sahib): pəncərəni İmtahan mərkəzi açır; təhsil haqqı cədvəlini Mühasibatlıq saxlayır.
    path("pencere/ac/", retake_admin_views.window_open, name="window_open"),
    path("pencere/<uuid:window_id>/bagla/", retake_admin_views.window_close, name="window_close"),
    path("tehsil-haqqi/", retake_admin_views.tuition_save, name="tuition_save"),
    path("tehsil-haqqi/<uuid:tuition_id>/sil/", retake_admin_views.tuition_delete, name="tuition_delete"),
    path("<uuid:application_id>/alt-qrup-jurnallari/", retake_views.subgroup_offerings, name="subgroup_offerings"),
]
