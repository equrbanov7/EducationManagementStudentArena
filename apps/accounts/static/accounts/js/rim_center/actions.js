/* RİM mərkəzi — sorğular və əməliyyat axınları (axtarış, detal, təsdiq, parol). */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});
    var actions = (ns.actions = {});

    /** Səbəb MƏCBURİ olan (dağıdıcı) əməliyyatlar. */
    // QA 2026-09-05 (P2-15): parol sıfırlaması da audit izinə səbəb yazır.
    var REASON_REQUIRED = { block: true, soft_delete: true, set_password: true };

    function http() {
        return window.EMSCore && window.EMSCore.fetchJSON;
    }

    /* ── Axtarış ────────────────────────────────────────────────────────── */

    actions.search = function search() {
        var cfg = ns.config();
        var fetchJSON = http();
        if (!cfg || !fetchJSON) {
            return;
        }
        var query = ns.state.query;
        // Boş sorğuda «hamısı» siyahısını çəkmirik: 8000+ hesablı tenantda bu
        // mənasız yükdür və operator onsuz da konkret adamı axtarır.
        if (!query) {
            ns.render.state("type_to_search", "fa-keyboard");
            ns.render.pager(null);
            return;
        }
        ns.render.state("loading", "fa-spinner fa-spin");

        var url =
            cfg.searchUrl +
            "?q=" +
            encodeURIComponent(query) +
            "&status=" +
            encodeURIComponent(ns.state.status) +
            "&page=" +
            encodeURIComponent(ns.state.page);

        fetchJSON(url)
            .then(function (payload) {
                ns.render.list(payload);
                ns.render.pager(payload);
            })
            .catch(function (err) {
                var container = document.querySelector("[data-rim-results]");
                if (container) {
                    container.innerHTML =
                        '<div class="rim-state"><i class="fas fa-circle-exclamation"></i> ' +
                        ns.escape(ns.errorMessage(err)) +
                        "</div>";
                }
                ns.render.pager(null);
            });
    };

    /* ── Detal ──────────────────────────────────────────────────────────── */

    actions.openDetail = function openDetail(userId) {
        var fetchJSON = http();
        var url = ns.detailUrl(userId);
        if (!fetchJSON || !url) {
            return;
        }
        fetchJSON(url)
            .then(function (payload) {
                ns.state.selectedUser = payload.user;
                ns.render.detail(payload.user);
                ns.modals.open("[data-rim-detail-modal]");
            })
            .catch(function (err) {
                window.alert(ns.errorMessage(err));
            });
    };

    /* ── Təsdiq tələb edən əməliyyatlar ─────────────────────────────────── */

    var CONFIRM_TEXT_KEYS = {
        set_password: "confirm_set_password",
        block: "confirm_block",
        unblock: "confirm_unblock",
        soft_delete: "confirm_soft_delete",
        restore: "confirm_restore"
    };

    var CONFIRM_TITLE_KEYS = {
        set_password: "set_password",
        block: "block",
        unblock: "unblock",
        soft_delete: "soft_delete",
        restore: "restore"
    };

    actions.requestConfirm = function requestConfirm(action) {
        if (!ns.state.selectedUser) {
            return;
        }
        ns.state.pendingAction = action;

        var titleEl = document.querySelector("[data-rim-confirm-title]");
        var textEl = document.querySelector("[data-rim-confirm-text]");
        var reasonEl = document.querySelector("[data-rim-confirm-reason]");
        var errorEl = document.querySelector("[data-rim-confirm-error]");

        if (titleEl) {
            titleEl.textContent = ns.t(CONFIRM_TITLE_KEYS[action] || action);
        }
        if (textEl) {
            textEl.textContent = ns.t(CONFIRM_TEXT_KEYS[action] || "");
        }
        if (reasonEl) {
            reasonEl.value = "";
        }
        if (errorEl) {
            errorEl.hidden = true;
            errorEl.textContent = "";
        }
        ns.modals.open("[data-rim-confirm-modal]");
    };

    actions.submitConfirm = function submitConfirm() {
        var cfg = ns.config();
        var fetchJSON = http();
        var action = ns.state.pendingAction;
        var user = ns.state.selectedUser;
        if (!cfg || !fetchJSON || !action || !user) {
            return;
        }

        var reasonEl = document.querySelector("[data-rim-confirm-reason]");
        var errorEl = document.querySelector("[data-rim-confirm-error]");
        var reason = reasonEl ? reasonEl.value.trim() : "";

        // Klient-tərəf yoxlama YALNIZ UX üçündür — serverdə eyni qayda tətbiq olunur.
        if (REASON_REQUIRED[action] && reason.length < cfg.minReasonLength) {
            if (errorEl) {
                errorEl.textContent = ns.t("reason_required");
                errorEl.hidden = false;
            }
            return;
        }

        var submitBtn = document.querySelector("[data-rim-confirm-submit]");
        if (submitBtn) {
            submitBtn.disabled = true;
        }

        fetchJSON(cfg.actionUrl, {
            method: "POST",
            data: { action: action, user_id: user.id, reason: reason }
        })
            .then(function (payload) {
                ns.modals.close("[data-rim-confirm-modal]");
                ns.state.selectedUser = payload.user;
                ns.render.detail(payload.user);

                if (action === "set_password" && payload.password) {
                    // Parol YALNIZ BURADA görünür — heç yerdə saxlanılmır.
                    ns.modals.showPassword(payload.password);
                }
                if (action === "restore" && payload.restore_notices) {
                    // Bərpa natamam ola bilər — «sakit uğur» qadağandır.
                    ns.modals.showNotices(payload.restore_notices);
                }
                actions.search();
            })
            .catch(function (err) {
                if (errorEl) {
                    errorEl.textContent = ns.errorMessage(err);
                    errorEl.hidden = false;
                }
            })
            .then(function () {
                if (submitBtn) {
                    submitBtn.disabled = false;
                }
            });
    };

    /* ── Şəxsi məlumat redaktəsi ────────────────────────────────────────── */

    actions.saveEdit = function saveEdit() {
        var cfg = ns.config();
        var fetchJSON = http();
        var user = ns.state.selectedUser;
        if (!cfg || !fetchJSON || !user) {
            return;
        }

        var payload = { action: "edit", user_id: user.id, reason: "" };
        var inputs = document.querySelectorAll("[data-rim-edit-field]");
        Array.prototype.forEach.call(inputs, function (input) {
            payload[input.dataset.rimEditField] = input.value;
        });

        var errorEl = document.querySelector("[data-rim-edit-error]");
        var saveBtn = document.querySelector("[data-rim-edit-save]");
        if (errorEl) {
            errorEl.hidden = true;
        }
        if (saveBtn) {
            saveBtn.disabled = true;
        }

        fetchJSON(cfg.actionUrl, { method: "POST", data: payload })
            .then(function (response) {
                ns.state.selectedUser = response.user;
                ns.render.detail(response.user);
                actions.search();
            })
            .catch(function (err) {
                var freshError = document.querySelector("[data-rim-edit-error]");
                if (freshError) {
                    freshError.textContent = ns.errorMessage(err);
                    freshError.hidden = false;
                }
            })
            .then(function () {
                var freshBtn = document.querySelector("[data-rim-edit-save]");
                if (freshBtn) {
                    freshBtn.disabled = false;
                }
            });
    };
})(window, document);
