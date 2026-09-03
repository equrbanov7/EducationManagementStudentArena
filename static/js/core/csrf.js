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

    /**
     * CSRF token — kuki adı layihəyə görə dəyişə bilər (`CSRF_COOKIE_NAME`;
     * məs. staging-də `emsarena_staging_csrftoken`).  Ona görə YALNIZ kukiyə
     * güvənmirik: tapılmasa DOM-dakı `{% csrf_token %}` gizli sahəsindən,
     * sonra isə `<meta name="csrf-token">`-dan oxuyuruq.  Əks halda bütün
     * `fetchJSON` yazıları boş `X-CSRFToken` göndərib 403 alır.
     * (QA dalğa 2, 2026-09-03 — :8100 klonunda hər AJAX yazısı 403 verirdi.)
     */
    EMSCore.getCsrfToken = function getCsrfToken() {
        var fromCookie = EMSCore.getCookie("csrftoken");
        if (fromCookie) {
            return fromCookie;
        }
        var input = document.querySelector("input[name=csrfmiddlewaretoken]");
        if (input && input.value) {
            return input.value;
        }
        var meta = document.querySelector("meta[name=csrf-token]");
        if (meta && meta.content) {
            return meta.content;
        }
        return null;
    };
})(window, document);
