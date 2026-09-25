"""Plagiat (oxşarlıq) yoxlaması — normallaşdırma, MinHash, çıxarıcı, mühərrik, qərarlar."""

from .decisions import dismiss_match, restore_match
from .dispatch import enqueue, run_now, schedule_similarity_check
from .engine import build_fingerprint, candidate_queryset, refresh_flags, run_similarity_check
from .minhash import estimate_containment, estimate_jaccard, exact_scores, shingles, signature
from .normalize import normalize_text

__all__ = [
    "build_fingerprint",
    "candidate_queryset",
    "dismiss_match",
    "enqueue",
    "estimate_containment",
    "estimate_jaccard",
    "exact_scores",
    "normalize_text",
    "refresh_flags",
    "restore_match",
    "run_now",
    "run_similarity_check",
    "schedule_similarity_check",
    "shingles",
    "signature",
]
