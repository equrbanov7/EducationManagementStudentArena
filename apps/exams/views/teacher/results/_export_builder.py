"""İmtahan nəticələri XLSX export builder-i (C2, 2026-07-03).

`export_exam_results_xlsx` view-undan çıxarılıb ki, həm sinxron yol (kiçik
datasetlər), həm də export job worker-i (böyük datasetlər) EYNİ kodu çağırsın.
Davranış birə-birdir. request-dən asılı deyil — filterlənmiş attempts siyahısı
parametr kimi gəlir.
"""

from datetime import datetime
from io import BytesIO

from django.utils import timezone
from django.utils.text import slugify

from apps.exams.public import calculate_test_attempt_result
from core.export_safety import sheet_cell

from ._helpers import (
    _appeal_bonus_map_for,
    _apply_appeal_bonus,
    _attempt_effective_duration,
    _attempt_effective_finish,
)

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build_exam_results_xlsx_export(exam, attempts_list, *, group_index=None):
    """(filename, content_type, bytes) qaytarır — attachment üçün hazır.

    2026-10-25: «Qruplar» / «Ana qrup» sətir sütunu ilə eyni indeksdən (`_group_index`);
    sonda «Zal» və «Apellyasiya». Sıra = ekrandakı süzgəc + sıralama (çağıran verir).
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - deps quraşdırılıb
        raise RuntimeError("openpyxl is not installed. Add openpyxl to requirements.") from exc

    # İmtahandan uzaqlaşdırılmış tələbələrin səbəbi ixracda görünsün (N+1-siz).
    from apps.exams.services.supervision import attach_attempt_interventions

    attach_attempt_interventions(attempts_list)
    from ._test_scores import attach_legacy_selected_options

    attach_legacy_selected_options(attempts_list)

    wb = Workbook()
    ws = wb.active
    # 2026-09-14 (w2sec qeydi): vərəq adında `/ \ ? * [ ] :` olanda openpyxl
    # `ValueError` (500) atırdı — qadağan simvollar boşluqla əvəzlənir.
    safe_title = "".join(" " if ch in "/\\?*[]:" else ch for ch in exam.title).strip("'").strip()
    ws.title = ((safe_title[:28] + "…") if len(safe_title) > 30 else safe_title) or "Results"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2563EB")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    is_test = exam.exam_type == "test"
    is_written_or_coding = exam.exam_type in ("written", "coding")

    headers = [
        "#",
        "Qruplar",
        "Ana qrup",
        "Ad Soyad",
        "İstifadəçi adı",
        "E-poçt",
        "Status",
        "Uzaqlaşdırma səbəbi",
        "Başlama",
        "Bitmə",
        "Müddət (s:dq:sn)",
    ]
    if is_written_or_coding:
        headers += ["Müəllim balı", "Yoxlanıb"]
    if is_test:
        headers += ["Düzgün", "Səhv", "Cavabsız", "Verilmiş sual", "Bal", "Maks. bal", "Faiz", "Apel. bonus"]
    else:
        headers += ["Düzgün", "Səhv", "Verilmiş sual"]
    headers += ["Zal", "Apellyasiya"]

    for col_idx, title in enumerate(headers, start=1):
        cell = sheet_cell(ws, row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
    ws.row_dimensions[1].height = 28

    now = timezone.now()
    # Loop-invariant precompute (sətir başına sorğu yoxdur): qrup indeksi (kohort + reyestr +
    # ana qrup, sabit sorğu sayı), apellyasiya bonusu və statusu (hər biri tək sorğu).
    from apps.exams import score_adjustments

    from ._group_index import build_group_index

    if group_index is None:
        group_index = build_group_index(exam)
    # Apellyasiya bonusları (tək sorğu) — export-dakı Bal/Faiz effektiv olsun.
    appeal_bonus_by_attempt = _appeal_bonus_map_for(attempts_list) if is_test else {}
    appeal_status_map = score_adjustments.status_by_attempt([att.id for att in attempts_list])
    for row_idx, att in enumerate(attempts_list, start=2):
        effective_finish, _ = _attempt_effective_finish(att, now=now)
        effective_duration = _attempt_effective_duration(att, effective_finish)

        user_groups = ", ".join(group_index.group_names(att.user_id))
        user_group = group_index.user_group.get(att.user_id)
        parent_group = user_group.parent_name if user_group is not None else ""

        # Müddəti hh:mm:ss formatına çevir
        if effective_duration is not None:
            d_total = max(int(effective_duration), 0)
            d_h, d_m, d_s = d_total // 3600, (d_total % 3600) // 60, d_total % 60
            duration_str = f"{d_h:02d}:{d_m:02d}:{d_s:02d}"
        else:
            duration_str = ""

        _intervention = getattr(att, "exam_intervention", None)
        _removal_reason = (
            _intervention.get("reason") if _intervention and _intervention.get("is_terminal") else ""
        ) or ""
        row = [
            row_idx - 1,
            user_groups,
            parent_group,
            att.user.get_full_name() or att.user.username,
            att.user.username,
            att.user.email or "",
            att.get_status_display(),
            _removal_reason,
            # UTC saxlanan tarixi əvvəlcə yerli zonaya (Asia/Baku) çevir, sonra tz-i
            # at — əks halda Excel UTC divar-saatını göstərir (UI-dən 4 saat geri).
            timezone.localtime(att.started_at).replace(tzinfo=None) if att.started_at else "",
            timezone.localtime(effective_finish).replace(tzinfo=None) if effective_finish else "",
            duration_str,
        ]

        if is_written_or_coding:
            row += [
                att.teacher_score if att.teacher_score is not None else "",
                "Bəli" if att.checked_by_teacher else "Xeyr",
            ]

        if is_test:
            test_result = calculate_test_attempt_result(att, answers=att.answers.all())
            appeal_bonus = appeal_bonus_by_attempt.get(att.id) or 0
            if appeal_bonus:
                test_result = _apply_appeal_bonus(test_result, appeal_bonus)
            row += [
                test_result.correct_count,
                test_result.wrong_count,
                test_result.unanswered_count,
                test_result.delivered_count,
                float(test_result.score_display) if test_result.score_display else 0,
                float(test_result.max_score_display) if test_result.max_score_display else 0,
                float(test_result.percentage_display) if test_result.percentage_display else 0,
                float(appeal_bonus) if appeal_bonus else 0,
            ]
        else:
            delivered = att.correct_count + att.wrong_count
            row += [att.correct_count, att.wrong_count, delivered]
        appeal = appeal_status_map.get(att.id)
        row += [att.room.name if att.room_id and att.room else "", appeal["label"] if appeal else ""]

        # Sola düzlənən sütunlar: Qruplar (2), Ana qrup (3), Ad Soyad (4), İstifadəçi adı (5),
        # E-poçt (6), Uzaqlaşdırma səbəbi (8), Başlama (9), Bitmə (10), Zal + Apellyasiya (son iki).
        left_columns = {2, 3, 4, 5, 6, 8, 9, 10, len(row) - 1, len(row)}
        # 2026-09-14 (audit F-07): ad/qrup/uzaqlaşdırma səbəbi kimi mətn xanaları
        # formula kimi şərh olunmasın — `sheet_cell` `'` prefiksi qoyur, ədədlər
        # və tarixlər dəyişmir.
        for col_idx, value in enumerate(row, start=1):
            cell = sheet_cell(ws, row=row_idx, column=col_idx, value=value)
            cell.alignment = left if col_idx in left_columns else center
            if isinstance(value, datetime):
                cell.number_format = "DD.MM.YYYY HH:MM"

    # Sütun genişlikləri (header sırasına uyğun)
    # #, Qruplar, Ana qrup, Ad Soyad, İstifadəçi adı, E-poçt, Status, Uzaqlaşdırma səbəbi, Başlama, Bitmə, Müddət
    widths = [5, 26, 18, 26, 20, 28, 16, 30, 20, 20, 16]
    if is_written_or_coding:
        widths += [14, 12]  # Müəllim balı, Yoxlanıb
    if is_test:
        widths += [10, 10, 12, 16, 8, 12, 8, 12]  # Düzgün, Səhv, Cavabsız, Verilmiş, Bal, Maks, Faiz, Apel.
    else:
        widths += [10, 10, 14]  # Düzgün, Səhv, Verilmiş sual
    widths += [18, 18]  # Zal, Apellyasiya
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    ws.freeze_panes = "A2"

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{slugify(exam.title) or 'exam'}-results-{timezone.now().strftime('%Y%m%d-%H%M')}.xlsx"
    return filename, XLSX_CONTENT_TYPE, buffer.getvalue()
