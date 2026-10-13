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

    /** «Filtrləri sıfırla» düyməsi yalnız ən azı bir filtr seçiləndə görünür. */
    ns.syncFilterReset = function syncFilterReset() {
        var btn = document.querySelector("[data-rim-filters-reset]");
        if (btn) {
            btn.hidden = !(ns.state.kind || ns.state.flag || ns.state.sort);
        }
    };

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

        D.on("click", "[data-rim-notice-close]", function (event) {
            event.preventDefault();
            ns.modals.close("[data-rim-notice-modal]");
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

        // Sahib 2026-10-11: hesab növü / vəziyyət / sıralama — dəyişən kimi siyahı yenilənir.
        D.on("change", "[data-rim-filter]", function (event, select) {
            var key = select.getAttribute("data-rim-filter");
            if (!key) {
                return;
            }
            ns.state[key] = select.value || "";
            ns.state.page = 1;
            ns.syncFilterReset();
            ns.actions.search();
        });

        D.on("click", "[data-rim-filters-reset]", function (event) {
            event.preventDefault();
            var selects = document.querySelectorAll("[data-rim-filter]");
            Array.prototype.forEach.call(selects, function (select) {
                select.value = "";
                ns.state[select.getAttribute("data-rim-filter")] = "";
                if (window.EMSBootstrapSelect) {
                    window.EMSBootstrapSelect.sync(select);
                }
            });
            ns.state.page = 1;
            ns.syncFilterReset();
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
        // 2026-10-14: vahid EMSSearchInput (1500 ms, ≥ 2 simvol, Enter dərhal, IME,
        // dəyişməyən dəyər göndərilmir); bind() idempotentdir — yığılmır.
        if (input) {
            window.EMSSearchInput.bind(input, {
                onSearch: function (value) {
                    ns.state.query = value;
                    ns.state.page = 1;
                    var clearBtn = document.querySelector("[data-rim-search-clear]");
                    if (clearBtn) {
                        clearBtn.hidden = !ns.state.query;
                    }
                    ns.actions.search({ quiet: true, input: input });
                }
            });
        }

        // Panel yenidən açılanda vəziyyəti sıfırla (köhnə nəticə qalmasın).
        ns.state.selectedUser = null;
        ns.state.pendingAction = null;
        ns.modals.closeAll();

        // Sahib 2026-10-11: ilk açılışda siyahı DƏRHAL yüklənir (boş ekran yoxdur). Swap-dan sonra
        // DOM təzədir — vəziyyəti DOM-a uyğunlaşdır (sorğu/filtr select-ləri defoltdadır).
        ns.state.query = input ? input.value.trim() : "";
        ns.state.status = "all";
        ns.state.kind = ns.state.flag = ns.state.sort = "";
        ns.state.page = 1;
        ns.syncFilterReset();
        ns.actions.search();
    });
})(window, document);
