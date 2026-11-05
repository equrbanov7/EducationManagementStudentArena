"""Qayıb limiti buraxılış qapısının əhatəsi (sahib 2026-11-04).

Sahib: «midterm zamanı qayıbdan kəsir göstərən tələbələr imtahan verə bilsin — texniki qayıb səhvi də ola bilər».
Qapı (``final_center.eligibility.admission_block_reason`` + ``journal_sync.registrar_block_reason(s)``) yalnız
midterm OLMAYAN imtahanlara tətbiq olunur; finalda qayıb limiti əvvəlki kimi buraxılmır.
"""


def absence_gate_applies(exam) -> bool:
    return getattr(exam, "exam_type_extended", "") != "midterm"


__all__ = ["absence_gate_applies"]
