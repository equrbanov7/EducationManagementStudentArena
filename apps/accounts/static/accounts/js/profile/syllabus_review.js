/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus təsdiqi — ekranın DAVRANIŞI (dizayn təhvili §3.3)
   ───────────────────────────────────────────────────────────────────────────
   AJAX-safe naxış (docs/frontend/AJAX_SAFE_JS_PATTERN.md):
     * kliklər `EMSDelegate.on` ilə `document`-ə DELEQASİYA olunur → panel swap
       olunandan sonra da işləyir;
     * per-swap init (`EMSReady`) yalnız NULL-SAFE, idempotent işlər görür.

   Filtr / sıralama / tab / səhifə SERVER tərəflidir — mövcud fraqment
   endpoint-i (`EMSProfileLoadSection`) çağırılır, yeni endpoint icad edilmir.

   ⚠️ BİZNES QƏRARI JS-DƏ VERİLMİR. «Səbəb məcburidir» burada yalnız düyməni
   deaktiv edir; həqiqi qapı serverdədir (`review_api.MIN_DECISION_REASON`),
   state maşınındadır və DB `CheckConstraint`-lərindədir. JS-i keçmək qərarı
   dəyişdirmir.

   ⚠️ MƏTN YOXDUR: bütün etiketlər `#syl-review-texts` / `#syl-review-dialogs`
   JSON bloklarından gəlir.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    var SECTION = "syllabus-review";
    var SEARCH_DEBOUNCE = 240;
    var PLACEHOLDER = "00000000-0000-0000-0000-000000000000";

    var searchTimer = null;
    var toastTimer = null;
    var state = null;
    var lastFocused = null;

    function root() {
        return document.querySelector("[data-syllabus-review]");
    }

    function panel() {
        return window.EMSSyllabusReviewPanel || null;
    }

    function readJson(id) {
        var node = document.getElementById(id);
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent) || {};
        } catch (error) {
            return {};
        }
    }

    function texts() {
        return readJson("syl-review-texts");
    }

    function dialogs() {
        return readJson("syl-review-dialogs");
    }

    function post(url, payload) {
        if (window.EMSCore && typeof window.EMSCore.fetchJSON === "function") {
            return window.EMSCore.fetchJSON(url, { method: "POST", data: payload || {} });
        }
        return Promise.reject(new Error("no_http_helper"));
    }

    /* ── Toast ────────────────────────────────────────────────────────── */
    function toast(el, message) {
        var node = el.querySelector("[data-syl-toast]");
        var text = el.querySelector("[data-syl-toast-text]");
        if (!node || !text || !message) {
            return;
        }
        text.textContent = message;
        node.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            node.hidden = true;
        }, 4200);
    }

    function errorText(err) {
        var payload = err && err.payload && err.payload.error;
        return payload || texts().error || "";
    }

    /* ── Server tərəfli filtr / tab / səhifə ──────────────────────────── */
    function reload(el, overrides) {
        if (typeof window.EMSProfileLoadSection !== "function") {
            return;
        }
        var url = new URL(el.getAttribute("data-profile-url") || "", window.location.origin);
        url.searchParams.set("section", SECTION);
        url.searchParams.set("tab", el.getAttribute("data-tab") || "queue");

        var search = el.querySelector("[data-syl-search]");
        if (search && search.value.trim()) {
            url.searchParams.set("q", search.value.trim());
        }
        el.querySelectorAll("select[data-syl-filter]").forEach(function (node) {
            if (node.value) {
                url.searchParams.set(node.getAttribute("data-syl-filter"), node.value);
            }
        });
        Object.keys(overrides || {}).forEach(function (key) {
            if (overrides[key] === null || overrides[key] === "") {
                url.searchParams.delete(key);
            } else {
                url.searchParams.set(key, overrides[key]);
            }
        });
        window.EMSProfileLoadSection(SECTION, url.pathname + url.search);
    }

    /* ── Baxış paneli ─────────────────────────────────────────────────── */
    function closePanel(el) {
        var node = el.querySelector("[data-syl-panel]");
        if (!node) {
            return;
        }
        node.hidden = true;
        state = null;
        if (lastFocused && typeof lastFocused.focus === "function") {
            lastFocused.focus();
        }
    }

    function showTab(el, name) {
        el.querySelectorAll("[data-syl-rv-tab]").forEach(function (node) {
            var on = node.getAttribute("data-syl-rv-tab") === name;
            node.classList.toggle("is-on", on);
            node.setAttribute("aria-current", on ? "page" : "false");
        });
        el.querySelectorAll("[data-syl-rv-pane]").forEach(function (node) {
            node.hidden = node.getAttribute("data-syl-rv-pane") !== name;
        });
    }

    function openPanel(el, versionId) {
        var node = el.querySelector("[data-syl-panel]");
        var renderer = panel();
        if (!node || !renderer) {
            return;
        }
        lastFocused = document.activeElement;
        var url = (el.getAttribute("data-open-url") || "").replace(PLACEHOLDER, versionId);
        post(url, {})
            .then(function (data) {
                state = { versionId: versionId, data: data, notes: {} };
                renderer.render(node, data, texts(), {});
                showTab(node, "sections");
                var general = node.querySelector("[data-syl-rv-general]");
                if (general) {
                    general.value = "";
                }
                node.hidden = false;
                var box = node.querySelector("[role='dialog']");
                if (box) {
                    box.focus();
                }
            })
            .catch(function (err) {
                toast(el, errorText(err));
            });
    }

    /* ── Qərar dialoqu ────────────────────────────────────────────────── */
    function closeModal(el) {
        var modal = el.querySelector("[data-syl-modal]");
        if (!modal) {
            return;
        }
        modal.hidden = true;
        if (state) {
            state.decision = null;
            state.sections = null;
        }
    }

    function renderLines(modal, lines) {
        var box = modal.querySelector("[data-syl-modal-lines]");
        if (!box) {
            return;
        }
        box.textContent = "";
        box.hidden = !lines.length;
        lines.forEach(function (line) {
            box.appendChild(panel().el("li", null, line));
        });
    }

    function renderSectionChips(el, modal, enabled) {
        var box = modal.querySelector("[data-syl-modal-secs]");
        var list = modal.querySelector("[data-syl-modal-secs-list]");
        if (!box || !list) {
            return;
        }
        box.hidden = !enabled;
        list.textContent = "";
        if (!enabled) {
            return;
        }
        var node = el.querySelector("[data-syl-panel]");
        panel()
            .sectionChoices(node)
            .forEach(function (section) {
                var chip = panel().el("button", "syl-secchip");
                chip.type = "button";
                chip.setAttribute("data-syl-secchip", section.id);
                chip.setAttribute("aria-pressed", "false");
                chip.appendChild(panel().el("span", "syl-secchip__box"));
                chip.appendChild(document.createTextNode(section.label));
                list.appendChild(chip);
            });
    }

    function validateReason(el) {
        var modal = el.querySelector("[data-syl-modal]");
        if (!modal || !state || !state.decision) {
            return false;
        }
        var config = dialogs()[state.decision] || {};
        var confirm = modal.querySelector("[data-syl-modal-confirm]");
        if (!config.reason_required) {
            if (confirm) {
                confirm.disabled = false;
            }
            return true;
        }
        var box = modal.querySelector("[data-syl-reason]");
        var note = modal.querySelector("[data-syl-reason-note]");
        var labels = texts();
        var min = labels.min_reason || 20;
        var ok = box && box.value.trim().length >= min;
        if (note) {
            note.textContent = ok ? labels.reason_ok : (labels.reason_short || "").replace("%(min)s", min);
            note.classList.toggle("is-bad", !ok);
        }
        if (confirm) {
            confirm.disabled = !ok;
        }
        return !!ok;
    }

    function openModal(el, decision) {
        var modal = el.querySelector("[data-syl-modal]");
        var config = dialogs()[decision];
        if (!modal || !config || !state) {
            return;
        }
        state.decision = decision;
        state.sections = {};

        modal.querySelector("[data-syl-modal-title]").textContent = config.title;
        modal.querySelector("[data-syl-modal-body]").textContent = config.body;

        var icon = modal.querySelector("[data-syl-modal-icon]");
        icon.className = "syl-modal__icon syl-modal__icon--" + config.tone;
        icon.textContent = { success: "✓", warning: "↩", danger: "✕" }[config.tone] || "";

        var confirm = modal.querySelector("[data-syl-modal-confirm]");
        confirm.textContent = config.ok;
        confirm.className = "syl-btn syl-btn--tone-" + config.tone;

        var reason = modal.querySelector("[data-syl-modal-reason]");
        reason.hidden = !config.reason_required;
        if (config.reason_required) {
            modal.querySelector("[data-syl-modal-reason-label]").textContent = config.reason_label;
            var box = modal.querySelector("[data-syl-reason]");
            box.value = "";
            box.placeholder = config.reason_placeholder || "";
        }
        renderSectionChips(el, modal, decision === "revise");
        renderLines(modal, config.lines || []);
        validateReason(el);

        modal.hidden = false;
        var dialog = modal.querySelector("[role='dialog']");
        if (dialog) {
            dialog.focus();
        }
    }

    function confirmDecision(el) {
        if (!state || !state.decision || !validateReason(el)) {
            return;
        }
        var node = el.querySelector("[data-syl-panel]");
        var modal = el.querySelector("[data-syl-modal]");
        var general = node.querySelector("[data-syl-rv-general]");
        var reasonBox = modal.querySelector("[data-syl-reason]");
        var payload = {
            action: state.decision,
            reason: reasonBox ? reasonBox.value.trim() : "",
            comment: general ? general.value.trim() : "",
            sections: panel().collectNotes(node)
        };
        var url = (el.getAttribute("data-decision-url") || "").replace(PLACEHOLDER, state.versionId);

        closeModal(el);
        post(url, payload)
            .then(function (data) {
                closePanel(el);
                toast(el, (data && data.message) || "");
                reload(el, { page: null });
            })
            .catch(function (err) {
                toast(el, errorText(err));
            });
    }

    /* ── Deleqasiya (document səviyyəsində BİR DƏFƏ) ──────────────────── */
    function bindOnce() {
        if (!window.EMSDelegate || window.__emsSyllabusReviewBound) {
            return;
        }
        window.__emsSyllabusReviewBound = true;
        var scope = "[data-syllabus-review] ";

        window.EMSDelegate.on("click", scope + "[data-syl-tab]", function (event, button) {
            var el = root();
            el.setAttribute("data-tab", button.getAttribute("data-syl-tab"));
            reload(el, { page: null });
        });
        window.EMSDelegate.on("change", scope + "select[data-syl-filter]", function () {
            reload(root(), { page: null });
        });
        window.EMSDelegate.on("input", scope + "[data-syl-search]", function () {
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(function () {
                reload(root(), { page: null });
            }, SEARCH_DEBOUNCE);
        });
        window.EMSDelegate.on("click", scope + "[data-syl-reset]", function () {
            var el = root();
            var url = new URL(el.getAttribute("data-profile-url") || "", window.location.origin);
            url.searchParams.set("section", SECTION);
            url.searchParams.set("tab", el.getAttribute("data-tab") || "queue");
            window.EMSProfileLoadSection(SECTION, url.pathname + url.search);
        });
        window.EMSDelegate.on("click", scope + "[data-syl-page]", function (event, button) {
            if (!button.disabled) {
                reload(root(), { page: button.getAttribute("data-syl-page") });
            }
        });
        window.EMSDelegate.on("click", scope + "[data-syl-open]", function (event, button) {
            openPanel(root(), button.getAttribute("data-syl-open"));
        });
        window.EMSDelegate.on("click", scope + "[data-syl-panel-close]", function () {
            closePanel(root());
        });
        window.EMSDelegate.on("click", scope + "[data-syl-rv-tab]", function (event, button) {
            showTab(root().querySelector("[data-syl-panel]"), button.getAttribute("data-syl-rv-tab"));
        });
        window.EMSDelegate.on("click", scope + "[data-syl-rv-notetoggle]", function (event, button) {
            var card = button.closest("[data-syl-rv-section]");
            var box = card && card.querySelector(".syl-rvsec__note");
            if (!box) {
                return;
            }
            var open = box.hidden;
            box.hidden = !open;
            button.setAttribute("aria-expanded", open ? "true" : "false");
            button.textContent = open ? texts().hide_note : texts().add_note;
            if (open) {
                var area = box.querySelector("textarea");
                if (area) {
                    area.focus();
                }
            }
        });
        window.EMSDelegate.on("input", scope + "[data-syl-rv-note]", function (event, area) {
            var card = area.closest("[data-syl-rv-section]");
            var filled = !!area.value.trim();
            if (card) {
                card.classList.toggle("has-note", filled);
                var badge = card.querySelector("[data-syl-rv-notebadge]");
                if (badge) {
                    badge.hidden = !filled;
                }
            }
            panel().paintFoot(root().querySelector("[data-syl-panel]"), texts());
        });
        window.EMSDelegate.on("click", scope + "[data-syl-decide]", function (event, button) {
            openModal(root(), button.getAttribute("data-syl-decide"));
        });
        window.EMSDelegate.on("click", scope + "[data-syl-modal-close]", function () {
            closeModal(root());
        });
        window.EMSDelegate.on("click", scope + "[data-syl-modal-confirm]", function () {
            confirmDecision(root());
        });
        window.EMSDelegate.on("input", scope + "[data-syl-reason]", function () {
            validateReason(root());
        });
        window.EMSDelegate.on("click", scope + "[data-syl-secchip]", function (event, chip) {
            // Bölmə işarəsi SƏBƏBİ əvəz etmir — sadəcə mətnə əlavə kontekst verir.
            var on = chip.getAttribute("aria-pressed") !== "true";
            chip.setAttribute("aria-pressed", on ? "true" : "false");
            chip.classList.toggle("is-on", on);
            var mark = chip.querySelector(".syl-secchip__box");
            if (mark) {
                mark.textContent = on ? "✓" : "";
            }
            if (state) {
                state.sections = state.sections || {};
                state.sections[chip.getAttribute("data-syl-secchip")] = on;
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }
            var el = root();
            if (!el) {
                return;
            }
            var modal = el.querySelector("[data-syl-modal]");
            if (modal && !modal.hidden) {
                closeModal(el);
                return;
            }
            var node = el.querySelector("[data-syl-panel]");
            if (node && !node.hidden) {
                closePanel(el);
            }
        });
    }

    /* ── Per-swap init (null-safe, idempotent) ────────────────────────── */
    window.EMSReady(function () {
        bindOnce();
        var el = root();
        if (!el) {
            return;
        }
        el.querySelectorAll("[data-syl-percent]").forEach(function (node) {
            var percent = parseInt(node.getAttribute("data-syl-percent"), 10) || 0;
            node.style.width = Math.max(0, Math.min(percent, 100)) + "%";
        });
    });
})();
