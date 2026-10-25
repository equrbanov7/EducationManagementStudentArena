/*
 * «Yük bölgüsü» — «İntensiv kurs» dialoqu (sahib 2026-10-25).
 *
 * Bir addımda: tapşırıq sətri + müəllim bölgüsü + qrupsuz jurnal + tələbə qeydiyyatı (server:
 * `apps/workload/services/intensive.py`). Seçicilər server-backed `EMSSearchableSelect`-dir; fənn və ya
 * tələbə dəyişəndə `intensive_preview` hər tələbənin vəziyyətini göstərir (yazılacaq / adi jurnalda
 * aktivdir / yazıla bilməz). Kafedra «Yük bölgüsü»nün süzgəcindən oxunur (`[data-wl-chair]`).
 *
 * AJAX-safe: `EMSDelegate.on` (bir dəfə) + DOM hər çağırışda yenidən axtarılır; əsas modul
 * (`window.EMSWorkloadDist`) null-safe oxunur.
 */
(function (window, document) {
    "use strict";

    var gettext = window.gettext || function (value) { return value; };
    var PICKERS = null;

    function modalEl() {
        return document.querySelector("[data-wli-modal]");
    }

    function chairId() {
        var select = document.querySelector("[data-wl-chair]");
        return select ? select.value : "";
    }

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function showError(text) {
        var node = document.querySelector("[data-wli-error]");
        if (!node) return;
        node.textContent = text || "";
        node.hidden = !text;
    }

    function messageFor(err) {
        var el = modalEl();
        var payload = err && err.payload;
        return (payload && (payload.message || payload.error)) || (el && el.dataset.textError) || gettext("Əməliyyat alınmadı.");
    }

    function lookupUrl(kind) {
        var el = modalEl();
        return (el ? el.dataset.lookupUrl : "") + "?kind=" + encodeURIComponent(kind);
    }

    function buildPickers() {
        var el = modalEl();
        if (!el || !window.EMSSearchableSelect) return null;
        var SS = window.EMSSearchableSelect;
        var common = { dependParam: "chair", getDependValue: chairId, skeleton: true };
        var pickers = {
            subject: SS.create(el.querySelector(".js-wli-subject"), Object.assign({ url: lookupUrl("subjects") }, common)),
            teacher: SS.create(el.querySelector(".js-wli-teacher"), Object.assign({ url: lookupUrl("teachers") }, common)),
            students: SS.create(
                el.querySelector(".js-wli-students"),
                Object.assign({ url: lookupUrl("students"), multi: true }, common)
            ),
        };
        if (!pickers.subject || !pickers.teacher || !pickers.students) return null;
        pickers.subject.on("change", preview);
        pickers.students.on("change", preview);
        return pickers;
    }

    function pickers() {
        var el = modalEl();
        if (!PICKERS || !el || !el.contains(PICKERS.subject.el)) PICKERS = buildPickers();
        return PICKERS;
    }

    function formData(action) {
        var form = document.querySelector("[data-wli-form]");
        var data = new FormData(form || undefined);
        var p = pickers();
        data.append("action", action);
        data.append("chair", chairId());
        if (p) {
            data.append("subject", p.subject.value());
            data.append("teacher", p.teacher.value());
            p.students.values().forEach(function (id) { data.append("students", id); });
        }
        return data;
    }

    function post(action) {
        var el = modalEl();
        return window.EMSCore.fetchJSON(el.dataset.actionUrl, { method: "POST", body: formData(action) });
    }

    function renderStudents(items) {
        var host = document.querySelector("[data-wli-students]");
        var el = modalEl();
        if (!host || !el) return;
        host.innerHTML = (items || [])
            .map(function (item) {
                var text = item.status === "ok"
                    ? el.dataset.textOk + (item.retake ? " — " + el.dataset.textRetake : "")
                    : item.message;
                return '<li class="wli__student wli__student--' + esc(item.status) + '"><b>' + esc(item.name) + "</b>" +
                    (item.group ? " · " + esc(item.group) : "") + '<span class="wli__student-note">' + esc(text) + "</span></li>";
            })
            .join("");
    }

    function preview() {
        var p = pickers();
        showError("");
        if (!p || !p.subject.value() || !p.students.values().length) {
            renderStudents([]);
            return;
        }
        post("intensive_preview")
            .then(function (payload) { renderStudents(payload.students); })
            .catch(function (err) { showError(messageFor(err)); });
    }

    function reset() {
        var form = document.querySelector("[data-wli-form]");
        if (form) form.reset();
        var p = pickers();
        if (p) {
            p.subject.reset();
            p.teacher.reset();
            p.students.reset();
        }
        renderStudents([]);
        showError("");
    }

    function open() {
        var el = modalEl();
        if (!el || !window.bootstrap || !window.bootstrap.Modal) return;
        if (!chairId()) {
            window.alert(gettext("Əvvəlcə kafedranı seçin."));
            return;
        }
        reset();
        window.bootstrap.Modal.getOrCreateInstance(el).show();
    }

    function submit(button) {
        var el = modalEl();
        showError("");
        button.disabled = true;
        post("intensive_create")
            .then(function () {
                window.bootstrap.Modal.getOrCreateInstance(el).hide();
                if (window.EMSToast && typeof window.EMSToast.show === "function") {
                    window.EMSToast.show(el.dataset.textDone, "success");
                }
                if (window.EMSWorkloadDist) window.EMSWorkloadDist.loadRows();
            })
            .catch(function (err) { showError(messageFor(err)); })
            .then(function () { button.disabled = false; });
    }

    function cancel(button) {
        var el = modalEl();
        if (!el) return;
        var question = gettext("İntensiv kurs ləğv edilsin? (yalnız jurnalda dərs yoxdursa mümkündür)");
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            window.EMSConfirm.open({ body: question, danger: true }).then(function (ok) {
                if (ok) sendCancel(el, button);
            });
        }
    }

    function sendCancel(el, button) {
        var data = new FormData();
        data.append("action", "intensive_cancel");
        data.append("row", button.dataset.rowId || "");
        window.EMSCore.fetchJSON(el.dataset.actionUrl, { method: "POST", body: data })
            .then(function () { if (window.EMSWorkloadDist) window.EMSWorkloadDist.loadRows(); })
            .catch(function (err) { window.alert(messageFor(err)); });
    }

    function bind() {
        var EMSDelegate = window.EMSDelegate;
        if (!EMSDelegate || bind.done) return;
        bind.done = true;
        EMSDelegate.on("click", "[data-wl-open-intensive]", function () { open(); });
        EMSDelegate.on("click", "[data-wli-submit]", function (event, button) { submit(button); });
        EMSDelegate.on("click", "[data-wl-intensive-cancel]", function (event, button) { cancel(button); });
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(bind);
    } else {
        document.addEventListener("DOMContentLoaded", bind);
    }
})(window, document);
