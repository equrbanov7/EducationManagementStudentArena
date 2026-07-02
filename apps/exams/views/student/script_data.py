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
