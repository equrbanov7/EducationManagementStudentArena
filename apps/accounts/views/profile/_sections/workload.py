"""Profil «workload-distribution» və «my-workload» bölmələri — dərs yükü.

Bölmələr SPA panelidir (``teaching-handover`` naxışı): server yalnız ÇƏRÇİVƏNİ
verir — icazə bayraqları, endpoint URL-ləri, kataloqlar; cədvəllər JSON-la gəlir.
Domen məntiqi ``apps/workload``-dadır və buraya YALNIZ ``public.py`` fasadından
çıxılır (modul sərhədi: accounts → workload, əks istiqamət YOXDUR).

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ — bax ``apps/workload/public.py`` docstring-i.
──────────────────────────────────────────────────────────────────────────────
"""

from apps.workload.public import build_distribution_context, build_my_workload_context


def build_workload_distribution_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Yük bölgüsü» — kafedra müdiri / RİM (yerində mutasiya)."""
    if "workload-distribution" not in allowed_sections or active_section != "workload-distribution":
        return
    section.update(
        build_distribution_context(
            request,
            organization=active_organization,
            chair_id=request.GET.get("chair") or None,
            academic_year=(request.GET.get("year") or "").strip(),
        )
    )


def build_my_workload_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Dərs yüküm» — müəllimin öz yükü (yalnız-oxu)."""
    if "my-workload" not in allowed_sections or active_section != "my-workload":
        return
    section.update(
        build_my_workload_context(
            request,
            organization=active_organization,
            academic_year=(request.GET.get("year") or "").strip(),
        )
    )


__all__ = ["build_my_workload_section", "build_workload_distribution_section"]
