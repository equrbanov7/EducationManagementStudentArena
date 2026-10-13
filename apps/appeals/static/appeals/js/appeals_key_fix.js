/* =========================================================================
   appeals_key_fix.js — reviewer qərar modalında «Cavab açarını hamı üçün düzəlt»
   və «Düzəlişi geri al» (2026-10-13, gecə).

   Niyə ayrı fayl: appeals_sections.js modal/siyahı axınını idarə edir; bu fayl yalnız
   açar düzəlişi düymələrinə cavab verir (EMSDelegate — AJAX swap-dan sonra da işləyir,
   modal gövdəsi hər açılışda yenidən yüklənir). Server bütün qaydaları təkrar yoxlayır
   (icazə açarı, tenant, seçim, səbəb) — burada yalnız UX validasiyası var.
   ========================================================================= */
(function () {
    "use strict";

    if (!window.EMSDelegate || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
        return;
    }

    function confirmAction(el, danger) {
        var opts = {
            title: el.getAttribute("data-i18n-confirm-title") || "",
            body: el.getAttribute("data-i18n-confirm-body") || "",
            danger: !!danger
        };
        // EMSConfirm base.html-də hər səhifəyə yüklənir; yoxdursa (fail-closed) əməliyyat icra olunmur.
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            return window.EMSConfirm.open(opts);
        }
        return Promise.resolve(false);
    }

    function toast(type, message) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, type);
        }
    }

    // Uğurdan sonra modal gövdəsini yenidən yüklə (yeni bal + açar kartı + tarixçə görünsün).
    function reloadReview(el) {
        var form = el.closest("[data-appeals-review-form]");
        var body = el.closest("[data-manage-modal-body]");
        var url = form ? form.getAttribute("action") : "";
        if (!form || !body || !url) { return; }
        window.fetch(url + (url.indexOf("?") === -1 ? "?" : "&") + "fragment=1", {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(function (response) { return response.ok ? response.text() : ""; })
            .then(function (html) {
                if (!html) { return; }
                body.innerHTML = html;
                if (window.EMSBootstrapSelect && window.EMSBootstrapSelect.init) { window.EMSBootstrapSelect.init(body); }
                if (window.EMSAppealsReview && window.EMSAppealsReview.init) { window.EMSAppealsReview.init(); }
            })
            .catch(function () { /* fail-soft: köhnə görünüş qalır */ });
    }

    function showError(box, errorEl, message) {
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.hidden = false;
        } else {
            toast("danger", message);
        }
        if (box) { box.classList.add("has-error"); }
    }

    function post(url, formData) {
        return window.EMSCore.fetchJSON(url, { method: "POST", body: formData });
    }

    function failureMessage(err) {
        return (err && err.payload && err.payload.error) || gettext("Yüklənmə alınmadı, yenidən cəhd edin.");
    }

    window.EMSDelegate.on("click", "[data-key-fix-submit]", function (event, button) {
        event.preventDefault();
        var box = button.closest("[data-key-fix-form]");
        if (!box || button.disabled) { return; }
        var errorEl = box.querySelector("[data-key-fix-error]");
        if (errorEl) { errorEl.hidden = true; }
        box.classList.remove("has-error");
        var chosen = Array.prototype.filter
            .call(box.querySelectorAll("[data-key-fix-option]"), function (input) { return input.checked; })
            .map(function (input) { return input.value; });
        var reasonEl = box.querySelector("[data-key-fix-reason]");
        var reason = reasonEl ? reasonEl.value.trim() : "";
        var minReason = parseInt(box.getAttribute("data-min-reason"), 10) || 10;
        if (!chosen.length) {
            showError(box, errorEl, box.getAttribute("data-i18n-need-option"));
            return;
        }
        if (reason.length < minReason) {
            showError(box, errorEl, box.getAttribute("data-i18n-need-reason"));
            return;
        }
        confirmAction(box, false).then(function (ok) {
            if (!ok) { return; }
            var data = new FormData();
            chosen.forEach(function (value) { data.append("corrected_option_ids", value); });
            data.append("reason", reason);
            button.disabled = true;
            post(box.getAttribute("data-key-fix-url"), data)
                .then(function (payload) {
                    toast("success", (payload && payload.toast) || "OK");
                    reloadReview(button);
                })
                .catch(function (err) {
                    button.disabled = false;
                    showError(box, errorEl, failureMessage(err));
                });
        });
    });

    window.EMSDelegate.on("click", "[data-key-fix-revoke-url]", function (event, button) {
        event.preventDefault();
        if (button.disabled) { return; }
        var card = button.closest("[data-key-fix-card]");
        var reasonEl = card ? card.querySelector("[data-key-fix-revoke-reason]") : null;
        var reason = reasonEl ? reasonEl.value.trim() : "";
        confirmAction(button, true).then(function (ok) {
            if (!ok) { return; }
            var data = new FormData();
            data.append("reason", reason);
            button.disabled = true;
            post(button.getAttribute("data-key-fix-revoke-url"), data)
                .then(function (payload) {
                    toast("success", (payload && payload.toast) || "OK");
                    reloadReview(button);
                })
                .catch(function (err) {
                    button.disabled = false;
                    toast("danger", failureMessage(err));
                });
        });
    });
})();
