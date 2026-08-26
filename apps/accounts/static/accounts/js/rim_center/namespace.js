/* RİM mərkəzi — namespace + paylaşılan köməkçilər.
 *
 * Bölmə AJAX ilə swap olunur, ona görə bütün init `EMSReady` altındadır və
 * DOM axtarışları hər dəfə yenidən aparılır (bax docs/frontend/AJAX_SAFE_JS_PATTERN.md).
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});

    /** Panelin kök elementi — swap olmayıbsa `null` (null-safe istifadə edin). */
    ns.root = function root() {
        return document.querySelector("[data-rim-root]");
    };

    /** Kök elementin `data-*` konfiqurasiyası. */
    ns.config = function config() {
        var el = ns.root();
        if (!el) {
            return null;
        }
        return {
            searchUrl: el.dataset.searchUrl || "",
            actionUrl: el.dataset.actionUrl || "",
            detailUrlTemplate: el.dataset.detailUrlTemplate || "",
            roleAssignmentUrl: el.dataset.roleAssignmentUrl || "",
            canSetPassword: el.dataset.canSetPassword === "1",
            canBlock: el.dataset.canBlock === "1",
            canSoftDelete: el.dataset.canSoftDelete === "1",
            canEdit: el.dataset.canEdit === "1",
            minReasonLength: parseInt(el.dataset.minReasonLength, 10) || 3,
            maxReasonLength: parseInt(el.dataset.maxReasonLength, 10) || 300
        };
    };

    /** Şablondakı JSON blokundan tərcümələr (xarici JS `{% trans %}` görmür). */
    ns.i18n = function i18n() {
        var el = document.querySelector("[data-rim-i18n]");
        if (!el) {
            return {};
        }
        try {
            return JSON.parse(el.textContent || "{}");
        } catch (err) {
            return {};
        }
    };

    /** Tərcümə açarı; tapılmasa açarın özü. */
    ns.t = function t(key) {
        var dict = ns.i18n();
        return dict[key] || key;
    };

    /** XSS qoruması — bütün server datası bu filtrdən keçib DOM-a girir. */
    ns.escape = function escape(value) {
        if (value === null || value === undefined) {
            return "";
        }
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    };

    /** Sadə debounce — axtarış hər klavişdə sorğu atmasın. */
    ns.debounce = function debounce(fn, wait) {
        var timer = null;
        return function debounced() {
            var args = arguments;
            var self = this;
            window.clearTimeout(timer);
            timer = window.setTimeout(function () {
                fn.apply(self, args);
            }, wait);
        };
    };

    /** `/accounts/rim/user/0/` şablonundan real URL. */
    ns.detailUrl = function detailUrl(userId) {
        var cfg = ns.config();
        if (!cfg || !cfg.detailUrlTemplate) {
            return "";
        }
        return cfg.detailUrlTemplate.replace(/0\/$/, String(userId) + "/");
    };

    /** Server xətasından istifadəçiyə göstəriləcək mətn. */
    ns.errorMessage = function errorMessage(err) {
        if (err && err.payload && err.payload.message) {
            return err.payload.message;
        }
        return ns.t("error");
    };

    /** Panelin cari vəziyyəti (səhifə, sorğu, status, seçilmiş istifadəçi). */
    ns.state = {
        query: "",
        status: "all",
        page: 1,
        selectedUser: null,
        pendingAction: null
    };
})(window, document);
