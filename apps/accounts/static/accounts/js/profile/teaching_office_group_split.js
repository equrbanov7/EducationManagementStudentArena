/* Qrup reyestri — ANA QRUPU ALT QRUPLARA BÖLMƏ dialoqu (sahib 2026-09-20).
 *
 * Səth: `_group_split_fields.html` (dialoq gövdəsi) + sətirdəki
 * `[data-tof-split-open]` düyməsi. Tələbə siyahısı sətrin `data-students-url`
 * JSON-undan gəlir (organizations:group_students). Bölgü DOM-da saxlanılır
 * (sütun = alt qrup; 0-cı sütun = ana qrupda qalanlar), göndərişdə gizli
 * `subgroups` sahəsinə JSON yazılır; formanı `teaching_office.js` (data-tof-form)
 * göndərir və uğurda reyestri yenidən yükləyir.
 *
 * AJAX-safe: EMSDelegate ilə delegasiya; vəziyyət modul daxilindədir və hər
 * açılışda sıfırlanır. Klaviatura: sütunlardakı checkbox-lar adi fokus sırasında,
 * «bura keçir» düymələri seçim olmayanda söndürülür. */
(function (window, document) {
    "use strict";
    if (!window.EMSDelegate) return;

    var DIALOG_ID = "tofGroupSplitDialog";
    var state = { groupId: "", groupName: "", students: [], columns: [], count: 2 };

    function dialog() { return document.getElementById(DIALOG_ID); }
    function rootEl() { var d = dialog(); return d ? d.querySelector("[data-tof-split]") : null; }
    function t(key) { var r = rootEl(); return r ? (r.getAttribute("data-t-" + key) || "") : ""; }
    function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
        });
    }
    function byName(a, b) { return String(a.name || "").localeCompare(String(b.name || ""), "az"); }

    /* ── Bölgü modeli ──────────────────────────────────────────────────────── */
    function defaultName(index) { return state.groupName + "-" + (index + 1); }
    function equalSplit() {
        var sorted = state.students.slice().sort(byName);
        var n = state.count;
        var size = Math.ceil(sorted.length / n);
        var columns = [{ name: "", ids: [] }];
        for (var i = 0; i < n; i += 1) {
            var existing = state.columns[i + 1];
            columns.push({
                name: existing && existing.name ? existing.name : defaultName(i),
                ids: sorted.slice(i * size, (i + 1) * size).map(function (s) { return s.id; }),
            });
        }
        state.columns = columns;
    }
    function columnOf(id) {
        for (var c = 0; c < state.columns.length; c += 1) {
            if (state.columns[c].ids.indexOf(id) !== -1) return c;
        }
        return 0;
    }
    function moveSelected(target) {
        var r = rootEl();
        if (!r) return;
        var picked = Array.prototype.map.call(r.querySelectorAll("[data-tof-split-pick]:checked"), function (cb) {
            return cb.value;
        });
        if (!picked.length) return;
        state.columns.forEach(function (col) {
            col.ids = col.ids.filter(function (id) { return picked.indexOf(id) === -1; });
        });
        state.columns[target].ids = state.columns[target].ids.concat(picked);
        render();
    }

    /* ── Render ─────────────────────────────────────────────────────────────── */
    function studentRow(student, column) {
        return (
            '<li class="tof-subsplit__student">' +
            '<label class="tof-subsplit__pick">' +
            '<input type="checkbox" data-tof-split-pick value="' + esc(student.id) + '" data-column="' + column + '">' +
            '<span class="tof-subsplit__avatar" aria-hidden="true">' + esc(initials(student.name)) + "</span>" +
            '<span class="tof-subsplit__name">' + esc(student.name) + '<small>@' + esc(student.username || "") + "</small></span>" +
            "</label></li>"
        );
    }
    function initials(name) {
        return String(name || "").split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p.charAt(0).toUpperCase(); }).join("") || "?";
    }
    function columnHtml(col, index) {
        var isParent = index === 0;
        var studentsById = {};
        state.students.forEach(function (s) { studentsById[s.id] = s; });
        var rows = col.ids.map(function (id) { return studentsById[id]; }).filter(Boolean).sort(byName);
        var head = isParent
            ? '<div class="tof-subsplit__colhead tof-subsplit__colhead--parent"><span class="tof-subsplit__coltitle"><i class="fas fa-house" aria-hidden="true"></i> ' + esc(t("parent")) + "</span>"
            : '<div class="tof-subsplit__colhead"><label class="tof-subsplit__namefield"><span class="visually-hidden">' + esc(t("name-label")) + '</span>' +
              '<input class="ems-input tof-subsplit__name-input" type="text" maxlength="255" data-tof-split-name data-column="' + index + '" value="' + esc(col.name) + '" aria-label="' + esc(t("name-label")) + '"></label>';
        head += '<span class="tof-subsplit__count-badge">' + rows.length + " " + esc(t("students")) + "</span></div>";
        var tools =
            '<div class="tof-subsplit__tools">' +
            '<button type="button" class="ems-btn ems-btn--sm tof-subsplit__selectall" data-tof-split-select-all data-column="' + index + '" title="' + esc(t("select-all")) + '" aria-label="' + esc(t("select-all")) + '">' +
            '<i class="fas fa-check-double" aria-hidden="true"></i></button>' +
            '<button type="button" class="ems-btn ems-btn--sm ems-btn--primary" data-tof-split-move data-column="' + index + '" disabled>' +
            '<i class="fas fa-arrow-right-to-bracket" aria-hidden="true"></i> ' + esc(t("move-here")) + "</button></div>";
        var list = rows.length
            ? '<ul class="tof-subsplit__list">' + rows.map(function (s) { return studentRow(s, index); }).join("") + "</ul>"
            : '<p class="tof-subsplit__empty">—</p>';
        return '<section class="tof-subsplit__col' + (isParent ? " tof-subsplit__col--parent" : "") + '" data-column="' + index + '">' + head + tools + list + "</section>";
    }
    function render() {
        var r = rootEl();
        if (!r) return;
        var board = r.querySelector("[data-tof-split-board]");
        // Alt qruplar əvvəl, «ana qrupda qalır» sütunu sonda (sağda).
        var order = state.columns.map(function (col, index) { return index; }).slice(1).concat([0]);
        board.innerHTML = order.map(function (index) { return columnHtml(state.columns[index], index); }).join("");
        var summary = r.querySelector("[data-tof-split-summary]");
        if (summary) {
            var parts = state.columns.slice(1).map(function (col) { return esc(col.name || "?") + ": <b>" + col.ids.length + "</b>"; });
            summary.innerHTML = parts.join(" · ") + (state.columns[0].ids.length ? ' · <span class="tof-subsplit__summary-parent">' + esc(t("parent")) + ": <b>" + state.columns[0].ids.length + "</b></span>" : "");
        }
        syncMoveButtons();
        serialize();
    }
    function syncMoveButtons() {
        var r = rootEl();
        if (!r) return;
        var picked = Array.prototype.map.call(r.querySelectorAll("[data-tof-split-pick]:checked"), function (cb) {
            return Number(cb.getAttribute("data-column"));
        });
        Array.prototype.forEach.call(r.querySelectorAll("[data-tof-split-move]"), function (btn) {
            var col = Number(btn.getAttribute("data-column"));
            var movable = picked.some(function (from) { return from !== col; });
            btn.disabled = !movable;
        });
    }
    function serialize() {
        var d = dialog();
        if (!d) return;
        var hidden = d.querySelector('input[name="subgroups"]');
        if (!hidden) return;
        hidden.value = JSON.stringify(
            state.columns.slice(1).map(function (col) { return { name: col.name, record_ids: col.ids }; })
        );
    }
    function showError(message) {
        var r = rootEl();
        var el = r ? r.querySelector("[data-tof-split-error]") : null;
        if (!el) return;
        el.textContent = message || "";
        el.hidden = !message;
    }

    /* ── Açılış: tələbələri gətir ───────────────────────────────────────────── */
    window.EMSDelegate.on("click", "[data-tof-split-open]", function (event, btn) {
        event.preventDefault();
        var d = dialog();
        var r = rootEl();
        if (!d || !r) return;
        state = { groupId: btn.getAttribute("data-group-id") || "", groupName: btn.getAttribute("data-group-name") || "", students: [], columns: [], count: 2 };
        var form = d.querySelector("form");
        if (form) {
            var idField = form.querySelector('input[name="id"]');
            if (idField) idField.value = state.groupId;
            var reason = form.querySelector('input[name="reason"]');
            if (reason) reason.value = "";
            var countSel = form.querySelector("[data-tof-subsplit-count]");
            if (countSel) { countSel.value = "2"; if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(countSel); }
        }
        showError("");
        var board = r.querySelector("[data-tof-split-board]");
        board.innerHTML = '<p class="tof-subsplit__loading"><i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> ' + esc(t("loading")) + "</p>";
        if (window.EMSOverlay) window.EMSOverlay.open(d);
        var url = btn.getAttribute("data-students-url") || "";
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                var rows = (payload && payload.rows) || [];
                state.students = rows
                    .filter(function (row) { return row && row.status === "enrolled"; })
                    .map(function (row) { return { id: String(row.id), name: row.name || row.username || "", username: row.username || "" }; });
                if (!state.students.length) {
                    board.innerHTML = '<p class="tof-subsplit__empty">' + esc(t("empty")) + "</p>";
                    return;
                }
                equalSplit();
                render();
            })
            .catch(function () {
                board.innerHTML = '<p class="tof-subsplit__error-inline">' + esc(t("load-failed")) + "</p>";
            });
    });

    /* ── Nəzarətlər ─────────────────────────────────────────────────────────── */
    window.EMSDelegate.on("change", "[data-tof-subsplit-count]", function (event, sel) {
        state.count = Math.max(2, Math.min(6, parseInt(sel.value, 10) || 2));
        if (state.students.length) { equalSplit(); render(); }
    });
    window.EMSDelegate.on("click", "[data-tof-split-auto]", function (event) {
        event.preventDefault();
        if (state.students.length) { equalSplit(); render(); }
    });
    window.EMSDelegate.on("change", "[data-tof-split-pick]", function () { syncMoveButtons(); });
    window.EMSDelegate.on("click", "[data-tof-split-select-all]", function (event, btn) {
        event.preventDefault();
        var col = btn.getAttribute("data-column");
        var r = rootEl();
        var boxes = r ? r.querySelectorAll('[data-tof-split-pick][data-column="' + col + '"]') : [];
        var allOn = boxes.length && Array.prototype.every.call(boxes, function (cb) { return cb.checked; });
        Array.prototype.forEach.call(boxes, function (cb) { cb.checked = !allOn; });
        syncMoveButtons();
    });
    window.EMSDelegate.on("click", "[data-tof-split-move]", function (event, btn) {
        event.preventDefault();
        moveSelected(Number(btn.getAttribute("data-column")));
    });
    window.EMSDelegate.on("input", "[data-tof-split-name]", function (event, input) {
        var col = Number(input.getAttribute("data-column"));
        if (state.columns[col]) { state.columns[col].name = input.value; serialize(); }
        var summary = rootEl() && rootEl().querySelector("[data-tof-split-summary]");
        if (summary) {
            summary.innerHTML = state.columns.slice(1).map(function (c) { return esc(c.name || "?") + ": <b>" + c.ids.length + "</b>"; }).join(" · ");
        }
    });

    /* ── Göndərişdən əvvəl yerli yoxlama (server də yoxlayır) ─────────────────
       Native CAPTURE dinləyici: teaching_office.js-in delegasiyalı `submit`
       (data-tof-form → POST) handler-indən ƏVVƏL işə düşür. */
    document.addEventListener(
        "submit",
        function (event) {
            var form = event.target;
            if (!form || !form.closest || !form.closest("#" + DIALOG_ID)) return;
            var filled = state.columns.slice(1).filter(function (c) { return c.ids.length; }).length;
            var unnamed = state.columns.slice(1).some(function (c) { return !String(c.name || "").trim(); });
            var message = "";
            if (!state.students.length || filled < 2) message = t("need-two");
            else if (unnamed) message = t("need-name");
            if (message) {
                event.preventDefault();
                event.stopImmediatePropagation();
                showError(message);
                return;
            }
            showError("");
            serialize();
        },
        true
    );
})(window, document);
