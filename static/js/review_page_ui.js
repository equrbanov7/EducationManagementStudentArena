/*
 * review_page_ui.js — «Təqdim olunan cavablar» səhifələrinin UX qatı (2026-09-28).
 * Sərbəst iş və kurs işi yoxlama səhifələri (templates `*review_submissions.html`).
 *
 * 1) Kütləvi əməllər paneli (`[data-rv-bulk]`) yalnız ən azı bir cavab seçiləndə
 *    görünür — əvvəl 0 seçimdə də solğun «Sil/Sıfırla» düymələri xəta kimi dururdu.
 * 2) Cədvəl başlığındakı checkbox (`[data-rv-select-all]`) hamısını seçir/təmizləyir
 *    (mövcud results_bulk_actions.js düymələrini tetikləyir — məntiq təkrarlanmır)
 *    və qismən seçimdə `indeterminate` göstərir.
 * AJAX-safe: document səviyyəsində bir dəfə delegə olunur.
 */
(function () {
    "use strict";

    if (window.__emsReviewPageUi) {
        return;
    }
    window.__emsReviewPageUi = true;

    function rowBoxes(table) {
        return table ? Array.prototype.slice.call(table.querySelectorAll("tbody input[type='checkbox']")) : [];
    }

    function sync() {
        var head = document.querySelector("[data-rv-select-all]");
        var table = head ? head.closest("table") : null;
        var boxes = rowBoxes(table);
        var checked = boxes.filter(function (b) { return b.checked; }).length;
        var bar = document.querySelector("[data-rv-bulk]");
        if (bar) {
            bar.hidden = checked === 0;
        }
        if (head) {
            head.checked = boxes.length > 0 && checked === boxes.length;
            head.indeterminate = checked > 0 && checked < boxes.length;
        }
    }

    document.addEventListener("change", function (event) {
        var head = event.target.closest && event.target.closest("[data-rv-select-all]");
        if (head) {
            var bar = document.querySelector("[data-rv-bulk]");
            var btn = bar && bar.querySelector(head.checked ? "[id^='selectAll']" : "[id^='clear']");
            if (btn) {
                btn.disabled = false;
                btn.click();
            } else {
                rowBoxes(head.closest("table")).forEach(function (b) {
                    b.checked = head.checked;
                    b.dispatchEvent(new Event("change", { bubbles: true }));
                });
            }
            window.setTimeout(sync, 0);
            return;
        }
        if (event.target.closest && event.target.closest(".rv-table tbody")) {
            window.setTimeout(sync, 0);
        }
    });

    document.addEventListener("click", function (event) {
        if (event.target.closest && event.target.closest("[data-rv-bulk] button")) {
            window.setTimeout(sync, 0);
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", sync);
    } else {
        sync();
    }
})();
