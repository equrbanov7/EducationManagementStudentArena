/* «Nəzarət otağı» — imtahan səviyyəli canlı nəzarət (sahib 2026-11-06).
 *
 * Bütün imtahan növləri üçün eynidir. Snapshot hər `data-poll-seconds` saniyədə yenilənir
 * (səhifə gizlidirsə gözləyir, xəta olanda tədricən seyrəlir). Əməllər:
 *   «Bərpa et»  → POST resume  (kilidli tələbə; istəyə görə əlavə şans)
 *   «Dayandır»  → POST pause   (müvəqqəti kilid, cəhd təhvil verilmir)
 *   «Bax»       → GET attempt  (canlı irəliləyiş + nəzarət xronologiyası)
 * Server hər əməldə icazəni və vəziyyəti yenidən yoxlayır; düymələr yalnız ipucudur.
 * AJAX-safe: init `EMSReady` (idempotent), hadisələr `EMSDelegate` (document səviyyəsi).
 */
(function (window, document) {
    "use strict";

    var MAX_BACKOFF_SECONDS = 60;
    var state = { root: null, rows: [], timer: null, failures: 0, current: null, inFlight: false };

    function t(key) {
        var labels = state.labels || {};
        return labels[key] || key;
    }

    function readJSON(id) {
        var node = document.getElementById(id);
        if (!node) return null;
        try {
            return JSON.parse(node.textContent || "null");
        } catch (error) {
            return null;
        }
    }

    function fillUrl(template, attemptId) {
        return String(template || "").replace(/\/0\/(resume\/|pause\/)?$/, "/" + attemptId + "/$1");
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function formatRemaining(seconds) {
        if (seconds === null || seconds === undefined) return "—";
        var s = Math.max(0, parseInt(seconds, 10) || 0);
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        var sec = s % 60;
        var pad = function (n) { return (n < 10 ? "0" : "") + n; };
        return (h ? h + ":" + pad(m) : m) + ":" + pad(sec);
    }

    function formatTime(iso) {
        if (!iso) return "—";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return "—";
        var pad = function (n) { return (n < 10 ? "0" : "") + n; };
        return pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    function stateBadge(row) {
        var variant = { active: "primary", warned: "warning", locked: "danger", completed: "success" }[row.state] || "neutral";
        var badge = el("span", "ems-badge ems-badge--" + variant + " svr-state", t("state_" + row.state));
        if (row.manual_lock) badge.title = t("manual_lock");
        return badge;
    }

    function heartbeatCell(row) {
        var hb = row.heartbeat;
        if (!hb || row.state === "completed") return el("span", "svr-muted", t("hb_none"));
        var ok = hb.status === "ok";
        var node = el("span", "svr-hb svr-hb--" + (ok ? "ok" : "stale"), ok ? t("hb_ok") : t("hb_stale"));
        return node;
    }

    function actionButton(kind, row, label, variant, icon) {
        var btn = el("button", "ems-btn ems-btn--sm" + (variant ? " ems-btn--" + variant : ""));
        btn.type = "button";
        btn.setAttribute("data-svr-action", kind);
        btn.setAttribute("data-attempt-id", row.attempt_id);
        var i = el("i", "fas " + icon);
        i.setAttribute("aria-hidden", "true");
        btn.appendChild(i);
        btn.appendChild(document.createTextNode(" " + label));
        return btn;
    }

    function renderRow(row) {
        var tr = el("tr", "svr-row svr-row--" + row.state);
        tr.setAttribute("data-attempt-id", row.attempt_id);

        var who = el("td", "svr-who");
        who.appendChild(el("span", "svr-who__name", row.name));
        var meta = el("span", "svr-who__meta", "@" + row.username + (row.group ? " · " + row.group : ""));
        who.appendChild(meta);
        if (row.flagged) who.appendChild(el("span", "ems-badge ems-badge--danger svr-flag", t("flagged")));
        tr.appendChild(who);

        var st = el("td");
        st.appendChild(stateBadge(row));
        if (row.manual_lock) st.appendChild(el("span", "svr-sub", t("manual_lock")));
        tr.appendChild(st);

        var limit = row.max_violations ? " / " + row.max_violations : "";
        tr.appendChild(el("td", "svr-num" + (row.violation_count ? " svr-num--hot" : ""), row.violation_count + limit));
        var answered = row.answered === null || row.answered === undefined ? "—" : row.answered + " / " + row.question_total;
        tr.appendChild(el("td", "svr-num", answered));
        tr.appendChild(el("td", "svr-num", row.state === "completed" ? formatTime(row.finished_at) : formatRemaining(row.remaining_seconds)));

        var hb = el("td");
        hb.appendChild(heartbeatCell(row));
        tr.appendChild(hb);

        var actions = el("td", "svr-actions");
        if (row.can_resume) {
            actions.appendChild(actionButton("resume", row, t("resume"), "success", "fa-play"));
        } else if (row.resume_refusal) {
            actions.appendChild(el("span", "svr-sub", t("refusal_" + row.resume_refusal)));
        }
        if (row.can_pause) {
            actions.appendChild(actionButton("pause", row, t("pause"), "", "fa-pause"));
        } else if (row.pause_refusal === "hall") {
            // Zaldakı midterm/final: dayandırma imtahan mərkəzinin zal monitorundadır (rəsmi yol).
            var hall = el("a", "svr-sub svr-hall-link", t("refusal_hall"));
            hall.href = state.root.getAttribute("data-hall-monitor-url") || "#";
            actions.appendChild(hall);
        }
        actions.appendChild(actionButton("details", row, t("details"), "ghost", "fa-eye"));
        tr.appendChild(actions);
        return tr;
    }

    function matchesFilter(row) {
        var q = (document.getElementById("svr-filter") || {}).value || "";
        var st = (document.getElementById("svr-state-filter") || {}).value || "";
        q = q.trim();
        if (st && row.state !== st) return false;
        if (!q) return true;
        // Kanonik qatlama (EMSSearch): «aqsin» ↔ «Aqşin», «QULİYEV» ↔ «quliyev», söz sırası, «534t» → «534 T az».
        if (window.EMSSearch) return window.EMSSearch.matches(q, row.name + " " + row.username + " " + (row.group || ""));
        return (row.name + " " + row.username + " " + (row.group || "")).toLowerCase().indexOf(q.toLowerCase()) !== -1;
    }

    function render() {
        var body = document.getElementById("svr-rows");
        var empty = document.getElementById("svr-empty");
        if (!body) return;
        var frag = document.createDocumentFragment();
        var shown = 0;
        state.rows.forEach(function (row) {
            if (!matchesFilter(row)) return;
            frag.appendChild(renderRow(row));
            shown += 1;
        });
        body.replaceChildren(frag);
        if (empty) empty.hidden = state.rows.length > 0;
    }

    function applySnapshot(snapshot) {
        if (!snapshot) return;
        state.rows = Array.isArray(snapshot.rows) ? snapshot.rows : [];
        var counts = snapshot.counts || {};
        document.querySelectorAll("[data-svr-count]").forEach(function (node) {
            var key = node.getAttribute("data-svr-count");
            node.textContent = counts[key] !== undefined ? counts[key] : 0;
        });
        render();
    }

    function setConn(live) {
        var conn = document.getElementById("svr-conn");
        if (!conn) return;
        conn.setAttribute("data-state", live ? "live" : "offline");
        conn.textContent = live ? t("live") : t("offline");
    }

    function schedule() {
        window.clearTimeout(state.timer);
        var base = parseInt(state.root.getAttribute("data-poll-seconds"), 10) || 5;
        var delay = Math.min(MAX_BACKOFF_SECONDS, base * Math.pow(2, state.failures));
        state.timer = window.setTimeout(poll, delay * 1000);
    }

    function poll() {
        if (!state.root || !state.root.isConnected) return;
        if (document.hidden || state.inFlight) {
            schedule();
            return;
        }
        state.inFlight = true;
        window.EMSCore.fetchJSON(state.root.getAttribute("data-snapshot-url"))
            .then(function (snapshot) {
                state.failures = 0;
                setConn(true);
                applySnapshot(snapshot);
            })
            .catch(function () {
                state.failures = Math.min(state.failures + 1, 4);
                setConn(false);
            })
            .then(function () {
                state.inFlight = false;
                schedule();
            });
    }

    function rowById(attemptId) {
        for (var i = 0; i < state.rows.length; i += 1) {
            if (String(state.rows[i].attempt_id) === String(attemptId)) return state.rows[i];
        }
        return null;
    }

    function dialogError(dialog, message) {
        var node = dialog && dialog.querySelector("[data-svr-dialog-error]");
        if (!node) return;
        node.textContent = message || "";
        node.hidden = !message;
    }

    function openDialog(id, row) {
        var dialog = document.getElementById(id);
        if (!dialog || !window.EMSOverlay) return null;
        state.current = row;
        dialog.querySelectorAll("[data-svr-dialog-student]").forEach(function (node) {
            node.textContent = row ? row.name + " (@" + row.username + ")" : "";
        });
        dialogError(dialog, "");
        window.EMSOverlay.open(id);
        return dialog;
    }

    function openResume(row) {
        var dialog = openDialog("svr-resume-dialog", row);
        if (!dialog) return;
        var extra = document.getElementById("svr-resume-extra");
        var wrap = dialog.querySelector("[data-svr-extra-wrap]");
        if (extra) extra.checked = false;
        // Əl ilə dayandırmada pozuntu yoxdur — «əlavə şans» mənasızdır.
        if (wrap) wrap.hidden = Boolean(row.manual_lock);
    }

    function openPause(row) {
        openDialog("svr-pause-dialog", row);
        var reason = document.getElementById("svr-pause-reason");
        if (reason) reason.value = "";
    }

    function fact(label, value) {
        var item = el("div", "svr-fact");
        item.appendChild(el("span", "svr-fact__label", label));
        item.appendChild(el("strong", "svr-fact__value", value));
        return item;
    }

    function openDetails(row) {
        var dialog = openDialog("svr-detail-dialog", row);
        if (!dialog) return;
        var nameEl = dialog.querySelector("[data-svr-detail-name]");
        var subEl = dialog.querySelector("[data-svr-detail-sub]");
        var facts = dialog.querySelector("[data-svr-detail-facts]");
        var list = dialog.querySelector("[data-svr-detail-timeline]");
        var empty = dialog.querySelector("[data-svr-detail-empty]");
        if (nameEl) nameEl.textContent = row.name;
        if (subEl) subEl.textContent = "@" + row.username + (row.group ? " · " + row.group : "");
        if (facts) facts.replaceChildren();
        if (list) list.replaceChildren();
        if (empty) empty.hidden = true;
        var url = fillUrl(state.root.getAttribute("data-attempt-url-template"), row.attempt_id);
        window.EMSCore.fetchJSON(url)
            .then(function (data) {
                var proctor = data.proctor || {};
                var risk = proctor.risk || {};
                if (facts) {
                    facts.appendChild(fact(t("fact_started"), formatTime(row.started_at)));
                    facts.appendChild(fact(t("fact_language"), (row.language || "—").toUpperCase()));
                    facts.appendChild(fact(t("fact_answers"), (data.answered || 0) + " / " + (data.total_questions || 0)));
                    facts.appendChild(fact(t("fact_violations"), String(data.violation_count || 0)));
                    facts.appendChild(fact(t("fact_risk"), (risk.score || 0) + " / " + (risk.threshold || 0)));
                }
                var timeline = Array.isArray(proctor.timeline) ? proctor.timeline : [];
                if (empty) empty.hidden = timeline.length > 0;
                timeline.forEach(function (entry) {
                    var li = el("li", "svr-timeline__item svr-timeline__item--" + (entry.severity || "low"));
                    li.appendChild(el("span", "svr-timeline__time", formatTime(entry.at)));
                    li.appendChild(el("span", "svr-timeline__label", entry.note ? entry.label + ": " + entry.note : entry.label));
                    if (list) list.appendChild(li);
                });
            })
            .catch(function () {
                dialogError(dialog, t("failed"));
            });
    }

    function confirmAction(kind) {
        var row = state.current;
        if (!row) return;
        var dialogId = kind === "resume" ? "svr-resume-dialog" : "svr-pause-dialog";
        var dialog = document.getElementById(dialogId);
        var template = state.root.getAttribute(kind === "resume" ? "data-resume-url-template" : "data-pause-url-template");
        var body = new FormData();
        if (kind === "resume") {
            var extra = document.getElementById("svr-resume-extra");
            if (extra && extra.checked && !row.manual_lock) body.append("grant_extra_chance", "1");
        } else {
            var reason = document.getElementById("svr-pause-reason");
            body.append("reason", reason ? reason.value : "");
        }
        var button = dialog && dialog.querySelector("[data-svr-confirm]");
        if (button) button.disabled = true;
        window.EMSCore.fetchJSON(fillUrl(template, row.attempt_id), { method: "POST", body: body })
            .then(function () {
                window.EMSOverlay.close(dialog);
                state.failures = 0;
                window.clearTimeout(state.timer);
                poll();
            })
            .catch(function (error) {
                var payload = (error && error.payload) || {};
                dialogError(dialog, payload.error || t("failed"));
            })
            .then(function () {
                if (button) button.disabled = false;
            });
    }

    window.EMSReady(function () {
        var root = document.getElementById("svr-root");
        if (!root || root === state.root) return;
        state.root = root;
        state.labels = readJSON("svr-i18n") || {};
        state.failures = 0;
        applySnapshot(readJSON("svr-initial-snapshot"));
        schedule();
    });

    window.EMSReady.once("supervision-room", function () {
        window.EMSDelegate.on("click", "#svr-root [data-svr-action]", function (event, button) {
            var row = rowById(button.getAttribute("data-attempt-id"));
            if (!row) return;
            var kind = button.getAttribute("data-svr-action");
            if (kind === "resume") openResume(row);
            else if (kind === "pause") openPause(row);
            else openDetails(row);
        });
        window.EMSDelegate.on("click", "[data-svr-confirm]", function (event, button) {
            confirmAction(button.getAttribute("data-svr-confirm"));
        });
        window.EMSDelegate.on("input", "#svr-filter", render);
        window.EMSDelegate.on("change", "#svr-state-filter", render);
        document.addEventListener("visibilitychange", function () {
            if (!document.hidden && state.root) {
                window.clearTimeout(state.timer);
                poll();
            }
        });
    });
})(window, document);
