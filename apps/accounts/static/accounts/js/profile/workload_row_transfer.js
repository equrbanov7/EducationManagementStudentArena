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

    var sourceSequence = 0;
    var sourceOffset = 0;
    var searchTimer;

    api.updateButton = function (find, task) {
        var button = find("[data-wl-open-transfer]");
        if (!button) return;
        var chair = find("[data-wl-chair] option:checked");
        button.hidden = !task || !chair || !chair.hasAttribute("data-wl-transferable") ||
            ["distributed", "amended"].indexOf(task.status) < 0;
    };

    api.setMode = function (transferOnly) {
        var dist = window.EMSWorkloadDist;
        var panel = dist && dist.q("[data-wl-row-modal]");
        if (!panel) return;
        ++sourceSequence;
        clearTimeout(searchTimer);
        panel.querySelector("[data-wl-transfer-picker]").hidden = !transferOnly;
        panel.querySelector("[data-wl-row-fields]").hidden = transferOnly;
        panel.querySelector("[data-wl-import-curriculum]").hidden = transferOnly;
        panel.querySelector("[data-wl-save-row]").hidden = transferOnly;
        panel.querySelector("[data-wl-row-heading]").textContent = transferOnly
            ? gettext("Başqa kafedraya göndər") : gettext("Tapşırıq sətri");
    };

    function sourceRows(append) {
        var dist = window.EMSWorkloadDist;
        var task = dist.state.task;
        var picker = dist.q("[data-wl-transfer-picker]");
        if (!task || !picker || picker.hidden) return;
        var select = picker.querySelector("[data-wl-transfer-source]");
        var more = picker.querySelector("[data-wl-transfer-more]");
        var message = picker.querySelector("[data-wl-source-status]");
        var search = picker.querySelector("[data-wl-transfer-search]").value.trim();
        var mine = ++sourceSequence;
        var params = new URLSearchParams({ task: task.id, q: search, limit: 50, offset: append ? sourceOffset : 0, panel: 0 });
        if (!append) {
            sourceOffset = 0;
            select.replaceChildren(new Option(gettext("Sətir seçin"), ""));
            refresh(select);
            api.fill(dist.q("[data-wl-row-form]"), null);
        }
        more.disabled = true;
        message.textContent = gettext("Sətirlər yüklənir…");
        window.EMSCore.fetchJSON(dist.q("[data-wl-root]").dataset.rowsUrl + "?" + params).then(function (result) {
            if (mine !== sourceSequence || !dist.state.task || dist.state.task.id !== task.id) return;
            (result.rows || []).forEach(function (row) {
                if (row.intensive) return;
                var groups = (row.groups || []).map(function (group) { return group.name; }).join(", ") || row.groups_text;
                var label = [row.subject, groups, row.period_label || row.season_label, row.specialty].filter(Boolean).join(" · ");
                select.add(new Option(label || row.id, row.id));
            });
            refresh(select);
            sourceOffset = result.next_offset;
            more.hidden = !result.has_more;
            more.disabled = false;
            message.textContent = select.options.length > 1 ? "" : gettext("Bu axtarışa uyğun sətir tapılmadı.");
        }).catch(function (err) {
            if (mine !== sourceSequence) return;
            more.hidden = !append;
            more.disabled = false;
            message.textContent = dist.messageFor(err && err.payload);
        });
    }

    function bind() {
        if (!window.EMSDelegate) return;
        window.EMSDelegate.on("click", "[data-wl-open-transfer]", function () {
            var dist = window.EMSWorkloadDist;
            if (!dist || !dist.state.task) return;
            api.setMode(true);
            dist.q("[data-wl-transfer-search]").value = "";
            sourceRows(false);
            var dialog = dist.modal("[data-wl-row-modal]");
            if (dialog) dialog.show();
        });
        window.EMSDelegate.on("input", "[data-wl-transfer-search]", function () {
            var dist = window.EMSWorkloadDist;
            var source = dist.q("[data-wl-transfer-source]");
            source.value = "";
            refresh(source);
            api.fill(dist.q("[data-wl-row-form]"), null);
            clearTimeout(searchTimer);
            ++sourceSequence;
            searchTimer = setTimeout(function () { sourceRows(false); }, 250);
        });
        window.EMSDelegate.on("click", "[data-wl-transfer-more]", function () { sourceRows(true); });
        window.EMSDelegate.on("change", "[data-wl-transfer-source]", function (event, select) {
            var dist = window.EMSWorkloadDist;
            api.fill(dist.q("[data-wl-row-form]"), select.value ? { id: select.value } : null);
        });
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
