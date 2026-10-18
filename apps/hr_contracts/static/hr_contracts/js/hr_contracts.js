/* «Əmək müqavilələri» (HR, `hr-contracts`) və «Müqavilələrim» (işçi, `my-contracts`) — sahib 2026-10-19.
 * Şablonlar: hr_contracts/cabinet/*.html. AJAX-safe: dinləyicilər `EMSDelegate` ilə BİR dəfə (təkrar qeyd
 * dinləyici yığmır); yazılar `EMSCore.fetchJSON` (FormData → CSRF başlığı avtomatik), uğurdan sonra bölmə
 * yerində yenilənir. Dialoqları `ems_ui/overlay.js` açır (`data-ems-overlay-open`); bu fayl formanı doldurur.
 * Dinamik dəyərlər (URL-lər, mətnlər, müqavilə JSON-u) DOM-un data-atributlarından oxunur — inline JS yoxdur.
 */
(function (window, document) {
    "use strict";

    if (window.EMSHrContracts) {
        return;
    }
    window.EMSHrContracts = true;

    var picker = null;

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function rootOf(node) {
        return node && node.closest ? node.closest("[data-hrc-root]") : null;
    }

    function reload(root) {
        var section = root ? root.getAttribute("data-hrc-section") : "";
        var here = window.location.pathname + window.location.search;
        var panel = root ? root.closest("[data-profile-section-panel]") : null;
        var url = here.indexOf("section=" + section) !== -1 ? here : panel && panel.getAttribute("data-source-url");
        if (window.EMSProfileLoadSection && section && url) {
            window.EMSProfileLoadSection(section, url);
        } else {
            window.location.reload();
        }
    }

    function showError(form, message) {
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        } else if (message) {
            toast(message, "error");
        }
    }

    function setText(scope, key, value) {
        scope.querySelectorAll('[data-hrc-text="' + key + '"]').forEach(function (node) {
            node.textContent = value || "";
        });
    }

    function field(form, name) {
        return form.querySelector('[data-hrc-field="' + name + '"]');
    }

    function setField(form, name, value) {
        var node = field(form, name);
        if (!node) {
            return;
        }
        node.value = value === null || value === undefined ? "" : String(value);
        if (node.tagName === "SELECT" && window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(node);
        }
    }

    function parsePayload(trigger) {
        try {
            return JSON.parse(trigger.getAttribute("data-hrc-contract") || "{}");
        } catch (error) {
            return {};
        }
    }

    /* ── Növ → bitmə tarixi (müddətsizdə yoxdur, müddətlidə məcburidir) ──── */
    function syncType(form) {
        var type = field(form, "contract_type");
        var end = field(form, "end_date");
        if (!type || !end) {
            return;
        }
        var indefinite = type.value === "indefinite";
        end.disabled = indefinite;
        if (indefinite) {
            end.value = "";
        }
        end.required = type.value === "fixed_term";
        var star = form.querySelector("[data-hrc-end-required]");
        if (star) {
            star.hidden = type.value !== "fixed_term";
        }
        var hint = form.querySelector("[data-hrc-end-hint]");
        if (hint) {
            hint.hidden = !indefinite;
        }
    }

    function ensurePicker(form) {
        var holder = form.querySelector(".js-hrc-employee");
        if (!holder || !window.EMSSearchableSelect) {
            return null;
        }
        if (holder._emsSearchable) {
            picker = holder._emsSearchable;
            return picker;
        }
        picker = window.EMSSearchableSelect.create(holder, {
            url: holder.getAttribute("data-staff-url"),
            multi: false,
            skeleton: true,
        });
        picker.on("change", function () {
            setField(form, "employee", picker.value());
        });
        return picker;
    }

    function shiftDate(iso, days) {
        if (!iso) {
            return "";
        }
        var date = new Date(iso + "T00:00:00");
        if (isNaN(date.getTime())) {
            return "";
        }
        date.setDate(date.getDate() + days);
        var month = String(date.getMonth() + 1).padStart(2, "0");
        var day = String(date.getDate()).padStart(2, "0");
        return date.getFullYear() + "-" + month + "-" + day;
    }

    function spanDays(start, end) {
        var a = new Date(start + "T00:00:00");
        var b = new Date(end + "T00:00:00");
        return isNaN(a.getTime()) || isNaN(b.getTime()) ? 0 : Math.round((b - a) / 86400000);
    }

    function openContract(trigger, mode) {
        var dialog = document.getElementById("hrcContractDialog");
        var form = dialog ? dialog.querySelector("form") : null;
        if (!form) {
            return;
        }
        form.reset();
        showError(form, "");
        var data = mode === "create" ? {} : parsePayload(trigger);
        var titles = form.querySelector(".hrc-dialog__titles");
        var title = dialog.querySelector(".ems-dialog__title");
        if (title && titles) {
            title.textContent = titles.getAttribute("data-title-" + mode) || title.textContent;
        }
        ["id", "renew_of", "employee", "number", "position", "unit", "start_date", "end_date", "probation_end",
            "weekly_hours", "staff_rate", "notes"].forEach(function (name) {
            setField(form, name, "");
        });
        setField(form, "contract_type", data.contract_type || "fixed_term");
        setField(form, "status", "active");
        var pick = ensurePicker(form);
        if (pick) {
            pick.reset();
        }
        var fixed = form.querySelector("[data-hrc-employee-fixed]");
        var chooser = form.querySelector("[data-hrc-employee-picker]");
        var renewNote = form.querySelector("[data-hrc-renew-note]");
        var statusField = form.querySelector("[data-hrc-status-field]");
        var currentFile = form.querySelector("[data-hrc-file-current]");
        if (fixed) { fixed.hidden = mode === "create"; }
        if (chooser) { chooser.hidden = mode !== "create"; }
        if (renewNote) { renewNote.hidden = mode !== "renew"; }
        if (statusField) { statusField.hidden = mode === "edit" && data.status !== "draft"; }
        if (currentFile) { currentFile.hidden = !(mode === "edit" && data.file_name); }
        setText(form, "employee_name", data.employee_name);
        setText(form, "file_name", data.file_name);
        if (mode !== "create") {
            setField(form, "employee", data.employee);
            ["position", "unit", "weekly_hours", "staff_rate"].forEach(function (name) {
                setField(form, name, data[name]);
            });
        }
        if (mode === "edit") {
            ["id", "number", "start_date", "end_date", "probation_end", "notes"].forEach(function (name) {
                setField(form, name, data[name]);
            });
            setField(form, "status", data.status === "draft" ? "draft" : "active");
        }
        if (mode === "renew") {
            setField(form, "renew_of", data.id);
            var start = data.end_date ? shiftDate(data.end_date, 1) : "";
            setField(form, "start_date", start);
            if (data.end_date && data.start_date && data.contract_type !== "indefinite") {
                setField(form, "end_date", shiftDate(start, spanDays(data.start_date, data.end_date)));
            }
        }
        syncType(form);
    }

    window.EMSDelegate.on("click", "[data-hrc-create]", function (event, trigger) {
        openContract(trigger, "create");
    });
    window.EMSDelegate.on("click", "[data-hrc-edit]", function (event, trigger) {
        openContract(trigger, "edit");
    });
    window.EMSDelegate.on("click", "[data-hrc-renew]", function (event, trigger) {
        openContract(trigger, "renew");
    });
    window.EMSDelegate.on("change", "[data-hrc-type]", function (event, select) {
        if (select.form) {
            syncType(select.form);
        }
    });

    /* ── «Göndərildi» / xitam: URL və «kim» mətni düymədən ─────────────── */
    window.EMSDelegate.on("click", "[data-hrc-open]", function (event, trigger) {
        var dialog = document.getElementById(trigger.getAttribute("data-ems-overlay-open"));
        var form = dialog ? dialog.querySelector("form") : null;
        if (!form) {
            return;
        }
        var date = form.querySelector('input[name="terminated_at"]');
        var today = date ? date.defaultValue : "";
        form.reset();
        if (date) {
            date.value = today;
        }
        showError(form, "");
        form.setAttribute("action", trigger.getAttribute("data-hrc-url") || "");
        setText(dialog, "who", trigger.getAttribute("data-hrc-who"));
        if (window.EMSOverlay && typeof window.EMSOverlay.syncReason === "function") {
            window.EMSOverlay.syncReason(form);
        }
    });

    /* ── Tarixçə ─────────────────────────────────────────────────────────── */
    window.EMSDelegate.on("click", "[data-hrc-history]", function (event, trigger) {
        var body = document.querySelector("#hrcHistoryDialog [data-hrc-history-body]");
        if (!body) {
            return;
        }
        body.textContent = body.getAttribute("data-loading") || "";
        window.EMSCore.fetchJSON(trigger.getAttribute("data-hrc-history"))
            .then(function (payload) {
                body.innerHTML = (payload && payload.html) || "";
            })
            .catch(function (error) {
                var payload = error && error.payload;
                body.textContent = (payload && payload.message) || "";
            });
    });

    /* ── Bütün POST formaları (panelin içində) ──────────────────────────── */
    window.EMSDelegate.on("submit", "[data-hrc-root] form[method='post']", function (event, form) {
        var root = rootOf(form);
        if (!root) {
            return;
        }
        event.preventDefault();
        var url = form.getAttribute("action");
        if (!url) {
            return;
        }
        var employee = field(form, "employee");
        var chooser = form.querySelector("[data-hrc-employee-picker]");
        if (employee && chooser && !chooser.hidden && !employee.value) {
            var titles = form.querySelector(".hrc-dialog__titles");
            showError(form, titles ? titles.getAttribute("data-employee-required") : "");
            return;
        }
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        showError(form, "");
        window.EMSCore.fetchJSON(url, { method: "POST", body: new FormData(form) })
            .then(function (payload) {
                toast(payload && payload.message, "success");
                var overlay = form.closest(".ems-overlay");
                if (overlay && window.EMSOverlay) {
                    window.EMSOverlay.close(overlay);
                }
                reload(root);
            })
            .catch(function (error) {
                var payload = error && error.payload;
                var structured = payload && typeof payload === "object";
                showError(form, (structured && payload.message) || root.getAttribute("data-hrc-error-generic") || "");
            })
            .finally(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });
})(window, document);
