"""«Xarici nəticələrin tanınması» kabinet bölməsinin qeydiyyatı (apps.registrar, sahib 2026-10-25).

``sections_api.py`` 600-sətir tavanındadır — bölmə burada saxlanılır və ``SECTION_PARTIALS`` /
``AJAX_SAFE_SECTIONS``-a birləşdirilir (``sections_hr_contracts`` naxışı). Panel server-render olunur (data
``{% credit_recognition_desk %}`` tag-ı ilə — açar + əhatə render vaxtı yenidən yoxlanır); axtarış / tələbə seçimi
paneli yerində yeniləyir, yazılar ``/jurnal/xarici-netice/…`` multipart POST-larına gedir → AJAX-safe.
``profile.html`` ``data-ajax-sections``-da da qeyd olunub (``test_section_registry_consistency``).
"""

from .sections_hr_contracts import HR_CONTRACT_AJAX_SECTIONS, HR_CONTRACT_SECTION_PARTIALS

RECOGNITION_SECTION_PARTIALS: dict[str, str] = {
    "credit-recognition": "accounts/profile/sections/_credit_recognition.html",
}

RECOGNITION_AJAX_SECTIONS: frozenset[str] = frozenset(RECOGNITION_SECTION_PARTIALS)

#: «Fənnimə aid apellyasiyalar» (apps.appeals, sahib 2026-10-27) — panel server-render olunur (data
#: ``{% teaching_appeals_panel %}`` tag-ı ilə, əhatə render vaxtı yenidən yoxlanır); çekməcə və Excel ayrıca GET-dir.
TEACHING_APPEALS_SECTION_PARTIALS: dict[str, str] = {
    "teaching-appeals": "accounts/profile/sections/_teaching_appeals.html",
}

#: ``sections_api``-a birləşən əlavə bölmələr (Əmək müqavilələri + Xarici nəticələrin tanınması).
EXTRA_SECTION_PARTIALS: dict[str, str] = (
    HR_CONTRACT_SECTION_PARTIALS | RECOGNITION_SECTION_PARTIALS | TEACHING_APPEALS_SECTION_PARTIALS
)
EXTRA_AJAX_SECTIONS: frozenset[str] = (
    HR_CONTRACT_AJAX_SECTIONS | RECOGNITION_AJAX_SECTIONS | frozenset(TEACHING_APPEALS_SECTION_PARTIALS)
)

__all__ = [
    "EXTRA_AJAX_SECTIONS",
    "EXTRA_SECTION_PARTIALS",
    "RECOGNITION_AJAX_SECTIONS",
    "RECOGNITION_SECTION_PARTIALS",
    "TEACHING_APPEALS_SECTION_PARTIALS",
]
