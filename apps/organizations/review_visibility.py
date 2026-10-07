"""Rəy görünürlüyü (identity reveal) konfiqurasiyası.

Sabitlər `models.py`-dan çıxarıldı ki, modul-ölçü budcəsi daxilində qalsın.
`models` geriyə-uyğunluq üçün re-export edir (mövcud
`from apps.organizations.models import REVIEW_VISIBILITY_FEATURES` çağırışları
dəyişmir). Qalıcı yazı :func:`save_review_identity_reveal` ilə — atomik, yalnız
``review_visibility`` açarının bir alt-açarına toxunur.
"""

from .settings_store import update_settings_key

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


def save_review_identity_reveal(organization, feature_name: str, enabled: bool) -> dict:
    """Anonimlik bayrağını kilid altında TƏZƏ dəyər üzərində yazır (digər açarlar/bayraqlar qalır)."""
    feature_config = REVIEW_VISIBILITY_FEATURES.get(feature_name)
    if feature_config is None:
        raise ValueError(f"Unsupported review visibility feature: {feature_name}")

    def _mutate(current):
        review_settings = dict(current) if isinstance(current, dict) else {}
        review_settings[feature_config["setting_key"]] = bool(enabled)
        return review_settings

    return update_settings_key(organization, REVIEW_VISIBILITY_SETTINGS_KEY, _mutate)
