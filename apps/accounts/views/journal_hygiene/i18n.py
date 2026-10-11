"""«Jurnal təmizliyi» panelinin JS mətnləri — server tərəfdə tərcümə olunub `json_script` ilə ötürülür.

Hər çağırış HƏRFİ kontekst + HƏRFİ mətndir (``xgettext`` dəyişəni oxumur). ``{n}``, ``{page}`` kimi
yer tutucuları JS doldurur.
"""

from __future__ import annotations

from django.utils.translation import pgettext


def panel_strings() -> dict:
    return {
        "empty_left": pgettext("accounts.journal_hygiene", "Bu süzgəcə uyğun ayrılmış tələbə yoxdur."),
        "empty_empty": pgettext("accounts.journal_hygiene", "Bu süzgəcə uyğun boş fənn yoxdur."),
        "empty_not_held": pgettext("accounts.journal_hygiene", "Bu süzgəcə uyğun keçirilməyən fənn yoxdur."),
        "empty_history": pgettext("accounts.journal_hygiene", "Hələ qərar yoxdur."),
        "group_size": pgettext("accounts.journal_hygiene", "açılışda {n} tələbə"),
        "not_held_note": pgettext("accounts.journal_hygiene", "açılış · {n} sətir"),
        "partial": pgettext(
            "accounts.journal_hygiene",
            "{n} açılış yarımçıq seçilib — keçirilməyən fənn bütöv çıxarılır. "
            "Açılışın bütün tələbələrini seçin («Uyğun olanların hamısını seç»).",
        ),
        "load_error": pgettext("accounts.journal_hygiene", "Siyahı yüklənmədi. Bir az sonra yenidən cəhd edin."),
        "loading": pgettext("accounts.journal_hygiene", "Yüklənir…"),
        "selected": pgettext("accounts.journal_hygiene", "{n} sətir seçilib"),
        "nothing_selected": pgettext("accounts.journal_hygiene", "Sətir seçin — əməl düymələri seçimdən sonra açılır."),
        "select_all_done": pgettext("accounts.journal_hygiene", "Süzgəcə uyğun ilk {n} sətir seçildi."),
        "prev": pgettext("accounts.journal_hygiene", "Əvvəlki"),
        "next": pgettext("accounts.journal_hygiene", "Sonrakı"),
        "page": pgettext("accounts.journal_hygiene", "Səhifə {page} / {pages} · {total} sətir"),
        "has_data": pgettext("accounts.journal_hygiene", "Məlumat var"),
        "no_data": pgettext("accounts.journal_hygiene", "Boş"),
        "absence": pgettext("accounts.journal_hygiene", "{n} saat qayıb"),
        "journal_closed": pgettext("accounts.journal_hygiene", "Jurnal bağlıdır"),
        "chip_all": pgettext("accounts.journal_hygiene", "Hamısı"),
        "active": pgettext("accounts.journal_hygiene", "Qüvvədədir"),
        "reverted": pgettext("accounts.journal_hygiene", "Geri qaytarılıb"),
        "not_revertable": pgettext("accounts.journal_hygiene", "Status o vaxtdan dəyişib — geri qaytarılmır"),
        "title_suspend": pgettext("accounts.journal_hygiene", "Jurnaldan dondurmaq — önizləmə"),
        "title_drop": pgettext("accounts.journal_hygiene", "Nəticələrdən çıxarmaq — önizləmə"),
        "title_revert": pgettext("accounts.journal_hygiene", "Qərarları geri qaytarmaq"),
        "sub_suspend": pgettext(
            "accounts.journal_hygiene",
            "Sətirlər jurnaldan və imtahan siyahısından çıxır, tarixçə qalır; bərpa əmri və ya «Bərpa et» qaytarır.",
        ),
        "sub_drop": pgettext(
            "accounts.journal_hygiene",
            "Sətirlər nəticə səthlərindən (transkript, statistika) də çıxır. Qeydiyyat silinmir — «Bərpa et» qaytarır.",
        ),
        "sub_revert": pgettext(
            "accounts.journal_hygiene", "Seçilmiş qərarlar ləğv olunur və qeydiyyatlar əvvəlki statusuna qayıdır."
        ),
        "revert_count": pgettext("accounts.journal_hygiene", "{n} qərar geri qaytarılacaq."),
        "rows": pgettext("accounts.journal_hygiene", "Sətir"),
        "journals": pgettext("accounts.journal_hygiene", "Jurnal"),
        "students": pgettext("accounts.journal_hygiene", "Tələbə"),
        "with_evidence": pgettext("accounts.journal_hygiene", "Məlumatı olan"),
        "new_status": pgettext("accounts.journal_hygiene", "Yeni status"),
        "journal_list": pgettext("accounts.journal_hygiene", "Toxunulan jurnallar"),
        "journal_more": pgettext("accounts.journal_hygiene", "və daha {n} jurnal"),
        "evidence_totals": pgettext("accounts.journal_hygiene", "Qeydiyyatlardakı məlumat"),
        "no_evidence": pgettext(
            "accounts.journal_hygiene", "Seçilmiş sətirlərdə heç bir bal, davamiyyət və ya sənəd yoxdur."
        ),
        "blocked": pgettext(
            "accounts.journal_hygiene",
            "{n} sətirdə məlumat var — onlar nəticələrdən çıxarıla bilməz, yalnız dondurula bilər. Seçimi dəyişin.",
        ),
        "missing": pgettext(
            "accounts.journal_hygiene", "{n} sətir artıq siyahıda deyil — siyahını yeniləyib yenidən seçin."
        ),
        "drift": pgettext("accounts.journal_hygiene", "Siyahı önizləmədən sonra dəyişib — yenidən önizləyin."),
        "rows_unit": pgettext("accounts.journal_hygiene", "sətir"),
        "sources": {
            "marks": pgettext("accounts.journal_hygiene", "Dərs xanası (davamiyyət / bal)"),
            "components": pgettext("accounts.journal_hygiene", "Komponent balı"),
            "criteria": pgettext("accounts.journal_hygiene", "Rubrik balı"),
            "selfwork": pgettext("accounts.journal_hygiene", "Sərbəst iş"),
            "coursework": pgettext("accounts.journal_hygiene", "Kurs işi"),
            "resits": pgettext("accounts.journal_hygiene", "Təkrar imtahan"),
            "exam_entries": pgettext("accounts.journal_hygiene", "İmtahan balı yazısı"),
            "legacy_facts": pgettext("accounts.journal_hygiene", "Köhnə sistemin nəticəsi"),
            "finals": pgettext("accounts.journal_hygiene", "Yekun qiymət"),
            "journal_corrections": pgettext("accounts.journal_hygiene", "Jurnal düzəlişi"),
            "selfwork_corrections": pgettext("accounts.journal_hygiene", "Sərbəst iş düzəlişi"),
            "coursework_corrections": pgettext("accounts.journal_hygiene", "Kurs işi düzəlişi"),
            "component_corrections": pgettext("accounts.journal_hygiene", "Komponent düzəlişi"),
            "guest_documents": pgettext("accounts.journal_hygiene", "Alt qrup sənədi"),
            "predecessors": pgettext("accounts.journal_hygiene", "Köçürmə tarixçəsi"),
            "folder_submissions": pgettext("accounts.journal_hygiene", "Fənn qovluğu təhvili"),
        },
    }


__all__ = ["panel_strings"]
