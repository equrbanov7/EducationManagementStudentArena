"""«Əmək müqavilələri» kabinet bölmələrinin qeydiyyatı (apps.hr_contracts, sahib 2026-10-19).

``sections_api.py`` 600-sətir tavanındadır — iki bölmə burada saxlanılır və ``SECTION_PARTIALS`` /
``AJAX_SAFE_SECTIONS``-a birləşdirilir. Hər ikisi server-render paneldir; bütün yazılar ayrıca
``/kadrlar/muqavileler/api/…`` JSON POST-larına gedir, filtr / KPI / səhifə linkləri paneli yerində yeniləyir →
AJAX-safe. ``profile.html`` ``data-ajax-sections``-da da qeyd olunub (``test_section_registry_consistency``).
"""

HR_CONTRACT_SECTION_PARTIALS: dict[str, str] = {
    "hr-contracts": "accounts/profile/sections/_hr_contracts.html",  # «Əmək müqavilələri» — HR
    "my-contracts": "accounts/profile/sections/_my_contracts.html",  # «Müqavilələrim» — işçinin öz bölməsi
}

HR_CONTRACT_AJAX_SECTIONS: frozenset[str] = frozenset(HR_CONTRACT_SECTION_PARTIALS)

__all__ = ["HR_CONTRACT_AJAX_SECTIONS", "HR_CONTRACT_SECTION_PARTIALS"]
