/**
 * EMSCore.getCookie / getCsrfToken — CSRF köməkçilərinin VAHİD mənbəyi.
 * ─────────────────────────────────────────────────────────────────────
 * Faza 6.3 (audit 2026-07-02): əvvəllər eyni getCookie 4 ayrı faylda
 * nüsxələnmişdi (register_wizard/draft.js, user_profile/modal.js,
 * examBankPicker.js, take_exam/config.js) — indi hamısı bura delegasiya edir.
 *
 * Yüklənmə: base.html + base_auth.html (bütün digər custom skriptlərdən ƏVVƏL).
 * Qaytarma: tapılmayanda null (Django sənədlərindəki standart pattern).
 */
(function (window, document) {
    "use strict";

    var EMSCore = (window.EMSCore = window.EMSCore || {});

    EMSCore.getCookie = function getCookie(name) {
        if (!name || !document.cookie || document.cookie === "") {
            return null;
        }
        var cookies = document.cookie.split(";");
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + "=") {
                return decodeURIComponent(cookie.substring(name.length + 1));
            }
        }
        return null;
    };

    EMSCore.getCsrfToken = function getCsrfToken() {
        return EMSCore.getCookie("csrftoken");
    };
})(window, document);
