/*
 * exam_score_entry_draft.js — «İmtahan balının daxil edilməsi»: QARALAMA, «Yadda saxlamamısınız» və 15 dəqiqə
 * GERİ SAYIMI (sahib 2026-10-25). `exam_score_entry.js`-in QARDAŞIDIR; ortaq API `window.EMSExamScoreEntry`
 * və `window.EMSExamScoreEntryColumns`.
 *
 *   · Qaralama: daxil edilən ballar (dəyişmiş sətirlər), sütunlar və rejim 1.2 s sonra SERVERƏ
 *     (`data-draft-url`, keş — istifadəçi × açılış × imtahan) və `localStorage`-a yazılır; səhifə yenilənəndə
 *     (və ya başqa cihazdan girəndə) bərpa olunur, zolaqda «Qaralamanı sil». Qaralama rəsmi bal DEYİL —
 *     sistemə yalnız təsdiq dialoqu yazır; uğurlu yazıdan sonra server onu silir.
 *   · Saxlamadan çıxış: brauzerin `beforeunload` xəbərdarlığı + səhifədaxili keçidlər (sidebar, bölmə, növ
 *     düymələri) `EMSConfirm` ilə «Yadda saxlamamısınız»; filtr dəyişəndə qaralama dərhal yazılır.
 *   · Geri sayım: daxil edənin açıq pəncərəsi (`data-edit-until`) — «mm:ss qalıb»; bitəndə sətir «Yekun» olur.
 *
 * CSP: inline yoxdur; i18n `#eseI18n`. AJAX-safe: `EMSDelegate` (açarlar `change|[data-ese-form]`,
 * `input|[data-ese-form]`, `input|[data-ese-columns]`, `click|[data-ese-columns]`, `click|[data-ese-draft-discard]`
 * — yalnız burada), sənəd dinləyiciləri `EMSReady.once` ilə BİR dəfə.
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    var SAVE_DELAY = 1200;
    var state = { timer: null, lastSent: "", bypass: false };

    function api() {
        return window.EMSExamScoreEntry || null;
    }

    function columns() {
        return window.EMSExamScoreEntryColumns || null;
    }

    function root() {
        var host = document.querySelector("[data-ese-root]");
        return host && host.getAttribute("data-offering") && host.getAttribute("data-assessment") ? host : null;
    }

    function t(key) {
        var el = document.getElementById("eseI18n");
        return el ? el.getAttribute("data-" + key) || "" : "";
    }

    function storageKey(host) {
        return ["ese-draft", host.getAttribute("data-user"), host.getAttribute("data-offering"), host.getAttribute("data-assessment")].join(":");
    }

    function storage(action, key, value) {
        try {
            if (action === "get") {
                return JSON.parse(window.localStorage.getItem(key) || "null");
            }
            if (action === "set") {
                window.localStorage.setItem(key, JSON.stringify(value));
            } else {
                window.localStorage.removeItem(key);
            }
        } catch (err) {
            return null; // gizli pəncərə / bloklanmış saxlama — server qaralaması kifayətdir
        }
        return null;
    }

    /* Yalnız DƏYİŞMİŞ sətirlər (server dəyərindən fərqli). */
    function collect(host) {
        var values = {};
        api().rows(host).forEach(function (row) {
            var selects = Array.prototype.slice.call(row.querySelectorAll("[data-ese-q]"));
            var q = selects.map(function (select) {
                return select.value || "";
            });
            var qDirty = selects.some(function (select) {
                return !select.disabled && (select.value || "") !== (select.getAttribute("data-initial") || "");
            });
            var score = api().scoreInput(row);
            var sDirty = !!score && !score.disabled && (score.value || "") !== (score.getAttribute("data-initial") || "");
            if (qDirty || sDirty) {
                values[row.getAttribute("data-enrollment")] = { q: q, score: score ? score.value || "" : "" };
            }
        });
        var cols = host.querySelector("[data-ese-question-maxes]");
        return {
            values: values,
            columns: cols ? cols.value : "",
            mode: columns() ? columns().mode(host) : "",
        };
    }

    function isDirty(host) {
        return !!host && !!api() && Object.keys(collect(host).values).length > 0;
    }

    function draftUrl(host, withQuery) {
        var url = host.getAttribute("data-draft-url") || "";
        if (!url || !withQuery) {
            return url;
        }
        return url + "?offering=" + encodeURIComponent(host.getAttribute("data-offering")) +
            "&assessment=" + encodeURIComponent(host.getAttribute("data-assessment")) +
            "&org=" + encodeURIComponent(host.getAttribute("data-org") || "");
    }

    function setStatus(host, text) {
        var bar = host.querySelector("[data-ese-draft-status]");
        if (bar) {
            bar.textContent = text || "";
        }
    }

    function timeLabel(date) {
        var d = date instanceof Date ? date : new Date(date);
        return isNaN(d.getTime()) ? "" : ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
    }

    function persist(host) {
        if (!host || !api()) {
            return;
        }
        var payload = collect(host);
        var empty = !Object.keys(payload.values).length;
        var text = JSON.stringify(payload);
        if (text === state.lastSent) {
            return;
        }
        state.lastSent = text;
        var key = storageKey(host);
        storage(empty ? "remove" : "set", key, { payload: payload, saved_at: new Date().toISOString() });
        var core = window.EMSCore;
        if (!core || typeof core.fetchJSON !== "function" || !draftUrl(host)) {
            return;
        }
        var request = empty
            ? core.fetchJSON(draftUrl(host, true), { method: "DELETE" })
            : core.fetchJSON(draftUrl(host), {
                method: "POST",
                data: {
                    offering: host.getAttribute("data-offering"),
                    assessment: host.getAttribute("data-assessment"),
                    org: host.getAttribute("data-org") || "",
                    payload: payload,
                },
            });
        request.then(function () {
            setStatus(host, empty ? "" : t("draft-saved") + " · " + timeLabel(new Date()));
        }).catch(function () {
            state.lastSent = ""; // növbəti dəyişiklikdə yenidən cəhd
        });
    }

    function schedule() {
        window.clearTimeout(state.timer);
        state.timer = window.setTimeout(function () {
            persist(root());
        }, SAVE_DELAY);
    }

    DELEGATE.on("change", "[data-ese-form]", schedule);
    DELEGATE.on("input", "[data-ese-form]", schedule);
    DELEGATE.on("input", "[data-ese-columns]", schedule);
    DELEGATE.on("click", "[data-ese-columns]", schedule);

    /* ---- Bərpa ---------------------------------------------------------------- */

    function applyValue(select, value) {
        if (value === "" || select.querySelector('option[value="' + value + '"]')) {
            select.value = value;
            api().syncPlaceholderToggle(select);
            if (window.EMSBootstrapSelect && select.dataset.bootstrapSelectReady === "true") {
                window.EMSBootstrapSelect.sync(select);
            }
        }
    }

    function restore(host, payload, savedAt) {
        if (!payload || !payload.values || !Object.keys(payload.values).length) {
            return;
        }
        var cols = host.querySelector("[data-ese-question-maxes]");
        if (payload.columns && cols && payload.columns !== cols.value && columns()) {
            columns().setColumns(host, payload.columns.split(",").map(Number));
        }
        if (payload.mode && columns() && host.querySelector('[data-ese-mode="' + payload.mode + '"]')) {
            columns().setMode(host, payload.mode);
        }
        api().rows(host).forEach(function (row) {
            var item = payload.values[row.getAttribute("data-enrollment")];
            if (!item || api().rowLocked(row, host)) {
                return;
            }
            row.querySelectorAll("[data-ese-q]").forEach(function (select, index) {
                if (!select.disabled && item.q && index < item.q.length) {
                    applyValue(select, String(item.q[index] || ""));
                }
            });
            var score = api().scoreInput(row);
            if (score && !score.readOnly && item.score !== undefined) {
                score.value = item.score;
            }
        });
        api().syncAll(host);
        state.lastSent = JSON.stringify(collect(host));
        showBanner(host, savedAt);
    }

    function showBanner(host, savedAt) {
        var form = host.querySelector("[data-ese-form]");
        if (!form || host.querySelector("[data-ese-draftbar]")) {
            return;
        }
        var bar = document.createElement("div");
        bar.className = "ems-msg ems-msg--info ese-draftbar";
        bar.setAttribute("data-ese-draftbar", "");
        bar.setAttribute("role", "status");
        var text = document.createElement("span");
        text.textContent = t("draft-restored") + (savedAt ? " · " + timeLabel(savedAt) : "");
        var discard = document.createElement("button");
        discard.type = "button";
        discard.className = "ems-btn ems-btn--sm ems-btn--ghost";
        discard.setAttribute("data-ese-draft-discard", "");
        discard.textContent = t("draft-discard");
        bar.appendChild(text);
        bar.appendChild(discard);
        form.parentNode.insertBefore(bar, form);
    }

    DELEGATE.on("click", "[data-ese-draft-discard]", function (event, btn) {
        event.preventDefault();
        var host = root();
        var reset = host ? host.querySelector("[data-ese-reset]") : null;
        if (reset) {
            reset.click();
        }
        if (host && columns()) {
            columns().setMode(host, "");
        }
        var bar = btn.closest("[data-ese-draftbar]");
        if (bar) {
            bar.remove();
        }
        persist(host);
    });

    function load(host) {
        var local = storage("get", storageKey(host));
        var core = window.EMSCore;
        if (!core || typeof core.fetchJSON !== "function" || !draftUrl(host)) {
            restore(host, local && local.payload, local && local.saved_at);
            return;
        }
        core.fetchJSON(draftUrl(host, true)).then(function (data) {
            if (root() !== host) {
                return; // panel artıq dəyişib
            }
            if (data && data.draft) {
                restore(host, data.draft, data.saved_at);
            } else {
                restore(host, local && local.payload, local && local.saved_at);
            }
        }).catch(function () {
            restore(host, local && local.payload, local && local.saved_at);
        });
    }

    /* ---- Geri sayım (daxil edənin 15 dəqiqəlik pəncərəsi) ---------------------- */

    function tick() {
        var host = root();
        if (!host || !api()) {
            return;
        }
        var expired = false;
        host.querySelectorAll("[data-ese-row][data-edit-until]").forEach(function (row) {
            var until = Date.parse(row.getAttribute("data-edit-until") || "");
            if (isNaN(until)) {
                return;
            }
            var left = Math.floor((until - Date.now()) / 1000);
            var label = row.querySelector("[data-ese-window]");
            if (left <= 0) {
                row.setAttribute("data-edit-until", "");
                row.setAttribute("data-final", "1");
                row.classList.add("is-final");
                if (label) {
                    label.hidden = true;
                }
                expired = true;
                return;
            }
            if (label) {
                label.textContent = Math.floor(left / 60) + ":" + ("0" + (left % 60)).slice(-2) + " · " + t("window-left");
            }
        });
        if (expired) {
            api().applyQuestionGrid(host);
            api().syncAll(host);
        }
    }

    /* ---- Saxlamadan çıxış ------------------------------------------------------ */

    function shouldGuard(anchor) {
        if (!anchor || state.bypass || anchor.target === "_blank" || anchor.hasAttribute("download")) {
            return false;
        }
        var href = anchor.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#" || /^(javascript|mailto|tel):/i.test(href)) {
            return false;
        }
        if (anchor.closest("[data-ems-overlay], .ems-drawer, .ems-dialog")) {
            return false;
        }
        return isDirty(root());
    }

    window.EMSReady.once("ese-draft-guards", function () {
        document.addEventListener("click", function (event) {
            if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }
            var anchor = event.target && event.target.closest ? event.target.closest("a[href]") : null;
            if (!shouldGuard(anchor)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            persist(root());
            var go = function () {
                state.bypass = true;
                window.location.assign(anchor.href);
            };
            if (!window.EMSConfirm) {
                go();
                return;
            }
            window.EMSConfirm.open({
                title: t("leave-title"),
                body: t("leave-body"),
                confirmLabel: t("leave-confirm"),
                cancelLabel: t("leave-cancel"),
                danger: true,
            }).then(function (ok) {
                if (ok) {
                    go();
                }
            });
        }, true);
        // Filtr dəyişəndə panel SPA ilə yenidən yüklənir — qaralama dərhal yazılsın (gecikmə gözlənilmir).
        document.addEventListener("change", function (event) {
            if (event.target && event.target.closest && event.target.closest("[data-ems-filters]")) {
                persist(root());
            }
        }, true);
        window.addEventListener("pagehide", function () {
            persist(root());
        });
        window.addEventListener("beforeunload", function (event) {
            var host = root();
            if (state.bypass || !host || host.getAttribute("data-submitting") === "1" || !isDirty(host)) {
                return;
            }
            persist(host);
            event.preventDefault();
            event.returnValue = "";
        });
    });

    window.EMSReady(function () {
        var host = root();
        if (!host || !api() || host.getAttribute("data-ese-draft-ready") === "1") {
            return;
        }
        host.setAttribute("data-ese-draft-ready", "1");
        state.bypass = false;
        state.lastSent = JSON.stringify(collect(host));
        load(host);
        window.clearInterval(window.__eseCountdown);
        window.__eseCountdown = window.setInterval(tick, 1000);
        tick();
    });
})(window, document);
