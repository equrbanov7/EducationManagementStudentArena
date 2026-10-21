/**
 * Zal monitoru — «Qayda pozanlar» paneli (sağ tərəf), 2026-10-21.
 *
 * Sahib: «say çoxaldıqca baxmaq çətinləşə bilər». Əvvəl hər poll-da bütün siyahı
 * `innerHTML` ilə yenidən çəkilirdi (300 tələbəlik zalda titrəmə, açıq olan heç nə qalmırdı).
 *
 *  · tələbə başına BİR sətir: ciddilik çipi, pozuntu sayı, növ üzrə cəm (`vio_types`), son an;
 *  · sıralama: ciddilik (dayandırılmış → şübhəli → ciddilik → ən yeni) və ya «ən yenilər»;
 *  · süzgəclər: ciddilik çipləri (saylarla), pozuntu növü (layihənin select komponenti),
 *    «yalnız yenilər» (bu ekranda açılmamış yeni hadisələr), ad / istifadəçi adı / yer № axtarışı;
 *  · sətir açılır → son hadisələrin qısa xronologiyası (kursorlu lentdən, bax
 *    `violation_feed.py`); tam tarixçə «Bax» modalındadır (dəyişməyib);
 *  · səhifələmə: ilk 30 sətir + «Daha çox göstər» / «Hamısını göstər»;
 *  · AÇARLI diff: sətir elementi `data-vio-key` ilə saxlanır, məzmun imzası dəyişməyibsə DOM-a
 *    toxunulmur, sıra dəyişəndə element köçürülür (yenidən yaradılmır) — açıq sətir açıq qalır.
 *
 * `room_aggregate.js` paneli `FXCVioPanel.create(...)` ilə qurur və hər snapshot-da `update()`
 * çağırır; «Bax / Bərpa et / Blokla» düymələrinin (`data-vio-act`) emalı orada qalıb.
 * Markup: `#fxc-violations-panel[data-violations-feed-url]`, `#fxc-violations-list`,
 * `#fxc-vio-search`, `#fxc-vio-type`, `[data-vio-sev]`, `[data-vio-sort]`, `#fxc-vio-new`,
 * `#fxc-vio-empty`, `#fxc-vio-foot`, `#fxc-vio-shown`, `#fxc-vio-more`, `#fxc-vio-all`, `#fxc-vio-less`.
 */
