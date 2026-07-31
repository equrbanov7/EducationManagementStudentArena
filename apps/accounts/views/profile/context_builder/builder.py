"""build_profile_response — əsas builder (stage-mixin birləşməsi, FAZA 4)."""

from ._stage1 import _Stage1Mixin
from ._stage2 import _Stage2Mixin
from ._stage3 import _Stage3Mixin
from ._stage4 import _Stage4Mixin


class _ProfileResponseBuilder(_Stage1Mixin, _Stage2Mixin, _Stage3Mixin, _Stage4Mixin):
    """Profil context/response yığımı (köhnə 1243-sətirlik god-func; ~130 lokal
    self.* sahələrinə, gövdə ardıcıl stage-lərə bölünüb)."""

    def __init__(self, request):
        self.request = request

    def run(self):
        from django.shortcuts import render

        early, context = self.run_context()
        if early is not None:
            return early
        return render(self.request, "accounts/profile.html", context)

    def run_context(self):
        """``(early_response, context)`` — render OLMADAN.

        Stage-lər yönləndirmə/403 qaytara bilir; belə halda ``early_response``
        dolur və ``context`` ``None`` olur.
        """
        r = self._stage_1()
        if r is not None:
            return r, None
        self._stage_2()
        r = self._stage_3()
        if r is not None:
            return r, None
        self._stage_4_context()
        return None, self.context


def build_profile_response(request):
    """Profil səhifəsinin context-ini yığıb HttpResponse qaytarır."""
    return _ProfileResponseBuilder(request).run()


def build_profile_context(request):
    """Profil context-ini render ETMƏDƏN qaytarır: ``(early_response, context)``.

    SPA bölmə fraqmenti üçün lazımdır: əvvəllər ``profile_section_fragment``
    bütün səhifəni (navbar + sidebar + footer + bütün asset teqləri) render edib
    JSON-a bükürdü və frontend oradan bir DOM node-u çıxarırdı — yəni hər bölmə
    dəyişməsində tam səhifə render olunurdu. İndi fraqment yalnız öz partial-ını
    render edir; context yığımı isə eynidir, ona görə icazə/tenant/RLS/filtr
    davranışı dəyişmir.
    """
    return _ProfileResponseBuilder(request).run_context()
