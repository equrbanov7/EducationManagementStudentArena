"""Domain sahə tipləri (EXAM-P1-09).

``EncryptedAccessCodeField`` — şəffaf şifrələmə: Python səviyyəsində dəyər həmişə
XAM mətndir (bütün mövcud ``exam.access_code`` oxu/müqayisə/göstərmə yolları
dəyişmədən işləyir), amma bazada Fernet ilə şifrlənmiş saxlanır. Köhnə xam mətn
sətirləri (hələ miqrasiya olunmamış) oxunanda olduğu kimi qaytarılır.

Kripto köməkçiləri model tərifi vaxtında dövri idxala səbəb olmasın deyə (
``services`` paketi ``models``-ı çəkir) sahə metodları daxilində gec idxal edilir.
"""

from django.db import models


class EncryptedAccessCodeField(models.CharField):
    """Bazada Fernet-şifrli saxlanan, Python-da xam görünən CharField."""

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        from apps.exams.services.access_code_crypto import decrypt_access_code

        return decrypt_access_code(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        from apps.exams.services.access_code_crypto import encrypt_access_code

        return encrypt_access_code(value)
