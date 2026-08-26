/* RİM mərkəzi — hadisə bağlanışı (AJAX-safe).
 *
 * Bütün klik-lər `EMSDelegate` ilə `document`-ə DELEGE olunur: panel AJAX-la
 * dəyişdiriləndə də düymələr işlək qalır (bax docs/frontend/AJAX_SAFE_JS_PATTERN.md).
 * Yalnız `input` hadisəsi panelin öz elementinə bağlanır — o da `EMSReady`
 * içindədir və hər swap-da yenidən qurulur (idempotent bayraqla).
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});

    if (!window.EMSReady || !window.EMSDelegate) {
        return;
    }

    /* ── Delegasiya olunmuş hadisələr — bir dəfə qeydiyyat ──────────────── */

    window.EMSReady.once("rim-center-delegates", function () {
        var D = window.EMSDelegate;

        D.on("click", "[data-rim-open]", function (event, btn) {
            event.preventDefault();
            ns.actions.openDetail(btn.getAttribute("data-rim-open"));
        });

        D.on("click", "[data-rim-act]", function (event, btn) {
            event.preventDefault();
            ns.actions.requestConfirm(btn.getAttribute("data-rim-act"));
        });

        D.on("click", "[data-rim-confirm-submit]", function (event) {
            event.preventDefault();
            ns.actions.submitConfirm();
        });

        D.on("click", "[data-rim-edit-save]", function (event) {
            event.preventDefault();
            ns.actions.saveEdit();
        });

        D.on("click", "[data-rim-modal-close]", function (event) {
            event.preventDefault();
            ns.modals.close("[data-rim-detail-modal]");
        });

        D.on("click", "[data-rim-confirm-close]", function (event) {
            event.preventDefault();
            ns.modals.close("[data-rim-confirm-modal]");
            ns.state.pendingAction = null;
        });

        D.on("click", "[data-rim-password-close]", function (event) {
            event.preventDefault();
            ns.modals.close("[data-rim-password-modal]");
            // Parol DOM-da qalmasın.
            ns.modals.clearPassword();
        });

        D.on("click", "[data-rim-password-copy]", function (event, btn) {
            event.preventDefault();
            ns.modals.copyPassword(btn);
        });

        D.on("click", "[data-rim-status]", function (event, btn) {
            event.preventDefault();
            var tabs = document.querySelectorAll("[data-rim-status]");
            Array.prototype.forEach.call(tabs, function (tab) {
                tab.classList.toggle("is-active", tab === btn);
            });
            ns.state.status = btn.getAttribute("data-rim-status") || "all";
            ns.state.page = 1;
            ns.actions.search();
        });

        D.on("click", "[data-rim-page]", function (event, btn) {
            event.preventDefault();
            if (btn.disabled) {
                return;
            }
            var direction = btn.getAttribute("data-rim-page");
            ns.state.page = Math.max(1, ns.state.page + (direction === "next" ? 1 : -1));
            ns.actions.search();
        });

        D.on("click", "[data-rim-search-clear]", function (event) {
            event.preventDefault();
            var input = document.querySelector("[data-rim-search]");
            if (input) {
                input.value = "";
                input.focus();
            }
            ns.state.query = "";
            ns.state.page = 1;
            ns.actions.search();
        });

        // ESC — açıq modalı bağlayır (parol modalı bağlananda dəyəri silir).
        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }
            ns.modals.closeAll();
            ns.modals.clearPassword();
            ns.state.pendingAction = null;
        });
    });

    /* ── Hər swap-dan sonra yenidən qurulan hissə ───────────────────────── */

    window.EMSReady(function () {
        var root = ns.root();
        if (!root) {
            return; // Bölmə bu səhifədə yoxdur — null-safe çıxış.
        }

        var input = document.querySelector("[data-rim-search]");
        // Eyni input-a təkrar listener yığmamaq üçün idempotent bayraq.
        if (input && !input.dataset.rimBound) {
            input.dataset.rimBound = "1";
            var onType = ns.debounce(function () {
                ns.state.query = input.value.trim();
                ns.state.page = 1;
                var clearBtn = document.querySelector("[data-rim-search-clear]");
                if (clearBtn) {
                    clearBtn.hidden = !ns.state.query;
                }
                ns.actions.search();
            }, 350);
            input.addEventListener("input", onType);
        }

        // Panel yenidən açılanda vəziyyəti sıfırla (köhnə nəticə qalmasın).
        ns.state.selectedUser = null;
        ns.state.pendingAction = null;
        ns.modals.closeAll();
    });
})(window, document);
