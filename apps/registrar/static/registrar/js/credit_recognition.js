/* «Xarici nəticələrin tanınması» (`credit-recognition`) — heyət paneli, sahib 2026-10-25.
 * Şablonlar: registrar/recognition/*.html. AJAX-safe: dinləyicilər `document`-də BİR dəfə (window bayrağı) —
 * panel AJAX ilə yenidən yüklənsə də təkrar bağlanmır. Yazılar `EMSCore.fetchJSON` (FormData → CSRF başlığı
 * avtomatik, fayl daxil), uğurdan sonra bölmə yerində yenilənir. Dialoqlar `ems_ui/overlay.js`-dədir
 * (`data-ems-overlay-open`); bu fayl yalnız «Ləğv et» URL-ini formaya yazır və POST-ları göndərir.
 */
(function (window, document) {
    "use strict";

    if (window.EMSCreditRecognition) {
        return;
    }
    window.EMSCreditRecognition = true;

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function rootOf(node) {
        return node && node.closest ? node.closest("[data-cr-root]") : null;
    }

    function reload(root) {
        var section = root ? root.getAttribute("data-cr-section") : "";
        var current = window.location.pathname + window.location.search;
        var panel = root ? root.closest("[data-profile-section-panel]") : null;
        var url = current.indexOf("section=" + section) !== -1 ? current : panel && panel.getAttribute("data-source-url");
        if (window.EMSProfileLoadSection && section && url) {
            window.EMSProfileLoadSection(section, url);
        } else {
            window.location.reload();
        }
    }

    function showError(form, message) {
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        } else if (message) {
            toast(message, "error");
        }
    }

    /* Sahib 2026-11-27: bal / sənəd / qurum sahələri yalnız səbəb seçiləndə açılır; Erasmus+ / mübadilədə xarici
       fənnin sahələri də. Gizli `fieldset` `disabled` olur — onun sahələri göndərilmir və brauzer yoxlamasını
       saxlamır. Server hər halda yenidən yoxlayır (credit_recognition.validate). */
    function syncReason(select) {
        var form = select && select.form;
        if (!form) {
            return;
        }
        var value = select.value || "";
        var detailed = (select.getAttribute("data-cr-detailed") || "").split(",").indexOf(value) !== -1;
        var other = value !== "" && value === select.getAttribute("data-cr-other");
        var after = form.querySelector("[data-cr-after-reason]");
        var extra = form.querySelector("[data-cr-detailed-fields]");
        if (after) {
            after.hidden = !value;
            after.disabled = !value;
        }
        if (extra) {
            extra.hidden = !detailed;
            extra.disabled = !detailed;
        }
        var institution = form.querySelector("[data-cr-institution]");
        if (institution) {
            institution.required = !other;
        }
        var star = form.querySelector("[data-cr-institution-req]");
        if (star) {
            star.hidden = other;
        }
    }

    document.addEventListener("change", function (event) {
        var select = event.target;
        if (select && select.matches && select.matches("[data-cr-program]") && rootOf(select)) {
            syncReason(select);
        }
    });

    /* Dialoq hər açılanda (forma sıfırlanıb) sahələr yenidən səbəbə uyğunlaşır. */
    document.addEventListener("click", function (event) {
        var opener = event.target.closest ? event.target.closest('[data-ems-overlay-open="crCreateDialog"]') : null;
        if (!opener || !rootOf(opener)) {
            return;
        }
        window.setTimeout(function () {
            var select = document.querySelector("#crCreateDialog [data-cr-program]");
            if (select) {
                syncReason(select);
            }
        }, 0);
    });

    /* «Ləğv et» — hədəf URL düymədən dialoqun formasına (dialoq panelin içində, bir dənədir). */
    document.addEventListener("click", function (event) {
        var trigger = event.target.closest ? event.target.closest("[data-cr-revoke]") : null;
        if (!trigger || !rootOf(trigger)) {
            return;
        }
        var dialog = document.getElementById("crRevokeDialog");
        var form = dialog ? dialog.querySelector("form") : null;
        if (!form) {
            return;
        }
        form.reset();
        showError(form, "");
        form.setAttribute("action", trigger.getAttribute("data-cr-url") || "");
        if (window.EMSOverlay && typeof window.EMSOverlay.syncReason === "function") {
            window.EMSOverlay.syncReason(form);
        }
    });

    /* Panelin içindəki bütün POST formaları (yaratma + ləğv) — JSON cavab, yerində yeniləmə. */
    document.addEventListener("submit", function (event) {
        var form = event.target;
        var root = rootOf(form);
        if (!root || (form.getAttribute("method") || "get").toLowerCase() !== "post") {
            return;
        }
        event.preventDefault();
        var url = form.getAttribute("action");
        if (!url || !window.EMSCore) {
            return;
        }
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        showError(form, "");
        window.EMSCore.fetchJSON(url, { method: "POST", body: new FormData(form) })
            .then(function (payload) {
                toast(payload && payload.message, "success");
                var overlay = form.closest(".ems-overlay");
                if (overlay && window.EMSOverlay) {
                    window.EMSOverlay.close(overlay);
                }
                reload(root);
            })
            .catch(function (error) {
                var payload = error && error.payload;
                var structured = payload && typeof payload === "object";
                var message = (structured && (payload.error || payload.detail)) || root.getAttribute("data-cr-error-generic") || "";
                showError(form, message);
            })
            .finally(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });
})(window, document);
