"""İmtahan nəticələri XLSX export builder-i (C2, 2026-07-03).

`export_exam_results_xlsx` view-undan çıxarılıb ki, həm sinxron yol (kiçik
datasetlər), həm də export job worker-i (böyük datasetlər) EYNİ kodu çağırsın.
request-dən asılı deyil — filterlənmiş attempts siyahısı parametr kimi gəlir.

2026-10-27 (sahib): sütunlar «Dəyərləndirilmiş nəticələr» ixracı ilə EYNİDİR —
``apps.exams.services.results_export.COLUMNS`` (tələbə + ata adı, qruplar / ana qrup,
imtahan, fənn, növ, kateqoriya, bal / maks / faiz, test sayğacları, «Yoxlayan»,
başlama / bitmə / müddət, zal + kompüter, cəhd №, status, uzaqlaşdırma səbəbi, apellyasiya).
Sıra = ekrandakı süzgəc + sıralama (çağıran verir).
"""

from apps.exams.services.results_export import XLSX_CONTENT_TYPE, build_results_xlsx, exam_attempt_rows

__all__ = ["XLSX_CONTENT_TYPE", "build_exam_results_xlsx_export"]


def build_exam_results_xlsx_export(exam, attempts_list, *, group_index=None):
    """(filename, content_type, bytes) qaytarır — attachment üçün hazır."""
    from ._group_index import build_group_index

    if group_index is None:
        group_index = build_group_index(exam)

    def group_lookup(user_id):
        user_group = group_index.user_group.get(user_id)
        return ", ".join(group_index.group_names(user_id)), (user_group.parent_name if user_group is not None else "")

    rows_by_attempt = exam_attempt_rows(attempts_list, group_lookup=group_lookup)
    rows = [rows_by_attempt[attempt.id] for attempt in attempts_list if attempt.id in rows_by_attempt]
    return build_results_xlsx(rows, sheet_title=exam.title, filename_stem=f"{exam.title}-results")
