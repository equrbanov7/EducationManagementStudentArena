"""1-ci kurs (qəbul ili) tələbə datasının FILL-ONLY tamamlanması (sahib 2026-10-27).

İki əməliyyat, hər ikisi YALNIZ BOŞ sahəni doldurur (dolu dəyər heç vaxt dəyişmir), qrupa/qeydin statusuna toxunmur:

* :mod:`.codes` — «Tələbə kodu» (``UserProfile.institutional_identifier``) olmayanlara: köhnə sistemdə FİN ilə
  tapılan (və istifadə olunmamış) legacy tələbə id-si, yoxdursa QRUP NÖMRƏSİNDƏN qurulmuş kod;
* :mod:`.atis_fill` — köhnə sistem deltasının yaratdığı (ATİS datası olmayan) hesablara ATİS ixracından FİN, doğum
  tarixi, telefon, real e-poçt (yalnız placeholder əvəzinə), vəsiqə, qəbul sahələri.

Stdout / audit — yalnız id-lər, kodlar və saylar (şəxs adı, FİN, telefon, e-poçt YOX).
"""

from .scope import first_year_records

__all__ = ["first_year_records"]
