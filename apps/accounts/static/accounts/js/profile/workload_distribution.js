/*
 * «Yük bölgüsü» bölməsinin idarəçisi (AJAX-safe).
 *
 * Dinamik dəyərlərin hamısı DOM-dan gəlir: endpoint URL-ləri `[data-wl-root]`
 * data-atributlarından, kataloqlar (fəaliyyət/fəsil/forma/səviyyə/səbəb)
 * `#wl-catalog` JSON blokundan (xarici JS Django template engine-dən keçmir —
 * bax CLAUDE.md).
 *
 * Naxış: `EMSDelegate.on` (document-ə bir dəfə delegated listener → AJAX swap-dan
 * sonra gələn düymələr də işləyir) + `EMSReady` (bölmə hər açılanda data yüklə).
 * Yazma əməlləri `EMSCore.fetchJSON` ilə (CSRF avtomatik).
 */
(function (window, document) {
    "use strict";

    var STATE = { catalog: null, rows: [], task: null, readiness: null, teachers: [] };

    function root() {
        return document.querySelector("[data-wl-root]");
    }

    function panel() {
        return document.querySelector('[data-profile-section-panel="workload-distribution"]');
    }

    /** HTML-ə yazılan hər istifadəçi mətni bundan keçir (ad/soyad XSS qapısı). */
    function esc(value) {
        var node = document.createElement("span");
        node.textContent = value == null ? "" : String(value);
        return node.innerHTML;
    }

    function q(selector) {
        var host = panel();
        return host ? host.querySelector(selector) : null;
    }

    function catalog() {
        if (STATE.catalog) return STATE.catalog;
        var node = q("#wl-catalog");
        if (!node) return {};
        try {
            STATE.catalog = JSON.parse(node.textContent || "{}");
        } catch (err) {
            STATE.catalog = {};
        }
        return STATE.catalog;
    }

    function activityLabels() {
        var map = {};
        (catalog().activities || []).forEach(function (item) {
            map[item.key] = item.label;
        });
        return map;
    }

    function filters() {
        return {
            chair: (q("[data-wl-chair]") || {}).value || "",
            year: (q("[data-wl-year]") || {}).value || "",
            season: (q("[data-wl-season]") || {}).value || "",
            q: (q("[data-wl-search]") || {}).value || "",
        };
    }

    function setBusy(busy) {
        var skeleton = q("[data-wl-skeleton]");
        if (skeleton) skeleton.hidden = !busy;
        var rowsHost = q("[data-wl-rows]");
        if (rowsHost) rowsHost.setAttribute("aria-busy", busy ? "true" : "false");
    }

    function showError(node, message) {
        if (!node) return;
        node.textContent = message || "";
        node.hidden = !message;
    }

    function messageFor(payload) {
        if (!payload) return "Əməliyyat alınmadı.";
        return payload.message || payload.error || "Əməliyyat alınmadı.";
    }

    function renderStatus() {
        var chip = q("[data-wl-status-chip]");
        if (!chip) return;
        if (!STATE.task) {
            chip.hidden = true;
            return;
        }
        chip.hidden = false;
        chip.textContent = STATE.task.status_label || STATE.task.status;
        chip.setAttribute("data-state", STATE.task.status);
    }

    /** Sətirləri (və panelləri) serverdən yenidən yüklə. */
    function loadRows() {
        var host = root();
        if (!host) return;
        var params = filters();
        if (!params.chair || !params.year) {
            STATE.rows = [];
            STATE.task = null;
            renderStatus();
            var empty0 = q("[data-wl-empty]");
            if (empty0) empty0.hidden = false;
            var rowsHost0 = q("[data-wl-rows]");
            if (rowsHost0) rowsHost0.innerHTML = "";
            return;
        }
        var url =
            host.dataset.rowsUrl +
            "?chair=" +
            encodeURIComponent(params.chair) +
            "&year=" +
            encodeURIComponent(params.year) +
            "&season=" +
            encodeURIComponent(params.season) +
            "&q=" +
            encodeURIComponent(params.q);
        setBusy(true);
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                STATE.rows = payload.rows || [];
                STATE.task = payload.task || null;
                STATE.readiness = payload.readiness || null;
                STATE.teachers = payload.teachers || [];
                var Render = window.EMSWorkloadRender;
                if (Render) {
                    Render.rows(q("[data-wl-rows]"), STATE.rows, activityLabels());
                    Render.teachers(q("[data-wl-teacher-panel]"), STATE.teachers);
                }
                var empty = q("[data-wl-empty]");
                if (empty) empty.hidden = STATE.rows.length > 0;
                renderStatus();
            })
            .catch(function () {
                var empty = q("[data-wl-empty]");
                if (empty) empty.hidden = false;
            })
            .then(function () {
                setBusy(false);
            });
    }

    /** Sətir modalının açılış siyahılarını (fənn/semestr/ixtisas/qrup) yüklə. */
    function loadOptions() {
        var host = root();
        if (!host) return Promise.resolve();
        var params = filters();
        if (!params.chair) return Promise.resolve();
        return window.EMSCore.fetchJSON(
            host.dataset.optionsUrl + "?chair=" + encodeURIComponent(params.chair)
        )
            .then(function (payload) {
                var Render = window.EMSWorkloadRender;
                if (!Render) return;
                Render.options(q('[data-wl-option="subjects"]'), payload.subjects, {
                    placeholder: "Seçilməyib",
                });
                Render.options(q('[data-wl-option="periods"]'), payload.periods, {
                    placeholder: "Seçilməyib",
                });
                Render.options(q('[data-wl-option="specialties"]'), payload.specialties, {
                    placeholder: "Seçilməyib",
                });
                Render.options(q('[data-wl-option="groups"]'), payload.groups, {});
            })
            .catch(function () {
                /* səssiz — modal boş siyahı ilə açılır */
            });
    }

    /** Kataloq açılışlarını (fəaliyyət, fəsil, forma, səviyyə, səbəb) doldur. */
    function fillCatalogSelects() {
        var Render = window.EMSWorkloadRender;
        if (!Render) return;
        var data = catalog();
        [
            ["seasons", "seasons"],
            ["row_kinds", "row_kinds"],
            ["education_forms", "education_forms"],
            ["degree_levels", "degree_levels"],
            ["amendment_reasons", "amendment_reasons"],
        ].forEach(function (pair) {
            var host = panel();
            if (!host) return;
            host.querySelectorAll('[data-wl-catalog="' + pair[0] + '"]').forEach(function (select) {
                Render.options(select, data[pair[1]], {});
            });
        });
    }

    function rowById(id) {
        for (var i = 0; i < STATE.rows.length; i += 1) {
            if (STATE.rows[i].id === id) return STATE.rows[i];
        }
        return null;
    }

    function modal(selector) {
        var node = q(selector);
        if (!node || !window.bootstrap || !window.bootstrap.Modal) return null;
        return window.bootstrap.Modal.getOrCreateInstance(node);
    }

    function formValues(form) {
        if (!form) return {};
        var data = {};
        Array.prototype.forEach.call(form.elements, function (field) {
            if (!field.name) return;
            if (field.type === "checkbox") {
                data[field.name] = field.checked ? "1" : "";
                return;
            }
            if (field.multiple) {
                data[field.name] = Array.prototype.filter
                    .call(field.options, function (option) {
                        return option.selected;
                    })
                    .map(function (option) {
                        return option.value;
                    });
                return;
            }
            data[field.name] = field.value;
        });
        return data;
    }

    function fillForm(form, row) {
        if (!form) return;
        Array.prototype.forEach.call(form.elements, function (field) {
            if (!field.name) return;
            if (field.type === "checkbox") {
                field.checked = false;
                return;
            }
            if (field.multiple) {
                Array.prototype.forEach.call(field.options, function (option) {
                    option.selected = false;
                });
                return;
            }
            field.value = field.type === "number" ? "0" : "";
        });
        if (!row) return;
        var mapping = {
            row_id: row.id,
            subject_id: row.subject_id,
            subject_text: row.subject,
            period_id: row.period_id,
            season: row.season,
            row_kind: row.row_kind,
            education_form: row.education_form,
            degree_level: row.degree_level,
            student_count: row.student_count,
            union_count: row.union_count,
            subgroup_count: row.subgroup_count,
            credits: row.credits,
        };
        Object.keys(mapping).forEach(function (name) {
            var field = form.elements[name];
            if (field && mapping[name] != null) field.value = mapping[name];
        });
    }

    // ── Delegated listener-lər (bir dəfə qoşulur) ───────────────────────────
    function bind() {
        var EMSDelegate = window.EMSDelegate;
        if (!EMSDelegate) return;

        EMSDelegate.on("change", "[data-wl-chair], [data-wl-season]", function () {
            loadRows();
            loadOptions();
        });
        EMSDelegate.on("change", "[data-wl-year]", loadRows);
        EMSDelegate.on("input", "[data-wl-search]", function () {
            window.clearTimeout(STATE.searchTimer);
            STATE.searchTimer = window.setTimeout(loadRows, 300);
        });

        EMSDelegate.on("click", "[data-wl-create-task]", function () {
            var host = root();
            if (!host) return;
            var params = filters();
            window.EMSCore.fetchJSON(host.dataset.taskUrl, {
                method: "POST",
                data: { chair: params.chair, year: params.year },
            })
                .then(loadRows)
                .catch(function (err) {
                    window.alert(messageFor(err && err.payload));
                });
        });

        EMSDelegate.on("click", "[data-wl-open-row-modal]", function () {
            fillCatalogSelects();
            loadOptions();
            fillForm(q("[data-wl-row-form]"), null);
            showError(q("[data-wl-row-error]"), "");
            var instance = modal("[data-wl-row-modal]");
            if (instance) instance.show();
        });

        EMSDelegate.on("click", "[data-wl-row-edit]", function (event, btn) {
            fillCatalogSelects();
            loadOptions();
            fillForm(q("[data-wl-row-form]"), rowById(btn.dataset.rowId));
            showError(q("[data-wl-row-error]"), "");
            var instance = modal("[data-wl-row-modal]");
            if (instance) instance.show();
        });

        EMSDelegate.on("click", "[data-wl-save-row]", function () {
            var host = root();
            if (!host || !STATE.task) {
                showError(q("[data-wl-row-error]"), "Əvvəlcə tapşırıq yaradılmalıdır.");
                return;
            }
            var payload = formValues(q("[data-wl-row-form]"));
            payload.task_id = STATE.task.id;
            payload.group_ids = payload.group_ids || [];
            window.EMSCore.fetchJSON(host.dataset.saveRowUrl, { method: "POST", data: payload })
                .then(function () {
                    var instance = modal("[data-wl-row-modal]");
                    if (instance) instance.hide();
                    loadRows();
                })
                .catch(function (err) {
                    showError(q("[data-wl-row-error]"), messageFor(err && err.payload));
                });
        });

        EMSDelegate.on("click", "[data-wl-row-remove]", function (event, btn) {
            var host = root();
            if (!host || !STATE.task) return;
            if (!window.confirm("Sətir silinsin?")) return;
            window.EMSCore.fetchJSON(host.dataset.deleteRowUrl, {
                method: "POST",
                data: { task_id: STATE.task.id, row_id: btn.dataset.rowId },
            })
                .then(loadRows)
                .catch(function (err) {
                    window.alert(messageFor(err && err.payload));
                });
        });

        // ── Bölgü modalı ───────────────────────────────────────────────────
        EMSDelegate.on("click", "[data-wl-assign-open]", function (event, btn) {
            var row = rowById(btn.dataset.rowId);
            if (!row) return;
            var Render = window.EMSWorkloadRender;
            var label = q("[data-wl-assign-row-label]");
            if (label) label.textContent = row.subject + " · " + row.season_label;
            var rowIdField = q("[data-wl-assign-row-id]");
            if (rowIdField) rowIdField.value = row.id;
            var idField = q("[data-wl-assign-id]");
            if (idField) idField.value = "";
            var activitySelect = q("[data-wl-assign-activity]");
            if (activitySelect && Render) {
                Render.options(
                    activitySelect,
                    Object.keys(row.activities || {}).map(function (key) {
                        return { key: key, label: activityLabels()[key] || key };
                    }),
                    {}
                );
                if (btn.dataset.activity) activitySelect.value = btn.dataset.activity;
                if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(activitySelect);
            }
            showError(q("[data-wl-assign-error]"), "");
            renderRemaining();
            loadTeacherPicker();
            var instance = modal("[data-wl-assign-modal]");
            if (instance) instance.show();
        });

        EMSDelegate.on("change", "[data-wl-assign-activity]", renderRemaining);

        EMSDelegate.on("click", "[data-wl-save-assign]", function () {
            var host = root();
            if (!host) return;
            var payload = formValues(q("[data-wl-assign-form]"));
            window.EMSCore.fetchJSON(host.dataset.assignUrl, { method: "POST", data: payload })
                .then(function () {
                    var instance = modal("[data-wl-assign-modal]");
                    if (instance) instance.hide();
                    loadRows();
                })
                .catch(function (err) {
                    showError(q("[data-wl-assign-error]"), messageFor(err && err.payload));
                });
        });

        EMSDelegate.on("click", "[data-wl-assign-remove]", function (event, btn) {
            var host = root();
            if (!host) return;
            if (!window.confirm("Bölgü silinsin?")) return;
            window.EMSCore.fetchJSON(host.dataset.unassignUrl, {
                method: "POST",
                data: { assignment_id: btn.dataset.assignmentId },
            })
                .then(loadRows)
                .catch(function (err) {
                    window.alert(messageFor(err && err.payload));
                });
        });

        // ── Təsdiq ─────────────────────────────────────────────────────────
        EMSDelegate.on("click", "[data-wl-open-confirm]", function () {
            var Render = window.EMSWorkloadRender;
            if (Render) Render.readiness(q("[data-wl-confirm-stats]"), STATE.readiness);
            showError(q("[data-wl-confirm-error]"), "");
            var instance = modal("[data-wl-confirm-modal]");
            if (instance) instance.show();
        });

        EMSDelegate.on("click", "[data-wl-do-confirm]", function () {
            var host = root();
            if (!host || !STATE.task) return;
            window.EMSCore.fetchJSON(host.dataset.confirmUrl, {
                method: "POST",
                data: { task_id: STATE.task.id, allow_vacant: "1" },
            })
                .then(function (payload) {
                    var instance = modal("[data-wl-confirm-modal]");
                    if (instance) instance.hide();
                    var sync = payload.sync || {};
                    window.alert(
                        "Bölgü təsdiqləndi. Jurnal açılışı: " +
                            (sync.created || 0) +
                            " yeni, " +
                            (sync.updated || 0) +
                            " yeniləndi. Bildiriş: " +
                            (payload.notified || 0)
                    );
                    loadRows();
                })
                .catch(function (err) {
                    showError(q("[data-wl-confirm-error]"), messageFor(err && err.payload));
                });
        });

        // ── Düzəliş (amendment) ────────────────────────────────────────────
        EMSDelegate.on("click", "[data-wl-do-amend]", function () {
            var host = root();
            if (!host || !STATE.task) return;
            var payload = formValues(q("[data-wl-amend-form]"));
            payload.task_id = STATE.task.id;
            window.EMSCore.fetchJSON(host.dataset.amendUrl, { method: "POST", data: payload })
                .then(function () {
                    var instance = modal("[data-wl-amend-modal]");
                    if (instance) instance.hide();
                    loadRows();
                })
                .catch(function (err) {
                    showError(q("[data-wl-amend-error]"), messageFor(err && err.payload));
                });
        });

        // ── Tədris planından idxal ─────────────────────────────────────────
        EMSDelegate.on("click", "[data-wl-import-curriculum]", function () {
            var host = root();
            if (!host) return;
            var params = filters();
            window.EMSCore.fetchJSON(
                host.dataset.curriculumUrl + "?chair=" + encodeURIComponent(params.chair)
            )
                .then(function (payload) {
                    var form = q("[data-wl-row-form]");
                    var first = (payload.results || [])[0];
                    if (!first || !form) {
                        showError(
                            q("[data-wl-row-error]"),
                            "Bu kafedranın ixtisasları üçün aktiv tədris planı sətri tapılmadı."
                        );
                        return;
                    }
                    ["subject_id", "season", "degree_level", "specialty_id", "credits"].forEach(
                        function (name) {
                            var field = form.elements[name];
                            if (field && first[name] != null) field.value = first[name];
                        }
                    );
                    var creditsValue = form.elements.credits_value;
                    if (creditsValue) creditsValue.value = first.credits_value || 0;
                    showError(
                        q("[data-wl-row-error]"),
                        "Plandan " +
                            payload.count +
                            " təklif tapıldı; birincisi doldurulub. Saatlar tədris planında saxlanmır — əl ilə yazın (təklif: " +
                            (first.suggested_total_hours || 0) +
                            " saat)."
                    );
                })
                .catch(function (err) {
                    showError(q("[data-wl-row-error]"), messageFor(err && err.payload));
                });
        });
    }

    function renderRemaining() {
        var node = q("[data-wl-assign-remaining]");
        if (!node) return;
        var rowId = (q("[data-wl-assign-row-id]") || {}).value;
        var activity = (q("[data-wl-assign-activity]") || {}).value;
        var row = rowById(rowId);
        var info = row && row.activities ? row.activities[activity] : null;
        if (!info) {
            node.textContent = "";
            node.classList.remove("is-empty");
            return;
        }
        node.textContent = "Qalıq: " + info.remaining + " / " + info.total + " saat";
        node.classList.toggle("is-empty", info.remaining <= 0);
    }

    function loadTeacherPicker() {
        var host = root();
        if (!host) return;
        var params = filters();
        window.EMSCore.fetchJSON(
            host.dataset.teachersUrl +
                "?chair=" +
                encodeURIComponent(params.chair) +
                "&year=" +
                encodeURIComponent(params.year)
        )
            .then(function (payload) {
                var select = q("[data-wl-assign-teacher]");
                if (!select) return;
                var html = '<option value="">Vakant (müəllim təyin edilməyib)</option>';
                (payload.results || []).forEach(function (item) {
                    var suffix = item.current_hours != null ? " · " + item.current_hours + "s" : "";
                    var mark = item.is_chair_member ? "" : " (kafedraya bağlanmamış)";
                    html +=
                        '<option value="' +
                        esc(item.id) +
                        '">' +
                        esc(item.full_name) +
                        suffix +
                        mark +
                        "</option>";
                });
                select.innerHTML = html;
                if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(select);
            })
            .catch(function () {
                /* səssiz — Vakant seçimi hər halda qalır */
            });
    }

    if (window.EMSReady) {
        window.EMSReady.once("workload-distribution-bind", bind);
        window.EMSReady(function () {
            if (!root()) return; // bölmə swap olunmayıb — null-safe
            STATE.catalog = null;
            fillCatalogSelects();
            loadRows();
            loadOptions();
        });
    }
})(window, document);
