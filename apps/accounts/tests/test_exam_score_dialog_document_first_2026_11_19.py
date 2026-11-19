"""«Təsdiq» dialoqunda sənəd sahəsi QEYDDƏN ƏVVƏL (sahib 2026-11-19).

Sahib (apellyasiya balı yazarkən): «burda qeyd yazmaq kifayət deyil ki? heç sənəd yükləməyə yer də yoxdur». Sənəd
sahəsi dialoqda VAR idi, amma «Qeyd»in altında — uzun siyahıda görünən hissədən kənarda qalırdı, məcburi sənədin
harada seçildiyi bilinmirdi. İndi fayl sahəsi xəbərdarlıqdan dərhal sonra gəlir, qeyd ondan sonra.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

TEMPLATE = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/partials/exam_score_entry/_save_dialog_body.html"
CONFIRM_JS = Path(settings.BASE_DIR) / "apps/accounts/static/accounts/js/exam_score_entry_confirm.js"


def test_document_field_comes_before_the_note():
    source = TEMPLATE.read_text(encoding="utf-8")
    warning = source.index('data-ese-just-text="appeal"')
    document = source.index("data-ese-just-file")
    note = source.index('id="ese-note"')
    assert warning < document < note


def test_missing_document_is_scrolled_into_view():
    source = CONFIRM_JS.read_text(encoding="utf-8")
    assert "[data-ese-just-drop]" in source and "scrollIntoView" in source and "is-required" in source
