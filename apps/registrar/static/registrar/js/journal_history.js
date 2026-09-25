/* Jurnal «Dəyişiklik tarixçəsi» paneli (UNEC müqayisəsi P1-3, 2026-09-25).
 *
 * Data: `data-url` (registrar:journal_history) — 20-lik səhifələr, yenidən köhnəyə.
 * Açılış: istənilən `[data-jhist-open]` düyməsi (alət zolağı «Tarixçə», gün özəti
 * modalındakı «Bu dərsin tarixçəsi»); `data-jhist-date="YYYY-MM-DD"` süzgəci əvvəlcədən qoyur.
 *
 * Süzgəclər: DƏRS TARİXİ serverdə (?date=, dəyişəndə 1-ci səhifədən yenidən oxunur);
 * TƏLƏBƏ adı və NÖV çipləri yüklənmiş qeydlər üzərində, müştəri tərəfində —
 * diakritikaya dözümlü (ə/e, ı/i, ş/s … fərqi axtarışı pozmur).
 *
 * CSP/AJAX-safe: inline yoxdur; kliklər `EMSDelegate.on` ilə document-ə delegasiya
 * olunur, document/window dinləyiciləri `EMSReady.once` ilə BİR dəfə qoşulur.
 * Server mətni YALNIZ textContent ilə yazılır (XSS qapısı).
 */
