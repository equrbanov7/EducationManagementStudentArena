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

    window.EMSReady.once("member-accordion-delete", function () {
        document.addEventListener("click", async function (e) {
            var btn = e.target.closest(".js-delete-member");
            if (!btn) { return; }

            var cfg = getCfg();
            if (!cfg) { return; }

            var url = btn.dataset.url;
            var memberId = btn.dataset.memberId;

            if (!confirm(cfg.dataset.i18nConfirmDeleteUser)) { return; }

            btn.disabled = true;

            try {
                var resp = await fetch(url, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": EMSCore.getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });

                var data = await resp.json();

                if (!resp.ok || !data.success) {
                    alert(data.error || cfg.dataset.i18nErrorDeleteFailed);
                    btn.disabled = false;
                    return;
                }

                var row = document.getElementById("member-row-" + memberId);
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
                decCountBySelector('.snav-item[data-key="members"] .snav-count');

            } catch (err) {
                console.error(err);
                alert(cfg.dataset.i18nErrorNetwork);
                btn.disabled = false;
            }
        });
    });
})();
