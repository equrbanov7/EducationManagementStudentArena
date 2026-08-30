/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus — SİYAHI ekranının davranışı (dizayn təhvili §3.1)
   ───────────────────────────────────────────────────────────────────────────
   AJAX-safe naxış (docs/frontend/AJAX_SAFE_JS_PATTERN.md):
     * kliklər `EMSDelegate.on` ilə `document`-ə DELEQASİYA olunur → panel
       swap olunandan sonra da işləyir;
     * per-swap init (`EMSReady`) yalnız NULL-SAFE, idempotent işlər görür.

   Filtr/sıralama/səhifə SERVER tərəflidir: `EMSProfileLoadSection` mövcud
   fraqment endpoint-ini çağırır (yeni endpoint icad edilmir). «Cədvəl ⇄ Kart»
   açarı isə tam KLİYENT tərəflidir — hər iki görünüş onsuz da render olunub.

   Mətn YOXDUR: bütün etiketlər şablondan `data-t-*` atributları ilə gəlir
   (xarici .js Django template engine-dən keçmir).
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    var SECTION = "syllabus-list";
    var EDITOR_SECTION = "syllabus-editor";
    var SEARCH_DEBOUNCE = 240;
    var MIN_REASON = 15;
    var VIEW_STORAGE_KEY = "ems.syllabus.view";

    var searchTimer = null;
    var toastTimer = null;
    var modalState = null;
    var lastFocused = null;

    function root() {
        return document.querySelector("[data-syllabus-list]");
    }

    function i18n(el, key) {
        var box = el ? el.querySelector("[data-syl-i18n]") : null;
        return (box && box.getAttribute("data-t-" + key)) || "";
    }

    function csrfFetch(url, payload) {
        if (window.EMSCore && typeof window.EMSCore.fetchJSON === "function") {
            return window.EMSCore.fetchJSON(url, { method: "POST", data: payload });
        }
        return Promise.reject(new Error("no_http_helper"));
    }

    /* ── Filtr vəziyyəti → server sorğusu ─────────────────────────────── */
    function currentQuery(el, overrides) {
        var params = {};
        var search = el.querySelector("[data-syl-search]");
        if (search && search.value.trim()) {
            params.q = search.value.trim();
        }
        el.querySelectorAll("select[data-syl-filter]").forEach(function (node) {
            if (node.value) {
                params[node.getAttribute("data-syl-filter")] = node.value;
            }
        });
        var chip = el.querySelector("[data-syl-filter='status'].is-on");
        if (chip && chip.getAttribute("data-value")) {
            params.status = chip.getAttribute("data-value");
        }
        Object.keys(overrides || {}).forEach(function (key) {
            if (overrides[key] === null || overrides[key] === "") {
                delete params[key];
            } else {
                params[key] = overrides[key];
            }
        });
        return params;
    }

    function reload(el, overrides) {
        if (typeof window.EMSProfileLoadSection !== "function") {
            return;
        }
        var base = el.getAttribute("data-profile-url") || "";
        var url = new URL(base, window.location.origin);
        url.searchParams.set("section", SECTION);
        var params = currentQuery(el, overrides);
        Object.keys(params).forEach(function (key) {
            url.searchParams.set(key, params[key]);
        });
        window.EMSProfileLoadSection(SECTION, url.pathname + url.search);
    }

    function openEditor(el, versionId) {
        if (!versionId || typeof window.EMSProfileLoadSection !== "function") {
            return;
        }
        var base = el.getAttribute("data-profile-url") || "";
        var url = new URL(base, window.location.origin);
        url.searchParams.set("section", EDITOR_SECTION);
        url.searchParams.set("version", versionId);
        window.EMSProfileLoadSection(EDITOR_SECTION, url.pathname + url.search);
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
        }, 4000);
    }

    /* ── Dialoq ───────────────────────────────────────────────────────── */
    function closeModal(el) {
        var modal = el.querySelector("[data-syl-modal]");
        if (!modal) {
            return;
        }
        modal.hidden = true;
        modalState = null;
        if (lastFocused && typeof lastFocused.focus === "function") {
            lastFocused.focus();
        }
    }

    function openModal(el, kind, context) {
        var modal = el.querySelector("[data-syl-modal]");
        if (!modal) {
            return;
        }
        modalState = { kind: kind, context: context, versionKind: "minor" };
        lastFocused = document.activeElement;

        modal.querySelector("[data-syl-modal-title]").textContent = i18n(el, kind + "-title");
        modal.querySelector("[data-syl-modal-body]").textContent = i18n(el, kind + "-body");
        modal.querySelector("[data-syl-modal-confirm]").textContent = i18n(el, kind + "-ok");

        var picks = modal.querySelector("[data-syl-modal-picks]");
        var reason = modal.querySelector("[data-syl-modal-reason]");
        picks.hidden = kind !== "newver";
        reason.hidden = kind !== "withdraw";
        if (kind === "withdraw") {
            var box = modal.querySelector("[data-syl-reason]");
            box.value = "";
            validateReason(el);
        }
        modal.hidden = false;
        var panel = modal.querySelector("[role='dialog']");
        if (panel) {
            panel.focus();
        }
    }

    function validateReason(el) {
        var box = el.querySelector("[data-syl-reason]");
        var note = el.querySelector("[data-syl-reason-note]");
        var confirm = el.querySelector("[data-syl-modal-confirm]");
        if (!box || !note || !confirm) {
            return false;
        }
        var ok = box.value.trim().length >= MIN_REASON;
        note.textContent = ok ? i18n(el, "reason-ok") : i18n(el, "reason-short");
        note.classList.toggle("is-bad", !ok);
        confirm.disabled = !ok;
        return ok;
    }

    function confirmModal(el) {
        if (!modalState) {
            return;
        }
        var ctx = modalState.context || {};
        var url = el.getAttribute("data-action-url");
        var payload = null;

        if (modalState.kind === "newver") {
            payload = { action: "new_version", syllabus: ctx.id, kind: modalState.versionKind };
        } else if (modalState.kind === "copy") {
            payload = { action: "copy", syllabus: ctx.id };
        } else if (modalState.kind === "create") {
            payload = { action: "create", offering: ctx.id };
        } else if (modalState.kind === "withdraw") {
            if (!validateReason(el)) {
                return;
            }
            payload = {
                action: "withdraw",
                version: ctx.version,
                reason: el.querySelector("[data-syl-reason]").value.trim()
            };
        }
        if (!payload) {
            return;
        }

        var openAfter = modalState.kind !== "withdraw";
        closeModal(el);
        csrfFetch(url, payload)
            .then(function (data) {
                toast(el, (data && data.message) || "");
                if (openAfter && data && data.version) {
                    openEditor(el, data.version);
                } else {
                    reload(el, { page: null });
                }
            })
            .catch(function (err) {
                var payloadError = err && err.payload && err.payload.error;
                toast(el, payloadError || i18n(el, "error"));
            });
    }

    /* ── Baxış paneli (drawer) ────────────────────────────────────────── */
    function closeDrawer(el) {
        var drawer = el.querySelector("[data-syl-drawer]");
        if (!drawer) {
            return;
        }
        drawer.hidden = true;
        if (lastFocused && typeof lastFocused.focus === "function") {
            lastFocused.focus();
        }
    }

    function renderDrawer(el, data) {
        var drawer = el.querySelector("[data-syl-drawer]");
        if (!drawer) {
            return;
        }
        drawer.querySelector("[data-syl-drawer-code]").textContent = data.code || "";
        drawer.querySelector("[data-syl-drawer-name]").textContent = data.name || "";
        drawer.querySelector("[data-syl-drawer-version]").textContent = data.version || "";
        drawer.querySelector("[data-syl-drawer-meta]").textContent =
            [data.program, data.period].filter(Boolean).join(" · ");

        var status = drawer.querySelector("[data-syl-drawer-status]");
        status.textContent = data.status_label || "";
        status.className = "syl-badge syl-badge--" + (data.status_tone || "neutral");

        var banner = drawer.querySelector("[data-syl-drawer-banner]");
        banner.textContent = [data.banner, data.decision_reason].filter(Boolean).join(" ");
        banner.className = "syl-drawer__banner syl-drawer__banner--" + (data.status_tone || "neutral");

        var blocks = drawer.querySelector("[data-syl-drawer-blocks]");
        blocks.textContent = "";
        (data.blocks || []).forEach(function (block) {
            var wrap = document.createElement("div");
            wrap.className = "syl-drawer__block";
            var title = document.createElement("p");
            title.className = "syl-drawer__block-title";
            title.textContent = block.title;
            var body = document.createElement("p");
            body.className = "syl-drawer__block-body";
            body.textContent = block.body;
            wrap.appendChild(title);
            wrap.appendChild(body);
            blocks.appendChild(wrap);
        });

        var history = drawer.querySelector("[data-syl-drawer-history]");
        history.textContent = "";
        (data.history || []).forEach(function (row) {
            var line = document.createElement("div");
            line.className = "syl-history__row";
            ["version", "what", "who"].forEach(function (key, index) {
                var cell = document.createElement("span");
                cell.className = ["syl-history__version", "syl-history__what", "syl-history__who"][index];
                cell.textContent = key === "who" ? [row.who, row.at].filter(Boolean).join(" · ") : (row[key] || "");
                line.appendChild(cell);
            });
            history.appendChild(line);
        });

        drawer.hidden = false;
        var panel = drawer.querySelector("[role='dialog']");
        if (panel) {
            panel.focus();
        }
    }

    function openDrawer(el, syllabusId) {
        var template = el.getAttribute("data-preview-url") || "";
        var url = template.replace("00000000-0000-0000-0000-000000000000", syllabusId);
        lastFocused = document.activeElement;
        fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data && data.ok) {
                    renderDrawer(el, data);
                } else {
                    toast(el, (data && data.error) || i18n(el, "error"));
                }
            })
            .catch(function () {
                toast(el, i18n(el, "error"));
            });
    }

    /* ── Əməllər ──────────────────────────────────────────────────────── */
    var DRAWER_ACTIONS = ["view", "notes", "reason", "submitted_view", "history"];
    var EDIT_ACTIONS = ["resume", "fix"];

    function handleAction(el, button) {
        var action = button.getAttribute("data-syl-action");
        var context = {
            id: button.getAttribute("data-id"),
            version: button.getAttribute("data-version"),
            pdf: button.getAttribute("data-pdf"),
            name: button.getAttribute("data-name")
        };
        if (EDIT_ACTIONS.indexOf(action) >= 0) {
            openEditor(el, context.version);
        } else if (DRAWER_ACTIONS.indexOf(action) >= 0) {
            openDrawer(el, context.id);
        } else if (action === "new_version") {
            openModal(el, "newver", context);
        } else if (action === "copy") {
            openModal(el, "copy", context);
        } else if (action === "create") {
            openModal(el, "create", context);
        } else if (action === "withdraw") {
            openModal(el, "withdraw", context);
        } else if (action === "pdf") {
            // Sənədin PDF nüsxəsi — mövcud renderer, ayrıca tabda yüklənir.
            if (context.pdf) {
                window.open(context.pdf, "_blank", "noopener");
            } else {
                toast(el, i18n(el, "pdf"));
            }
        }
    }

    /* ── Deleqasiya (document səviyyəsində BİR DƏFƏ) ──────────────────── */
    function bindOnce() {
        if (!window.EMSDelegate || window.__emsSyllabusListBound) {
            return;
        }
        window.__emsSyllabusListBound = true;

        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-action]", function (event, button) {
            handleAction(root(), button);
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-filter='status']", function (event, button) {
            reload(root(), { status: button.getAttribute("data-value"), page: null });
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-page]", function (event, button) {
            if (!button.disabled) {
                reload(root(), { page: button.getAttribute("data-syl-page") });
            }
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-reset]", function () {
            var el = root();
            var base = el.getAttribute("data-profile-url") || "";
            var url = new URL(base, window.location.origin);
            url.searchParams.set("section", SECTION);
            window.EMSProfileLoadSection(SECTION, url.pathname + url.search);
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-view]", function (event, button) {
            applyView(root(), button.getAttribute("data-syl-view"), true);
        });
        window.EMSDelegate.on("change", "[data-syllabus-list] select[data-syl-filter]", function () {
            reload(root(), { page: null });
        });
        window.EMSDelegate.on("input", "[data-syllabus-list] [data-syl-search]", function () {
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(function () {
                reload(root(), { page: null });
            }, SEARCH_DEBOUNCE);
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-drawer-close]", function () {
            closeDrawer(root());
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-modal-close]", function () {
            closeModal(root());
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-modal-confirm]", function () {
            confirmModal(root());
        });
        window.EMSDelegate.on("click", "[data-syllabus-list] [data-syl-kind]", function (event, button) {
            if (!modalState) {
                return;
            }
            modalState.versionKind = button.getAttribute("data-syl-kind");
            root().querySelectorAll("[data-syl-kind]").forEach(function (node) {
                var on = node === button;
                node.classList.toggle("is-on", on);
                node.setAttribute("aria-pressed", on ? "true" : "false");
            });
        });
        window.EMSDelegate.on("input", "[data-syllabus-list] [data-syl-reason]", function () {
            validateReason(root());
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
            var drawer = el.querySelector("[data-syl-drawer]");
            if (drawer && !drawer.hidden) {
                closeDrawer(el);
            }
        });
    }

    /* ── Per-swap init (null-safe, idempotent) ────────────────────────── */
    function applyView(el, view, persist) {
        if (!el) {
            return;
        }
        el.setAttribute("data-view", view);
        el.querySelectorAll("[data-syl-view]").forEach(function (node) {
            var on = node.getAttribute("data-syl-view") === view;
            node.classList.toggle("is-on", on);
            node.setAttribute("aria-pressed", on ? "true" : "false");
        });
        if (persist) {
            try {
                window.localStorage.setItem(VIEW_STORAGE_KEY, view);
            } catch (e) {
                /* private mode — seçim yalnız bu səhifə üçün qalır */
            }
        }
    }

    function paintBars(el) {
        el.querySelectorAll("[data-syl-percent]").forEach(function (node) {
            var percent = parseInt(node.getAttribute("data-syl-percent"), 10) || 0;
            node.style.width = Math.max(0, Math.min(percent, 100)) + "%";
        });
    }

    window.EMSReady(function () {
        bindOnce();
        var el = root();
        if (!el) {
            return;
        }
        paintBars(el);
        var stored = null;
        try {
            stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
        } catch (e) {
            stored = null;
        }
        applyView(el, stored === "card" ? "card" : el.getAttribute("data-view") || "table", false);
    });
})();
