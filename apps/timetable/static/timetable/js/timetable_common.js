/**
 * Avtomatik dərs cədvəli — ortaq köməkçilər (window.EMSTimetable).
 * ─────────────────────────────────────────────────────────────────────
 * AJAX-safe: yalnız EMSDelegate (document üzərində, təkrar qeydiyyat yığılmır).
 * Şəbəkə sorğuları EMSCore.fetchJSON ilə (CSRF başlığı avtomatik).
 * Bu fayl heç bir mətn tərcüməsi daşımır — mətnlər şablonun data-* atributlarındadır.
 */
(function (window, document) {
    "use strict";

    var TT = (window.EMSTimetable = window.EMSTimetable || {});

    TT.post = function (url, data) {
        return window.EMSCore.fetchJSON(url, { method: "POST", data: data || {} });
    };

    TT.get = function (url) {
        return window.EMSCore.fetchJSON(url);
    };

    TT.toast = function (text, level) {
        if (text && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(String(text), level || "info");
        }
    };

    /** Server xətasından istifadəçiyə göstəriləcək mətn (yoxdursa fallback). */
    TT.errorText = function (error, fallback) {
        var payload = error && error.payload;
        if (payload && typeof payload === "object" && payload.message) {
            return String(payload.message);
        }
        return fallback || "";
    };

    /** Elementi və onun bütün uşaqlarını təmizlə (innerHTML işlətmədən). */
    TT.clear = function (node) {
        while (node && node.firstChild) {
            node.removeChild(node.firstChild);
        }
    };

    /** Sadə siyahı elementi (mətn — HTML inyeksiyası yoxdur). */
    TT.listItems = function (list, rows) {
        TT.clear(list);
        (rows || []).forEach(function (text) {
            var li = document.createElement("li");
            li.textContent = String(text);
            list.appendChild(li);
        });
    };

    TT.setBusy = function (button, busy) {
        if (!button) {
            return;
        }
        button.disabled = !!busy;
        button.setAttribute("aria-busy", busy ? "true" : "false");
    };

    // Semestr / baxış seçiciləri: dəyişən kimi GET forması göndərilir.
    window.EMSDelegate.on("change", "[data-tt-autosubmit] select", function (event, select) {
        var form = select.closest("form");
        if (form) {
            form.submit();
        }
    });
})(window, document);
