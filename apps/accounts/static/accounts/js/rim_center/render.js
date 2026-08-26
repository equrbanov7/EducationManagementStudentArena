/* RİM mərkəzi — siyahı və detal kartının render-i. */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});
    var render = (ns.render = {});
    var esc = ns.escape;

    function statusBadge(user) {
        var labelKey = {
            active: "status_active",
            blocked: "status_blocked",
            deleted: "status_deleted"
        }[user.status] || "status_active";
        return (
            '<span class="rim-badge rim-badge--' +
            esc(user.status) +
            '">' +
            esc(ns.t(labelKey)) +
            "</span>"
        );
    }

    function roleChips(user) {
        var roles = user.roles || [];
        if (!roles.length) {
            return '<span class="rim-role-chip">' + esc(ns.t("no_roles")) + "</span>";
        }
        // İKİLİ ROL: bir istifadəçinin eyni təşkilatda birdən çox aktiv üzvlüyü
        // ola bilər (məs. həm müəllim, həm kafedra müdiri) — hamısı göstərilir
        // və çoxlu olduqda vurğulanır ki, operator səlahiyyət fərqini görsün.
        var multi = roles.length > 1;
        return roles
            .map(function (role) {
                var title = role.scope_unit ? role.role_label + " — " + role.scope_unit : role.role_label;
                return (
                    '<span class="rim-role-chip' +
                    (multi ? " rim-role-chip--multi" : "") +
                    '" title="' +
                    esc(title) +
                    '">' +
                    esc(role.role_label) +
                    "</span>"
                );
            })
            .join("");
    }

    function flags(user) {
        var out = [];
        if (user.password_change_required) {
            out.push('<span class="rim-flag"><i class="fas fa-hourglass-half"></i> ' + esc(ns.t("password_change_required")) + "</span>");
        }
        if (!user.email_verified) {
            out.push('<span class="rim-flag"><i class="fas fa-envelope-circle-check"></i> ' + esc(ns.t("email_unverified")) + "</span>");
        }
        return out.join("");
    }

    function metaLine(user) {
        var bits = [];
        if (user.email) {
            bits.push('<span><i class="fas fa-envelope"></i> ' + esc(user.email) + "</span>");
        }
        if (user.fin) {
            bits.push("<span>" + esc(ns.t("fin")) + ": " + esc(user.fin) + "</span>");
        }
        if (user.organization) {
            bits.push('<span><i class="fas fa-building"></i> ' + esc(user.organization) + "</span>");
        }
        if (user.department) {
            bits.push("<span>" + esc(user.department) + "</span>");
        }
        return bits.join("");
    }

    /** Axtarış nəticəsinin bir kartı. Username QƏSDƏN açıq göstərilir. */
    render.card = function card(user) {
        return (
            '<article class="rim-card' +
            (user.status === "deleted" ? " rim-card--deleted" : "") +
            '" data-rim-card data-user-id="' +
            esc(user.id) +
            '">' +
            '<div class="rim-card-main">' +
            '<p class="rim-card-name">' +
            esc(user.full_name || user.username) +
            "</p>" +
            '<span class="rim-card-username"><i class="fas fa-at"></i>' +
            esc(user.username) +
            "</span>" +
            '<div class="rim-card-meta">' +
            metaLine(user) +
            "</div>" +
            '<div class="rim-card-roles">' +
            roleChips(user) +
            "</div>" +
            "</div>" +
            '<div class="rim-card-side">' +
            statusBadge(user) +
            flags(user) +
            '<div class="rim-card-actions">' +
            '<button type="button" class="rim-btn rim-btn--ghost rim-btn--sm" data-rim-open="' +
            esc(user.id) +
            '">' +
            esc(ns.t("open")) +
            "</button>" +
            "</div>" +
            "</div>" +
            "</article>"
        );
    };

    render.list = function list(payload) {
        var container = document.querySelector("[data-rim-results]");
        if (!container) {
            return;
        }
        var results = (payload && payload.results) || [];
        if (!results.length) {
            container.innerHTML = '<div class="rim-state"><i class="fas fa-user-slash"></i> ' + esc(ns.t("empty")) + "</div>";
            return;
        }
        container.innerHTML = results.map(render.card).join("");
    };

    render.state = function state(messageKey, iconClass) {
        var container = document.querySelector("[data-rim-results]");
        if (!container) {
            return;
        }
        container.innerHTML =
            '<div class="rim-state"><i class="fas ' + (iconClass || "fa-info-circle") + '"></i> ' + esc(ns.t(messageKey)) + "</div>";
    };

    render.pager = function pager(payload) {
        var container = document.querySelector("[data-rim-pager]");
        if (!container) {
            return;
        }
        if (!payload || payload.num_pages <= 1) {
            container.innerHTML = payload && payload.total
                ? '<span class="rim-pager-info">' + esc(payload.total) + " " + esc(ns.t("total_found")) + "</span>"
                : "";
            return;
        }
        container.innerHTML =
            '<button type="button" class="rim-btn rim-btn--ghost rim-btn--sm" data-rim-page="prev"' +
            (payload.has_previous ? "" : " disabled") +
            ">" +
            esc(ns.t("prev")) +
            "</button>" +
            '<span class="rim-pager-info">' +
            esc(payload.page) +
            " / " +
            esc(payload.num_pages) +
            " " +
            esc(ns.t("page_of")) +
            " — " +
            esc(payload.total) +
            " " +
            esc(ns.t("total_found")) +
            "</span>" +
            '<button type="button" class="rim-btn rim-btn--ghost rim-btn--sm" data-rim-page="next"' +
            (payload.has_next ? "" : " disabled") +
            ">" +
            esc(ns.t("next")) +
            "</button>";
    };

    function detailItem(labelKey, value) {
        return (
            '<div class="rim-detail-item"><span class="rim-detail-key">' +
            esc(ns.t(labelKey)) +
            '</span><span class="rim-detail-value">' +
            esc(value || "—") +
            "</span></div>"
        );
    }

    function editForm(user) {
        var fields = [
            ["first_name", user.first_name],
            ["last_name", user.last_name],
            ["patronymic", user.patronymic],
            ["email", user.email],
            ["phone", user.phone],
            ["fin", user.fin]
        ];
        return (
            '<p class="rim-section-title">' +
            esc(ns.t("edit")) +
            "</p>" +
            '<div class="rim-form-grid" data-rim-edit-form>' +
            fields
                .map(function (pair) {
                    var name = pair[0];
                    return (
                        '<div><label class="rim-field-label" for="rim-edit-' +
                        esc(name) +
                        '">' +
                        esc(ns.t(name)) +
                        '</label><input type="text" class="rim-input" id="rim-edit-' +
                        esc(name) +
                        '" data-rim-edit-field="' +
                        esc(name) +
                        '" value="' +
                        esc(pair[1] || "") +
                        '"></div>'
                    );
                })
                .join("") +
            "</div>" +
            '<p class="rim-error" data-rim-edit-error hidden></p>' +
            '<div class="rim-actions-row"><button type="button" class="rim-btn rim-btn--primary" data-rim-edit-save>' +
            esc(ns.t("save")) +
            "</button></div>"
        );
    }

    function actionButtons(user) {
        var actions = user.actions || {};
        var buttons = [];
        if (actions.set_password) {
            buttons.push(
                '<button type="button" class="rim-btn rim-btn--primary" data-rim-act="set_password">' +
                    '<i class="fas fa-key"></i> ' +
                    esc(ns.t("set_password")) +
                    "</button>"
            );
        }
        if (actions.block) {
            buttons.push(
                '<button type="button" class="rim-btn rim-btn--warning" data-rim-act="block">' +
                    '<i class="fas fa-ban"></i> ' +
                    esc(ns.t("block")) +
                    "</button>"
            );
        }
        if (actions.unblock) {
            buttons.push(
                '<button type="button" class="rim-btn rim-btn--ghost" data-rim-act="unblock">' +
                    '<i class="fas fa-unlock"></i> ' +
                    esc(ns.t("unblock")) +
                    "</button>"
            );
        }
        if (actions.soft_delete) {
            buttons.push(
                '<button type="button" class="rim-btn rim-btn--danger" data-rim-act="soft_delete">' +
                    '<i class="fas fa-user-slash"></i> ' +
                    esc(ns.t("soft_delete")) +
                    "</button>"
            );
        }
        if (actions.restore) {
            buttons.push(
                '<button type="button" class="rim-btn rim-btn--primary" data-rim-act="restore">' +
                    '<i class="fas fa-rotate-left"></i> ' +
                    esc(ns.t("restore")) +
                    "</button>"
            );
        }
        return '<div class="rim-actions-row">' + buttons.join("") + "</div>";
    }

    /** Detal modalının məzmunu. */
    render.detail = function detail(user) {
        var titleEl = document.querySelector("[data-rim-detail-title]");
        var bodyEl = document.querySelector("[data-rim-detail-body]");
        if (!titleEl || !bodyEl) {
            return;
        }
        titleEl.textContent = user.full_name || user.username;

        var cfg = ns.config() || {};
        var html =
            '<div class="rim-detail-grid">' +
            detailItem("username", user.username) +
            detailItem("full_name", user.full_name) +
            detailItem("email", user.email) +
            detailItem("fin", user.fin) +
            detailItem("phone", user.phone) +
            "</div>" +
            '<p class="rim-section-title">' +
            esc(ns.t("roles")) +
            "</p>" +
            '<div class="rim-card-roles">' +
            roleChips(user) +
            "</div>" +
            '<div class="rim-actions-row"><a class="rim-btn rim-btn--ghost rim-btn--sm" href="' +
            esc(user.role_assignment_url || cfg.roleAssignmentUrl || "#") +
            '">' +
            esc(ns.t("manage_roles")) +
            "</a></div>" +
            actionButtons(user);

        if (user.actions && user.actions.edit) {
            html += editForm(user);
        }
        bodyEl.innerHTML = html;
    };
})(window, document);
