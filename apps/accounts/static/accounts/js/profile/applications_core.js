/* «Müraciətlərim» — paylaşılan köməkçilər (mətn, tarix, ölçü, toast, HTTP).
 *
 * Üç fayla bölünmə ölçü büdcəsinə görədir (`check_module_size.py`, 600 sətir):
 * bu fayl NÜVƏ köməkçiləridir və `applications.js` / `applications_detail.js` /
 * `applications_dialogs.js` onları `window.EMSApplications` üzərindən oxuyur.
 *
 * Mətnlər `#apx-i18n` JSON blokundan gəlir — xarici .js Django template
 * engine-dən keçmir (CLAUDE.md «dinamik dəyər» qaydası).
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    /* ── Kiçik köməkçilər ───────────────────────────────────────────────── */
    NS.esc = function (value) {
        var div = document.createElement("div");
        div.textContent = value === null || value === undefined ? "" : String(value);
        return div.innerHTML;
    };

    NS.t = function (key, vars) {
        var text = (NS.i18n && NS.i18n[key]) || "";
        if (!vars) {
            return text;
        }
        Object.keys(vars).forEach(function (name) {
            text = text.split("{" + name + "}").join(String(vars[name]));
        });
        return text;
    };

    NS.pad = function (value) {
        return value < 10 ? "0" + value : String(value);
    };

    NS.date = function (iso) {
        if (!iso) {
            return "";
        }
        var d = new Date(iso);
        if (isNaN(d.getTime())) {
            return "";
        }
        return NS.pad(d.getDate()) + "." + NS.pad(d.getMonth() + 1) + "." + d.getFullYear();
    };

    NS.dateTime = function (iso) {
        if (!iso) {
            return "";
        }
        var d = new Date(iso);
        if (isNaN(d.getTime())) {
            return "";
        }
        return NS.date(iso) + ", " + NS.pad(d.getHours()) + ":" + NS.pad(d.getMinutes());
    };

    NS.size = function (bytes) {
        var value = Number(bytes) || 0;
        if (value < 1024) {
            return value + " B";
        }
        if (value < 1024 * 1024) {
            return Math.round(value / 1024) + " KB";
        }
        return (value / (1024 * 1024)).toFixed(1) + " MB";
    };

    NS.toast = function (message, level) {
        if (!message) {
            return;
        }
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level || "success", 2800);
        }
    };

    /* Server xətasını (`{"ok":false,"errors":{…}}`) düz mətn siyahısına çevirir. */
    NS.errorList = function (error) {
        var payload = error && error.payload;
        var messages = [];
        if (payload && payload.errors) {
            Object.keys(payload.errors).forEach(function (field) {
                if (field === "code") {
                    return;
                }
                var entries = payload.errors[field];
                (Array.isArray(entries) ? entries : [entries]).forEach(function (item) {
                    messages.push(String(item));
                });
            });
        }
        if (!messages.length) {
            messages.push(NS.t("error"));
        }
        return messages;
    };

    /* CSRF token-i PANELİN öz formasından oxunur — kuki adı mühitə görə
     * dəyişə bilir (`CSRF_COOKIE_NAME`), formadakı dəyər isə həmişə cari
     * sirlə uyğundur. Kuki yalnız ehtiyat yoldur. */
    NS.csrfToken = function () {
        var scope = NS.root || document;
        var input = scope.querySelector("[data-apx-csrf] input[name=csrfmiddlewaretoken]");
        if (input && input.value) {
            return input.value;
        }
        return (window.EMSCore && window.EMSCore.getCsrfToken && window.EMSCore.getCsrfToken()) || "";
    };

    /* ── HTTP ───────────────────────────────────────────────────────────── */
    NS.api = {
        list: function (params) {
            var query = Object.keys(params)
                .filter(function (key) {
                    return params[key] !== "" && params[key] !== null && params[key] !== undefined;
                })
                .map(function (key) {
                    return encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
                })
                .join("&");
            return window.EMSCore.fetchJSON(NS.urls.list + (query ? "?" + query : ""));
        },
        detail: function (id) {
            return window.EMSCore.fetchJSON(NS.urls.detail.replace(NS.ID_PLACEHOLDER, id));
        },
        kpis: function () {
            return window.EMSCore.fetchJSON(NS.urls.kpis);
        },
        catalog: function () {
            return window.EMSCore.fetchJSON(NS.urls.catalog);
        },
        create: function (formData) {
            return window.EMSCore.fetchJSON(NS.urls.create, {
                method: "POST",
                body: formData,
                headers: { "X-CSRFToken": NS.csrfToken() },
            });
        },
        action: function (id, formData) {
            return window.EMSCore.fetchJSON(NS.urls.action.replace(NS.ID_PLACEHOLDER, id), {
                method: "POST",
                body: formData,
                headers: { "X-CSRFToken": NS.csrfToken() },
            });
        },
    };

    NS.ID_PLACEHOLDER = "00000000-0000-0000-0000-000000000000";
})();
