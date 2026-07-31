"""Rəy görünürlüyü (identity reveal) konfiqurasiyası.

Sırf sabitlərdir — `models.py`-dan çıxarıldı ki, modul-ölçü budcəsi
daxilində qalsın. `models` geriyə-uyğunluq üçün re-export edir
(mövcud `from apps.organizations.models import REVIEW_VISIBILITY_FEATURES`
çağırışları dəyişmir).
"""

REVIEW_VISIBILITY_SETTINGS_KEY = "review_visibility"
WRITTEN_EXAM_IDENTITY_REVEAL_SETTINGS_KEY = "written_exam_identity_reveal_enabled"
ASSIGNMENT_IDENTITY_REVEAL_SETTINGS_KEY = "assignment_identity_reveal_enabled"
PROJECT_IDENTITY_REVEAL_SETTINGS_KEY = "project_identity_reveal_enabled"
LAB_IDENTITY_REVEAL_SETTINGS_KEY = "lab_identity_reveal_enabled"
REVIEW_VISIBILITY_FEATURES = {
    "written_exam": {
        "setting_key": WRITTEN_EXAM_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Yazılı imtahanda müəllimə tələbə adını göstər",
        "short_label": "Yazılı imtahan",
    },
    "assignment": {
        "setting_key": ASSIGNMENT_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Sərbəst işdə müəllimə tələbə adını göstər",
        "short_label": "Sərbəst iş",
    },
    "project": {
        "setting_key": PROJECT_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Kurs işində müəllimə tələbə adını göstər",
        "short_label": "Kurs işi",
    },
    "lab": {
        "setting_key": LAB_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Lab işində müəllimə tələbə adını göstər",
        "short_label": "Lab işi",
    },
}
