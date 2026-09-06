"""Jurnal xana deduplukasiyası üçün saf, yaddaş-məhdud seçki alqoritmi.

Bu modul Django model/settings import etmir. Beləliklə həm importer, həm də
yalnız-oxu reconciliation CLI eyni alqoritmi Django konteksti qaldırmadan
istifadə edir.
"""

from __future__ import annotations

import hashlib


class CellElection:
    """Qalib seçimi üçün yaddaş-məhdud iki-keçidli prefiltr.

    Mənbə axını primary-key sırasındadır, qalib qaydası isə sonrakı sətirdə
    ola bilər. Birinci keçid təkrarlana bilən hash bucket-ləri tapır; ikinci
    keçid yalnız həmin namizədləri tam açarla müqayisə edir. Yalançı-müsbət
    mümkündür, yalançı-mənfi isə struktur olaraq mümkün deyil.
    """

    __slots__ = ("_bits", "_mask", "_repeats")

    def __init__(self, *, expected_rows: int) -> None:
        exponent = max(10, min(28, int(max(1, expected_rows)).bit_length() + 5))
        self._mask = (1 << exponent) - 1
        self._bits = bytearray(1 << (exponent - 3))
        self._repeats: set[int] = set()

    def bucket(self, key: tuple) -> int:
        digest = hashlib.blake2b(repr(key).encode("utf-8", "surrogatepass"), digest_size=8)
        return int.from_bytes(digest.digest(), "big") & self._mask

    def observe(self, key: tuple) -> None:
        """Birinci keçid: açarı gör, ikinci görüşdə bucket-i namizəd et."""

        bucket = self.bucket(key)
        index, bit = bucket >> 3, 1 << (bucket & 7)
        if self._bits[index] & bit:
            self._repeats.add(bucket)
        else:
            self._bits[index] |= bit

    def is_candidate(self, key: tuple) -> bool:
        """İkinci keçid: açar dəqiq seçkiyə göndərilməlidirmi?"""

        return self.bucket(key) in self._repeats

    @property
    def candidate_buckets(self) -> int:
        return len(self._repeats)


def elect_winners(candidates) -> dict[tuple, int]:
    """``(key, rank, legacy_pk)`` namizədlərindən hər xana qalibini seç."""

    winners: dict[tuple, tuple[tuple[int, str, int], int]] = {}
    for key, rank, legacy_pk in candidates:
        best = winners.get(key)
        if best is None or rank > best[0]:
            winners[key] = (rank, legacy_pk)
    return {key: legacy_pk for key, (_rank, legacy_pk) in winners.items()}


__all__ = ["CellElection", "elect_winners"]
