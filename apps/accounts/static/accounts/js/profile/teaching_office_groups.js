/* Ekran 06 «Qruplar» — TƏLƏBƏ ÇEKMECƏSİ.
 *
 * Qrup sətrindəki «Tələbələr» düyməsi (`[data-tof-students-open]`) sağdan
 * çekmecə açır, siyahı JSON-dan gəlir (`data-url`), axtarış/status süzgəci
 * müştəri tərəfindədir (qrup ≤ bir neçə yüz tələbədir). Hərəkət düymələri
 * («Qrupdan çıxar» = başqa qrupa köçür / «Dondur» / «Uzaqlaşdır») səbəb dialoqlarını
 * `data-tof-open` + `data-tof-prefill` ilə açır — göndərişi `teaching_office.js`
 * edir (səbəb ≥20 + təsdiq məcburidir), uğurda bölmə yenilənir və çekmecə
 * eyni qrup üçün YENİDƏN açılır ki, istifadəçi nəticəni görsün.
 *
 * AJAX-safe: EMSDelegate (bölmə swap-dan sonra da işləyir), null-safe.
 * CSP: xarici fayl; dinamik mətnlər data-atributdan oxunur. */
(function (window, document) {
    "use strict";

    var DRAWER_ID = "tofGroupStudentsDrawer";
    var DIALOG_IDS = ["tofStudentTransferDialog", "tofStudentFreezeDialog", "tofStudentExpelDialog"];
    var state = { url: "", name: "", planUrl: "", rows: [], canManage: false, canMove: false, status: "", reopen: "" };

    function drawer() { return document.getElementById(DRAWER_ID); }
    function root() { var d = drawer(); return d ? d.querySelector("[data-tof-students]") : null; }
    function t(key) { var r = root(); return r ? (r.getAttribute("data-t-" + key) || "") : ""; }
    function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
        });
    }
    function initials(name) {
        return String(name || "").split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p.charAt(0).toUpperCase(); }).join("") || "?";
    }
    function statusLabel(key) { return t("status-" + key) || key; }
    function withStudent(url, recordId) { return url + (url.indexOf("?") === -1 ? "?" : "&") + "student=" + encodeURIComponent(recordId); }

    function prefill(obj) { return JSON.stringify(obj); }

    function actionButtons(row) {
        var out = [];
        if (state.planUrl) {
            out.push('<a class="ems-btn ems-btn--sm" href="' + esc(withStudent(state.planUrl, row.id)) + '" download title="' + esc(t("plan")) + '"><i class="fas fa-file-word" aria-hidden="true"></i><span class="tof-students__btn-label">DOCX</span></a>');
        }
        // «Qrupdan çıxar» = başqa qrupa RƏSMİ köçürmə (DB qapısı qrup dəyişikliyini
        // yalnız köçürmə xidmətinə buraxır) — əmr № + tarix + hədəf qrup + səbəb.
        if (state.canMove && row.status === "enrolled") {
            out.push('<button type="button" class="ems-btn ems-btn--sm" data-tof-open="tofStudentTransferDialog" data-tof-student-name="' + esc(row.name) + '" data-tof-prefill=\'' + esc(prefill({ record_id: row.id, kind: "group_transfer" })) + '\'>' + esc(t("detach")) + "</button>");
            out.push('<button type="button" class="ems-btn ems-btn--sm ems-btn--warning" data-tof-open="tofStudentFreezeDialog" data-tof-student-name="' + esc(row.name) + '" data-tof-prefill=\'' + esc(prefill({ record_id: row.id, kind: "academic_leave" })) + '\'>' + esc(t("freeze")) + "</button>");
            out.push('<button type="button" class="ems-btn ems-btn--sm ems-btn--danger" data-tof-open="tofStudentExpelDialog" data-tof-student-name="' + esc(row.name) + '" data-tof-prefill=\'' + esc(prefill({ record_id: row.id, kind: "expulsion" })) + '\'>' + esc(t("expel")) + "</button>");
        }
        return out.join("");
    }

    function rowHtml(row) {
        var meta = ["@" + row.username];
        if (row.admission_year) { meta.push(t("admission") + " " + row.admission_year); }
        if (row.program) { meta.push(row.program); }
        return (
            '<li class="tof-students__row tof-students__row--' + esc(row.status) + '" data-tof-student-row data-status="' + esc(row.status) + '" data-search="' + esc((row.name + " " + row.username).toLowerCase()) + '">' +
            '<span class="tof-students__avatar" aria-hidden="true">' + esc(initials(row.name)) + "</span>" +
            '<div class="tof-students__main">' +
            '<div class="tof-students__name">' + esc(row.name) + ' <span class="ems-badge ems-badge--' + esc(row.status) + '">' + esc(statusLabel(row.status)) + "</span></div>" +
            '<div class="tof-students__sub">' + esc(meta.join(" · ")) + "</div>" +
            "</div>" +
            '<div class="tof-students__actions">' + actionButtons(row) + "</div>" +
            "</li>"
        );
    }

    function applyFilter() {
        var r = root();
        if (!r) { return; }
        var search = r.querySelector("[data-tof-students-search]");
        var needle = search ? String(search.value || "").trim().toLowerCase() : "";
        var visible = 0;
        Array.prototype.forEach.call(r.querySelectorAll("[data-tof-student-row]"), function (li) {
            var ok = (!needle || li.getAttribute("data-search").indexOf(needle) !== -1) &&
                (!state.status || li.getAttribute("data-status") === state.status);
            li.hidden = !ok;
            if (ok) { visible += 1; }
        });
        var empty = r.querySelector("[data-tof-students-empty]");
        var emptyText = r.querySelector("[data-tof-students-empty-text]");
        if (empty) {
            empty.hidden = !(state.rows.length && !visible);
            if (emptyText) { emptyText.textContent = t("no-match"); }
        }
    }

    function render() {
        var r = root();
        if (!r) { return; }
        var list = r.querySelector("[data-tof-students-list]");
        var meta = r.querySelector("[data-tof-students-meta]");
        var empty = r.querySelector("[data-tof-students-empty]");
        var emptyText = r.querySelector("[data-tof-students-empty-text]");
        list.setAttribute("aria-busy", "false");
        list.innerHTML = state.rows.map(rowHtml).join("");
        if (meta) { meta.textContent = t("count").replace("%d", String(state.rows.length)); }
        if (empty) {
            empty.hidden = state.rows.length > 0;
            if (emptyText) { emptyText.textContent = t("empty"); }
        }
        applyFilter();
    }

    function showError(message) {
        var r = root();
        if (!r) { return; }
        var box = r.querySelector("[data-tof-students-error]");
        var list = r.querySelector("[data-tof-students-list]");
        if (list) { list.innerHTML = ""; list.setAttribute("aria-busy", "false"); }
        if (box) { box.textContent = message; box.hidden = false; }
    }

    function resetDrawer(name) {
        var d = drawer();
        var r = root();
        if (!d || !r) { return; }
        var title = d.querySelector(".ems-drawer__title");
        if (title) { title.textContent = name; }
        var box = r.querySelector("[data-tof-students-error]");
        if (box) { box.hidden = true; }
        var search = r.querySelector("[data-tof-students-search]");
        if (search) { search.value = ""; }
        state.status = "";
        Array.prototype.forEach.call(r.querySelectorAll("[data-tof-students-status]"), function (chip) {
            chip.classList.toggle("is-active", chip.getAttribute("data-tof-students-status") === "");
        });
        var meta = r.querySelector("[data-tof-students-meta]");
        if (meta) { meta.textContent = t("loading"); }
        var list = r.querySelector("[data-tof-students-list]");
        if (list) {
            list.setAttribute("aria-busy", "true");
            list.innerHTML = '<li class="tof-students__skeleton" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--lg"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></li>'.repeat(3);
        }
        var plan = d.querySelector("[data-tof-students-plan]");
        if (plan) {
            plan.hidden = !state.planUrl;
            plan.setAttribute("href", state.planUrl || "#");
        }
    }

    function open(button) {
        var d = drawer();
        if (!d || !window.EMSOverlay) { return; }
        state.url = button.getAttribute("data-url") || "";
        state.name = button.getAttribute("data-name") || "";
        state.planUrl = button.getAttribute("data-plan-url") || "";
        state.groupId = button.getAttribute("data-group-id") || "";
        state.rows = [];
        resetDrawer(state.name);
        window.EMSOverlay.open(d, button);
        if (!state.url) { return; }
        var requestUrl = state.url;
        window.EMSCore.fetchJSON(requestUrl)
            .then(function (payload) {
                if (state.url !== requestUrl) { return; }
                state.rows = payload.rows || [];
                state.canManage = !!payload.can_manage;
                state.canMove = !!payload.can_move_students;
                render();
            })
            .catch(function () {
                if (state.url !== requestUrl) { return; }
                showError(t("error"));
            });
    }

    function reopenAfterReload() {
        if (!state.reopen) { return; }
        var url = state.reopen;
        state.reopen = "";
        var button = document.querySelector('[data-tof-students-open][data-url="' + url.replace(/"/g, '\\"') + '"]');
        if (button) { open(button); }
    }

    window.EMSReady(function () {
        if (window.__tofGroupStudentsBound) { return; }
        window.__tofGroupStudentsBound = true;

        window.EMSDelegate.on("click", "[data-tof-students-open]", function (event, button) {
            event.preventDefault();
            open(button);
        });
        window.EMSDelegate.on("input", "[data-tof-students-search]", function () { applyFilter(); });
        window.EMSDelegate.on("click", "[data-tof-students-status]", function (event, chip) {
            state.status = chip.getAttribute("data-tof-students-status") || "";
            Array.prototype.forEach.call(chip.parentNode.querySelectorAll("[data-tof-students-status]"), function (c) {
                c.classList.toggle("is-active", c === chip);
            });
            applyFilter();
        });
        // Dialoq açılanda hədəf tələbənin adı görünsün (prefill yalnız [name] sahələri doldurur).
        window.EMSDelegate.on("click", "[data-tof-open][data-tof-student-name]", function (event, button) {
            var dialog = document.getElementById(button.getAttribute("data-tof-open"));
            var target = dialog ? dialog.querySelector("[data-tof-movement-name]") : null;
            if (target) { target.textContent = button.getAttribute("data-tof-student-name") || ""; }
        });
        // Çekmecədən açılan dialoq göndəriləndə bölmə yenilənəcək — sonra çekmecəni eyni qrup üçün qaytar.
        window.EMSDelegate.on("submit", "form[data-tof-form]", function (event, form) {
            var overlay = form.closest(".ems-overlay");
            if (overlay && DIALOG_IDS.indexOf(overlay.id) !== -1 && state.url) { state.reopen = state.url; }
        });
        document.addEventListener("profile:section:loaded", function (event) {
            var section = event && event.detail ? event.detail.section : "";
            if (section && section !== "groups-registry") { return; }
            reopenAfterReload();
        });
    });
})(window, document);
