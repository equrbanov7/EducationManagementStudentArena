"""Bölmə fraqmenti üçün tənbəl (lazy) context dəyərləri (tutum 2026-10-06).

Yük testi (8 replika × 0.5 CPU, 1000 tələbə kabinetdə gəzir): fraqment ucu
(``/accounts/profile/api/sections/<bölmə>/``) hər bölmə üçün BÜTÜN profil qabığını
— bildiriş vəziyyəti, oxunmamış say, kurs/imtahan/post sayları, sidebar badge dəsti,
parol formaları — qurub sonra yalnız bölmənin partial-ını render edirdi. Partial
bunların çoxunu heç oxumur: ~25 ms app CPU və ~10 SQL sorğu boşa gedirdi.

Mexanizm: fraqment rejimində (``_ProfileResponseBuilder.lean``) qabığa aid dəyərlər
``LazyValue`` kimi context-ə qoyulur. Django şablon mühərriki dəyişəni həll edəndə
çağırıla bilən obyekti ÖZÜ çağırır (``Variable._resolve_lookup``) — yəni partial
dəyəri oxuyursa, hesablanır və nəticə tam rejimdəki ilə EYNİDİR; oxumursa heç vaxt
hesablanmır. Bölmələrə görə açar siyahısı saxlamağa ehtiyac yoxdur (yeni şablon
dəyişəni səssizcə boş render olunmur).

Tam səhifə (``/accounts/profile/?section=…``) yolu dəyişmir: orada ``lean`` söndürülüb
və hər dəyər əvvəlki kimi dərhal hesablanır.

Qayda: builder-in Python kodu dəyəri istifadə edirsə (``bool(...)``, ``.get``, başqa
qurucuya ötürmə) əvvəlcə ``force(...)`` çağırmalıdır.
"""

from __future__ import annotations

_UNSET = object()


class LazyValue:
    """Yaddaşlı (memo), arqumentsiz çağırış: ilk çağırışda hesablayır, sonra eyni nəticə."""

    __slots__ = ("_fn", "_value")

    def __init__(self, fn):
        self._fn = fn
        self._value = _UNSET

    def __call__(self):
        if self._value is _UNSET:
            self._value = self._fn()
            self._fn = None
        return self._value

    @property
    def evaluated(self) -> bool:
        return self._value is not _UNSET

    def __repr__(self) -> str:  # pragma: no cover — yalnız debug
        state = repr(self._value) if self.evaluated else "<pending>"
        return f"LazyValue({state})"


def force(value):
    """``LazyValue``-dursa hesablanmış dəyəri, deyilsə dəyərin özünü qaytarır."""
    return value() if isinstance(value, LazyValue) else value
