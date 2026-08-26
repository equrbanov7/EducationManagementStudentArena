"""Kabinet modul görünürlüyü (U16) — superadmin aç/bağla paneli.

Superadmin hər təşkilat üçün kabinet modullarını (sidebar bölmə qrupları)
aktivləşdirib-söndürə bilir. Vəziyyət ``Organization.settings`` JSON-unda
``module_visibility`` açarı altında saxlanır (review-visibility pattern-i ilə
eyni). Söndürülmüş modulun bölmələri rbac-da ``allowed_sections``-dan çıxarılır
— sidebar linki, səhifə renderi və AJAX fragment-i eyni anda bağlanır.
Superadmin HƏMİŞƏ hər şeyi görür (panel əks halda özünü kilidləyə bilərdi).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

MODULE_VISIBILITY_SETTINGS_KEY = "module_visibility"

# label — panel etiketi; sections — modul bağlıykən gizlənən profil bölmələri;
# default — heç bir tənzimləmə yoxdursa ilkin vəziyyət.
CABINET_MODULES: dict[str, dict] = {
    "posts": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Postlar (bloq)"),
        "sections": ("posts", "create-post", "pending-post-approvals"),
        "default": False,  # U16: postlar susmaya görə yalnız superadmin-ə görünür
    },
    "statistics": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Statistika"),
        "sections": ("statistics",),
        "default": True,
    },
    "subjects": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Fənlərim (tələbə)"),
        "sections": ("my-subjects",),
        "default": True,
    },
    "transcript": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Transkript"),
        "sections": ("my-transcript",),
        "default": True,
    },
    "schedule": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Dərs cədvəli"),
        "sections": ("my-schedule",),
        "default": True,
    },
    "calendar": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Akademik təqvim"),
        "sections": ("academic-calendar",),
        "default": True,
    },
    "journal": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Elektron jurnal"),
        "sections": ("my-journal",),
        "default": True,
    },
    # Köhnə "approvals" (qiymət təsdiqləri) modulu ləğv edildi — təsdiq zənciri
    # yoxdur. Yerini RİM-in semestr-sonu jurnal bağlaması tutur.
    "journal_close": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Jurnal bağlama (RİM)"),
        "sections": ("journal-close",),
        "default": True,
    },
    "analytics": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Akademik analitika"),
        "sections": ("analytics",),
        "default": True,
    },
    "appeals": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Apellyasiyalar"),
        "sections": ("my-appeals", "manage-appeals"),
        "default": True,
    },
    "question_bank": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Sual bankı"),
        "sections": ("question-bank",),
        "default": True,
    },
    "exams_cab": {
        "label": pgettext_lazy("accounts.cabinet_modules", "İmtahan bölmələri"),
        "sections": ("my-exams", "assigned-exams"),
        "default": True,
    },
    "courses_cab": {
        "label": pgettext_lazy("accounts.cabinet_modules", "Kurs bölmələri"),
        "sections": ("my-courses", "assigned-courses", "courses"),
        "default": True,
    },
    "groups": {"label": pgettext_lazy("accounts.cabinet_modules", "Qruplar"), "sections": ("groups",), "default": True},
}


def _stored(organization) -> dict:
    raw = organization.settings if isinstance(organization.settings, dict) else {}
    value = raw.get(MODULE_VISIBILITY_SETTINGS_KEY, {})
    return value if isinstance(value, dict) else {}


def is_module_enabled(organization, module_key: str) -> bool:
    """Modulun bu təşkilat üçün aktiv olub-olmadığı (tənzimləmə yoxdursa default)."""
    config = CABINET_MODULES.get(module_key)
    if config is None:
        return True
    return bool(_stored(organization).get(module_key, config["default"]))


def set_module_enabled(organization, module_key: str, enabled: bool) -> None:
    """Modulu aç/bağla — settings JSON-da qalıcı."""
    if module_key not in CABINET_MODULES:
        raise ValueError(f"Naməlum kabinet modulu: {module_key}")
    if not isinstance(organization.settings, dict):
        organization.settings = {}
    stored = dict(_stored(organization))
    stored[module_key] = bool(enabled)
    organization.settings[MODULE_VISIBILITY_SETTINGS_KEY] = stored
    organization.save(update_fields=["settings", "updated_at"])


def disabled_sections(organization) -> set:
    """Söndürülmüş modulların bütün bölmələri (rbac allowed_sections-dan çıxarılır)."""
    hidden: set = set()
    for key, config in CABINET_MODULES.items():
        if not is_module_enabled(organization, key):
            hidden.update(config["sections"])
    return hidden


def default_disabled_sections() -> set:
    """Aktiv təşkilat konteksti olmayan sessiyalar üçün gizli bölmələr.

    Modul görünürlüyü org-səviyyəlidir; org yoxdursa modulun DEFAULT-u tətbiq
    olunur — default-u False olan modullar (postlar) org-suz superadmin
    sessiyasında da görünmür (U20)."""
    hidden: set = set()
    for config in CABINET_MODULES.values():
        if not config["default"]:
            hidden.update(config["sections"])
    return hidden


def module_items(organization) -> list:
    """Panel üçün sıralı siyahı: {key, label, enabled}."""
    return [
        {"key": key, "label": config["label"], "enabled": is_module_enabled(organization, key)}
        for key, config in CABINET_MODULES.items()
    ]
