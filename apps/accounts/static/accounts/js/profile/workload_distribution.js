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
        return node.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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

    /* 2026-09-13 frontend auditi F7: bu faylın AZ literalları i18n-siz idi —
       EN/RU/TR-də dərs yükü paneli qarışıq dilli görünürdü. `gettext` /
       `interpolate` `JavaScriptCatalog`-dan (`base.html`, `/jsi18n/`) gəlir;
       msgid-lər `djangojs` kataloqundadır (`scripts/i18n_source_scan.py` hərfi
       `gettext(` çağırışlarını sayır — ona görə ad dəyişdirilmir). Kataloq
       yüklənməyibsə lokal fallback msgid-in özünü (AZ) qaytarır. */
    var gettext = window.gettext || function (value) { return value; };

    function fmt(template, params) {
        if (typeof window.interpolate === "function") {
            return window.interpolate(template, params, true);
        }
        return template.replace(/%\((\w+)\)s/g, function (_, key) {
            return params[key] == null ? "" : String(params[key]);
        });
    }

    function messageFor(payload) {
        if (!payload) return gettext("Əməliyyat alınmadı.");
        return payload.message || payload.error || gettext("Əməliyyat alınmadı.");
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
        var mine = (STATE.rowsSeq = (STATE.rowsSeq || 0) + 1); // köhnə cavab atılır
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                if (mine !== STATE.rowsSeq) return;
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
                if (window.EMSWorkloadAmend) window.EMSWorkloadAmend.afterRows();
            })
            .catch(function () {
                var empty = q("[data-wl-empty]");
                if (empty && mine === STATE.rowsSeq) empty.hidden = false;
            })
            .then(function () {
                if (mine === STATE.rowsSeq) setBusy(false);
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
                    placeholder: gettext("Seçilməyib"),
                });
                Render.options(q('[data-wl-option="periods"]'), payload.periods, {
                    placeholder: gettext("Seçilməyib"),
                });
                Render.options(q('[data-wl-option="specialties"]'), payload.specialties, {
                    placeholder: gettext("Seçilməyib"),
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

    /** `workload_distribution_forms.js` — null-safe (fayl sırası pozulsa bölmə sadəcə yazmır). */
    function forms() {
        return window.EMSWorkloadForms || { values: function () { return {}; }, fillRow: function () {} };
    }

    /** Təsdiqlənmiş sənəddə yazı düzəliş dialoqundan keçir (`workload_distribution_amend.js`). */
    function write(opts) {
        if (window.EMSWorkloadAmend) return window.EMSWorkloadAmend.write(opts);
        return window.EMSCore.fetchJSON(opts.url, { method: "POST", data: opts.data })
            .then(opts.done)
            .catch(function (err) {
                showError(q(opts.error), messageFor(err && err.payload));
            });
    }

    function hideModal(selector) {
        var instance = modal(selector);
        if (instance) instance.hide();
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
        window.EMSSearchInput.delegate("[data-wl-search]", { onSearch: loadRows }); // 2026-10-14: 1500 ms, ≥2, Enter, IME

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

        // 2026-10-15: açılışlar YÜKLƏNƏNDƏN sonra doldurulur — əvvəl gec gələn siyahı fənn/semestri silirdi.
        function openRowModal(row) {
            fillCatalogSelects();
            showError(q("[data-wl-row-error]"), "");
            loadOptions().then(function () {
                forms().fillRow(q("[data-wl-row-form]"), row);
            });
            var instance = modal("[data-wl-row-modal]");
            if (instance) instance.show();
        }

        EMSDelegate.on("click", "[data-wl-open-row-modal]", function () {
            openRowModal(null);
        });

        EMSDelegate.on("click", "[data-wl-row-edit]", function (event, btn) {
            openRowModal(rowById(btn.dataset.rowId));
        });

        EMSDelegate.on("click", "[data-wl-save-row]", function () {
            var host = root();
            if (!host || !STATE.task) {
                showError(q("[data-wl-row-error]"), gettext("Əvvəlcə tapşırıq yaradılmalıdır."));
                return;
            }
            var payload = forms().values(q("[data-wl-row-form]"));
            payload.task_id = STATE.task.id;
            payload.group_ids = payload.group_ids || [];
            write({
                url: host.dataset.saveRowUrl,
                data: payload,
                modal: "[data-wl-row-modal]",
                error: "[data-wl-row-error]",
                done: function () {
                    hideModal("[data-wl-row-modal]");
                    loadRows();
                },
            });
        });

        EMSDelegate.on("click", "[data-wl-row-remove]", function (event, btn) {
            var host = root();
            if (!host || !STATE.task) return;
            // 2026-09-14 (audit FE-F19): native confirm() → EMSConfirm (vahid dialoq); ləğv = sorğu yoxdur.
            window.EMSConfirm.open({ body: gettext("Sətir silinsin?"), danger: true }).then(function (ok) {
                if (!ok) return;
                write({
                    url: host.dataset.deleteRowUrl,
                    data: { task_id: STATE.task.id, row_id: btn.dataset.rowId },
                    done: loadRows,
                });
            });
        });

        // ── Bölgü modalı ───────────────────────────────────────────────────
        EMSDelegate.on("click", "[data-wl-assign-open]", function (event, btn) {
            openAssignModal(rowById(btn.dataset.rowId), btn.dataset.activity, null);
        });

        EMSDelegate.on("change", "[data-wl-assign-activity]", renderRemaining);

        EMSDelegate.on("click", "[data-wl-save-assign]", function () {
            var host = root();
            if (!host) return;
            write({
                url: host.dataset.assignUrl,
                data: forms().values(q("[data-wl-assign-form]")),
                modal: "[data-wl-assign-modal]",
                error: "[data-wl-assign-error]",
                done: function (result) {
                    hideModal("[data-wl-assign-modal]");
                    // Audit 2026-09-28 W4: müəllim dəyişikliyi cədvəldə toqquşma yaradıbsa xəbərdarlıq.
                    if (result && result.warning && window.EMSToast) {
                        window.EMSToast.show(result.warning, "warning");
                    }
                    loadRows();
                },
            });
        });

        EMSDelegate.on("click", "[data-wl-assign-remove]", function (event, btn) {
            var host = root();
            if (!host) return;
            window.EMSConfirm.open({ body: gettext("Bölgü silinsin?"), danger: true }).then(function (ok) {
                if (!ok) return;
                write({
                    url: host.dataset.unassignUrl,
                    data: { assignment_id: btn.dataset.assignmentId },
                    done: loadRows,
                });
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
                        fmt(
                            gettext(
                                "Bölgü təsdiqləndi. Jurnal açılışı: %(created)s yeni, %(updated)s yeniləndi. Bildiriş: %(notified)s"
                            ),
                            {
                                created: sync.created || 0,
                                updated: sync.updated || 0,
                                notified: payload.notified || 0,
                            }
                        )
                    );
                    loadRows();
                })
                .catch(function (err) {
                    showError(q("[data-wl-confirm-error]"), messageFor(err && err.payload));
                });
        });

        // ── Düzəliş (amendment): dialoq və təkrar sorğu `workload_distribution_amend.js`-dədir ──

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
                            gettext("Bu kafedranın ixtisasları üçün aktiv tədris planı sətri tapılmadı.")
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
                        fmt(
                            gettext(
                                "Plandan %(count)s təklif tapıldı; birincisi doldurulub. Saatlar tədris planında saxlanmır — əl ilə yazın (təklif: %(hours)s saat)."
                            ),
                            { count: payload.count, hours: first.suggested_total_hours || 0 }
                        )
                    );
                })
                .catch(function (err) {
                    showError(q("[data-wl-row-error]"), messageFor(err && err.payload));
                });
        });
    }

    function assignmentById(row, id) {
        if (!row || !id) return null;
        return (row.assignments || []).filter(function (item) {
            return item.id === id;
        })[0] || null;
    }

    /** Bölgü modalı: yeni təyinat (`assignment=null`) və ya mövcudun redaktəsi (2026-10-15). */
    function openAssignModal(row, activity, assignment) {
        if (!row) return;
        var Render = window.EMSWorkloadRender;
        var form = q("[data-wl-assign-form]");
        var label = q("[data-wl-assign-row-label]");
        if (label) label.textContent = row.subject + " · " + row.season_label;
        if (form) {
            form.elements.row_id.value = row.id;
            form.elements.assignment_id.value = assignment ? assignment.id : "";
            form.elements.hours.value = assignment ? assignment.hours : 1;
            form.elements.groups_note.value = assignment ? assignment.groups_note || "" : "";
            form.elements.is_hourly_paid.checked = !!(assignment && assignment.is_hourly_paid);
        }
        var activitySelect = q("[data-wl-assign-activity]");
        if (activitySelect && Render) {
            Render.options(
                activitySelect,
                Object.keys(row.activities || {}).map(function (key) {
                    return { key: key, label: activityLabels()[key] || key };
                }),
                {}
            );
            if (activity) activitySelect.value = activity;
            if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(activitySelect);
        }
        var save = q("[data-wl-save-assign]");
        if (save) save.textContent = assignment ? gettext("Yadda saxla") : gettext("Əlavə et");
        showError(q("[data-wl-assign-error]"), "");
        renderRemaining();
        loadTeacherPicker().then(function () {
            var select = q("[data-wl-assign-teacher]");
            if (!select || !assignment || !assignment.teacher_id) return;
            if (forms().ensureOption) forms().ensureOption(select, assignment.teacher_id, assignment.teacher_name);
            select.value = assignment.teacher_id;
            if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(select);
        });
        var instance = modal("[data-wl-assign-modal]");
        if (instance) instance.show();
    }

    // Kiçik körpü: düzəliş / fəaliyyət / fokus əlavələri (`workload_distribution_amend.js`) əsas
    // vəziyyəti buradan oxuyur — ikinci fetch/STATE yoxdur.
    window.EMSWorkloadDist = {
        state: STATE,
        q: q,
        root: root,
        modal: modal,
        rowById: rowById,
        loadRows: loadRows,
        showError: showError,
        messageFor: messageFor,
        openAssign: function (rowId, assignmentId) {
            var row = rowById(rowId);
            var assignment = assignmentById(row, assignmentId);
            if (assignment) openAssignModal(row, assignment.activity, assignment);
        },
    };

    function renderRemaining() {
        var node = q("[data-wl-assign-remaining]");
        if (!node) return;
        var rowId = (q("[data-wl-assign-row-id]") || {}).value;
        var activity = (q("[data-wl-assign-activity]") || {}).value;
        var row = rowById(rowId);
        var info = row && row.activities ? row.activities[activity] : null;
        var editing = assignmentById(row, (q("[data-wl-assign-id]") || {}).value);
        if (info && editing && editing.activity === activity) {
            info = { remaining: info.remaining + editing.hours, total: info.total };
        }
        if (!info) {
            node.textContent = "";
            node.classList.remove("is-empty");
            return;
        }
        node.textContent = fmt(gettext("Qalıq: %(remaining)s / %(total)s saat"), {
            remaining: info.remaining,
            total: info.total,
        });
        node.classList.toggle("is-empty", info.remaining <= 0);
    }

    function loadTeacherPicker() {
        var host = root();
        if (!host) return Promise.resolve();
        var params = filters();
        return window.EMSCore.fetchJSON(
            host.dataset.teachersUrl +
                "?chair=" +
                encodeURIComponent(params.chair) +
                "&year=" +
                encodeURIComponent(params.year)
        )
            .then(function (payload) {
                var select = q("[data-wl-assign-teacher]");
                if (!select) return;
                var html = '<option value="">' + esc(gettext("Vakant (müəllim təyin edilməyib)")) + "</option>";
                (payload.results || []).forEach(function (item) {
                    var suffix = item.current_hours != null ? " · " + item.current_hours + "s" : "";
                    var mark = item.is_chair_member ? "" : " " + gettext("(kafedraya bağlanmamış)");
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