(function () {
    "use strict";

    if (!window.EMSDelegate || !window.EMSReady) {
        return;
    }

    var ROW_PREVIEW = 8;
    var state = null;
    var lastTrigger = null;
    var searchTimer = null;

    function panel() {
        return document.querySelector("[data-jhist]");
    }

    function part(root, name) {
        return root ? root.querySelector("[data-jhist-" + name + "]") : null;
    }

    function show(node, visible) {
        if (node) {
            node.hidden = !visible;
        }
    }

    function t(root, key) {
        return (root && root.getAttribute("data-t-" + key)) || "";
    }

    // Tolerant axtarış (EMSSearch: az↔en hərfləri, «234king» → «234 K ing»).
    // «İ».toLowerCase() = «i» + U+0307 (birləşən nöqtə) — mətndən atılır.
    function searchMatcher(query) {
        var q = String(query || "").trim();
        var m = window.EMSSearch ? window.EMSSearch.matcher(q) : null;
        var low = q.toLowerCase();
        return function (text) {
            var t = String(text || "").replace(/\u0307/g, "");
            return m ? m(t) : !low || t.toLowerCase().indexOf(low) !== -1;
        };
    }

    function fmtDate(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
        return m ? m[3] + "." + m[2] + "." + m[1] : iso || "";
    }

    function shiftDay(iso, days) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
        if (!m) {
            return "";
        }
        var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3] + days));
        return d.toISOString().slice(0, 10);
    }

    function initials(name) {
        var parts = String(name || "").trim().split(/\s+/).filter(Boolean);
        var first = parts.length ? parts[0].charAt(0) : "";
        var second = parts.length > 1 ? parts[1].charAt(0) : "";
        return (first + second).toUpperCase() || "·";
    }

    function clone(root, name) {
        var tpl = root.querySelector('template[data-jhist-tpl="' + name + '"]');
        return tpl ? tpl.content.firstElementChild.cloneNode(true) : null;
    }

    function field(node, name) {
        return node.querySelector('[data-f="' + name + '"]');
    }

    function setField(node, name, value) {
        var target = field(node, name);
        if (target) {
            target.textContent = value == null ? "" : String(value);
        }
        return target;
    }

    function freshState(url) {
        return { url: url, entries: [], hasMore: false, nextOffset: 0, total: null, date: "", dates: [], token: 0 };
    }

    // ── Süzgəc ───────────────────────────────────────────────────────────────
    function currentKind(root) {
        var active = root.querySelector("[data-jhist-kind].is-active");
        return active ? active.getAttribute("data-jhist-kind") || "" : "";
    }

    function rowMatches(row, needle, match, date) {
        if (date && row.date !== date && String(row.old).indexOf(date) !== 0 && String(row.new).indexOf(date) !== 0) {
            return false;
        }
        if (needle && (row.lesson_level || !match(row.student))) {
            return false;
        }
        return true;
    }

    // ── Render ───────────────────────────────────────────────────────────────
    function dayLabel(root, day) {
        var today = root.getAttribute("data-today") || "";
        if (day === today) {
            return t(root, "today");
        }
        if (day === shiftDay(today, -1)) {
            return t(root, "yesterday");
        }
        return fmtDate(day);
    }

    function buildRow(root, row) {
        var tr = clone(root, "row");
        if (!tr) {
            return null;
        }
        setField(tr, "student", row.lesson_level ? t(root, "lesson") : row.student);
        if (row.lesson_level) {
            field(tr, "student").classList.add("is-lesson");
        }
        var dateNode = setField(tr, "date", row.date ? fmtDate(row.date) : "");
        if (dateNode && !row.date) {
            dateNode.hidden = true;
        }
        // Dərs sətrində tarix artıq «Nə» sütununun başındadır — təkrar yazılmır.
        var item = row.item || "";
        if (row.date && item.indexOf(row.date) === 0) {
            item = item.slice(row.date.length).replace(/^\s*·\s*/, "");
        }
        setField(tr, "item", item);
        setField(tr, "old", row.old);
        setField(tr, "new", row.new);
        return tr;
    }

    function buildEntry(root, entry, rows) {
        var card = clone(root, "entry");
        if (!card) {
            return null;
        }
        card.classList.add("jhist-entry--" + (entry.group || "mark"));
        setField(card, "initials", initials(entry.user));
        setField(card, "user", entry.user);
        if (entry.impersonated_by) {
            show(field(card, "imp"), true);
            setField(card, "imp-text", t(root, "imp") + ": " + entry.impersonated_by);
        }
        setField(card, "kind", entry.kind_label);
        var countText = rows.length === entry.count ? String(entry.count) : rows.length + " / " + entry.count;
        setField(card, "count", countText + " " + t(root, "changes"));
        var time = setField(card, "time", entry.time);
        if (time) {
            time.setAttribute("datetime", entry.when || "");
        }
        var body = field(card, "rows");
        rows.forEach(function (row, index) {
            var tr = buildRow(root, row);
            if (!tr) {
                return;
            }
            if (index >= ROW_PREVIEW) {
                tr.hidden = true;
                tr.setAttribute("data-jhist-extra", "");
            }
            body.appendChild(tr);
        });
        var hiddenCount = rows.length - ROW_PREVIEW;
        var expand = card.querySelector("[data-jhist-expand]");
        if (expand && hiddenCount > 0) {
            expand.hidden = false;
            expand.textContent = "+" + hiddenCount + " " + t(root, "expand");
            expand.setAttribute("data-label-more", expand.textContent);
            expand.setAttribute("aria-expanded", "false");
        }
        var capped = entry.count - (entry.rows || []).length;
        if (capped > 0 && rows.length === (entry.rows || []).length) {
            var note = setField(card, "capped", "+" + capped + " " + t(root, "capped"));
            show(note, true);
        }
        return card;
    }

    function render() {
        var root = panel();
        if (!root || !state) {
            return;
        }
        var list = part(root, "list");
        list.textContent = "";
        var qInput = part(root, "q");
        var needle = qInput ? qInput.value.trim() : "";
        var match = searchMatcher(needle);
        var kind = currentKind(root);
        var visible = 0;
        var lastDay = "";
        state.entries.forEach(function (entry) {
            if (kind && entry.group !== kind) {
                return;
            }
            var rows = (entry.rows || []).filter(function (row) {
                return rowMatches(row, needle, match, state.date);
            });
            if ((needle || state.date) && !rows.length) {
                return;
            }
            if (entry.day !== lastDay) {
                var head = clone(root, "day");
                if (head) {
                    setField(head, "label", dayLabel(root, entry.day));
                    list.appendChild(head);
                }
                lastDay = entry.day;
            }
            var card = buildEntry(root, entry, rows);
            if (card) {
                list.appendChild(card);
                visible += 1;
            }
        });
        var filtered = Boolean(needle || kind);
        show(part(root, "empty"), !state.entries.length && !state.date);
        show(part(root, "nomatch"), !visible && (state.entries.length > 0 || Boolean(state.date)));
        show(part(root, "partial"), filtered && state.hasMore);
        show(part(root, "more"), state.hasMore);
        var count = part(root, "count");
        if (count) {
            var total = state.total == null ? state.entries.length : state.total;
            count.textContent = state.entries.length + " / " + total + " " + t(root, "shown");
        }
        var totalNode = part(root, "total");
        if (totalNode && state.total != null && !state.date) {
            totalNode.textContent = " · " + state.total + " " + t(root, "total");
        }
    }

    function fillDates(root) {
        var select = part(root, "date");
        if (!select || !state.dates.length) {
            return;
        }
        var keep = state.date;
        while (select.options.length > 1) {
            select.remove(1);
        }
        state.dates.forEach(function (item) {
            var option = document.createElement("option");
            option.value = item.value;
            option.textContent = fmtDate(item.value) + (item.kinds && item.kinds.length ? " · " + item.kinds.join(", ") : "");
            select.appendChild(option);
        });
        if (keep && !state.dates.some(function (item) { return item.value === keep; })) {
            var extra = document.createElement("option");
            extra.value = keep;
            extra.textContent = fmtDate(keep);
            select.appendChild(extra);
        }
        select.value = keep;
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    // ── Şəbəkə ──────────────────────────────────────────────────────────────
    function load(append) {
        var root = panel();
        if (!root || !state) {
            return;
        }
        var token = ++state.token;
        var params = new URLSearchParams();
        params.set("offset", append ? String(state.nextOffset) : "0");
        if (state.date) {
            params.set("date", state.date);
        }
        show(part(root, "loading"), true);
        show(part(root, "error"), false);
        if (!append) {
            show(part(root, "empty"), false);
            show(part(root, "nomatch"), false);
        }
        var moreBtn = part(root, "more");
        if (moreBtn) {
            moreBtn.disabled = true;
        }
        var url = state.url + (state.url.indexOf("?") === -1 ? "?" : "&") + params.toString();
        window.EMSCore.fetchJSON(url, { method: "GET" })
            .then(function (data) {
                if (!state || token !== state.token) {
                    return;
                }
                show(part(root, "loading"), false);
                if (!data || data.ok !== true) {
                    show(part(root, "error"), true);
                    return;
                }
                state.entries = append ? state.entries.concat(data.entries || []) : data.entries || [];
                state.hasMore = Boolean(data.has_more);
                state.nextOffset = data.next_offset || state.entries.length;
                if (!append && typeof data.total === "number") {
                    state.total = data.total;
                }
                if (data.dates && data.dates.length) {
                    state.dates = data.dates;
                    fillDates(root);
                }
                render();
            })
            .catch(function () {
                if (!state || token !== state.token) {
                    return;
                }
                show(part(root, "loading"), false);
                show(part(root, "error"), true);
            })
            .then(function () {
                if (moreBtn) {
                    moreBtn.disabled = false;
                }
            });
    }

    // ── Açılış / bağlanış ────────────────────────────────────────────────────
    function open(trigger) {
        var root = panel();
        if (!root) {
            return;
        }
        var url = root.getAttribute("data-url") || "";
        var firstOpen = !state || state.url !== url;
        if (firstOpen) {
            state = freshState(url);
        }
        // Tarixi YALNIZ açan düymə verirsə dəyişirik (gün özəti) — alət zolağından
        // yenidən açanda istifadəçinin öz seçdiyi süzgəc itmir.
        var presetDate = (trigger && trigger.getAttribute("data-jhist-date")) || "";
        if (!presetDate && !firstOpen) {
            presetDate = state.date;
        }
        lastTrigger = trigger || null;
        // Gün özəti modalından açılıbsa o modal bağlanır (iki üst-üstə dialoq olmasın).
        var dayModal = trigger && trigger.closest("[data-jd-day-modal]");
        if (dayModal) {
            dayModal.hidden = true;
            // jd_day_summary.js açanda gövdə scroll-unu kilidləyir — burada azad edilir,
            // yoxsa panel bağlanandan sonra səhifə sürüşməz (paneli öz sinfi kilidləyir).
            document.body.style.overflow = "";
        }
        root.hidden = false;
        document.body.classList.add("jhist-open");
        var box = root.querySelector(".jhist__panel");
        if (box) {
            box.focus();
        }
        if (firstOpen || presetDate !== state.date) {
            state.date = presetDate;
            var select = part(root, "date");
            if (select) {
                if (presetDate && !Array.prototype.some.call(select.options, function (o) { return o.value === presetDate; })) {
                    var option = document.createElement("option");
                    option.value = presetDate;
                    option.textContent = fmtDate(presetDate);
                    select.appendChild(option);
                }
                select.value = presetDate;
                if (window.EMSBootstrapSelect) {
                    window.EMSBootstrapSelect.refresh(select);
                }
            }
            load(false);
        } else {
            render();
        }
    }

    function close() {
        var root = panel();
        if (!root || root.hidden) {
            return;
        }
        root.hidden = true;
        document.body.classList.remove("jhist-open");
        if (lastTrigger && document.contains(lastTrigger)) {
            lastTrigger.focus();
        }
        lastTrigger = null;
    }

    window.EMSDelegate.on("click", "[data-jhist-open]", function (event, button) {
        event.preventDefault();
        open(button);
    });

    window.EMSDelegate.on("click", "[data-jhist-close]", function (event) {
        event.preventDefault();
        close();
    });

    window.EMSDelegate.on("click", "[data-jhist-more]", function (event) {
        event.preventDefault();
        if (state && state.hasMore) {
            load(true);
        }
    });

    window.EMSDelegate.on("click", "[data-jhist-kind]", function (event, chip) {
        event.preventDefault();
        var root = panel();
        if (!root) {
            return;
        }
        root.querySelectorAll("[data-jhist-kind]").forEach(function (node) {
            var on = node === chip;
            node.classList.toggle("is-active", on);
            node.setAttribute("aria-pressed", on ? "true" : "false");
        });
        render();
    });

    window.EMSDelegate.on("click", "[data-jhist-expand]", function (event, button) {
        event.preventDefault();
        var card = button.closest(".jhist-entry");
        if (!card) {
            return;
        }
        var expanded = button.getAttribute("aria-expanded") === "true";
        card.querySelectorAll("[data-jhist-extra]").forEach(function (tr) {
            tr.hidden = expanded;
        });
        button.setAttribute("aria-expanded", expanded ? "false" : "true");
        button.textContent = expanded ? button.getAttribute("data-label-more") : t(panel(), "collapse");
    });

    window.EMSDelegate.on("change", "[data-jhist-date]", function (event, select) {
        if (!state) {
            return;
        }
        state.date = select.value || "";
        load(false);
    });

    window.EMSDelegate.on("input", "[data-jhist-q]", function () {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(render, 120);
    });

    window.EMSReady.once("jhist-esc", function () {
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                var root = panel();
                // Açıq tarix menyusu əvvəlcə öz-özünə bağlanır — panel ikinci Escape ilə.
                if (root && !root.hidden && !root.querySelector(".bootstrap-single-select__menu.show")) {
                    close();
                }
            }
        });
    });
})();
