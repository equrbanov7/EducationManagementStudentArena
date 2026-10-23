"""Final / midterm giriş forması — «İstifadəçi adı VƏ YA e-poçt» → TƏK hesab (sahib 2026-10-23).

Sahib: «final, midterm imtahanında username-dən əlavə e-mail də yazmağa icazə ver, problem olmasın». Axtarış
əsas giriş formasının (``accounts.backends.single_login_candidate``) qaydası ilə eynidir — kanonik forma
NFKC + trim + kiçik hərf (``accounts.identity.canonical_identity``); ``exams → accounts`` importu modul dövrü
yaratdığı üçün burada yerli surətdir. Dəyər İKİ fərqli hesaba uyğun gəlirsə (birinin istifadəçi adı digərinin
e-poçtu) ``None`` — təsadüfi «birinci» hesab seçilmir; çağıran generik «səhv» cavabı verir (sayım sızmır).
"""

from __future__ import annotations

import unicodedata

from django.contrib.auth import get_user_model
from django.db.models import Q


def canonical_login(value) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def find_login_user(identifier):
    key = canonical_login(identifier)
    if not key:
        return None
    candidates = list(
        get_user_model()._default_manager.filter(Q(username__iexact=key) | Q(email__iexact=key)).order_by("pk")[:2]
    )
    return candidates[0] if len(candidates) == 1 else None


__all__ = ["canonical_login", "find_login_user"]
