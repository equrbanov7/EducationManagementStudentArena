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
        r = self._stage_1()
        if r is not None:
            return r
        self._stage_2()
        r = self._stage_3()
        if r is not None:
            return r
        return self._stage_4()


def build_profile_response(request):
    """Profil səhifəsinin context-ini yığıb HttpResponse qaytarır."""
    return _ProfileResponseBuilder(request).run()
