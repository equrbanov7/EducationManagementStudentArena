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
    var ADD_DIALOG_ID = "tofGroupAddStudentsDialog";
    var MOVE_DIALOG_ID = "tofGroupMoveDialog";
    var DIALOG_IDS = ["tofStudentTransferDialog", "tofStudentFreezeDialog", "tofStudentExpelDialog", ADD_DIALOG_ID, MOVE_DIALOG_ID];
    var state = {
        url: "", name: "", planUrl: "", candidatesUrl: "", groupActive: true,
        rows: [], canManage: false, canMove: false, status: "", reopen: ""
    };

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
        // «Qrupu dəyiş» (sahib, 2026-09-08): səbəbli sadə köçürmə — qrup əməli
        // (`move_student`, `unit.group_manage`). Əmrli rəsmi hərəkət «Tələbə
        // reyestri»ndə qalır; dondur/uzaqlaşdır isə `student.movement` açarı ilə.
        if (state.canManage && row.status === "enrolled") {
            out.push('<button type="button" class="ems-btn ems-btn--sm ems-btn--primary" data-tof-open="' + MOVE_DIALOG_ID + '" data-tof-student-name="' + esc(row.name) + '" data-tof-prefill=\'' + esc(prefill({ action: "move_student", record_id: row.id, id: "", reason: "" })) + '\'><i class="fas fa-people-arrows" aria-hidden="true"></i> ' + esc(t("move")) + "</button>");
        }
        if (state.canMove && row.status === "enrolled") {
            out.push('<button type="button" class="ems-btn ems-btn--sm ems-btn--warning" data-tof-open="tofStudentFreezeDialog" data-tof-student-name="' + esc(row.name) + '" data-tof-prefill=\'' + esc(prefill({ record_id: row.id, kind: "academic_leave" })) + '\'>' + esc(t("freeze")) + "</button>");
            out.push('<button type="button" class="ems-btn ems-btn--sm ems-btn--danger" data-tof-open="tofStudentExpelDialog" data-tof-student-name="' + esc(row.name) + '" data-tof-prefill=\'' + esc(prefill({ record_id: row.id, kind: "expulsion" })) + '\'>' + esc(t("expel")) + "</button>");
        }
        return out.join("");
    }

    function rowHtml(row) {
        // Sahib (2026-09-07): «qeydiyyat qrupu» yox — ixtisas ŞİFRİ + qısa adı vacibdir.
        var meta = ["@" + row.username];
        var program = [row.program_code, row.program_name || row.program].filter(Boolean).join(" · ");
        if (program) { meta.push(program); }
        if (row.education_form_label) { meta.push(row.education_form_label); }
        if (row.admission_year) { meta.push(t("admission") + " " + row.admission_year); }
        return (
            '<li class="tof-students__row tof-students__row--' + esc(row.status) + '" data-tof-student-row data-status="' + esc(row.status) + '" data-search="' + esc((row.name + " " + row.username).toLowerCase()) + '">' +
            '<span class="tof-students__avatar" aria-hidden="true">' + esc(initials(row.name)) + "</span>" +
            '<div class="tof-students__main">' +
            '<div class="tof-students__name">' +
            (row.profile_url
                ? '<a class="tof-students__link" href="' + esc(row.profile_url) + '" target="_blank" rel="noopener" title="' + esc(t("profile")) + '">' + esc(row.name) + "</a>"
                : esc(row.name)) +
            ' <span class="ems-badge ems-badge--' + esc(row.status) + '">' + esc(statusLabel(row.status)) + "</span></div>" +
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
        // «Tələbə əlavə et» — açıq qrupa görə prefill/namizəd URL-i qoyulur;
        // arxiv qrupa əlavə yoxdur (server də rədd edir).
        var add = d.querySelector("[data-tof-students-add]");
        if (add) {
            add.hidden = !(state.groupActive && state.candidatesUrl);
            add.setAttribute("data-candidates-url", state.candidatesUrl || "");
            add.setAttribute("data-group-name", state.name || "");
            add.setAttribute("data-tof-prefill", prefill({ action: "add_students", id: state.groupId || "" }));
        }
    }

    /* ---- «Tələbə əlavə et» seçicisi ---------------------------------------
       Namizəd URL-i QRUPA görə dəyişir, `EMSSearchableSelect` isə URL-i
       yaradılanda bağlayır — ona görə hər açılışda seçici sıfırdan qurulur
       (təmiz markup klonu). Seçilmiş id-lər gizli `record_ids` sahəsinə
       vergüllə yazılır; `teaching_office.js` formanı olduğu kimi göndərir. */
    var pickerTemplate = null;

    function addDialog() { return document.getElementById(ADD_DIALOG_ID); }

    function pickerHost(dialog) { return dialog ? dialog.querySelector("[data-tof-add-picker]") : null; }

    function freshPickerRoot(host) {
        if (!pickerTemplate) {
            var seed = host.querySelector(".js-tof-add-students");
            pickerTemplate = seed ? seed.cloneNode(true) : null;
        }
        if (!pickerTemplate) { return null; }
        host.innerHTML = "";
        var node = pickerTemplate.cloneNode(true);
        node.classList.remove("ems-ss--multi", "ems-ss--single", "has-value", "is-open");
        host.appendChild(node);
        return node;
    }

    function syncAddSummary(dialog, count) {
        var summary = dialog.querySelector("[data-tof-add-summary]");
        if (!summary) { return; }
        summary.textContent = count
            ? (summary.getAttribute("data-t-count") || "%d").replace("%d", String(count))
            : (summary.getAttribute("data-t-none") || "");
        summary.classList.toggle("has-selection", count > 0);
    }

    function buildAddPicker(button) {
        var dialog = addDialog();
        var host = pickerHost(dialog);
        if (!dialog || !host || !window.EMSSearchableSelect) { return; }
        var url = button.getAttribute("data-candidates-url") || "";
        var groupName = button.getAttribute("data-group-name") || "";
        var nameEl = dialog.querySelector("[data-tof-add-group-name]");
        if (nameEl) { nameEl.textContent = groupName; }
        var hidden = dialog.querySelector('input[name="record_ids"]');
        if (hidden) { hidden.value = ""; }
        syncAddSummary(dialog, 0);
        var rootEl = freshPickerRoot(host);
        if (!rootEl || !url) { return; }
        var picker = window.EMSSearchableSelect.create(rootEl, {
            url: url,
            multi: true,
            skeleton: true,
            pageSize: 20,
            emptyText: host.getAttribute("data-empty") || "",
            removeLabel: host.getAttribute("data-remove-label") || "",
            onChange: function () {
                var ids = picker && typeof picker.ids === "function" ? picker.ids() : [];
                if (hidden) { hidden.value = ids.join(","); }
                syncAddSummary(dialog, ids.length);
            }
        });
        host._tofPicker = picker;
        // Dialoq görünəndən sonra fokus axtarış sahəsinə — dərhal yazmağa hazır.
        window.setTimeout(function () {
            var input = rootEl.querySelector("input");
            if (input && !dialog.hidden) { input.focus(); }
        }, 30);
    }

    function open(button) {
        var d = drawer();
        if (!d || !window.EMSOverlay) { return; }
        state.url = button.getAttribute("data-url") || "";
        state.name = button.getAttribute("data-name") || "";
        state.planUrl = button.getAttribute("data-plan-url") || "";
        state.candidatesUrl = button.getAttribute("data-candidates-url") || "";
        state.groupActive = button.getAttribute("data-group-active") !== "0";
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
        // «Tələbə əlavə et» — ortaq prefill-dən SONRA (bubble sırası) seçici qurulur.
        window.EMSDelegate.on("click", "[data-tof-add-students]", function (event, button) {
            buildAddPicker(button);
        });
        // Tələbə seçilməyibsə göndərmə — ortaq handler-dən ƏVVƏL (capture) kəsilir.
        document.addEventListener("submit", function (event) {
            var form = event.target;
            if (!form || !form.closest) { return; }
            var overlay = form.closest("#" + ADD_DIALOG_ID);
            if (!overlay) { return; }
            var hidden = form.querySelector('input[name="record_ids"]');
            if (hidden && hidden.value) { return; }
            event.preventDefault();
            event.stopImmediatePropagation();
            var box = form.querySelector("[data-ems-form-error]");
            var host = pickerHost(overlay);
            if (box) {
                box.textContent = host ? (host.getAttribute("data-empty") || "") : "";
                box.hidden = false;
            }
            var input = host ? host.querySelector("input") : null;
            if (input) { input.focus(); }
        }, true);
        // Çekmecədən açılan dialoq göndəriləndə bölmə yenilənəcək — sonra çekmecəni eyni qrup üçün qaytar.
        // ⚠️ SEÇİCİ QƏSDƏN FƏRQLİDİR: `EMSDelegate.on` eyni «hadisə|seçici» açarını
        // ƏVƏZ EDİR — çılpaq `form[data-tof-form]` yazılsa `teaching_office.js`-in
        // JSON göndəriş dinləyicisi silinir və dialoqlar adi (tam səhifə) POST edir
        // (2026-09-08 reqressiyası). Bu, yalnız «yenidən aç» qeydidir.
        window.EMSDelegate.on("submit", ".ems-overlay form[data-tof-form]", function (event, form) {
            var overlay = form.closest(".ems-overlay");
            if (!overlay || DIALOG_IDS.indexOf(overlay.id) === -1 || !state.url) { return; }
            // Sətirdən («+») açılan əlavə dialoqu çekmecəsizdir — köhnə qrupun çekmecəsini qaytarma.
            if (overlay.id === ADD_DIALOG_ID) {
                var d = drawer();
                if (!d || d.hidden) { return; }
            }
            state.reopen = state.url;
        });
        document.addEventListener("profile:section:loaded", function (event) {
            var section = event && event.detail ? event.detail.section : "";
            if (section && section !== "groups-registry") { return; }
            reopenAfterReload();
        });
    });
})(window, document);
