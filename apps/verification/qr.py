"""QR kodu — mövcud ``qrcode`` paketi ilə (requirements/base.txt, canlı imtahan lobbisi); YENİ asılılıq yoxdur.

Sənədə şəkil kimi DEYİL, modul matrisi kimi verilir: PDF-də hər modul vektor kvadratdır (çapda kəskin,
Pillow lazım deyil, deterministikdir — eyni URL → eyni baytlar). Səhv düzəltmə səviyyəsi **M** (~15%):
kağız əzilsə / möhür üstünə düşsə də oxunur.
"""

from __future__ import annotations

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def qr_matrix(data: str) -> list[list[bool]]:
    """``data`` → kvadrat bool matrisi (``True`` = qara modul), kənar boşluğu (quiet zone) DAXİL DEYİL."""
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=0, box_size=1)
    code.add_data(data)
    code.make(fit=True)
    return [list(row) for row in code.get_matrix()]


__all__ = ["qr_matrix"]
