/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus redaktoru — AUTOSAVE MÜHƏRRİKİ və naviqasiya (dizayn təhvili §3.2)
   ───────────────────────────────────────────────────────────────────────────
   AJAX-safe naxış (docs/frontend/AJAX_SAFE_JS_PATTERN.md): kliklər/dəyişikliklər
   `EMSDelegate` ilə `document`-ə deleqasiya olunur, per-swap init isə yalnız
   null-safe və idempotent işlər görür. Bölmə panel içində swap olunduqda
   listener-lər itmir.

   ⚠️ BİZNES QƏRARI BURADA VERİLMİR. Tamamlanma faizi, bölmə statusu və
   «göndərilə bilər?» cavabı YALNIZ serverin autosave cavabından gəlir
   (`apps.syllabus.completion`). Bu fayl heç vaxt öz qaydasını hesablamır —
   əks halda iki həqiqət mənbəyi yaranardı və kilid qaydaları yan keçilə bilərdi.

   saveState — dizayn §3.2-dəki ALTI vəziyyət:
     saving · saved · failed · offline · conflict · stale
   Mətnlər şablondan `data-t-*` ilə gəlir; burada mətn YAZILMIR.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    var SECTION = "syllabus-editor";
    var SAVE_DEBOUNCE = 800;
    var TOAST_MS = 4000;

    /* Struktur dəyişən bölmələr: saxlandıqdan sonra fraqment yenidən yüklənir,
       çünki server markup-u dəyişir (TN etiketləri, tapşırıq yuvaları, arxiv). */
    var STRUCTURAL = { out: true, self: true };

    var saveTimer = null;
    var toastTimer = null;
    var dirty = {};
    var inFlight = false;
    var modalState = null;
    var lastFocused = null;

    function root() {
        return document.querySelector("[data-syllabus-editor]");
    }

    function fields() {
        return window.EMSSyllabusFields || null;
    }

    function i18n(el, key) {
        var api = fields();
        return api ? api.i18n(el, key) : "";
    }

    function isReadonly(el) {
        return !el || el.getAttribute("data-readonly") === "1";
    }

    /* ── Toast ────────────────────────────────────────────────────────── */
    function toast(el, message) {
        var node = el ? el.querySelector("[data-syl-toast]") : null;
        var text = el ? el.querySelector("[data-syl-toast-text]") : null;
        if (!node || !text || !message) {
            return;
        }
        text.textContent = message;
        node.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            node.hidden = true;
        }, TOAST_MS);
    }

    /* ── saveState — çip + banner + retry düyməsi ─────────────────────── */
    /* Render işi görüntü modulundadır (`…_fields.js`) — bu fayl kontrollerdir. */
    function setSaveState(el, state, suffix) {
        var api = fields();
        if (api) {
            api.paintSaveState(el, state, suffix);
        }
    }

    function applyCompletion(el, report) {
        var api = fields();
        if (api) {
            api.paintCompletion(el, report, isReadonly(el));
        }
    }

    function savedStamp() {
        var now = new Date();
        function pad(value) {
            return (value < 10 ? "0" : "") + value;
        }
        return pad(now.getHours()) + ":" + pad(now.getMinutes());
    }

    /* ── Autosave ─────────────────────────────────────────────────────── */
    function revisionOf(el, sectionId) {
        var box = el.querySelector("[data-syl-panel='" + sectionId + "']");
        var raw = box ? box.getAttribute("data-revision") : null;
        var parsed = parseInt(raw, 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    function reloadSection(el, step) {
        if (typeof window.EMSProfileLoadSection !== "function") {
            return;
        }
        var base = el.getAttribute("data-profile-url") || "";
        var url = new URL(base, window.location.origin);
        url.searchParams.set("section", SECTION);
        url.searchParams.set("version", el.getAttribute("data-version") || "");
        if (step) {
            url.searchParams.set("step", step);
        }
        window.EMSProfileLoadSection(SECTION, url.pathname + url.search);
    }

    function activeStep(el) {
        var panel = el.querySelector(".syl-panel.is-on");
        return panel ? panel.getAttribute("data-syl-panel") : null;
    }

    function flush(el) {
        var api = fields();
        var http = window.EMSCore && window.EMSCore.fetchJSON;
        if (!el || !api || !http || isReadonly(el) || inFlight) {
            return;
        }
        var pending = Object.keys(dirty);
        if (!pending.length) {
            return;
        }
        /* Offline: göndərmirik, dəyişikliklər `dirty`-də növbəyə alınır və
           bağlantı qayıdanda `online` hadisəsi yenidən `flush` çağırır. */
        if (window.navigator && window.navigator.onLine === false) {
            setSaveState(el, "offline");
            return;
        }
        var sectionId = pending[0];
        var data = api.collect(el, sectionId);
        if (!data) {
            delete dirty[sectionId];
            flush(el);
            return;
        }

        inFlight = true;
        setSaveState(el, "saving");
        var payload = { section: sectionId, data: data, revision: revisionOf(el, sectionId) };

        window.EMSCore.fetchJSON(el.getAttribute("data-save-url"), { method: "POST", data: payload })
            .then(function (response) {
                inFlight = false;
                delete dirty[sectionId];
                var box = el.querySelector("[data-syl-panel='" + sectionId + "']");
                if (box && response && typeof response.revision !== "undefined") {
                    box.setAttribute("data-revision", String(response.revision));
                }
                applyCompletion(el, response && response.completion);
                setSaveState(el, "saved", savedStamp());
                if (STRUCTURAL[sectionId]) {
                    reloadSection(el, activeStep(el));
                    return;
                }
                flush(el);
            })
            .catch(function (error) {
                inFlight = false;
                var status = error && error.status;
                if (status === 409) {
                    /* Optimistik kilid pozuldu: dəyişiklik SAXLANILMADI, ona görə
                       `dirty` təmizlənmir — istifadəçi serverdəkini yükləməlidir. */
                    setSaveState(el, "conflict");
                } else if (status === 403 || status === 404) {
                    setSaveState(el, "stale");
                } else if (window.navigator && window.navigator.onLine === false) {
                    setSaveState(el, "offline");
                } else {
                    setSaveState(el, "failed");
                }
            });
    }

    /* `prev` / `send` bölmələrinin saxlanacaq məzmunu yoxdur. */
    function isSavable(sectionId) {
        return sectionId !== "prev" && sectionId !== "send";
    }

    function queue(el, sectionId, immediate) {
        if (!el || !sectionId || isReadonly(el) || !isSavable(sectionId)) {
            return;
        }
        dirty[sectionId] = true;
        window.clearTimeout(saveTimer);
        if (immediate) {
            flush(el);
            return;
        }
        saveTimer = window.setTimeout(function () {
            flush(el);
        }, SAVE_DEBOUNCE);
    }

    /* ── Addım naviqasiyası ───────────────────────────────────────────── */
    function goStep(el, target) {
        if (!el) {
            return;
        }
        var panels = Array.prototype.slice.call(el.querySelectorAll("[data-syl-panel]"));
        if (!panels.length) {
            return;
        }
        var ids = panels.map(function (panel) {
            return panel.getAttribute("data-syl-panel");
        });
        var current = ids.indexOf(activeStep(el));
        var index = ids.indexOf(target);
        if (target === "next") {
            index = Math.min(ids.length - 1, current + 1);
        } else if (target === "prev-step") {
            index = Math.max(0, current - 1);
        }
        if (index < 0) {
            return;
        }
        panels.forEach(function (panel, position) {
            panel.classList.toggle("is-on", position === index);
        });
        el.querySelectorAll(".syl-step").forEach(function (button) {
            var on = button.getAttribute("data-syl-step") === ids[index];
            button.classList.toggle("is-on", on);
            if (on) {
                button.setAttribute("aria-current", "step");
            } else {
                button.removeAttribute("aria-current");
            }
        });
        var navPrev = el.querySelector("[data-syl-nav='prev']");
        var navNext = el.querySelector("[data-syl-nav='next']");
        if (navPrev) {
            navPrev.disabled = index === 0;
        }
        if (navNext) {
            navNext.disabled = index === ids.length - 1;
        }
        var heading = panels[index].querySelector("h3");
        if (heading && typeof heading.scrollIntoView === "function") {
            heading.scrollIntoView({ block: "nearest" });
        }
    }

    /* ── Dialoq (təsdiqə göndər / mövzunu arxivlə) ────────────────────── */
    function closeModal(el) {
        var modal = el ? el.querySelector("[data-syl-editor-modal]") : null;
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
        var modal = el ? el.querySelector("[data-syl-editor-modal]") : null;
        if (!modal) {
            return;
        }
        modalState = { kind: kind, context: context || {} };
        lastFocused = document.activeElement;

        modal.querySelector("[data-syl-modal-title]").textContent = i18n(el, kind + "-title");
        modal.querySelector("[data-syl-modal-body]").textContent = i18n(el, kind + "-body");
        modal.querySelector("[data-syl-modal-confirm]").textContent = i18n(el, kind + "-ok");
        modal.querySelector("[data-syl-modal-cancel]").textContent = i18n(el, kind + "-cancel");
        modal.querySelectorAll("[data-syl-lines]").forEach(function (list) {
            list.hidden = list.getAttribute("data-syl-lines") !== kind;
        });

        modal.hidden = false;
        var box = modal.querySelector("[role='dialog']");
        if (box) {
            box.focus();
        }
    }

    /* Qiyməti olan tapşırıq SİLİNMİR — arxiv sətrinə köçürülür, sonra bölmə
       yenidən yüklənir ki, server markup-u (arxiv siyahısı) doğru olsun. */
    function archiveSlot(el, index) {
        var slot = el.querySelector("[data-syl-slot='" + index + "']");
        var box = el.querySelector("[data-syl-archived]");
        if (!slot || !box) {
            return;
        }
        var input = slot.querySelector("[data-selfwork-title]");
        var title = input ? String(input.value || "").trim() : "";
        if (!title) {
            return;
        }
        var row = document.createElement("p");
        row.className = "syl-archived__row";
        row.setAttribute("data-syl-archived-row", "");
        row.setAttribute("data-title", title);
        row.setAttribute("data-note", i18n(el, "archived-note"));
        box.appendChild(row);
        box.hidden = false;
        if (input) {
            input.value = "";
        }
        slot.setAttribute("data-graded", "0");
        slot.setAttribute("data-graded-count", "0");
        queue(el, "self", true);
    }

    function runAction(el, payload, onDone) {
        window.EMSCore.fetchJSON(el.getAttribute("data-action-url"), { method: "POST", data: payload })
            .then(function (response) {
                toast(el, (response && response.message) || "");
                if (typeof onDone === "function") {
                    onDone(response);
                }
            })
            .catch(function (error) {
                var message = error && error.payload && error.payload.error;
                toast(el, message || i18n(el, "blocked"));
            });
    }

    function confirmModal(el) {
        if (!modalState) {
            return;
        }
        var kind = modalState.kind;
        var context = modalState.context;
        closeModal(el);
        if (kind === "archive") {
            archiveSlot(el, context.index);
            return;
        }
        runAction(el, { action: "submit", version: el.getAttribute("data-version") }, function () {
            reloadSection(el, "send");
        });
    }

    /* ── Sərbəst iş strukturu ─────────────────────────────────────────── */
    function pickSelfwork(el, button) {
        var key = button.getAttribute("data-syl-selfwork");
        var current = el.querySelector("[data-syl-selfwork].is-on");
        if (button.disabled || (current && current === button)) {
            return;
        }
        /* Yeni struktur mövcud QİYMƏTLƏNMİŞ tapşırıqdan az yuva verirsə,
           dəyişikliyə icazə verilmir — əvvəlcə həmin tapşırıq arxivlənməlidir. */
        var slots = el.querySelectorAll("[data-syl-slot]");
        var count = parseInt(button.getAttribute("data-count"), 10);
        if (!isNaN(count)) {
            for (var index = count; index < slots.length; index += 1) {
                if (slots[index].getAttribute("data-graded") === "1") {
                    toast(el, i18n(el, "graded-lock"));
                    return;
                }
            }
        }
        el.querySelectorAll("[data-syl-selfwork]").forEach(function (node) {
            var on = node === button;
            node.classList.toggle("is-on", on);
            node.setAttribute("aria-pressed", on ? "true" : "false");
        });
        el.setAttribute("data-selfwork", key);
        queue(el, "self", true);
    }

    /* ── Təlim nəticələri ─────────────────────────────────────────────── */
    function addOutcome(el) {
        var api = fields();
        var box = el ? el.querySelector("[data-syl-outcomes]") : null;
        var sample = box ? box.querySelector("[data-syl-outcome]") : null;
        if (!api || !box || !sample) {
            return;
        }
        var row = sample.cloneNode(true);
        var input = row.querySelector("[data-outcome]");
        if (input) {
            input.value = "";
            input.disabled = false;
        }
        var remove = row.querySelector("[data-syl-outcome-remove]");
        if (remove) {
            remove.disabled = false;
        }
        box.appendChild(row);
        api.retagOutcomes(el);
        if (input) {
            input.focus();
        }
        queue(el, "out", true);
    }

    /* Dizayn §3.2: minimumdan aşağı düşən silmə BLOKLANIR — istifadəçiyə
       səbəb izah olunur, sətir silinmir. */
    function removeOutcome(el, button) {
        var api = fields();
        var box = el ? el.querySelector("[data-syl-outcomes]") : null;
        var row = button.closest("[data-syl-outcome]");
        if (!api || !box || !row) {
            return;
        }
        var min = parseInt(box.getAttribute("data-min"), 10) || 0;
        if (box.querySelectorAll("[data-syl-outcome]").length <= min) {
            toast(el, i18n(el, "min-outcomes"));
            return;
        }
        row.parentNode.removeChild(row);
        api.retagOutcomes(el);
        queue(el, "out", true);
    }

    /* ── Deleqasiya (document səviyyəsində BİR DƏFƏ) ──────────────────── */
    function on(event, selector, handler) {
        window.EMSDelegate.on(event, "[data-syllabus-editor] " + selector, handler);
    }

    function bindOnce() {
        if (!window.EMSDelegate || window.__emsSyllabusEditorBound) {
            return;
        }
        window.__emsSyllabusEditorBound = true;

        /* `data-syl-step` üç yerdədir: sol naviqasiya, «Düzəlt» düymələri və
           çatışmazlıq siyahısı — hamısı eyni hədəf bölməyə tullanır. */
        on("click", "[data-syl-step]", function (event, button) {
            goStep(root(), button.getAttribute("data-syl-step"));
        });
        on("click", "[data-syl-nav]", function (event, button) {
            var direction = button.getAttribute("data-syl-nav");
            goStep(root(), direction === "prev" ? "prev-step" : "next");
        });

        /* Mətn sahələri: debounce ilə; seçim/açılış sahələri: dərhal. */
        on("input", "[data-field], [data-field-lines], [data-outcome], [data-week='topic'], [data-selfwork-title]",
            function (event, node) {
                var el = root();
                var api = fields();
                if (!api) {
                    return;
                }
                api.refresh(el);
                queue(el, api.sectionOf(node), false);
            });
        on("change", "select[data-week], [data-syl-midterm]", function (event, node) {
            var el = root();
            var api = fields();
            if (!api) {
                return;
            }
            api.refresh(el);
            queue(el, api.sectionOf(node), true);
        });
        on("input", "[data-syl-midterm]", function () {
            var api = fields();
            if (api) {
                api.refresh(root());
            }
        });

        on("click", "[data-syl-method]", function (event, button) {
            var el = root();
            if (button.disabled) {
                return;
            }
            var on_ = !button.classList.contains("is-on");
            button.classList.toggle("is-on", on_);
            button.setAttribute("aria-pressed", on_ ? "true" : "false");
            queue(el, "method", true);
        });
        on("click", "[data-syl-selfwork]", function (event, button) {
            pickSelfwork(root(), button);
        });
        on("click", "[data-syl-outcome-add]", function () {
            addOutcome(root());
        });
        on("click", "[data-syl-outcome-remove]", function (event, button) {
            removeOutcome(root(), button);
        });
        on("click", "[data-syl-clear]", function (event, button) {
            var el = root();
            var slot = el.querySelector("[data-syl-slot='" + button.getAttribute("data-syl-clear") + "']");
            var input = slot ? slot.querySelector("[data-selfwork-title]") : null;
            if (input) {
                input.value = "";
                queue(el, "self", true);
            }
        });
        on("click", "[data-syl-archive]", function (event, button) {
            openModal(root(), "archive", { index: button.getAttribute("data-syl-archive") });
        });

        on("click", "[data-syl-save-now]", function () {
            var el = root();
            var step = activeStep(el);
            if (step) {
                queue(el, step, true);
            }
        });
        on("click", "[data-syl-retry]", function () {
            flush(root());
        });
        on("click", "[data-syl-reload]", function () {
            var el = root();
            reloadSection(el, activeStep(el));
        });
        on("click", "[data-syl-submit]", function (event, button) {
            var el = root();
            if (button.disabled) {
                toast(el, i18n(el, "blocked"));
                return;
            }
            openModal(el, "submit", {});
        });
        on("click", "[data-syl-modal-close]", function () {
            closeModal(root());
        });
        on("click", "[data-syl-modal-confirm]", function () {
            confirmModal(root());
        });

        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }
            var el = root();
            var modal = el ? el.querySelector("[data-syl-editor-modal]") : null;
            if (modal && !modal.hidden) {
                closeModal(el);
            }
        });

        /* Bağlantı qayıdanda növbədə qalan bölmələr avtomatik göndərilir. */
        window.addEventListener("online", function () {
            var el = root();
            if (el && Object.keys(dirty).length) {
                flush(el);
            }
        });
        window.addEventListener("offline", function () {
            var el = root();
            if (el) {
                setSaveState(el, "offline");
            }
        });
    }

    /* ── Per-swap init (null-safe, idempotent) ────────────────────────── */
    window.EMSReady(function () {
        bindOnce();
        var el = root();
        if (!el || !fields()) {
            return;
        }
        dirty = {};
        inFlight = false;
        window.clearTimeout(saveTimer);

        var fill = el.querySelector("[data-syl-progress-fill]");
        if (fill) {
            fill.style.width = (parseInt(fill.getAttribute("data-syl-percent"), 10) || 0) + "%";
        }
        fields().refresh(el);
        goStep(el, el.getAttribute("data-active") || activeStep(el));
        setSaveState(el, window.navigator && window.navigator.onLine === false ? "offline" : "saved");
    });
})();
