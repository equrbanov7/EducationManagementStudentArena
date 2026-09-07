/* RİM «yeni inzibati bölmə» — şöbə / mərkəz / institut / laboratoriya.
 *
 * ⚠️ YAZI YOLU BURADA DEYİL: forma MÖVCUD struktur-ağac endpoint-inə gedir
 * (`organizations:structure_tree_action`, `action=create_child`) — eyni
 * `unit.tree_manage` açarı, eyni görünürlük qapısı, eyni audit sətri. Ona görə
 * cavab formatı da ağac ekranının cavabıdır: `{ok, unit_id}` və ya
 * `{ok:false, error, message}`.
 *
 * Server `request.POST` oxuyur → gövdə `application/x-www-form-urlencoded`
 * olmalıdır (JSON gövdə `request.POST`-a düşmür). Bu, `teaching_office.js`-dəki
 * naxışın eynisidir.
 *
 * Qaydalar (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md):
 *   · inline JS yoxdur — URL-lər `data-*`, mətnlər JSON blokundadır;
 *   · `EMSDelegate.on` ilə document səviyyəsində delegasiya (swap-safe);
 *   · dialoq yoxdursa (icazəsiz operator) heç nə etmir — null-safe;
 *   · selektorlar `#rimc-admin-unit` ilə DARALDILIB: `EMSDelegate` eyni
 *     hadisə+selektor cütünü ƏVƏZ edir, ona görə hesab axınının selektorları
 *     (`[data-rimc-option]`, `[data-rimc-open]`) burada TƏKRAR YAZILMIR.
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCreate = window.EMSRimCreate || {});
    if (!window.EMSDelegate || !window.EMSReady) {
        return;
    }

    var unit = (ns.unit = {});
    var DIALOG = "rimc-admin-unit";
    var REQUIRED = ["parent", "name", "unit_type"];
    /* Server xəta kodu → sahə. Kod maşın-oxunaqlıdır (`structure_actions._error`),
     * mətn isə serverdən gəlir — burada təkrar tərcümə edilmir. */
    var ERROR_FIELDS = {
        not_found: "parent",
        name_required: "name",
        bad_type: "unit_type"
    };

    var state = { busy: false };

    function root() {
        return document.querySelector("[data-rimc-root]");
    }

    function dialog() {
        return document.getElementById(DIALOG);
    }

    function t(key) {
        return ns.t ? ns.t(key) : key;
    }

    function field(name) {
        var host = dialog();
        return host ? host.querySelector('[data-rimu-field="' + name + '"]') : null;
    }

    function value(name) {
        var el = field(name);
        return el ? String(el.value || "").trim() : "";
    }

    /* ── Sahə xətaları ──────────────────────────────────────────────────── */

    function clearErrors() {
        var host = dialog();
        if (!host) {
            return;
        }
        var boxes = host.querySelectorAll("[data-rimu-error]");
        Array.prototype.forEach.call(boxes, function (box) {
            box.hidden = true;
            box.textContent = "";
        });
        var summary = host.querySelector("[data-rimu-form-error]");
        if (summary) {
            summary.hidden = true;
            summary.textContent = "";
        }
    }

    function showError(payload) {
        var host = dialog();
        if (!host) {
            return;
        }
        clearErrors();
        var code = (payload && payload.error) || "";
        var message = (payload && payload.message) || t("unit_failed");
        var box = host.querySelector('[data-rimu-error="' + (ERROR_FIELDS[code] || "") + '"]');
        if (box) {
            box.textContent = message;
            box.hidden = false;
            return;
        }
        var summary = host.querySelector("[data-rimu-form-error]");
        if (summary) {
            summary.textContent = message;
            summary.hidden = false;
        }
    }

    /* ── Vəziyyət ───────────────────────────────────────────────────────── */

    /** Məcburi sahələr doludursa «Bölməni yarat» aktivləşir. */
    unit.refresh = function refresh() {
        var host = dialog();
        var button = host ? host.querySelector("[data-rimu-submit]") : null;
        if (!button) {
            return;
        }
        var ok = !state.busy;
        REQUIRED.forEach(function (name) {
            if (!value(name)) {
                ok = false;
            }
        });
        button.disabled = !ok;
        button.setAttribute("aria-disabled", ok ? "false" : "true");
    };

    /* Seçici (combo) dəyəri `create_combo.js`-in ÖZ handler-ində yazılır; onun
     * selektorunu təkrar qeyd etsək handler ƏVƏZ olunardı. Ona görə selektor
     * dialoqla daraldılıb və oxu `setTimeout(0)` ilə seçimdən SONRAYA atılır. */
    function refreshLater() {
        window.setTimeout(unit.refresh, 0);
    }

    function setBusy(busy) {
        state.busy = busy;
        var host = dialog();
        var body = host ? host.querySelector("[data-rimu-body]") : null;
        var button = host ? host.querySelector("[data-rimu-submit]") : null;
        if (body) {
            body.setAttribute("aria-busy", busy ? "true" : "false");
        }
        if (button) {
            if (busy) {
                button.dataset.rimuLabel = button.dataset.rimuLabel || button.textContent;
                button.textContent = t("unit_busy");
            } else if (button.dataset.rimuLabel) {
                button.textContent = button.dataset.rimuLabel;
            }
        }
        unit.refresh();
        if (busy && button) {
            button.disabled = true;
            button.setAttribute("aria-disabled", "true");
        }
    }

    function setDone(done) {
        var host = dialog();
        if (!host) {
            return;
        }
        var body = host.querySelector("[data-rimu-body]");
        var panel = host.querySelector("[data-rimu-done]");
        if (body) {
            body.hidden = done;
        }
        if (panel) {
            panel.hidden = !done;
        }
        [
            ["[data-rimu-submit]", !done],
            ["[data-rimu-cancel]", !done],
            ["[data-rimu-again]", done],
            ["[data-rimu-tree-link]", done],
            ["[data-rimu-done-close]", done]
        ].forEach(function (pair) {
            var el = host.querySelector(pair[0]);
            if (el) {
                el.hidden = !pair[1];
            }
        });
    }

    function reset() {
        var host = dialog();
        if (!host) {
            return;
        }
        var form = host.querySelector("[data-rimu-form]");
        if (form) {
            form.reset();
        }
        if (ns.combo && ns.combo.reset) {
            // YALNIZ bu dialoqun seçicisi — hesab formunun seçiciləri toxunulmur.
            ns.combo.reset(host);
        }
        clearErrors();
        setDone(false);
        setBusy(false);
    }

    /* ── Uğur vəziyyəti ─────────────────────────────────────────────────── */

    function typeLabel() {
        var el = field("unit_type");
        if (!el || el.selectedIndex < 0) {
            return "";
        }
        var option = el.options[el.selectedIndex];
        return option ? option.textContent : "";
    }

    function parentLabel() {
        var host = dialog();
        var input = host ? host.querySelector("[data-rimc-combo-input]") : null;
        return input ? input.value : "";
    }

    function showDone(unitId) {
        var host = dialog();
        if (!host) {
            return;
        }
        var pairs = [
            ["[data-rimu-done-name]", value("name")],
            ["[data-rimu-done-type]", typeLabel()],
            ["[data-rimu-done-parent]", parentLabel()]
        ];
        pairs.forEach(function (pair) {
            var el = host.querySelector(pair[0]);
            if (el) {
                el.textContent = pair[1];
            }
        });
        var link = host.querySelector("[data-rimu-tree-link]");
        var base = link ? link.getAttribute("data-rimu-tree-base") || link.getAttribute("href") : "";
        if (link && base) {
            // Bazanı bir dəfə yadda saxlayırıq — ikinci yaradılışda URL üst-üstə düşməsin.
            link.setAttribute("data-rimu-tree-base", base);
            link.setAttribute("href", base + "&st_unit=" + encodeURIComponent(unitId || ""));
        }
        setDone(true);
    }

    /* ── Göndərmə ───────────────────────────────────────────────────────── */

    function body() {
        var payload = new window.URLSearchParams();
        payload.append("action", "create_child");
        payload.append("parent", value("parent"));
        payload.append("name", value("name"));
        payload.append("unit_type", value("unit_type"));
        payload.append("code", value("code"));
        return payload.toString();
    }

    function submit() {
        var host = root();
        var fetchJSON = window.EMSCore && window.EMSCore.fetchJSON;
        var url = host ? host.getAttribute("data-unit-action-url") : "";
        if (!url || !fetchJSON || state.busy) {
            return;
        }
        if (!value("parent")) {
            // Seçicidə mətn yazılıb, amma siyahıdan SEÇİLMƏYİB — id boşdur.
            showError({ error: "not_found", message: t("unit_parent_required") });
            return;
        }
        clearErrors();
        setBusy(true);
        fetchJSON(url, {
            method: "POST",
            body: body(),
            headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" }
        })
            .then(function (payload) {
                showDone((payload && payload.unit_id) || "");
            })
            .catch(function (err) {
                showError(err && err.payload);
            })
            .then(function () {
                setBusy(false);
            });
    }

    /* ── Hadisələr ──────────────────────────────────────────────────────── */

    unit.open = function open() {
        if (!window.EMSOverlay || !dialog()) {
            return;
        }
        reset();
        window.EMSOverlay.open(DIALOG);
    };

    window.EMSDelegate.on("submit", "[data-rimu-form]", function (event) {
        event.preventDefault();
        submit();
    });

    window.EMSDelegate.on("click", "[data-rimu-submit]", function (event) {
        event.preventDefault();
        submit();
    });

    window.EMSDelegate.on("click", "[data-rimu-again]", function (event) {
        event.preventDefault();
        reset();
        var host = dialog();
        var first = host ? host.querySelector("[data-rimc-combo-input]") : null;
        if (first) {
            first.focus();
        }
    });

    window.EMSDelegate.on("input", "[data-rimu-field]", unit.refresh);
    window.EMSDelegate.on("change", "[data-rimu-field]", unit.refresh);
    window.EMSDelegate.on("mousedown", "#rimc-admin-unit [data-rimc-option]", refreshLater);
    window.EMSDelegate.on("keydown", "#rimc-admin-unit [data-rimc-combo-input]", refreshLater);
    window.EMSDelegate.on("input", "#rimc-admin-unit [data-rimc-combo-input]", refreshLater);

    window.EMSReady(function () {
        if (!dialog()) {
            return; // İcazəsiz operator — dialoq render olunmayıb.
        }
        unit.refresh();
    });
})(window, document);
