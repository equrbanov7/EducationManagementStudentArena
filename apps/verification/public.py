"""verification modulunun PUBLIC API fasadı — başqa app-lar YALNIZ buradan import edir.

Sənədi quran modul (registrar transkripti) bunları işlədir:

* ``issue_sealed_document(...)`` → ``(bytes, seal)`` — möhür + kodun sənədə çapı (``render(mark)``);
* ``SealMark`` — çap olunan rekvizitlər (kod, URL, qısa ünvan, verilmə anı);
* ``qr_matrix(url)`` — QR modul matrisi (PDF-də vektor kimi çəkmək üçün; şəkil/skript yoxdur);
* ``mask_holder_name(user)`` — publik səhifə üçün «Elvin Q.»;
* ``payloads_by_code(organization=…, codes=…)`` — öz təşkilatının möhür faktları (məs. arayışın təqdim yeri);
* ``DocType`` — sənəd növləri.

Asılılıq istiqaməti: registrar → verification (əksinə YOX — verification registrar-ı tanımır).
"""

from .models import DocType
from .qr import qr_matrix
from .services import SealMark, issue_sealed_document, mask_holder_name, payloads_by_code, verification_url

__all__ = [
    "DocType",
    "SealMark",
    "issue_sealed_document",
    "mask_holder_name",
    "payloads_by_code",
    "qr_matrix",
    "verification_url",
]
