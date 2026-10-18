"""«Alt qrupa tələbə əlavə et» URL-ləri — ``accounts`` ad sahəsinə ``include`` olunur (``accounts:subgroup_placement_*``)."""

from django.urls import path

from . import actions, api

urlpatterns = [
    path("students/", api.placement_students, name="subgroup_placement_students"),
    path("student/<int:student_id>/", api.placement_student, name="subgroup_placement_student"),
    path("subjects/", api.placement_subjects, name="subgroup_placement_subjects"),
    path("offerings/", api.placement_offerings, name="subgroup_placement_offerings"),
    path("preview/", api.placement_preview, name="subgroup_placement_preview"),
    path("recent/", api.placement_recent, name="subgroup_placement_recent"),
    path("place/", actions.placement_place, name="subgroup_placement_place"),
    path("undo/", actions.placement_undo, name="subgroup_placement_undo"),
]
