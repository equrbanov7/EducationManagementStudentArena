/* «Alt qrup tələbələri» — «+ Alt qrupa tələbə əlavə et» modalı (sahib 2026-11-05).
 * Şablon: sections/subgroup_students/_add_fields.html (+ ems_ui/_form_dialog.html).
 *
 * YENİ YAZI YOLU YOXDUR: jurnal seçiləndən sonra jurnal modalının RƏSMİ endpoint-ləri işlənir —
 * qrup / tələbə axtarışı (`registrar:journal_guest_group_search` / `journal_guest_student_search`) və əlavə
 * (`registrar:journal_guest_add`: kredit həddi + jurnal tutumu + siyahı qapısı + audit). URL şablonları formanın
 * data-atributlarındadır (jurnal id-si yerində sıfır UUID).
 *
 * AJAX-safe: seçicilər hər panel swap-ından sonra EMSReady ilə (idempotent) qurulur, göndəriş isə sənəd
 * səviyyəsində BİR DƏFƏ EMSDelegate ilə tutulur. Uğurdan sonra bölmə yerində yenilənir (cədvəl + statistika).
 */
(function (window, document) {
    "use strict";

    var STATE = "__sstAdd";
    var SECTION = "subgroup-students";

    function attr(form, name) {
        return form.getAttribute(name) || "";
    }

    function forOffering(template, form, offeringId) {
        return template.split(attr(form, "data-zero-id")).join(offeringId);
    }

    function setStep(form, step, enabled) {
        var box = form.querySelector('[data-sst-step="' + step + '"]');
        if (!box) {
            return;
        }
        box.classList.toggle("is-disabled", !enabled);
        var input = box.querySelector("input");
        if (input) {
            input.disabled = !enabled;
        }
    }

    function showError(form, message) {
        var box = form.querySelector("[data-ems-form-error]");
        if (!box) {
            return;
        }
        box.textContent = message || "";
        box.hidden = !message;
    }

    function init(form) {
        if (form[STATE] || !window.EMSSearchableSelect) {
            return;
        }
        var create = window.EMSSearchableSelect.create;
        var groupOpts = {
            url: forOffering(attr(form, "data-group-url"), form, attr(form, "data-zero-id")),
            placeholder: attr(form, "data-ph-group-idle"),
            emptyText: attr(form, "data-empty-group"),
            skeleton: true,
        };
        var studentOpts = {
            url: forOffering(attr(form, "data-student-url"), form, attr(form, "data-zero-id")),
            placeholder: attr(form, "data-ph-student-idle"),
            emptyText: attr(form, "data-empty-student"),
            skeleton: true,
            dependParam: "group",
        };
        var state = { offering: "" };
        var journal = create(form.querySelector(".js-sst-journal"), {
            url: attr(form, "data-journals-url"),
            emptyText: attr(form, "data-empty-journal"),
            skeleton: true,
        });
        var group = create(form.querySelector(".js-sst-group"), groupOpts);
        studentOpts.getDependValue = function () {
            return group ? group.value() : "";
        };
        var student = create(form.querySelector(".js-sst-student"), studentOpts);
        if (!journal || !group || !student) {
            return;
        }
        form[STATE] = { journal: journal, group: group, student: student, state: state };
        setStep(form, "group", false);
        setStep(form, "student", false);

        journal.on("change", function () {
            state.offering = journal.value() || "";
            groupOpts.url = forOffering(attr(form, "data-group-url"), form, state.offering || attr(form, "data-zero-id"));
            studentOpts.url = forOffering(attr(form, "data-student-url"), form, state.offering || attr(form, "data-zero-id"));
            group.reset();
            student.reset();
            group.setPlaceholder(attr(form, state.offering ? "data-ph-group" : "data-ph-group-idle"));
            student.setPlaceholder(attr(form, "data-ph-student-idle"));
            setStep(form, "group", !!state.offering);
            setStep(form, "student", false);
            showError(form, "");
        });
        group.on("change", function () {
            student.reset();
            var ready = !!group.value();
            student.setPlaceholder(attr(form, ready ? "data-ph-student" : "data-ph-student-idle"));
            setStep(form, "student", ready);
            showError(form, "");
        });
    }

    function validate(form, parts) {
        if (!parts.offering) {
            return attr(form, "data-msg-journal");
        }
        if (!parts.group || !parts.student) {
            return attr(form, "data-msg-student");
        }
        var reason = form.querySelector("[name=reason]");
        if (!reason || !reason.value.trim()) {
            return attr(form, "data-msg-reason");
        }
        var file = form.querySelector("[name=document]");
        var hasFile = !!(file && file.files && file.files.length);
        if (!hasFile && attr(form, "data-document-optional") !== "1") {
            return attr(form, "data-msg-document");
        }
        return "";
    }

    function errorMessage(form, err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object") {
            return payload.message || payload.error || attr(form, "data-msg-generic");
        }
        return attr(form, "data-msg-generic");
    }

    function reloadSection() {
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection(SECTION, window.location.href);
        } else {
            window.location.reload();
        }
    }

    function submit(event, form) {
        event.preventDefault();
        var entry = form[STATE];
        if (!entry || form.getAttribute("data-busy") === "1") {
            return;
        }
        var parts = {
            offering: entry.state.offering,
            group: entry.group.value() || "",
            student: entry.student.value() || "",
        };
        var problem = validate(form, parts);
        if (problem) {
            showError(form, problem);
            return;
        }
        showError(form, "");
        var body = new window.FormData();
        body.append("group", parts.group);
        body.append("student", parts.student);
        body.append("reason", form.querySelector("[name=reason]").value.trim());
        if (form.querySelector("[data-sst-release]").checked) {
            body.append("release_source", "1");
        }
        var file = form.querySelector("[name=document]");
        if (file && file.files && file.files.length) {
            body.append("document", file.files[0]);
        }
        var button = form.querySelector("[type=submit]");
        form.setAttribute("data-busy", "1");
        if (button) {
            button.disabled = true;
        }
        window.EMSCore.fetchJSON(forOffering(attr(form, "data-add-url"), form, parts.offering), {
            method: "POST",
            body: body,
        })
            .then(function (payload) {
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(form);
                }
                if (window.EMSToast && typeof window.EMSToast.show === "function") {
                    window.EMSToast.show((payload && payload.message) || attr(form, "data-msg-done"), "success");
                }
                reloadSection();
            })
            .catch(function (err) {
                showError(form, errorMessage(form, err));
            })
            .then(function () {
                form.removeAttribute("data-busy");
                if (button) {
                    button.disabled = false;
                }
            });
    }

    window.EMSReady(function () {
        var form = document.querySelector("[data-sst-add-form]");
        if (form) {
            init(form);
        }
    });

    if (!window.__sstAddBound && window.EMSDelegate) {
        window.__sstAddBound = true;
        window.EMSDelegate.on("submit", "[data-sst-add-form]", submit);
    }
})(window, document);
