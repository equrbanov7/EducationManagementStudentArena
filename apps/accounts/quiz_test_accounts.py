"""Müvəqqəti quiz test hesabları (sahib 2026-11-20) — TƏK MƏNBƏ.

Sahib: quiz üçün 30 test tələbə hesabı — ``testuser1`` … ``testuser30``, parol ``12345678`` (sahibin açıq istəyi
ilə koddadır), hamısı yeni ``TestQrup`` qrupunda; dərhal girib quiz yazsınlar (ilk-giriş / e-poçt / profil
tamamlama qapısı yoxdur). Sonra hamısı silinəcək (``create_quiz_test_accounts_20261120 --undo --apply``).

Hesabın «bizimdir» işarəsi İKİ şərtdir: istifadəçi adı siyahıdadır VƏ e-poçt ``<ad>@quiz-test-20261120.invalid``-dır
(``.invalid`` — real ünvan deyil, heç bir məktub getmir). Yalnız ad uyğunluğu kifayət deyil: real hesab adını
``testuserN``-ə dəyişə bilməsin deyə ``testuser`` həm də rezerv addır (``services/username_change``).
"""

from __future__ import annotations

COUNT = 30
USERNAMES = tuple(f"testuser{index}" for index in range(1, COUNT + 1))
PASSWORD = "12345678"  # nosec B105 — sahibin açıq istəyi (2026-11-20): müvəqqəti quiz hesabları
GROUP_NAME = "TestQrup"
GROUP_SLUG = "quiz-test-20261120-testqrup"
#: Qrupun ``settings`` açarı — undo yalnız bu işarəli qrupu silir.
GROUP_MARKER_KEY = "quiz_test_accounts_20261120"
EMAIL_DOMAIN = "quiz-test-20261120.invalid"
PROGRAM_CODE = "QUIZ-TEST-20261120"
PROGRAM_NAME = "Test quiz (müvəqqəti)"
ADMISSION_YEAR = 2026
FIRST_NAME = "Test"


def email_for(username: str) -> str:
    return f"{username}@{EMAIL_DOMAIN}"


def last_name_for(username: str) -> str:
    return f"User {username.removeprefix('testuser')}"


def is_quiz_test_account(user) -> bool:
    """Bu əmrin yaratdığı test hesabıdır (ad + işarə e-poçtu birlikdə)."""
    username = str(getattr(user, "username", "") or "")
    if username not in USERNAMES:
        return False
    return str(getattr(user, "email", "") or "").lower() == email_for(username)


__all__ = [
    "ADMISSION_YEAR",
    "COUNT",
    "EMAIL_DOMAIN",
    "FIRST_NAME",
    "GROUP_MARKER_KEY",
    "GROUP_NAME",
    "GROUP_SLUG",
    "PASSWORD",
    "PROGRAM_CODE",
    "PROGRAM_NAME",
    "USERNAMES",
    "email_for",
    "is_quiz_test_account",
    "last_name_for",
]
