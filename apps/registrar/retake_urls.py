"""25% / alt qrup müraciəti URL-ləri — ``/tekrar-imtahan/`` (``config/urls.py``, namespace ``retake``).

``/jurnal/`` altında DEYİL: şəbəkə zonası ``/jurnal/``-u kənardan bağlayır, tələbə isə evdən müraciət edir.
"""

from django.urls import path

from . import retake_views

app_name = "retake"

urlpatterns = [
    path("muraciet/", retake_views.apply, name="apply"),
    path("<uuid:application_id>/qebz/", retake_views.upload_receipt, name="receipt"),
    path("<uuid:application_id>/geri-gotur/", retake_views.withdraw, name="withdraw"),
    path("<uuid:application_id>/odenis/", retake_views.payment, name="payment"),
    path("<uuid:application_id>/qerar/", retake_views.decision, name="decision"),
    path("<uuid:application_id>/netice/", retake_views.result, name="result"),
    path("iz/<int:student_id>/", retake_views.trail, name="trail"),
    path("<uuid:application_id>/alt-qrup-jurnallari/", retake_views.subgroup_offerings, name="subgroup_offerings"),
]
