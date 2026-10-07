/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus — TƏKRAR İSTİFADƏ dialoqu (sahib tələbi 2026-10-08)
   ───────────────────────────────────────────────────────────────────────────
   «Bu fənnin bu semestr üçün artıq sillabusu var»: mənbə seçimi →
   «Eyni sillabusu istifadə et (bağla)» | «Kopyala və uyğunlaşdır» |
   «Hamısına tətbiq et»; bağlı dosyedə «Ayır» / «Mənbədən yenilə»; mənbədə
   «Bağlı sillabuslara tətbiq et».

   AJAX-safe (docs/frontend/AJAX_SAFE_JS_PATTERN.md): kliklər `EMSDelegate.on`
   ilə document-ə BİR DƏFƏ deleqasiya olunur; dialoq düymənin ÖZ bölmə
   panelindən tapılır (`[data-profile-section-panel]`) — siyahı və redaktor
   panelləri eyni anda DOM-da ola bilər.  Mətn YOXDUR: etiketlər serverdən
   (JSON) və ya `data-t-*` atributlarından gəlir.  Qərarları server verir —
   düymənin aktivliyi yalnız göstərişdir.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    var ACTIONS = ["reuse", "unlink", "sync", "propagate"];
    var state = null;
    var confirmState = null;
    var toastTimer = null;

    function panelOf(node) {
        return (node && node.closest("[data-profile-section-panel]")) || document;
    }

    function t(panel, key) {
        var box = panel.querySelector("[data-syl-reuse-i18n]");
        return (box && box.getAttribute("data-t-" + key)) || "";
    }

    function fmt(text, params) {
        return String(text || "").replace(/\{(\w+)\}/g, function (match, key) {
            return params && params[key] !== undefined ? params[key] : match;
        });
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = text;
        }
        return node;
    }

    function http(url, payload) {
        if (!window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
            return Promise.reject(new Error("no_http_helper"));
        }
        return payload === undefined
            ? window.EMSCore.fetchJSON(url)
            : window.EMSCore.fetchJSON(url, { method: "POST", data: payload });
    }

    function errorText(panel, err) {
        return (err && err.payload && err.payload.error) || t(panel, "error");
    }

    /* ── Bölmə ilə əlaqə: toast, yeniləmə, redaktor ───────────────────── */
    function toast(panel, message) {
        var node = panel.querySelector("[data-syl-toast]");
        var text = panel.querySelector("[data-syl-toast-text]");
        if (!node || !text || !message) {
            return;
        }
        text.textContent = message;
        node.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            node.hidden = true;
        }, 5000);
    }

    function profileUrl(panel) {
        var host = panel.querySelector("[data-profile-url]");
        return (host && host.getAttribute("data-profile-url")) || window.location.pathname;
    }

    function openEditor(panel, versionId) {
        if (!versionId || typeof window.EMSProfileLoadSection !== "function") {
            return;
        }
        var url = new URL(profileUrl(panel), window.location.origin);
        url.searchParams.set("section", "syllabus-editor");
        url.searchParams.set("version", versionId);
        window.EMSProfileLoadSection("syllabus-editor", url.pathname + url.search);
    }

    function refresh(panel, versionId) {
        var section = panel.getAttribute && panel.getAttribute("data-profile-section-panel");
        if (section === "syllabus-list" && window.EMSSyllabusList) {
            window.EMSSyllabusList.reload();
        } else if (section === "syllabus-editor") {
            var host = panel.querySelector("[data-syllabus-editor]");
            openEditor(panel, versionId || (host && host.getAttribute("data-version")));
        }
    }

    /* ── Dialoq qabığı ────────────────────────────────────────────────── */
    function show(node, on) {
        if (node) {
            node.hidden = !on;
        }
    }

    function focusBox(modal) {
        var box = modal.querySelector("[role='dialog']");
        if (box) {
            box.focus();
        }
    }

    function closePicker(reload) {
        if (!state) {
            return;
        }
        var current = state;
        state = null;
        current.modal.hidden = true;
        if (current.trigger && typeof current.trigger.focus === "function" && document.contains(current.trigger)) {
            current.trigger.focus();
        }
        if (reload || current.dirty) {
            refresh(current.panel);
        }
    }

    function selected() {
        if (!state || !state.data) {
            return null;
        }
        return (state.data.siblings || []).filter(function (row) {
            return row.id === state.sourceId;
        })[0] || null;
    }

    /* ── Mənbə kartları ──────────────────────────────────────────────── */
    function sourceCard(panel, row) {
        var card = el("button", "syl-pick syl-reuse__src");
        card.type = "button";
        card.setAttribute("role", "radio");
        card.setAttribute("data-syl-reuse-src", row.id);
        card.appendChild(el("span", "syl-pick__radio"));
        var body = el("span", "syl-reuse__src-body");
        var head = el("span", "syl-reuse__src-head");
        head.appendChild(el("span", "syl-pick__title", row.group));
        var badge = el("span", "syl-badge syl-badge--" + (row.status_tone || "neutral"), row.status_label);
        head.appendChild(badge);
        head.appendChild(el("span", "syl-version", row.version_label));
        body.appendChild(head);
        var meta = [row.author, row.approver].filter(Boolean).join(" · ");
        if (meta) {
            body.appendChild(el("span", "syl-pick__note", meta));
        }
        var hours = el(
            "span",
            "syl-reuse__hours " + (row.hours_same ? "is-same" : "is-diff"),
            (row.hours_same ? "✓ " + t(panel, "hours-same") : "≠ " + t(panel, "hours-diff")) + " — " + row.hours_text
        );
        body.appendChild(hours);
        if (row.linked_count) {
            body.appendChild(el("span", "syl-pick__note", fmt(t(panel, "linked-count"), { count: row.linked_count })));
        }
        card.appendChild(body);
        return card;
    }

    function candidateRow(panel, entry, mode, checked) {
        var label = el("label", "syl-reuse__cand");
        var box = el("input");
        box.type = "checkbox";
        box.setAttribute("data-syl-reuse-cand", entry.offering);
        box.checked = Boolean(checked) && Boolean(mode);
        box.disabled = !mode;
        label.appendChild(box);
        var text = el("span", "syl-reuse__cand-text");
        text.appendChild(el("span", "syl-reuse__cand-name", entry.group));
        text.appendChild(el("span", "syl-meta", entry.hours_text));
        label.appendChild(text);
        label.appendChild(el("span", "syl-reuse__mode syl-reuse__mode--" + (mode || "none"), t(panel, "mode-" + (mode || "none"))));
        return label;
    }

    function renderCandidates(panel) {
        var wrap = state.modal.querySelector("[data-syl-reuse-bulk]");
        var list = state.modal.querySelector("[data-syl-reuse-cands]");
        var source = selected();
        var data = state.data;
        list.textContent = "";
        var free = (data.candidates || []).filter(function (entry) {
            return entry.state === "none";
        });
        if (!source || !free.length) {
            show(wrap, false);
            return;
        }
        if (data.target.kind === "offering" && !data.target.blocked) {
            var own = source.can_link ? "link" : source.can_copy ? "copy" : "";
            var self = { offering: data.target.offering, group: data.target.group, hours_text: data.target.hours_text };
            list.appendChild(candidateRow(panel, self, own, true));
        }
        free.forEach(function (entry) {
            list.appendChild(candidateRow(panel, entry, (source.modes || {})[entry.offering] || "", true));
        });
        (data.candidates || [])
            .filter(function (entry) {
                return entry.state !== "none";
            })
            .forEach(function (entry) {
                var row = el("p", "syl-reuse__cand syl-reuse__cand--done");
                row.appendChild(el("span", "syl-reuse__cand-name", entry.group));
                row.appendChild(el("span", "syl-meta", entry.state_label));
                list.appendChild(row);
            });
        show(wrap, true);
    }

    function selectSource(panel, sourceId) {
        state.sourceId = sourceId;
        state.modal.querySelectorAll("[data-syl-reuse-src]").forEach(function (node) {
            var on = node.getAttribute("data-syl-reuse-src") === sourceId;
            node.classList.toggle("is-on", on);
            node.setAttribute("aria-checked", on ? "true" : "false");
            node.tabIndex = on ? 0 : -1;
        });
        var source = selected();
        var blocked = state.data.target.blocked;
        ["link", "copy"].forEach(function (kind) {
            var button = state.modal.querySelector("[data-syl-reuse-do='" + kind + "']");
            var hint = state.modal.querySelector("[data-syl-reuse-hint='" + kind + "']");
            var allowed = Boolean(source && !blocked && source["can_" + kind]);
            button.disabled = !allowed;
            hint.textContent = !source ? "" : allowed ? t(panel, kind + "-ok") : source[kind + "_reason"] || "";
            hint.classList.toggle("is-bad", Boolean(source) && !allowed);
        });
        renderCandidates(panel);
    }

    function render(panel, data) {
        var modal = state.modal;
        state.data = data;
        var target = data.target || {};
        modal.querySelector("[data-syl-reuse-target]").textContent = [
            target.subject,
            target.group,
            target.period,
            target.hours_text
        ]
            .filter(Boolean)
            .join(" · ");
        show(modal.querySelector("[data-syl-reuse-loading]"), false);
        var blocked = modal.querySelector("[data-syl-reuse-blocked]");
        var siblings = data.siblings || [];
        blocked.textContent = target.blocked ? target.blocked_reason : siblings.length ? "" : t(panel, "empty");
        show(blocked, Boolean(target.blocked) || !siblings.length);
        var list = modal.querySelector("[data-syl-reuse-sources]");
        list.textContent = "";
        siblings.forEach(function (row) {
            list.appendChild(sourceCard(panel, row));
        });
        show(modal.querySelector("[data-syl-reuse-sources-wrap]"), siblings.length > 0);
        show(modal.querySelector("[data-syl-reuse-choice]"), siblings.length > 0 && !target.blocked);
        show(modal.querySelector("[data-syl-reuse-replace]"), Boolean(target.replaces_draft));
        show(modal.querySelector("[data-syl-reuse-blank]"), Boolean(data.can_create_blank));
        if (siblings.length) {
            var preferred = siblings.filter(function (row) {
                return row.can_link;
            })[0] || siblings[0];
            selectSource(panel, preferred.id);
        } else {
            show(modal.querySelector("[data-syl-reuse-bulk]"), false);
        }
    }

    function openPicker(panel, trigger) {
        var modal = panel.querySelector("[data-syl-reuse-modal]");
        if (!modal) {
            return;
        }
        var kind = trigger.getAttribute("data-row-kind") === "missing" ? "offering" : "syllabus";
        var id = trigger.getAttribute("data-id");
        state = { panel: panel, modal: modal, trigger: trigger, kind: kind, id: id, data: null, dirty: false };
        ["[data-syl-reuse-sources-wrap]", "[data-syl-reuse-choice]", "[data-syl-reuse-bulk]", "[data-syl-reuse-blocked]",
            "[data-syl-reuse-results]", "[data-syl-reuse-blank]"].forEach(function (selector) {
            show(modal.querySelector(selector), false);
        });
        show(modal.querySelector("[data-syl-reuse-loading]"), true);
        modal.querySelector("[data-syl-reuse-target]").textContent = "";
        var closer = modal.querySelector(".syl-modal__foot [data-syl-reuse-close]");
        if (closer && t(panel, "cancel")) {
            closer.textContent = t(panel, "cancel");
        }
        modal.hidden = false;
        focusBox(modal);
        var url = new URL(modal.getAttribute("data-options-url"), window.location.origin);
        url.searchParams.set(kind, id);
        http(url.pathname + url.search)
            .then(function (data) {
                if (state && state.modal === modal) {
                    render(panel, data || {});
                }
            })
            .catch(function (err) {
                if (!state) {
                    return;
                }
                show(modal.querySelector("[data-syl-reuse-loading]"), false);
                var blocked = modal.querySelector("[data-syl-reuse-blocked]");
                blocked.textContent = errorText(panel, err);
                show(blocked, true);
            });
    }

    /* ── Əməllər ─────────────────────────────────────────────────────── */
    function targetPayload(payload) {
        payload[state.kind] = state.id;
        return payload;
    }

    function setBusy(on) {
        state.modal.querySelectorAll("[data-syl-reuse-do], [data-syl-reuse-blank]").forEach(function (button) {
            if (on) {
                button.setAttribute("data-was-disabled", button.disabled ? "1" : "0");
                button.disabled = true;
            } else {
                button.disabled = button.getAttribute("data-was-disabled") === "1";
            }
        });
    }

    function renderResults(panel, results) {
        var list = state.modal.querySelector("[data-syl-reuse-results]");
        var names = {};
        (state.data.candidates || []).forEach(function (entry) {
            names[entry.offering] = entry.group;
        });
        names[state.data.target.offering] = state.data.target.group;
        list.textContent = "";
        (results || []).forEach(function (row) {
            var item = el("li", "syl-reuse__result syl-reuse__result--" + row.status);
            item.appendChild(el("strong", "", names[row.offering] || ""));
            item.appendChild(el("span", "", " — " + (t(panel, "res-" + row.status) || row.status)));
            if (row.message) {
                item.appendChild(el("span", "syl-meta", row.message));
            }
            list.appendChild(item);
        });
        show(list, Boolean((results || []).length));
    }

    function runAction(panel, kind) {
        var source = selected();
        if (!state || !source) {
            return;
        }
        var modal = state.modal;
        var payload = { action: kind, source: source.id };
        if (kind === "bulk") {
            payload.offerings = Array.prototype.map.call(
                modal.querySelectorAll("[data-syl-reuse-cand]:checked"),
                function (box) {
                    return box.getAttribute("data-syl-reuse-cand");
                }
            );
            if (!payload.offerings.length) {
                return;
            }
        } else {
            targetPayload(payload);
        }
        setBusy(true);
        http(modal.getAttribute("data-action-url"), payload)
            .then(function (data) {
                toast(panel, (data && data.message) || "");
                if (kind === "bulk") {
                    /* Nəticə ekranı: seçim blokları bağlanır (hədəflərin vəziyyəti dəyişib),
                       dialoq bağlananda siyahı yenilənir. */
                    state.dirty = true;
                    setBusy(false);
                    ["[data-syl-reuse-sources-wrap]", "[data-syl-reuse-choice]", "[data-syl-reuse-bulk]",
                        "[data-syl-reuse-blank]"].forEach(function (selector) {
                        show(modal.querySelector(selector), false);
                    });
                    var close = modal.querySelector(".syl-modal__foot [data-syl-reuse-close]");
                    if (close && t(panel, "done")) {
                        close.textContent = t(panel, "done");
                    }
                    renderResults(panel, data && data.results);
                    return;
                }
                var current = state;
                state = null;
                current.modal.hidden = true;
                if (kind === "copy") {
                    openEditor(current.panel, data && data.version);
                } else {
                    refresh(current.panel, data && data.version);
                }
            })
            .catch(function (err) {
                if (state) {
                    setBusy(false);
                }
                toast(panel, errorText(panel, err));
            });
    }

    function createBlank(panel) {
        if (!state || state.kind !== "offering") {
            return;
        }
        var url = state.modal.getAttribute("data-create-url");
        var offering = state.id;
        setBusy(true);
        http(url, { action: "create", offering: offering })
            .then(function (data) {
                var current = state;
                state = null;
                current.modal.hidden = true;
                toast(panel, (data && data.message) || "");
                openEditor(panel, data && data.version);
            })
            .catch(function (err) {
                if (state) {
                    setBusy(false);
                }
                toast(panel, errorText(panel, err));
            });
    }

    /* ── «Ayır» / «Mənbədən yenilə» / «Bağlı sillabuslara tətbiq et» ───── */
    function openConfirm(panel, action, trigger) {
        var modal = panel.querySelector("[data-syl-reuse-confirm]");
        if (!modal) {
            return;
        }
        confirmState = { panel: panel, modal: modal, action: action, id: trigger.getAttribute("data-id"), trigger: trigger };
        var title = t(panel, action + "-title");
        modal.querySelector("[data-syl-reuse-confirm-title]").textContent = title;
        modal.querySelector("[data-syl-reuse-confirm-body]").textContent = t(panel, action + "-body");
        var ok = modal.querySelector("[data-syl-reuse-confirm-ok]");
        ok.textContent = t(panel, action + "-ok");
        ok.disabled = false;
        var box = modal.querySelector("[data-syl-reuse-confirm-box]");
        if (box) {
            box.setAttribute("aria-label", title);
        }
        modal.hidden = false;
        focusBox(modal);
    }

    function closeConfirm() {
        if (!confirmState) {
            return;
        }
        var current = confirmState;
        confirmState = null;
        current.modal.hidden = true;
        if (current.trigger && document.contains(current.trigger)) {
            current.trigger.focus();
        }
    }

    function runConfirm() {
        if (!confirmState) {
            return;
        }
        var current = confirmState;
        var ok = current.modal.querySelector("[data-syl-reuse-confirm-ok]");
        ok.disabled = true;
        http(current.modal.getAttribute("data-action-url"), { action: current.action, syllabus: current.id })
            .then(function (data) {
                confirmState = null;
                current.modal.hidden = true;
                toast(current.panel, (data && data.message) || "");
                if (current.action === "unlink" && data && data.version) {
                    openEditor(current.panel, data.version);
                } else {
                    refresh(current.panel, data && data.version);
                }
            })
            .catch(function (err) {
                ok.disabled = false;
                toast(current.panel, errorText(current.panel, err));
            });
    }

    /* ── Deleqasiya (document səviyyəsində BİR DƏFƏ) ──────────────────── */
    function bindOnce() {
        if (!window.EMSDelegate || window.__emsSyllabusReuseBound) {
            return;
        }
        window.__emsSyllabusReuseBound = true;
        var on = window.EMSDelegate.on;

        on("click", "[data-profile-section-panel] [data-syl-action]", function (event, button) {
            var action = button.getAttribute("data-syl-action");
            if (ACTIONS.indexOf(action) < 0) {
                return;
            }
            var panel = panelOf(button);
            if (action === "reuse") {
                openPicker(panel, button);
            } else {
                openConfirm(panel, action, button);
            }
        });
        on("click", "[data-syl-reuse-modal] [data-syl-reuse-src]", function (event, button) {
            if (state) {
                selectSource(state.panel, button.getAttribute("data-syl-reuse-src"));
            }
        });
        on("click", "[data-syl-reuse-modal] [data-syl-reuse-do]", function (event, button) {
            if (state && !button.disabled) {
                runAction(state.panel, button.getAttribute("data-syl-reuse-do"));
            }
        });
        on("click", "[data-syl-reuse-modal] [data-syl-reuse-blank]", function () {
            if (state) {
                createBlank(state.panel);
            }
        });
        on("click", "[data-syl-reuse-modal] [data-syl-reuse-close]", function () {
            closePicker(false);
        });
        on("click", "[data-syl-reuse-confirm] [data-syl-reuse-confirm-close]", closeConfirm);
        on("click", "[data-syl-reuse-confirm] [data-syl-reuse-confirm-ok]", runConfirm);

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                if (confirmState) {
                    closeConfirm();
                } else if (state) {
                    closePicker(false);
                }
                return;
            }
            /* Radio qrupu: ox düymələri ilə mənbə seçimi (WAI-ARIA radiogroup). */
            if (!state || (event.key !== "ArrowDown" && event.key !== "ArrowUp")) {
                return;
            }
            var current = document.activeElement;
            if (!current || !current.hasAttribute || !current.hasAttribute("data-syl-reuse-src")) {
                return;
            }
            var cards = Array.prototype.slice.call(state.modal.querySelectorAll("[data-syl-reuse-src]"));
            var index = cards.indexOf(current) + (event.key === "ArrowDown" ? 1 : -1);
            var next = cards[(index + cards.length) % cards.length];
            if (next) {
                event.preventDefault();
                selectSource(state.panel, next.getAttribute("data-syl-reuse-src"));
                next.focus();
            }
        });
    }

    window.EMSReady(function () {
        bindOnce();
    });
})();
