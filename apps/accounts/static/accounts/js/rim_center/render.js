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
            deleted: "status_deleted",
            archived: "status_archived"
        }[user.status] || "status_active";
        // Sahib 2026-11-04: əməkdaş arxivi («işdən ayrılıb») tələbə arxivindən (məzun/xaric) ayrı yazılır.
        if (user.status === "archived" && user.archive_kind === "staff") {
            labelKey = "status_archived_staff";
        }
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

    function lastLogin(user) {
        if (!user.last_login) {
            return '<span class="rim-flag"><i class="fas fa-user-clock"></i> ' + esc(ns.t("never_logged_in")) + "</span>";
        }
        var when = new Date(user.last_login);
        var text = isNaN(when.getTime()) ? user.last_login : when.toLocaleString(document.documentElement.lang || undefined, {
            year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
        });
        return '<span class="rim-flag"><i class="fas fa-right-to-bracket"></i> ' + esc(ns.t("last_login")) + ": " + esc(text) + "</span>";
    }

    function flags(user) {
        var out = [lastLogin(user)];
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
        // Sorğusuz açılış: nə göstərildiyini izah edən qısa sətir (ekran «boş» deyil, ən yenilərdir).
        var hint = payload && !payload.query && payload.sort === "recent"
            ? '<p class="rim-hint"><i class="fas fa-clock-rotate-left" aria-hidden="true"></i> ' + esc(ns.t("latest_hint")) + "</p>"
            : "";
        container.innerHTML = hint + results.map(render.card).join("");
    };

    /** Status tablarının sayları (cari axtarış + növ + vəziyyət filtrlərinə görə). */
    render.counts = function counts(map) {
        var nodes = document.querySelectorAll("[data-rim-count]");
        Array.prototype.forEach.call(nodes, function (node) {
            var key = node.getAttribute("data-rim-count");
            var value = map && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : null;
            node.textContent = value === null ? "" : String(value);
            node.classList.toggle("is-zero", value === 0);
        });
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

    // Redaktə formasında telefon: server şablonu (`{% phone_field %}`) klonlanır, ölkə + yerli nömrə təyin olunur.
    render.mountPhone = function mountPhone(bodyEl, user) {
        var slot = bodyEl.querySelector("[data-rim-phone-slot]");
        var tpl = document.querySelector("template[data-rim-phone-template]");
        if (!slot || !tpl) {
            return;
        }
        slot.appendChild(tpl.content.cloneNode(true));
        var box = slot.querySelector("[data-phone-field]");
        if (!box) {
            return;
        }
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.init(slot);
        }
        if (window.EMSPhoneField) {
            window.EMSPhoneField.set(box, user.phone_country, user.phone_national != null ? user.phone_national : user.phone);
        }
    };

    /* Detal kartı (2026-11-04) bölmələrlə `detail_view.js`-də qurulur; köməkçilər ora açılır. */
    render.statusBadge = statusBadge;
    render.roleChips = roleChips;
    render.flags = flags;

    /** Detal modalının məzmunu — `detail_view.js` (Əsas məlumatlar · Vəzifə və bölmə · Rollar · Status). */
    render.detail = function detail(user) {
        if (ns.detailView) {
            ns.detailView.render(user);
        }
    };
})(window, document);
