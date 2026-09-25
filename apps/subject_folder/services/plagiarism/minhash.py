"""Söz 5-qram «shingle»-ləri, MinHash imzası (128 permutasiya) və oxşarlıq ölçüləri.

DETERMİNİSTİKDİR: Python-un ``hash()``-ı (proses başına təsadüfi toxum) İSTİFADƏ
EDİLMİR — shingle heşi ``blake2b`` (64 bit), permutasiyalar sabit toxumlu
``random.Random`` ilə qurulan universal heş ailəsidir
(``h_i(x) = (a_i·x + b_i) mod p``, ``p = 2^61 − 1``). Eyni mətn hər prosesdə,
hər serverdə eyni imzanı verir — saxlanmış imzalar müqayisə oluna bilir.

Böyük sənəddə shingle sayı ``MAX_SHINGLES``-lə məhdudlaşır: ən KİÇİK heşlər
saxlanılır («bottom-k» eskizi) — bu seçmə iki sənəddə eyni qaydadır, ona görə
Jaccard təxmini qərəzsiz qalır.
"""

from __future__ import annotations

import hashlib
import random

SHINGLE_SIZE = 5
NUM_PERMUTATIONS = 128
MAX_SHINGLES = 20_000
_PRIME = (1 << 61) - 1
_SEED = 20260925


def _permutations():
    rng = random.Random(_SEED)
    return tuple((rng.randrange(1, _PRIME), rng.randrange(0, _PRIME)) for _ in range(NUM_PERMUTATIONS))


_PERMUTATIONS = _permutations()


def hash64(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


def shingle_map(words, *, size: int = SHINGLE_SIZE) -> dict[int, str]:
    """``{heş: "söz1 söz2 … söz5"}`` — nümunə fraqment göstərmək üçün mətn də saxlanılır.

    Sözlər ``size``-dan azdırsa bütün mətn TƏK shingle-dir (qısa cavablar da müqayisə olunur).
    """
    if not words:
        return {}
    if len(words) < size:
        phrase = " ".join(words)
        return {hash64(phrase): phrase}
    result = {}
    for index in range(len(words) - size + 1):
        phrase = " ".join(words[index : index + size])
        result.setdefault(hash64(phrase), phrase)
    if len(result) > MAX_SHINGLES:
        keep = sorted(result)[:MAX_SHINGLES]
        result = {key: result[key] for key in keep}
    return result


def shingles(words, *, size: int = SHINGLE_SIZE) -> set[int]:
    return set(shingle_map(words, size=size))


def signature(hashes) -> list[int]:
    """128 elementli MinHash imzası; boş dəst → boş siyahı."""
    values = [value % _PRIME for value in hashes]
    if not values:
        return []
    return [min((a * value + b) % _PRIME for value in values) for a, b in _PERMUTATIONS]


def estimate_jaccard(left, right) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(1 for a, b in zip(left, right) if a == b) / len(left)


def estimate_containment(jaccard: float, size_a: int, size_b: int) -> float:
    """Jaccard təxminindən kiçik dəstin böyükdə «olma» payı: |A∩B| / min(|A|,|B|).

    ``|A∩B| = J·(|A|+|B|)/(1+J)`` — ölçüləri çox fərqli sənədlərdə (qısa iş uzun
    işin içindən köçürülüb) Jaccard aşağı, «olma» payı isə yüksək olur.
    """
    smaller = min(size_a, size_b)
    if smaller <= 0 or jaccard <= 0:
        return 0.0
    return min(1.0, jaccard * (size_a + size_b) / ((1 + jaccard) * smaller))


def exact_scores(left: set, right: set) -> dict:
    """Dəqiq ``jaccard`` + ``containment`` + kəsişmə ölçüsü."""
    if not left or not right:
        return {"jaccard": 0.0, "containment": 0.0, "shared": 0}
    shared = len(left & right)
    union = len(left | right)
    return {
        "jaccard": shared / union if union else 0.0,
        "containment": shared / min(len(left), len(right)),
        "shared": shared,
    }


__all__ = [
    "MAX_SHINGLES",
    "NUM_PERMUTATIONS",
    "SHINGLE_SIZE",
    "estimate_containment",
    "estimate_jaccard",
    "exact_scores",
    "hash64",
    "shingle_map",
    "shingles",
    "signature",
]
