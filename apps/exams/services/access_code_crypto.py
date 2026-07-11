"""Access-code at-rest şifrələməsi (EXAM-P1-09).

İmtahan giriş kodu müəllim-görünən paylaşılan sirdir (müəllim onu tələbələrə
paylaşır, tələbə girişdə yazır) — buna görə birtərəfli hash YOX, geri-açıla
bilən **Fernet-at-rest** istifadə olunur (PIN ``pin_cipher`` pattern-i ilə eyni
primitiv). Baza sütununda şifrlənmiş mətn saxlanır; oxuyanda açılır, beləliklə
müqayisə/göstərmə yolları dəyişməz qalır.

Açar imtahan PIN-ləri kimi ``SECRET_KEY``-dən törədilir — ayrıca sirr saxlamağa
ehtiyac yoxdur, amma ``SECRET_KEY`` fırlansa kodlar açıla bilməz (PIN-lərlə eyni
tradeoff). Geriyə-uyğunluq üçün açıla bilməyən dəyər (köhnə xam mətn) olduğu kimi
qaytarılır ki, hələ miqrasiya olunmamış sətirlər oxunmaqda davam etsin.
"""

from base64 import urlsafe_b64encode
from hashlib import sha256

from django.conf import settings

from cryptography.fernet import Fernet, InvalidToken


class AccessCodeDecryptionError(ValueError):
    """Stored value looks encrypted but cannot be authenticated/decrypted."""


def _fernet() -> Fernet:
    key = urlsafe_b64encode(sha256(f"exam-access-code:{settings.SECRET_KEY}".encode()).digest())
    return Fernet(key)


def encrypt_access_code(plain: str) -> str:
    """Xam giriş kodunu Fernet ilə şifrələ. Boş dəyər boş qalır."""
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_access_code(stored: str) -> str:
    """Şifrlənmiş giriş kodunu aç; yalnız real legacy 6-rəqəmli xam kodu qəbul et.

    Fernet autentifikasiyası keçməyən uzun/zədələnmiş ciphertext-i xam giriş
    koduna çevirmək fail-open davranış olardı. Köhnə sxem ``CharField(6)`` idi
    və model səviyyəsində alfanumerik sətirlər də yaradıla bilirdi; fallback
    buna görə yalnız exact 6 ASCII alfanumerik simvolla məhdudlaşdırılır.
    """
    if not stored:
        return ""
    try:
        return _fernet().decrypt(stored.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        if len(stored) == 6 and stored.isascii() and stored.isalnum():
            return stored
        raise AccessCodeDecryptionError("Access-code ciphertext could not be authenticated.") from exc


__all__ = ["AccessCodeDecryptionError", "encrypt_access_code", "decrypt_access_code"]
