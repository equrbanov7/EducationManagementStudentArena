/* Kafedralararası yük köçürməsi. Saat/sətir redaktəsi ayrıca Save yolunda qalır. */
(function (window) {
    "use strict";
    var api = (window.EMSWorkloadTransfer = {});
    var gettext = window.gettext || function (value) { return value; };
    var sequence = 0;

    function refresh(select) {
        if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(select);
    }

    api.payload = function (rowId, taskId, chairId, note) {
        return { row_id: rowId, task_id: taskId, destination_chair_id: chairId,
            amend_reason: "correction", amend_note: String(note || "").trim() };
    };

    api.fill = function (form, row) {
        var box = form && form.querySelector("[data-wl-transfer]");
        var dist = window.EMSWorkloadDist;
        if (!box || !dist) return;
        var select = box.querySelector("[data-wl-transfer-chair]");
        var button = box.querySelector("[data-wl-transfer-submit]");
        var status = box.querySelector("[data-wl-transfer-status]");
        var note = box.querySelector("[data-wl-transfer-note]");
        var mine = ++sequence;
        box.hidden = !row || !dist.state.task;
        button.disabled = true;
        note.value = "";
        status.textContent = "";
        select.replaceChildren(new Option(gettext("Kafedra seçin"), ""));
        refresh(select);
        if (box.hidden) return;
        box.dataset.rowId = row.id;
        box.dataset.taskId = dist.state.task.id;
        var params = new URLSearchParams({ row_id: row.id, task_id: dist.state.task.id });
        status.textContent = gettext("Kafedralar yüklənir…");
        window.EMSCore.fetchJSON(box.dataset.optionsUrl + "?" + params.toString()).then(function (result) {
            if (mine !== sequence) return;
            (result.results || []).forEach(function (chair) {
                select.appendChild(new Option(chair.name, chair.id));
            });
            button.disabled = !result.results || !result.results.length;
            status.textContent = button.disabled
                ? gettext("Səlahiyyətiniz daxilində uyğun təsdiqlənmiş kafedra tapşırığı yoxdur.") : "";
            refresh(select);
        }).catch(function (err) {
            if (mine === sequence) status.textContent = dist.messageFor(err && err.payload);
        });
    };

    function bind() {
        if (!window.EMSDelegate) return;
        window.EMSDelegate.on("click", "[data-wl-transfer-submit]", function (event, button) {
            var box = button.closest("[data-wl-transfer]");
            if (!box || button.disabled) return;
            var status = box.querySelector("[data-wl-transfer-status]");
            var payload = api.payload(box.dataset.rowId, box.dataset.taskId,
                box.querySelector("[data-wl-transfer-chair]").value,
                box.querySelector("[data-wl-transfer-note]").value);
            if (!payload.destination_chair_id || !payload.amend_note) {
                status.textContent = gettext("Hədəf kafedranı və köçürmə səbəbini yazın.");
                return;
            }
            button.disabled = true;
            status.textContent = gettext("Köçürülür…");
            window.EMSCore.fetchJSON(box.dataset.url, { method: "POST", data: payload }).then(function (result) {
                status.textContent = gettext("Yük sətri köçürüldü.");
                window.location.assign(result.edit_url);
            }).catch(function (err) {
                button.disabled = false;
                status.textContent = window.EMSWorkloadDist.messageFor(err && err.payload);
            });
        });
    }
    if (window.EMSReady) window.EMSReady.once("workload-row-transfer", bind);
})(window);
