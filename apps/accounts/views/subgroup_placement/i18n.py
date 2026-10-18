"""«Alt qrupa tələbə əlavə et» panelinin JS mətnləri — ``<script type="application/json">`` adası ilə ötürülür.

Hər çağırış HƏRFİ kontekst + HƏRFİ mətndir (``xgettext`` dəyişəni oxumur).
"""

from __future__ import annotations

from django.utils.translation import pgettext


def panel_strings() -> dict:
    return {
        "loading": pgettext("accounts.subgroup_placement", "Yüklənir…"),
        "error": pgettext("accounts.subgroup_placement", "Əməliyyat alınmadı — yenidən cəhd edin."),
        "student_empty": pgettext("accounts.subgroup_placement", "Bu ada uyğun tələbə tapılmadı."),
        "subject_empty": pgettext(
            "accounts.subgroup_placement", "Bu semestr başqa qruplarda bu ada uyğun fənn yoxdur."
        ),
        "no_offerings": pgettext(
            "accounts.subgroup_placement", "Bu fənn bu semestr başqa qrupların heç birində açılmayıb."
        ),
        "subject_idle": pgettext("accounts.subgroup_placement", "Əvvəlcə tələbəni seçin…"),
        "subject_ready": pgettext("accounts.subgroup_placement", "Fənn axtarın…"),
        "credits": pgettext("accounts.subgroup_placement", "kredit"),
        "this_semester": pgettext("accounts.subgroup_placement", "Bu semestr"),
        "own": pgettext("accounts.subgroup_placement", "Öz fənləri"),
        "subgroup": pgettext("accounts.subgroup_placement", "Alt qrup"),
        "limit": pgettext("accounts.subgroup_placement", "Hədd"),
        "remaining": pgettext("accounts.subgroup_placement", "Qalan"),
        "over_limit": pgettext("accounts.subgroup_placement", "Kredit həddi keçilib"),
        "failed_title": pgettext("accounts.subgroup_placement", "Kəsilmiş fənlər"),
        "failed_none": pgettext("accounts.subgroup_placement", "Kəsilmiş fənn yoxdur."),
        "failed_pick": pgettext("accounts.subgroup_placement", "Bu fənni seç"),
        "current_title": pgettext("accounts.subgroup_placement", "Bu semestrin fənləri"),
        "history_title": pgettext("accounts.subgroup_placement", "Yerləşdirmə tarixçəsi"),
        "history_none": pgettext("accounts.subgroup_placement", "Hələ yerləşdirmə olmayıb."),
        "teacher": pgettext("accounts.subgroup_placement", "Müəllim"),
        "no_teacher": pgettext("accounts.subgroup_placement", "Müəllim təyin olunmayıb"),
        "schedule": pgettext("accounts.subgroup_placement", "Cədvəl"),
        "no_schedule": pgettext("accounts.subgroup_placement", "Cədvəl hələ qurulmayıb"),
        "students": pgettext("accounts.subgroup_placement", "tələbə"),
        "free": pgettext("accounts.subgroup_placement", "boş yer"),
        "credit_impact": pgettext("accounts.subgroup_placement", "Kredit"),
        "clash": pgettext("accounts.subgroup_placement", "Toqquşma"),
        "no_clash": pgettext("accounts.subgroup_placement", "Toqquşma yoxdur"),
        "clash_with": pgettext("accounts.subgroup_placement", "üst-üstə düşür"),
        "choose": pgettext("accounts.subgroup_placement", "Seç"),
        "chosen": pgettext("accounts.subgroup_placement", "Seçildi"),
        "locked": pgettext("accounts.subgroup_placement", "Jurnal bağlıdır"),
        "already_here": pgettext("accounts.subgroup_placement", "Artıq bu jurnaldadır"),
        "full": pgettext("accounts.subgroup_placement", "Dolub"),
        "releases_own": pgettext(
            "accounts.subgroup_placement", "Öz qrupunun jurnalında bu fənn var — yerləşdirmədə ondan azad ediləcək."
        ),
        "retake": pgettext("accounts.subgroup_placement", "Kəsilmiş fənnin təkrarı"),
        "checks_ok": pgettext("accounts.subgroup_placement", "Bütün yoxlamalar uğurludur — yerləşdirmək olar."),
        "checks_fail": pgettext("accounts.subgroup_placement", "Yerləşdirmə mümkün deyil:"),
        "warning": pgettext("accounts.subgroup_placement", "Xəbərdarlıq"),
        "after": pgettext("accounts.subgroup_placement", "Yerləşdirmədən sonra"),
        "placed": pgettext("accounts.subgroup_placement", "Yerləşdirildi"),
        "undone": pgettext("accounts.subgroup_placement", "Geri götürüldü"),
        "undo": pgettext("accounts.subgroup_placement", "Geri götür"),
        "document": pgettext("accounts.subgroup_placement", "Sənədə bax"),
        "order": pgettext("accounts.subgroup_placement", "Sərəncam"),
        "by": pgettext("accounts.subgroup_placement", "Kim"),
        "at": pgettext("accounts.subgroup_placement", "Nə vaxt"),
        "reason": pgettext("accounts.subgroup_placement", "Səbəb"),
        "from_to": pgettext("accounts.subgroup_placement", "qrupdan → jurnala"),
        "recent_none": pgettext("accounts.subgroup_placement", "Hələ yerləşdirmə yoxdur."),
        "more": pgettext("accounts.subgroup_placement", "Daha çox"),
        "doc_required": pgettext(
            "accounts.subgroup_placement", "Fayl yükləyin və ya sərəncamın nömrəsi ilə tarixini yazın."
        ),
        "reason_required": pgettext("accounts.subgroup_placement", "Səbəb ən azı 10 simvol olmalıdır."),
        "clash_confirm": pgettext("accounts.subgroup_placement", "Toqquşmanı təsdiqləyin."),
        "undo_reason": pgettext("accounts.subgroup_placement", "Geri götürmə səbəbi (ən azı 10 simvol)"),
        "view_as": pgettext("accounts.subgroup_placement", "«Başqasının adından» rejimində yalnız baxış mümkündür."),
    }


__all__ = ["panel_strings"]