(function () {
    "use strict";

    if (window.FXCVioPanel) return;

    var PAGE = 30;
    var SEV_RANK = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };
    var SEVERITIES = ["critical", "high", "medium", "low"];
    var FEED_MIN_GAP_MS = 4000;

    function esc(text) {
        var d = document.createElement("div");
        d.textContent = text == null ? "" : String(text);
        return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function fmt(template, values) {
        return String(template || "").replace(/%\((\w+)\)s/g, function (_m, key) {
            return values[key] == null ? "" : String(values[key]);
        });
    }

    function searchMatcher(query) {
        var q = String(query || "").trim();
        var m = q && window.EMSSearch ? window.EMSSearch.matcher(q) : null;
        var low = q.toLowerCase();
        return function (text) {
            var t = String(text || "").replace(/̇/g, "");
            return m ? m(t) : !low || t.toLowerCase().indexOf(low) !== -1;
        };
    }

    function heartbeatIssue(s) {
        return window.FXCProctor ? window.FXCProctor.heartbeatInfo(s.heartbeat) : null;
    }

    function needsAttention(s) {
        return (s.violation_count > 0) || s.supervision_status === "locked" || !!s.flagged ||
            !!heartbeatIssue(s) || (s.signal_count > 0);
    }

    function rowKey(s) {
        return s.attempt_id ? "a" + s.attempt_id : "t" + (s.ticket_id || "") + "-" + (s.student_id || "");
    }

    function severityOf(s) {
        if (SEV_RANK[s.max_severity]) return s.max_severity;
        if (s.violation_count > 0 || s.supervision_status === "locked") return "medium";
        return "low";
    }

    function timeOf(iso) {
        if (!iso) return "";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        try { return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }); } catch (err) { return ""; }
    }

    function cmpDesc(a, b) { return a === b ? 0 : (a > b ? -1 : 1); }

    /** Sətrin GÖRÜNƏN sahələri — zamanla öz-özünə dəyişənlər (heartbeat «age», qalan saniyə) daxil deyil. */
    var SIG_FIELDS = ["attempt_id", "ticket_id", "session_id", "name", "username", "group", "student_number",
        "photo_url", "initials", "seat", "exam_title", "exam_kind_label", "supervision_status", "flagged",
        "risk_score", "risk_threshold", "max_severity", "signal_count", "violation_count", "vio_types",
        "vio_types_more", "last_event_at"];

    function rowSignature(s) {
        var out = SIG_FIELDS.map(function (f) { return s[f] == null ? null : s[f]; });
        var hb = heartbeatIssue(s);
        out.push(hb ? hb.cls : "");
        return JSON.stringify(out);
    }

    function create(opts) {
        var listEl = opts.listEl;
        if (!listEl) return null;
        var panelEl = opts.panelEl || listEl.parentNode;
        var countEl = opts.countEl;
        var t = opts.t || function (_path, fallback) { return fallback; };
        var kindSuffix = opts.kindSuffix || function () { return ""; };
        var feedUrl = (panelEl && panelEl.dataset.violationsFeedUrl) || "";
        function byId(id) { return document.getElementById(id); }
        var searchEl = byId("fxc-vio-search");
        var typeEl = byId("fxc-vio-type");
        var newEl = byId("fxc-vio-new");
        var emptyEl = byId("fxc-vio-empty");
        var footEl = byId("fxc-vio-foot");
        var shownEl = byId("fxc-vio-shown");
        var moreBtn = byId("fxc-vio-more");
        var allBtn = byId("fxc-vio-all");
        var lessBtn = byId("fxc-vio-less");

        var state = {
            q: "", sev: "", type: "", sort: "severity", onlyNew: false, limit: PAGE,
            expanded: {}, seen: null, labels: {}, events: {}, loadedAttempt: {},
            cursor: null, inflight: false, lastFeedAt: 0, pulse: {}
        };
        var rows = [];            // diqqət tələb edən bütün sətirlər (son snapshot)
        var byKey = {};           // açar → sətir datası
        var nodes = {};           // açar → DOM elementi
        var sigs = {};            // açar → əsas hissənin imzası
        var detailSigs = {};      // açar → açılan hissənin imzası
        var lastCount = -1;
        var typeOptionsKey = null;
        var labelsKey = "";

        function L(key, fallback) { return t("violations.panel." + key, fallback); }
        function label(code) { return state.labels[code] || code; }
        function sevLabel(sev) {
            return window.FXCProctor ? window.FXCProctor.severityLabel(sev) : sev;
        }
        function isUnseen(s) {
            var key = rowKey(s);
            return !!s.last_event_at && (!state.seen || (state.seen[key] || "") < s.last_event_at);
        }

        // ── Süzgəc + sıralama ────────────────────────────────────────────────
        function matches(s) {
            if (state.sev && severityOf(s) !== state.sev) return false;
            if (state.type && !(s.vio_types || []).some(function (e) { return e[0] === state.type; })) return false;
            if (state.onlyNew && !isUnseen(s)) return false;
            if (state.q) {
                var hay = [s.name, s.username, s.group, s.student_number, s.exam_title,
                    s.seat != null ? "#" + s.seat + " " + s.seat : ""].join(" ");
                if (!searchMatcher(state.q)(hay)) return false;
            }
            return true;
        }

        function compare(a, b) {
            var sevA = SEV_RANK[severityOf(a)] || 0, sevB = SEV_RANK[severityOf(b)] || 0;
            var lastA = a.last_event_at || "", lastB = b.last_event_at || "";
            if (state.sort === "recent") {
                return cmpDesc(lastA, lastB) || cmpDesc(sevA, sevB) || String(a.name).localeCompare(String(b.name));
            }
            return cmpDesc(a.supervision_status === "locked" ? 1 : 0, b.supervision_status === "locked" ? 1 : 0) ||
                cmpDesc(a.flagged ? 1 : 0, b.flagged ? 1 : 0) || cmpDesc(sevA, sevB) || cmpDesc(lastA, lastB) ||
                cmpDesc(a.risk_score || 0, b.risk_score || 0) || cmpDesc(a.violation_count || 0, b.violation_count || 0) ||
                String(a.name).localeCompare(String(b.name));
        }

        // ── Sətir HTML-i ─────────────────────────────────────────────────────
        function subjectOf(s) {
            var subj = s.exam_title || "";
            if (subj.indexOf("—") !== -1) subj = subj.split("—").pop().trim();
            return subj;
        }

        function typesHtml(s) {
            var list = s.vio_types || [];
            if (!list.length) return "";
            return '<div class="fxc-vio-types">' + list.map(function (e) {
                return '<span class="fxc-vio-type fxc-vio-type--' + esc(e[2]) +
                    (state.type === e[0] ? " is-match" : "") + '">' + esc(label(e[0])) +
                    ' <b>×' + esc(e[1]) + "</b></span>";
            }).join("") + (s.vio_types_more ? '<span class="fxc-vio-type fxc-vio-type--more">' +
                esc(fmt(L("moreTypes", "+%(count)s növ"), { count: s.vio_types_more })) + "</span>" : "") +
                "</div>";
        }

        function actionsHtml(s) {
            if (!s.attempt_id && !s.ticket_id) return "";
            var view = s.attempt_id
                ? '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-ghost" data-vio-act="detail" data-attempt="' +
                    esc(s.attempt_id) + '"><i class="fas fa-eye" aria-hidden="true"></i> ' +
                    esc(t("violations.view", "Bax")) + "</button>"
                : "";
            if (!s.ticket_id) return view ? '<div class="fxc-vio-actions">' + view + "</div>" : "";
            var locked = s.supervision_status === "locked";
            var main = locked
                ? '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-success" data-vio-act="grant" data-session="' +
                    esc(s.session_id) + '" data-ticket="' + esc(s.ticket_id) + '"><i class="fas fa-rotate-left" aria-hidden="true"></i> ' +
                    esc(t("violations.grantChance", "Bərpa et")) + "</button>"
                : '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-danger-ghost" data-vio-act="block" data-session="' +
                    esc(s.session_id) + '" data-ticket="' + esc(s.ticket_id) + '"><i class="fas fa-ban" aria-hidden="true"></i> ' +
                    esc(t("violations.block", "Blokla")) + "</button>";
            return '<div class="fxc-vio-actions">' + view + main + "</div>";
        }

        function mainHtml(s, key, open, unseen) {
            var P = window.FXCProctor;
            var sev = severityOf(s);
            var locked = s.supervision_status === "locked";
            var who = P
                ? P.avatarHtml(s, "sm") + '<span class="fxc-vio-who__txt"><span class="fxc-vio-name">' + esc(s.name) +
                    '</span><span class="fxc-vio-meta">' + P.metaLine(s) + "</span></span>"
                : '<span class="fxc-vio-who__txt"><span class="fxc-vio-name">' + esc(s.name) + "</span></span>";
            var last = timeOf(s.last_event_at);
            var sub = [];
            if (s.seat != null) sub.push("#" + esc(s.seat));
            sub.push(esc(subjectOf(s)) + esc(kindSuffix(s)));
            if (locked) sub.push("<b>" + esc(t("violations.locked", "Dayandırılıb")) + "</b>");
            if (last) {
                sub.push('<span class="fxc-vio-last" title="' + esc(L("lastAt", "Son hadisə")) + '"><i class="fas fa-clock" ' +
                    'aria-hidden="true"></i> ' + esc(last) + "</span>");
            }
            if (unseen) sub.push('<span class="fxc-vio-new">' + esc(L("isNew", "Yeni")) + "</span>");
            return '<div class="fxc-vio-top">' +
                    '<button type="button" class="fxc-vio-toggle fxc-vio-who" data-vio-toggle aria-expanded="' +
                        (open ? "true" : "false") + '" aria-controls="fxc-vio-d-' + esc(key) + '">' +
                        '<i class="fas fa-chevron-right fxc-vio-chev" aria-hidden="true"></i>' + who + "</button>" +
                    '<span class="fxc-vio-side"><span class="fxc-vio-sevchip fxc-vio-sevchip--' + esc(sev) + '">' +
                        esc(sevLabel(sev)) + '</span><span class="fxc-vio-count-badge">' + esc(s.violation_count || 0) + " " +
                        esc(t("violations.word", "pozuntu")) + "</span></span>" +
                "</div>" +
                '<div class="fxc-vio-sub">' + sub.join(" · ") + "</div>" +
                typesHtml(s) +
                // Risk nişanları + əməliyyatlar bir sətirdə — sətir hündürlüyü azalır (çox tələbədə sıx siyahı).
                '<div class="fxc-vio-bar">' + (P ? '<div class="fxc-vio-pbadges">' + P.badgesHtml(s) + "</div>" : "") +
                    actionsHtml(s) + "</div>";
        }

        function rowClass(s, open, unseen) {
            return "fxc-vio-row fxc-vio-row--sev-" + severityOf(s) +
                (s.supervision_status === "locked" ? " fxc-vio-row--locked" : "") +
                (s.flagged ? " fxc-vio-row--flagged" : "") + (unseen ? " fxc-vio-row--unseen" : "") +
                (open ? " is-open" : "");
        }

        // ── Açılan hissə: son hadisələr ──────────────────────────────────────
        function detailHtml(s) {
            var evs = (s.attempt_id && state.events[s.attempt_id]) || [];
            var P = window.FXCProctor;
            var body;
            if (!evs.length && s.attempt_id && !state.loadedAttempt[s.attempt_id]) {
                body = '<p class="fxc-vio-detail__msg">' + esc(L("loadingEvents", "Hadisələr yüklənir…")) + "</p>";
            } else if (P) {
                body = P.timelineHtml(evs.map(function (e) {
                    return { at: e.at, severity: e.severity, source: e.source, code: e.code, label: label(e.code) };
                }));
            } else {
                body = '<ol class="fxc-tl">' + evs.map(function (e) {
                    return '<li class="fxc-tl__item">' + esc(timeOf(e.at)) + " " + esc(label(e.code)) + "</li>";
                }).join("") + "</ol>";
            }
            return '<div class="fxc-vio-detail__title">' + esc(L("latest", "Son hadisələr")) + "</div>" + body +
                (s.attempt_id ? '<p class="fxc-vio-detail__hint">' +
                    esc(L("fullHistory", "Tam tarixçə və qeyd üçün «Bax» düyməsini basın.")) + "</p>" : "");
        }

        function syncDetail(key) {
            var el = nodes[key], s = byKey[key];
            if (!el || !s) return;
            var detail = el.querySelector(".fxc-vio-detail");
            var open = !!state.expanded[key];
            detail.hidden = !open;
            if (!open) return;
            var evs = (s.attempt_id && state.events[s.attempt_id]) || [];
            var sig = evs.map(function (e) { return e.id; }).join(",") + "|" + !!state.loadedAttempt[s.attempt_id] +
                "|" + labelsKey;
            if (detailSigs[key] === sig) return;
            detailSigs[key] = sig;
            detail.innerHTML = detailHtml(s);
        }

        // ── Açarlı diff ──────────────────────────────────────────────────────
        function ensureRow(key) {
            var el = nodes[key];
            if (el) return el;
            el = document.createElement("div");
            el.dataset.vioKey = key;
            el.innerHTML = '<div class="fxc-vio-main"></div><div class="fxc-vio-detail" id="fxc-vio-d-' + esc(key) + '" hidden></div>';
            nodes[key] = el;
            return el;
        }

        function syncRow(s) {
            var key = rowKey(s);
            var el = ensureRow(key);
            var open = !!state.expanded[key];
            var unseen = isUnseen(s);
            var sig = rowSignature(s) + "|" + open + "|" + unseen + "|" + state.type + "|" + labelsKey;
            if (sigs[key] !== sig) {
                sigs[key] = sig;
                el.className = rowClass(s, open, unseen);
                el.firstChild.innerHTML = mainHtml(s, key, open, unseen);
            }
            if (state.pulse[key]) {
                delete state.pulse[key];
                el.classList.remove("fxc-vio-row--pulse");
                void el.offsetWidth;
                el.classList.add("fxc-vio-row--pulse");
            }
            syncDetail(key);
            return el;
        }

        function render() {
            labelsKey = JSON.stringify(state.labels);
            var filtered = rows.filter(matches).sort(compare);
            var visible = filtered.slice(0, state.limit);
            var wanted = {};
            visible.forEach(function (s) { wanted[rowKey(s)] = true; });
            Object.keys(nodes).forEach(function (key) {
                if (wanted[key]) return;
                if (nodes[key].parentNode) nodes[key].parentNode.removeChild(nodes[key]);
                if (!byKey[key]) { delete nodes[key]; delete sigs[key]; delete detailSigs[key]; }
            });
            visible.forEach(function (s, i) {
                var el = syncRow(s);
                if (listEl.children[i] !== el) listEl.insertBefore(el, listEl.children[i] || null);
            });
            if (emptyEl) {
                emptyEl.hidden = visible.length > 0;
                emptyEl.textContent = rows.length
                    ? L("noMatch", "Süzgəcə uyğun tələbə yoxdur.")
                    : t("violations.empty", "Qayda pozan yoxdur");
            }
            if (footEl) {
                footEl.hidden = filtered.length <= PAGE;
                if (shownEl) shownEl.textContent = fmt(L("shown", "%(shown)s / %(total)s göstərilir"), {
                    shown: visible.length, total: filtered.length
                });
                if (moreBtn) moreBtn.hidden = visible.length >= filtered.length;
                if (allBtn) allBtn.hidden = visible.length >= filtered.length;
                if (lessBtn) lessBtn.hidden = state.limit <= PAGE || filtered.length <= PAGE;
            }
        }

        // ── Süzgəc idarələrinin sayları / seçimləri ──────────────────────────
        function syncControls() {
            var sevCounts = { "": rows.length };
            var typeCounts = {};
            rows.forEach(function (s) {
                var sev = severityOf(s);
                sevCounts[sev] = (sevCounts[sev] || 0) + 1;
                (s.vio_types || []).forEach(function (e) { typeCounts[e[0]] = (typeCounts[e[0]] || 0) + 1; });
            });
            Array.prototype.forEach.call(document.querySelectorAll("[data-vio-sev-count]"), function (el) {
                el.textContent = sevCounts[el.dataset.vioSevCount] || 0;
            });
            if (!typeEl) return;
            var codes = Object.keys(typeCounts).sort(function (a, b) {
                return cmpDesc(typeCounts[a], typeCounts[b]) || label(a).localeCompare(label(b));
            });
            var key = codes.map(function (c) { return c + ":" + typeCounts[c] + ":" + label(c); }).join("|");
            if (key === typeOptionsKey) return;
            typeOptionsKey = key;
            var first = typeEl.options[0];
            var allText = first ? first.textContent : "";
            if (state.type && !typeCounts[state.type]) state.type = "";
            typeEl.innerHTML = '<option value="">' + esc(allText) + "</option>" + codes.map(function (c) {
                return '<option value="' + esc(c) + '">' + esc(label(c)) + " (" + esc(typeCounts[c]) + ")</option>";
            }).join("");
            typeEl.value = state.type;
            if (typeof typeEl._refreshBootstrapSelect === "function") typeEl._refreshBootstrapSelect();
        }

        // ── Kursorlu hadisə lenti ────────────────────────────────────────────
        function applyFeed(d, single) {
            if (!d || !Array.isArray(d.events)) return;
            var limit = d.per_attempt || 5;
            Object.keys(d.labels || {}).forEach(function (code) { state.labels[code] = d.labels[code]; });
            var touched = {};
            d.events.forEach(function (e) {
                if (!e || !e.attempt) return;
                var buf = state.events[e.attempt] || (state.events[e.attempt] = []);
                if (buf.some(function (x) { return x.id === e.id; })) return;
                buf.push(e);
                touched[e.attempt] = true;
            });
            Object.keys(touched).forEach(function (aid) {
                state.events[aid].sort(function (a, b) { return cmpDesc(a.at || "", b.at || ""); });
                state.events[aid] = state.events[aid].slice(0, limit);
                if (d.delta && !single) state.pulse["a" + aid] = true;
            });
            if (!single && d.cursor) state.cursor = d.cursor;
            render();
        }

        function getJSON(url) {
            return window.fetch(url, {
                credentials: "same-origin", cache: "no-store",
                headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" }
            }).then(function (r) { return r.ok ? r.json() : null; });
        }

        function withParam(url, name, value) {
            return url + (url.indexOf("?") === -1 ? "?" : "&") + name + "=" + encodeURIComponent(value);
        }

        function fetchFeed() {
            if (!feedUrl || state.inflight || !rows.length || typeof window.fetch !== "function") return;
            var now = Date.now();
            if (now - state.lastFeedAt < FEED_MIN_GAP_MS) return;
            state.inflight = true;
            state.lastFeedAt = now;
            getJSON(state.cursor ? withParam(feedUrl, "cursor", state.cursor) : feedUrl)
                .then(function (d) { applyFeed(d, false); })
                .catch(function () { /* növbəti snapshot-da yenidən */ })
                .then(function () { state.inflight = false; });
        }

        function fetchAttempt(attemptId) {
            if (!feedUrl || !attemptId || state.loadedAttempt[attemptId] || typeof window.fetch !== "function") return;
            getJSON(withParam(feedUrl, "attempt", attemptId))
                .then(function (d) { state.loadedAttempt[attemptId] = true; applyFeed(d, true); })
                .catch(function () { state.loadedAttempt[attemptId] = true; render(); });
        }

        // ── Hadisələr (bir dəfə bağlanır) ────────────────────────────────────
        function markSeen(key) {
            var s = byKey[key];
            if (s && s.last_event_at && state.seen) state.seen[key] = s.last_event_at;
        }

        function toggle(key) {
            var s = byKey[key];
            if (!s) return;
            state.expanded[key] = !state.expanded[key];
            if (state.expanded[key]) {
                markSeen(key);
                if (s.attempt_id && !(state.events[s.attempt_id] || []).length) fetchAttempt(s.attempt_id);
            }
            render();
        }

        function setPressed(selector, attr, value) {
            Array.prototype.forEach.call(document.querySelectorAll(selector), function (btn) {
                var on = (btn.getAttribute(attr) || "") === value;
                btn.setAttribute("aria-pressed", on ? "true" : "false");
                btn.classList.toggle("is-active", on);
            });
        }

        function rerender() { state.limit = PAGE; render(); }

        if (listEl.dataset.fxcVioBound !== "1") {
            listEl.dataset.fxcVioBound = "1";
            listEl.addEventListener("click", function (evt) {
                var target = evt.target.closest ? evt.target : null;
                if (!target) return;
                var row = target.closest("[data-vio-key]");
                if (!row) return;
                if (target.closest("[data-vio-toggle]")) { toggle(row.dataset.vioKey); return; }
                if (target.closest('[data-vio-act="detail"]')) { markSeen(row.dataset.vioKey); render(); }
            });
            if (searchEl) searchEl.addEventListener("input", function () { state.q = searchEl.value || ""; rerender(); });
            if (typeEl) typeEl.addEventListener("change", function () { state.type = typeEl.value || ""; rerender(); });
            if (panelEl) {
                panelEl.addEventListener("click", function (evt) {
                    var sevBtn = evt.target.closest && evt.target.closest("[data-vio-sev]");
                    var sortBtn = evt.target.closest && evt.target.closest("[data-vio-sort]");
                    if (sevBtn) {
                        state.sev = sevBtn.getAttribute("data-vio-sev") || "";
                        setPressed("[data-vio-sev]", "data-vio-sev", state.sev);
                        rerender();
                    } else if (sortBtn) {
                        state.sort = sortBtn.getAttribute("data-vio-sort") || "severity";
                        setPressed("[data-vio-sort]", "data-vio-sort", state.sort);
                        rerender();
                    }
                });
            }
            if (newEl) {
                newEl.addEventListener("click", function () {
                    state.onlyNew = !state.onlyNew;
                    newEl.setAttribute("aria-pressed", state.onlyNew ? "true" : "false");
                    newEl.classList.toggle("is-active", state.onlyNew);
                    rerender();
                });
            }
            if (moreBtn) moreBtn.addEventListener("click", function () { state.limit += PAGE; render(); });
            if (allBtn) allBtn.addEventListener("click", function () { state.limit = Infinity; render(); });
            if (lessBtn) lessBtn.addEventListener("click", function () { state.limit = PAGE; render(); });
        }

        function update(snapshot) {
            Object.keys((snapshot && snapshot.event_labels) || {}).forEach(function (code) {
                state.labels[code] = snapshot.event_labels[code];
            });
            rows = ((snapshot && snapshot.students) || []).filter(needsAttention);
            byKey = {};
            rows.forEach(function (s) { byKey[rowKey(s)] = s; });
            if (state.seen === null) {
                // İlk snapshot = «baxılıb» bazası: yalnız ekran açıldıqdan SONRAKI hadisələr «yeni»dir.
                state.seen = {};
                rows.forEach(function (s) { if (s.last_event_at) state.seen[rowKey(s)] = s.last_event_at; });
            }
            if (countEl) countEl.textContent = rows.length;
            // Pozan yoxdursa süzgəc zolağı gizlənir (imtahan əvvəli boş idarələr göz yormasın).
            if (panelEl) panelEl.classList.toggle("is-empty", !rows.length);
            if (lastCount >= 0 && rows.length > lastCount && panelEl) {
                panelEl.classList.remove("fxc-flash");
                void panelEl.offsetWidth;
                panelEl.classList.add("fxc-flash");
            }
            lastCount = rows.length;
            syncControls();
            render();
            fetchFeed();
        }

        return {
            update: update,
            applyFeed: applyFeed,
            state: state,
            needsAttention: needsAttention
        };
    }

    window.FXCVioPanel = { create: create, needsAttention: needsAttention, severities: SEVERITIES };
})();
