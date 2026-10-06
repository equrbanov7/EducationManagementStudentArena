"""build_profile_response — əsas builder (stage-mixin birləşməsi, FAZA 4)."""

from ._lazy import LazyValue, force
from ._stage1 import _Stage1Mixin
from ._stage2 import _Stage2Mixin
from ._stage3 import _Stage3Mixin
from ._stage4 import _Stage4Mixin


class _ProfileResponseBuilder(_Stage1Mixin, _Stage2Mixin, _Stage3Mixin, _Stage4Mixin):
    """Profil context/response yığımı (köhnə 1243-sətirlik god-func; ~130 lokal
    self.* sahələrinə, gövdə ardıcıl stage-lərə bölünüb)."""

    def __init__(self, request, *, lean=False):
        self.request = request
        # Fraqment rejimi (yalnız GET): qabığa aid dəyərlər tənbəldir (bax `_lazy.py`).
        self.lean = bool(lean) and request.method == "GET"

    def _defer(self, fn):
        """Tam rejimdə ``fn()``-in nəticəsi, fraqment rejimində tənbəl ``LazyValue(fn)``."""
        return LazyValue(fn) if self.lean else fn()

    def _pick(self, source, key, *default):
        """``source[key]`` (və ya ``.get(key, default)``); ``source`` tənbəldirsə nəticə də tənbəldir."""
        if isinstance(source, LazyValue):
            return LazyValue(lambda: _lookup(force(source), key, default))
        return _lookup(source, key, default)

    def run(self):
        from django.shortcuts import render

        early, context = self.run_context()
        if early is not None:
            return early
        context["grades_notice"] = self._grades_notice_due()
        return render(self.request, "accounts/profile.html", context)

    def _grades_notice_due(self) -> bool:
        """Sahib 2026-10-02: parol bərpasından sonrakı ilk girişdə köçürülmüş ballar barədə modal.

        Yalnız tələbəyə (ballar onlarındır), view-as rejimində heç vaxt (aktorun gördüyü hədəfin modalı deyil).
        """
        if getattr(self.request, "view_as_mode", None):
            return False
        profile = getattr(self.request.user, "profile", None)
        if profile is None or not getattr(profile, "grades_notice_pending", False):
            return False
        return bool((getattr(self, "capabilities", None) or {}).get("is_student"))

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


def _lookup(mapping, key, default):
    return mapping.get(key, default[0]) if default else mapping[key]


def build_profile_response(request):
    """Profil səhifəsinin context-ini yığıb HttpResponse qaytarır."""
    return _ProfileResponseBuilder(request).run()


def build_profile_context(request, *, lean=False):
    """Profil context-ini render ETMƏDƏN qaytarır: ``(early_response, context)``.

    ``lean=True`` (bölmə fraqmenti): qabığa aid (sidebar/navbar) dəyərlər
    ``LazyValue`` kimi qalır və yalnız partial onları oxuyanda hesablanır.

    SPA bölmə fraqmenti üçün lazımdır: əvvəllər ``profile_section_fragment``
    bütün səhifəni (navbar + sidebar + footer + bütün asset teqləri) render edib
    JSON-a bükürdü və frontend oradan bir DOM node-u çıxarırdı — yəni hər bölmə
    dəyişməsində tam səhifə render olunurdu. İndi fraqment yalnız öz partial-ını
    render edir; context yığımı isə eynidir, ona görə icazə/tenant/RLS/filtr
    davranışı dəyişmir.
    """
    return _ProfileResponseBuilder(request, lean=lean).run_context()
