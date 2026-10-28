"""Müraciət məzmununun idarə edilməsi üçün tərcümələr."""

from django.utils.translation import pgettext


def content_i18n():
    return {
        "selectChair": pgettext("applications.content", "Məktəbə aid kafedranı seçin"),
        "editApplication": pgettext("applications.content", "Müraciəti redaktə et"),
        "deleteApplication": pgettext("applications.content", "Müraciəti sil"),
        "restoreApplication": pgettext("applications.content", "Müraciəti bərpa et"),
        "editReply": pgettext("applications.content", "Cavabı redaktə et"),
        "deleteReply": pgettext("applications.content", "Cavabı sil"),
        "restoreReply": pgettext("applications.content", "Cavabı bərpa et"),
        "edited": pgettext("applications.content", "Redaktə edilib"),
        "deletedBanner": pgettext(
            "applications.content", "Bu müraciət silinib. Bərpa olunduqda əvvəlki vəziyyəti saxlanılacaq."
        ),
        "restorePrompt": pgettext("applications.content", "Müraciət əvvəlki qərarı və yazışması ilə bərpa edilsin?"),
        "deletePrompt": pgettext(
            "applications.content", "Müraciət siyahıdan çıxarılsın? Onu «Silinənlər» bölməsindən bərpa edə bilərsiniz."
        ),
        "replyVisibilityPrompt": pgettext(
            "applications.content", "Əməliyyatı təsdiqləyin. Cavab audit tarixçəsində saxlanılır."
        ),
        "selectRecipient": pgettext("applications.content", "Prorektoru seçin"),
        "trash": pgettext("applications.content", "Silinənlər"),
        "edit": pgettext("applications.content", "Redaktə et"),
        "subject": pgettext("applications.content", "Mövzu"),
        "text": pgettext("applications.content", "Mətn"),
        "historyNote": pgettext(
            "applications.content", "Əvvəlki mətn tarixçədə saxlanılır. Müraciətin ünvanı və qərarı dəyişmir."
        ),
        "cancel": pgettext("applications.content", "Ləğv et"),
        "save": pgettext("applications.content", "Yadda saxla"),
    }
