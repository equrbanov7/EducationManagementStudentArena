/*
 * member_accordion.js
 * Source: apps/courses/templates/courses/partials/_member_accordion.html
 * Delete-member (AJAX) from the dashboard members preview: removes row and
 * decrements the count badges. i18n from #memberAccordionConfig data-*;
 * CSRF from EMSCore.
 */
(function () {
    "use strict";

    function getCfg() {
        return document.getElementById("memberAccordionConfig");
    }

    // Audit 2026-09-28 FQ-FE-4: native alert() → EMSToast (aria-live, dizayn sistemi).
    function toastError(message) {
        if (!message) { return; }
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, "error");
        } else if (window.console) {
            window.console.error(message);
        }
    }

    window.EMSReady.once("member-accordion-delete", function () {
        document.addEventListener("click", async function (e) {
            var btn = e.target.closest(".js-delete-member");
            if (!btn) { return; }

            var cfg = getCfg();
            if (!cfg) { return; }

            var url = btn.dataset.url;
            var memberId = btn.dataset.memberId;

            // 2026-09-14 (audit FE-F19): native confirm() → EMSConfirm (vahid dialoq); ləğv = sorğu yoxdur.
            var who = btn.dataset.memberName ? btn.dataset.memberName + "\n\n" : "";
            var confirmed = await window.EMSConfirm.open({
                title: cfg.dataset.i18nConfirmDeleteUserTitle,
                body: who + cfg.dataset.i18nConfirmDeleteUser,
                confirmLabel: cfg.dataset.i18nDelete,
                danger: true
            });
            if (!confirmed) { return; }

            btn.disabled = true;

            try {
                // EMSCore.fetchJSON: 403/500 və qeyri-JSON cavab `catch`-ə düşür (err.payload).
                var data = await EMSCore.fetchJSON(url, { method: "POST" });

                if (!data || !data.success) {
                    toastError((data && data.error) || cfg.dataset.i18nErrorDeleteFailed);
                    btn.disabled = false;
                    return;
                }

                var row = document.getElementById("member-row-" + memberId);
                var wasStudent = !!(row && row.querySelector(".cd-avatar--student"));
                if (row) { row.remove(); }

                function decCountElement(el) {
                    if (!el) { return; }
                    var n = parseInt(el.textContent || "0", 10);
                    el.textContent = Math.max(0, n - 1);
                }

                function decCountById(id) {
                    decCountElement(document.getElementById(id));
                }

                function decCountBySelector(selector) {
                    document.querySelectorAll(selector).forEach(decCountElement);
                }

                decCountById("sidebar-members-count");
                decCountById("accordion-members-count");
                decCountBySelector('[data-count="members"]');
                if (wasStudent) { decCountBySelector('[data-count="students"]'); }

            } catch (err) {
                console.error(err);
                var payload = err && err.payload;
                if (!(payload && typeof payload === "object" && payload.view_as_blocked)) {
                    if (err && err.status) {
                        toastError((payload && typeof payload === "object" && payload.error) || cfg.dataset.i18nErrorDeleteFailed);
                    } else {
                        toastError(cfg.dataset.i18nErrorNetwork);
                    }
                }
                btn.disabled = false;
            }
        });
    });
})();
