/*
 * «Mühasibatlıq» → «Dərs saatının ödəniş dərəcələri» — yazı formaları (sahib 2026-10-19).
 *
 * `[data-ac-rate-form]` formaları (dərəcəni yadda saxla, «Ləğv et») `EMSCore.fetchJSON` ilə POST olunur (FormData —
 * CSRF başlığı avtomatik); uğurdan sonra toast və bölmə yerində yenilənir (`EMSProfileLoadSection`), dərəcə kartı
 * açıq qalır. «Ləğv et» əvvəlcə layihənin vahid təsdiq dialoqunu (`EMSConfirm`) açır.
 *
 * AJAX-safe: dinləyici `document`-də BİR dəfə (window bayrağı); `[data-ac-rates]` yoxdursa heç nə etmir.
 * CSP: inline kod yoxdur, mətnlər data-atributlardadır.
 */
(function (window, document) {
    "use strict";

    if (window.EMSAccountingRates) {
        return;
    }
    window.EMSAccountingRates = true;

    var keepOpen = false;

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function showError(card, form, message) {
        var box = form.querySelector("[data-ac-rate-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        } else if (message) {
            toast(message, "error");
        }
    }

    function reload(card) {
        keepOpen = true;
        var panel = card ? card.closest("[data-profile-section-panel]") : null;
        var url = panel ? panel.getAttribute("data-source-url") : "";
        var current = window.location.pathname + window.location.search;
        if (current.indexOf("section=accounting") !== -1) {
            url = current;
        }
        if (window.EMSProfileLoadSection && url) {
            window.EMSProfileLoadSection("accounting", url);
        } else {
            window.location.reload();
        }
    }

    /* Yeniləmədən sonra kart açıq qalsın (yazıdan sonra istifadəçi nəticəni görsün). */
    if (typeof window.EMSReady === "function") {
        window.EMSReady(function () {
            if (!keepOpen) {
                return;
            }
            var card = document.querySelector("[data-ac-rates]");
            if (card) {
                keepOpen = false;
                card.open = true;
            }
        });
    }

    function send(form, card) {
        var url = form.getAttribute("action");
        if (!url || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
            return;
        }
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        showError(card, form, "");
        window.EMSCore.fetchJSON(url, { method: "POST", body: new FormData(form) })
            .then(function (payload) {
                toast(payload && payload.message, "success");
                reload(card);
            })
            .catch(function (error) {
                var payload = error && error.payload;
                var text = (payload && (payload.error || payload.detail)) || card.getAttribute("data-ac-rates-error") || "";
                showError(card, form, text);
            })
            .then(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    }

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.matches || !form.matches("[data-ac-rate-form]")) {
            return;
        }
        var card = form.closest("[data-ac-rates]");
        if (!card) {
            return;
        }
        event.preventDefault();
        var confirmText = event.submitter && event.submitter.getAttribute("data-ac-confirm");
        if (confirmText && window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            window.EMSConfirm.open({ body: confirmText, danger: true }).then(function (ok) {
                if (ok) {
                    send(form, card);
                }
            });
            return;
        }
        send(form, card);
    });
})(window, document);
