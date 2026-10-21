"""Browser script payload builders for student exam pages."""

from django.utils.translation import pgettext


def take_exam_script_data(remaining_seconds):
    return {
        "remainingSeconds": remaining_seconds,
        "i18n": {
            "autosaveSaving": pgettext("exams.template.take_exam", "autosave_saving"),
            "autosaveSaved": pgettext("exams.template.take_exam", "autosave_saved"),
            "draftSaved": pgettext("exams.template.take_exam", "draft_saved"),
            "draftSavedWithCheck": pgettext("exams.template.take_exam", "draft_saved_with_check"),
            "saveError": pgettext("exams.template.take_exam", "save_error"),
            "saveErrorRetry": pgettext("exams.template.take_exam", "save_error_retry"),
            "autosaveBusy": pgettext(
                "exams.template.take_exam",
                "Server hazırda çox yüklüdür. Cavablarınız brauzerdə saxlanılır və avtomatik yenidən göndəriləcək — səhifəni bağlamayın.",
            ),
            "autosaveOffline": pgettext(
                "exams.template.take_exam",
                "Cavablar hələ serverə yazılmayıb. Onlar brauzerdə saxlanılır və bağlantı bərpa olunanda avtomatik göndəriləcək — internet bağlantısını yoxlayın, səhifəni bağlamayın.",
            ),
            "autosaveRecovered": pgettext("exams.template.take_exam", "Cavablarınız yenidən saxlanılır."),
            # 2026-10-21: yalnız HƏQİQİ konflikt (başqa tab/kompüter eyni sualı fərqli cavablayıb) bloklayır.
            "autosaveConflict": pgettext(
                "exams.template.take_exam",
                "Bu imtahan başqa tabda və ya kompüterdə də yenilənib: eyni suallara fərqli cavab verilib. "
                "Digər cavablar saxlanıldı. Davam etmək üçün səhifəni yeniləyin.",
            ),
            "autosaveShared": pgettext(
                "exams.template.take_exam",
                "Bu imtahan başqa tabda və ya kompüterdə də açıqdır. Cavablar birləşdirilir — yalnız bir tabda davam edin.",
            ),
            "autosaveSecondTab": pgettext(
                "exams.template.take_exam",
                "Bu imtahan artıq başqa tabda açıqdır — bu tabdan cavablar yazılmır. "
                "İmtahanı həmin tabda davam etdirin və ya onu bağlayıb bu səhifəni yeniləyin.",
            ),
            "btnSaving": pgettext("exams.template.take_exam", "btn_saving"),
            "btnSaved": pgettext("exams.template.take_exam", "btn_saved"),
            "btnDraftSaved": pgettext("exams.template.take_exam", "btn_draft_saved"),
            "finishUnansweredCount": pgettext("exams.template.take_exam", "confirm_finish_unanswered_count"),
            "finishAllAnswered": pgettext("exams.template.take_exam", "confirm_finish_all_answered"),
            "timeUpMessage": pgettext("exams.template.take_exam", "time_up_auto_submit"),
            "mark": pgettext("exams.template.take_exam", "Mark"),
            "marked": pgettext("exams.template.take_exam", "Marked"),
        },
    }
