/* =========================================================================
   «Audit jurnalı» — bölmə-xüsusi davranış (2026-09-08).

   1) nisbi vaxt ipucu («2 saat əvvəl») — hər sətrin `<time datetime>`-ından;
   2) əməliyyat bölgüsü zolağının seqment enləri (`data-al-pct`, inline style yox);
   3) sətir kliki / «Detal» → çekmecə: `audit:detail` JSON-u render olunur
      (meta, səbəb, əvvəl → sonra fərqi, xam JSON), «bu icraçı / eyni sorğu»
      filtr linkləri;
   4) KPI kartı (`ems:kpi-filter`) və leqenda düymələri filtr panelinin
      select-ini dəyişib avto-tətbiq edir; «Yenilə» paneli yerində yükləyir.

   AJAX-safe: hər şey `EMSDelegate` / `EMSReady` ilə; seçicilər `[data-al-…]`
   ilə UNİKALDIR (EMSDelegate eyni «hadisə|seçici» açarını əvəz edir).
   Mətnlər data-atributlardan gəlir (xarici JS şablondan keçmir).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (!window.EMSDelegate || window.__emsAuditLogBound) {
        return;
    }
    window.__emsAuditLogBound = true;

    var DRAWER_ID = "alDetailDrawer";
    var SECTION = "audit-log";
    var REL_MAX_DAYS = 30;
    var state = { url: "", id: "", entry: null };

    function root() {
        return document.querySelector("[data-al-root]");
    }

    function esc(value) {
        return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
        });
    }

    function fmt(template, args) {
        var index = 0;
        return String(template || "").replace(/%[sd]/g, function () {
            var value = args[index];
            index += 1;
            return value === null || value === undefined ? "" : String(value);
        });
    }

    function t(host, key) {
        return host ? host.getAttribute("data-t-" + key) || "" : "";
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function loadSection(url) {
        if (typeof window.EMSProfileLoadSection === "function" && document.querySelector('[data-profile-section-panel="' + SECTION + '"]')) {
            window.EMSProfileLoadSection(SECTION, url);
            return true;
        }
        return false;
    }

    /* ---- Nisbi vaxt ------------------------------------------------------- */

    function relativeLabel(host, iso) {
        var then = Date.parse(iso);
        if (isNaN(then)) {
            return "";
        }
        var diff = Math.max(0, Date.now() - then);
        var minutes = Math.floor(diff / 60000);
        if (minutes < 1) {
            return t(host, "rel-now");
        }
        if (minutes < 60) {
            return fmt(t(host, "rel-min"), [minutes]);
        }
        var hours = Math.floor(minutes / 60);
        if (hours < 24) {
            return fmt(t(host, "rel-hour"), [hours]);
        }
        var days = Math.floor(hours / 24);
        if (days > REL_MAX_DAYS) {
            return "";
        }
        return fmt(t(host, "rel-day"), [days]);
    }

    function refreshRelative() {
        var host = root();
        if (!host) {
            return;
        }
        var cells = host.querySelectorAll("[data-al-time]");
        for (var i = 0; i < cells.length; i += 1) {
            var rel = cells[i].parentNode ? cells[i].parentNode.querySelector("[data-al-rel]") : null;
            if (!rel) {
                continue;
            }
            var label = relativeLabel(host, cells[i].getAttribute("datetime"));
            rel.textContent = label;
            rel.hidden = !label;
        }
    }

    /* ---- Bölgü zolağı ----------------------------------------------------- */

    function sizeMix() {
        var host = root();
        if (!host) {
            return;
        }
        var segments = host.querySelectorAll("[data-al-mix] [data-al-pct]");
        for (var i = 0; i < segments.length; i += 1) {
            var pct = parseFloat(segments[i].getAttribute("data-al-pct"));
            if (!isNaN(pct)) {
                // CSSOM ilə ölçü — CSP `style-src-attr` inline atributuna toxunmur.
                segments[i].style.flexGrow = String(Math.max(pct, 0.5));
                segments[i].style.flexBasis = "0";
            }
        }
    }

    /* ---- Filtr panelinə yazma --------------------------------------------- */

    function filterForm() {
        var host = root();
        return host ? host.querySelector("form[data-ems-filters]") : null;
    }

    function setSelectAndApply(name, value) {
        var form = filterForm();
        if (!form) {
            return;
        }
        var select = form.querySelector('select[name="' + name + '"]');
        if (!select) {
            return;
        }
        var found = false;
        for (var i = 0; i < select.options.length; i += 1) {
            if (select.options[i].value === value) {
                found = true;
                break;
            }
        }
        select.value = found ? value : "";
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.sync === "function") {
            window.EMSBootstrapSelect.sync(select);
        }
        if (window.EMSFilterBar && typeof window.EMSFilterBar.apply === "function") {
            window.EMSFilterBar.apply(form);
        } else {
            form.requestSubmit ? form.requestSubmit() : form.submit();
        }
    }

    /* ---- Çekmecə ---------------------------------------------------------- */

    function drawer() {
        return document.getElementById(DRAWER_ID);
    }

    function detailHost() {
        var el = drawer();
        return el ? el.querySelector("[data-al-detail]") : null;
    }

    function setBusy(host, busy) {
        var skeleton = host.querySelector("[data-al-detail-skeleton]");
        if (skeleton) {
            skeleton.hidden = !busy;
        }
        host.setAttribute("aria-busy", busy ? "true" : "false");
    }

    function showError(host, message) {
        var el = host.querySelector("[data-al-detail-error]");
        if (el) {
            el.textContent = message || "";
            el.hidden = !message;
        }
    }

    function isPlainObject(value) {
        return value !== null && typeof value === "object" && !Array.isArray(value);
    }

    function fmtValue(host, value) {
        if (value === null || value === undefined) {
            return '<span class="al-val al-val--empty">' + esc(t(host, "empty")) + "</span>";
        }
        if (typeof value === "boolean") {
            return '<span class="al-val al-val--mono">' + esc(value ? t(host, "yes") : t(host, "no")) + "</span>";
        }
        if (typeof value === "number") {
            return '<span class="al-val al-val--mono">' + esc(String(value)) + "</span>";
        }
        if (typeof value === "string") {
            if (!value.length) {
                return '<span class="al-val al-val--empty">' + esc(t(host, "empty-string")) + "</span>";
            }
            return '<span class="al-val">' + esc(value) + "</span>";
        }
        if (Array.isArray(value) || isPlainObject(value)) {
            var text;
            try {
                text = JSON.stringify(value, null, 2);
            } catch (err) {
                text = String(value);
            }
            return '<pre class="al-json">' + esc(text) + "</pre>";
        }
        return '<span class="al-val">' + esc(String(value)) + "</span>";
    }

    var STATE_TONE = { added: "success", removed: "danger", changed: "primary", same: "muted" };

    function diffRow(host, item) {
        var state = STATE_TONE[item.state] ? item.state : "changed";
        return (
            '<tr class="al-diff__row al-diff__row--' + state + '"' + (state === "same" ? " data-al-same hidden" : "") + ">" +
            '<th scope="row">' + esc(item.key) + "</th>" +
            '<td class="al-diff__old">' + fmtValue(host, item.old) + "</td>" +
            '<td class="al-diff__new">' + fmtValue(host, item.new) + "</td>" +
            '<td><span class="ems-badge ems-badge--' + STATE_TONE[state] + '">' + esc(t(host, state)) + "</span></td>" +
            "</tr>"
        );
    }

    function metaItem(label, valueHtml, wide) {
        return (
            '<div class="al-meta__item' + (wide ? " al-meta__item--wide" : "") + '"><dt>' + esc(label) + "</dt><dd>" + valueHtml + "</dd></div>"
        );
    }

    function copyButton(host, value) {
        if (!value || !window.navigator || !window.navigator.clipboard) {
            return "";
        }
        return (
            '<button type="button" class="al-copy" data-al-copy="' + esc(value) + '" title="' + esc(t(host, "copy")) + '">' +
            '<i class="fas fa-copy" aria-hidden="true"></i></button>'
        );
    }

    function render(host, entry) {
        var body = host.querySelector("[data-al-detail-body]");
        if (!body) {
            return;
        }
        var actor = entry.actor;
        var actorHtml = actor
            ? '<span class="al-actor"><span class="al-avatar" aria-hidden="true">' + esc(actor.initials) + "</span>" +
              '<span class="al-actor__main"><a class="al-actor__name" href="' + esc(actor.url) + '" target="_blank" rel="noopener">' + esc(actor.name) + "</a>" +
              '<span class="al-actor__user ems-mono">@' + esc(actor.username) + "</span></span></span>"
            : '<span class="al-muted">' + esc(t(host, "anon")) + "</span>";
        var resource = entry.resource || {};
        var resourceHtml = resource.repr ? esc(resource.repr) : '<span class="al-muted">—</span>';
        var typeHtml = resource.type ? '<span class="al-res__type">' + esc(resource.type) + "</span>" : '<span class="al-muted">—</span>';
        if (resource.id) {
            typeHtml += ' <span class="al-meta__mono">#' + esc(resource.id) + "</span>";
        }
        var objectHtml = resource.content_type
            ? '<span class="al-meta__mono">' + esc(resource.content_type) + (resource.object_id ? " #" + esc(resource.object_id) : "") + "</span>"
            : "";

        var html =
            '<div class="al-detail__head">' +
            '<span class="ems-badge ems-badge--' + esc(entry.action_tone || "neutral") + '">' + esc(entry.action_label) + "</span>" +
            '<h3 class="al-detail__title">' + resourceHtml + "</h3>" +
            '<span class="al-detail__time">' + esc(entry.created_display) + "</span>" +
            "</div>";

        html += '<dl class="al-meta">';
        html += metaItem(t(host, "actor"), actorHtml);
        html += metaItem(t(host, "time"), esc(entry.created_display) + ' <span class="al-time__rel">' + esc(relativeLabel(root() || host, entry.created_at)) + "</span>");
        if (entry.organization) {
            html += metaItem(t(host, "org"), esc(entry.organization));
        }
        html += metaItem(t(host, "type"), typeHtml);
        if (objectHtml) {
            html += metaItem(t(host, "object"), objectHtml);
        }
        html += metaItem(t(host, "ip"), entry.ip_address ? '<span class="al-meta__mono">' + esc(entry.ip_address) + "</span>" + copyButton(host, entry.ip_address) : '<span class="al-muted">—</span>');
        html += metaItem(t(host, "request"), entry.request_id ? '<span class="al-meta__mono">' + esc(entry.request_id) + "</span>" + copyButton(host, entry.request_id) : '<span class="al-muted">—</span>');
        html += metaItem(t(host, "record"), '<span class="al-meta__mono">' + esc(entry.id) + "</span>" + copyButton(host, entry.id));
        if (entry.user_agent) {
            html += metaItem(t(host, "agent"), '<span class="al-meta__agent">' + esc(entry.user_agent) + "</span>", true);
        }
        html += "</dl>";

        html += '<section class="al-section"><div class="al-section__head"><h4 class="al-section__title">' + esc(t(host, "reason")) + "</h4></div>";
        if (entry.reason) {
            html += '<blockquote class="al-quote">' + esc(entry.reason) + "</blockquote>";
        } else if (entry.reason_required) {
            html += '<p class="al-quote al-quote--missing"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ' + esc(t(host, "no-reason")) + " — " + esc(t(host, "reason-required")) + "</p>";
        } else {
            html += '<p class="al-empty">' + esc(t(host, "no-reason")) + "</p>";
        }
        html += "</section>";

        var diff = entry.diff || [];
        var sameCount = 0;
        for (var i = 0; i < diff.length; i += 1) {
            if (diff[i].state === "same") {
                sameCount += 1;
            }
        }
        html += '<section class="al-section"><div class="al-section__head"><h4 class="al-section__title">' + esc(t(host, "changes")) + "</h4>";
        if (diff.length) {
            html += '<span class="al-section__count">' + esc(fmt(t(host, "changed-count"), [entry.changed_count || 0])) + "</span>";
        }
        html += "</div>";
        if (!diff.length) {
            html += '<p class="al-empty">' + esc(t(host, "no-changes")) + "</p>";
        } else {
            html += '<div class="al-diffwrap"><table class="al-diff"><thead><tr>' +
                '<th scope="col">' + esc(t(host, "field")) + "</th>" +
                '<th scope="col">' + esc(t(host, "before")) + "</th>" +
                '<th scope="col">' + esc(t(host, "after")) + "</th>" +
                '<th scope="col">' + esc(t(host, "state")) + "</th>" +
                "</tr></thead><tbody>";
            for (var j = 0; j < diff.length; j += 1) {
                html += diffRow(host, diff[j]);
            }
            html += "</tbody></table></div>";
            if (sameCount) {
                html += '<button type="button" class="ems-btn ems-btn--sm ems-btn--ghost al-diff__toggle" data-al-toggle-same aria-pressed="false"' +
                    ' data-show="' + esc(fmt(t(host, "show-same"), [sameCount])) + '" data-hide="' + esc(t(host, "hide-same")) + '">' +
                    esc(fmt(t(host, "show-same"), [sameCount])) + "</button>";
            }
        }
        html += "</section>";

        var raw = entry.raw || {};
        if (raw.old_values || raw.new_values || raw.changes) {
            var rawText;
            try {
                rawText = JSON.stringify(raw, null, 2);
            } catch (err) {
                rawText = "";
            }
            html += '<details class="al-raw"><summary>' + esc(t(host, "raw")) + "</summary>" + '<pre class="al-json">' + esc(rawText) + "</pre></details>";
        }
        body.innerHTML = html;

        var links = drawer() ? drawer().querySelector("[data-al-detail-links]") : null;
        if (links) {
            var linkHtml = "";
            var filterLinks = entry.filter_links || {};
            if (filterLinks.actor) {
                linkHtml += '<a class="ems-btn ems-btn--sm ems-btn--ghost" href="' + esc(filterLinks.actor) + '" data-al-filter-link><i class="fas fa-user" aria-hidden="true"></i> ' + esc(t(host, "filter-actor")) + "</a>";
            }
            if (filterLinks.request) {
                linkHtml += '<a class="ems-btn ems-btn--sm ems-btn--ghost" href="' + esc(filterLinks.request) + '" data-al-filter-link><i class="fas fa-link" aria-hidden="true"></i> ' + esc(t(host, "filter-request")) + "</a>";
            }
            links.innerHTML = linkHtml;
        }
    }

    function load(host) {
        if (!window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
            return;
        }
        setBusy(host, true);
        showError(host, "");
        var body = host.querySelector("[data-al-detail-body]");
        if (body) {
            body.innerHTML = "";
        }
        var links = drawer() ? drawer().querySelector("[data-al-detail-links]") : null;
        if (links) {
            links.innerHTML = "";
        }
        var requestUrl = state.url;
        window.EMSCore.fetchJSON(requestUrl)
            .then(function (payload) {
                if (requestUrl !== state.url) {
                    return; // başqa sətir açılıb — köhnə cavab atılır
                }
                setBusy(host, false);
                state.entry = payload && payload.entry ? payload.entry : null;
                if (state.entry) {
                    render(host, state.entry);
                } else {
                    showError(host, t(host, "error"));
                }
            })
            .catch(function (err) {
                if (requestUrl !== state.url) {
                    return;
                }
                setBusy(host, false);
                showError(host, (err && err.payload && err.payload.message) || t(host, "error"));
            });
    }

    function openDetail(btn) {
        var el = drawer();
        var host = detailHost();
        if (!el || !host) {
            return;
        }
        state.url = btn.getAttribute("data-url") || "";
        state.id = btn.getAttribute("data-al-id") || "";
        state.entry = null;
        if (!state.url) {
            return;
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.open(el);
        }
        load(host);
    }

    /* ---- Hadisələr ------------------------------------------------------- */

    window.EMSDelegate.on("click", "[data-al-open]", function (event, btn) {
        event.preventDefault();
        openDetail(btn);
    });

    // Sətrin özünə klik = «Detal». Link/düymə/mətn seçimi istisnadır.
    window.EMSDelegate.on("click", "[data-al-rows] .ems-table tbody tr", function (event, row) {
        if (event.defaultPrevented || event.button !== 0) {
            return;
        }
        if (event.target && event.target.closest && event.target.closest("a, button, input, select, textarea, label, [data-al-stop]")) {
            return;
        }
        var selection = window.getSelection ? window.getSelection() : null;
        if (selection && String(selection).length) {
            return;
        }
        var btn = row.querySelector("[data-al-open]");
        if (btn) {
            openDetail(btn);
        }
    });

    window.EMSDelegate.on("click", "[data-al-toggle-same]", function (event, btn) {
        event.preventDefault();
        var scope = btn.closest(".al-section") || document;
        var open = btn.getAttribute("aria-pressed") !== "true";
        var rows = scope.querySelectorAll("[data-al-same]");
        for (var i = 0; i < rows.length; i += 1) {
            rows[i].hidden = !open;
        }
        btn.setAttribute("aria-pressed", open ? "true" : "false");
        btn.textContent = open ? btn.getAttribute("data-hide") : btn.getAttribute("data-show");
    });

    window.EMSDelegate.on("click", "[data-al-copy]", function (event, btn) {
        event.preventDefault();
        var value = btn.getAttribute("data-al-copy") || "";
        var host = detailHost();
        if (!value || !window.navigator || !window.navigator.clipboard) {
            return;
        }
        window.navigator.clipboard.writeText(value).then(function () {
            toast(t(host, "copied"), "success");
        }, function () { /* icazə yoxdur — səssiz keç */ });
    });

    // Çekmecədən filtr linki — SPA-da paneli yerində yükləyir, qabıqsız səhifədə adi keçid.
    window.EMSDelegate.on("click", "[data-al-filter-link]", function (event, link) {
        var href = link.getAttribute("href") || "";
        if (!href) {
            return;
        }
        if (loadSection(href)) {
            event.preventDefault();
            if (window.EMSOverlay) {
                window.EMSOverlay.close(drawer());
            }
        }
    });

    window.EMSDelegate.on("click", "[data-al-filter-action]", function (event, btn) {
        event.preventDefault();
        var key = btn.getAttribute("data-al-filter-action") || "";
        var pressed = btn.getAttribute("aria-pressed") === "true";
        setSelectAndApply("al_action", pressed ? "" : key);
    });

    window.EMSDelegate.on("click", "[data-al-refresh]", function (event, btn) {
        event.preventDefault();
        btn.disabled = true;
        if (!loadSection(window.location.href)) {
            window.location.reload();
        }
    });

    // KPI kartı (nav.js `ems:kpi-filter`) → «Yalnız» select-i.
    window.EMSReady.once("al-kpi-filter", function () {
        document.addEventListener("ems:kpi-filter", function (event) {
            var target = event.target;
            if (!target || !target.closest || !target.closest("[data-al-root]")) {
                return;
            }
            var detail = event.detail || {};
            setSelectAndApply("al_flag", detail.filter || "");
        });
    });

    // Nisbi vaxt hər dəqiqə təzələnir (yalnız bölmə görünəndə iş görür).
    window.EMSReady.once("al-rel-timer", function () {
        window.setInterval(refreshRelative, 60000);
    });

    window.EMSReady(function () {
        refreshRelative();
        sizeMix();
    });
})(window, document);
