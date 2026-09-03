/* «Müraciətlərim» — DİALOQLAR (dizayn §4.8/§4.9 + əməl dialoqları).
 *
 * Beş dialoq bir naxışla işləyir: `[data-apx-dialog="<ad>"]` gizli qalır, açılanda
 * panel fokuslanır, Esc və overlay bağlayır (a11y §7). Fayl seçimləri dialoqun
 * öz `__files` massivində saxlanılır — DOM-dan asılı deyil.
 *
 * Yoxlama qaydaları (5 / 20 / 10) SERVER-dən gələn `rules` obyektindəndir —
 * burada sabit yazılmır (backend müqaviləsi §8.3).
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    var MAX_FILES = 5;
    var MAX_MB = 10;
    var EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".docx"];

    //: Əməl → reason dialoqunun başlıq/etiket açarları + fayl qəbulu.
    var REASON = {
        return_for_correction: ["dlgReturnTitle", "dlgReturnLabel", false, "note"],
        cancel: ["dlgCancelTitle", "dlgCancelLabel", false, "free"],
        provide_info: ["dlgProvideTitle", "dlgProvideLabel", true, "note"],
    };

    function dialog(name) {
        return NS.root && NS.root.querySelector('[data-apx-dialog="' + name + '"]');
    }

    function showErrors(box, messages) {
        var list = box.querySelector("[data-apx-errors]");
        if (!list) {
            return;
        }
        if (!messages || !messages.length) {
            list.hidden = true;
            list.innerHTML = "";
            return;
        }
        list.innerHTML = messages
            .map(function (message) {
                return "<li>" + NS.esc(message) + "</li>";
            })
            .join("");
        list.hidden = false;
    }

    function open(name) {
        var box = dialog(name);
        if (!box) {
            return null;
        }
        box.hidden = false;
        showErrors(box, []);
        var panel = box.querySelector(".apx-dlg__panel");
        if (panel) {
            try {
                panel.focus();
            } catch (error) {
                /* fokus alınmasa da dialoq işləyir */
            }
        }
        return box;
    }

    function close(name) {
        var box = dialog(name);
        if (box) {
            box.hidden = true;
            box.__files = [];
        }
    }

    /* Esc: ən üstdəki açıq dialoqu bağlayır; heç nə açıq deyilsə false. */
    function closeTop() {
        var boxes = NS.root ? NS.root.querySelectorAll("[data-apx-dialog]") : [];
        var found = false;
        boxes.forEach(function (box) {
            if (!box.hidden) {
                box.hidden = true;
                found = true;
            }
        });
        return found;
    }

    /* ── Fayl seçimi ────────────────────────────────────────────────────── */
    function renderPicked(box) {
        var host = box.querySelector("[data-apx-picked]");
        if (!host) {
            return;
        }
        var files = box.__files || [];
        host.innerHTML = files
            .map(function (file, index) {
                return (
                    '<div class="apx-picked__item"><i class="fas fa-file-lines" aria-hidden="true"></i>' +
                    '<span class="apx-picked__name">' + NS.esc(file.name) + "</span>" +
                    '<span class="apx-picked__size">' + NS.esc(NS.size(file.size)) + "</span>" +
                    '<button type="button" class="apx-picked__drop" data-apx-drop-file="' + index +
                    '" aria-label="' + NS.esc(NS.t("closeDetail")) + '">' +
                    '<i class="fas fa-xmark" aria-hidden="true"></i></button></div>'
                );
            })
            .join("");
    }

    function addFiles(box, fileList) {
        box.__files = box.__files || [];
        var errors = [];
        Array.prototype.forEach.call(fileList, function (file) {
            var lower = file.name.toLowerCase();
            var okExt = EXTENSIONS.some(function (extension) {
                return lower.slice(-extension.length) === extension;
            });
            if (!okExt) {
                errors.push(NS.t("fileBadType", { name: file.name }));
                return;
            }
            if (file.size > MAX_MB * 1024 * 1024) {
                errors.push(NS.t("fileTooBig", { name: file.name }));
                return;
            }
            if (box.__files.length >= MAX_FILES) {
                errors.push(NS.t("tooManyFiles"));
                return;
            }
            box.__files.push(file);
        });
        showErrors(box, errors);
        renderPicked(box);
    }

    /* ── §4.8 «Yeni müraciət» (eyni dialoq «yenidən göndər» rejimində) ──── */
    function counter(box) {
        var field = box.querySelector("[data-apx-body]");
        var node = box.querySelector("[data-apx-counter]");
        if (!field || !node) {
            return;
        }
        var length = field.value.trim().length;
        var min = box.__mode === "reason" ? NS.rules.note : NS.rules.body;
        var short = length < min;
        node.textContent = short ? NS.t("counterShort", { min: min, n: length }) : NS.t("counterOk", { n: length });
        node.classList.toggle("is-short", short);
    }

    function renderKindChoices(box) {
        var host = box.querySelector("[data-apx-kind-list]");
        if (!host) {
            return;
        }
        var kinds = (NS.catalog && NS.catalog.kinds) || [];
        host.innerHTML = kinds
            .map(function (kind) {
                return (
                    '<button type="button" class="apx-option" role="option" data-apx-pick-kind="' +
                    NS.esc(kind.code) + '" aria-selected="' + (box.__kind === kind.code ? "true" : "false") + '">' +
                    '<span class="apx-option__dot" data-bg="' + NS.esc(kind.fg) + '" data-fg="' +
                    NS.esc(kind.fg) + '"></span>' +
                    '<span class="apx-option__main"><span class="apx-option__label">' + NS.esc(kind.label) +
                    '</span><span class="apx-option__note">' + NS.esc(kind.note) + "</span></span>" +
                    '<span class="apx-option__days">' + NS.esc(NS.t("days", { n: kind.sla_days })) + "</span></button>"
                );
            })
            .join("");
        NS.paintSwatches(host);
        var hint = box.querySelector("[data-apx-route-text]");
        if (hint) {
            var chosen = kinds.filter(function (kind) {
                return kind.code === box.__kind;
            })[0];
            hint.textContent = chosen ? chosen.routing_hint : NS.t("routeEmpty");
        }
    }

    function openCreate(mode, app, presetKind) {
        var box = open("create");
        if (!box) {
            return;
        }
        box.__files = [];
        box.__mode = mode || "create";
        box.__kind = app && app.kind ? app.kind.code : (presetKind || "");
        box.__app = app || null;
        box.querySelector("[data-apx-subject]").value = app ? app.subject : "";
        box.querySelector("[data-apx-body]").value = app ? app.body : "";
        box.querySelector("[data-apx-kind-list]").parentNode.hidden = box.__mode === "resubmit";
        box.querySelector("[data-apx-route]").hidden = box.__mode === "resubmit";
        renderKindChoices(box);
        renderPicked(box);
        counter(box);
    }

    function sendCreate() {
        var box = dialog("create");
        if (!box) {
            return;
        }
        var subject = box.querySelector("[data-apx-subject]");
        var body = box.querySelector("[data-apx-body]");
        var badSubject = subject.value.trim().length < NS.rules.subject;
        var badBody = body.value.trim().length < NS.rules.body;
        subject.classList.toggle("is-invalid", badSubject);
        body.classList.toggle("is-invalid", badBody);
        if (badSubject || badBody || (box.__mode !== "resubmit" && !box.__kind)) {
            counter(box);
            return;
        }
        if (box.__mode === "resubmit") {
            NS.submitAction(box.__app.id, "resubmit", {
                subject: subject.value.trim(),
                body: body.value.trim(),
            }, box.__files)
                .then(function () {
                    close("create");
                })
                .catch(function (error) {
                    showErrors(box, NS.errorList(error));
                });
            return;
        }
        var form = new FormData();
        form.append("kind", box.__kind);
        form.append("subject", subject.value.trim());
        form.append("body", body.value.trim());
        (box.__files || []).forEach(function (file) {
            form.append("files", file);
        });
        NS.api
            .create(form)
            .then(function (payload) {
                close("create");
                NS.state.tab = "mine";
                NS.state.stat = "open";
                NS.state.page = 1;
                NS.renderTabs();
                NS.loadList().then(function () {
                    NS.openApplication(payload.application.id);
                });
                NS.refreshCounts();
                NS.toast(NS.t("toastCreated", { unit: payload.application.current_unit.name }));
            })
            .catch(function (error) {
                showErrors(box, NS.errorList(error));
            });
    }

    /* ── §4.9 «Müraciəti yönləndir» ─────────────────────────────────────── */
    function openForward(app) {
        var box = open("forward");
        if (!box) {
            return;
        }
        box.__unit = "";
        box.__app = app;
        box.querySelector("[data-apx-forward-sub]").textContent = app.number + " · " + app.subject;
        box.querySelector("[data-apx-note]").value = "";
        box.querySelector("[data-apx-keep]").checked = true;
        // Cari şöbə siyahıdan ÇIXARILIR — server eyni şöbəni `unit.same` ilə rədd edir.
        var units = ((NS.catalog && NS.catalog.units) || []).filter(function (unit) {
            return unit.code !== app.current_unit.code;
        });
        box.querySelector("[data-apx-unit-list]").innerHTML = units
            .map(function (unit) {
                return (
                    '<button type="button" class="apx-option" role="option" data-apx-pick-unit="' +
                    NS.esc(unit.code) + '" aria-selected="false">' +
                    '<span class="apx-option__main"><span class="apx-option__label">' + NS.esc(unit.name) +
                    '</span><span class="apx-option__note">' + NS.esc(unit.note) + "</span></span></button>"
                );
            })
            .join("");
    }

    function sendForward() {
        var box = dialog("forward");
        var note = box.querySelector("[data-apx-note]").value.trim();
        if (!box.__unit || note.length < NS.rules.note) {
            showErrors(box, [NS.t("counterShort", { min: NS.rules.note, n: note.length })]);
            return;
        }
        var keep = box.querySelector("[data-apx-keep]").checked;
        NS.submitAction(box.__app.id, "forward", {
            target_unit: box.__unit,
            text: note,
            keep_watching: keep ? "true" : "false",
        })
            .then(function (app) {
                close("forward");
                var unit = app.current_unit.name;
                NS.toast(
                    keep
                        ? NS.t("toastForwarded", { no: app.number, unit: unit })
                        : NS.t("toastForwardedOnly", { no: app.number, unit: unit })
                );
            })
            .catch(function (error) {
                showErrors(box, NS.errorList(error));
            });
    }

    /* ── Səbəb dialoqu (qaytar / ləğv et / məlumat göndər) ──────────────── */
    function openReason(action, app) {
        var config = REASON[action];
        var box = open("reason");
        if (!box || !config) {
            return;
        }
        box.__files = [];
        box.__action = action;
        box.__app = app;
        box.__mode = "reason";
        box.querySelector("[data-apx-reason-title]").textContent = NS.t(config[0]);
        box.querySelector("[data-apx-reason-sub]").textContent = app.number + " · " + app.subject;
        box.querySelector("[data-apx-reason-label]").textContent = NS.t(config[1]);
        box.querySelector("[data-apx-reason-send]").textContent = NS.t("dlgSend");
        box.querySelector("[data-apx-reason-files]").hidden = !config[2];
        box.querySelector("[data-apx-note]").value = "";
        box.querySelector("[data-apx-counter]").textContent = "";
        renderPicked(box);
    }

    function sendReason() {
        var box = dialog("reason");
        var config = REASON[box.__action] || [];
        var text = box.querySelector("[data-apx-note]").value.trim();
        if (config[3] === "note" && text.length < NS.rules.note) {
            showErrors(box, [NS.t("counterShort", { min: NS.rules.note, n: text.length })]);
            return;
        }
        NS.submitAction(box.__app.id, box.__action, { text: text }, box.__files)
            .then(function () {
                close("reason");
            })
            .catch(function (error) {
                showErrors(box, NS.errorList(error));
            });
    }

    /* ── «Təyin et» ─────────────────────────────────────────────────────── */
    function openAssign(app) {
        var box = open("assign");
        if (!box) {
            return;
        }
        box.__app = app;
        box.querySelector("[data-apx-assign-sub]").textContent = app.number + " · " + app.subject;
        box.querySelector("[data-apx-note]").value = "";
        var select = box.querySelector("[data-apx-assignee]");
        select.innerHTML = "";
        window.EMSCore.fetchJSON(NS.urls.assignees + "?application=" + encodeURIComponent(app.id))
            .then(function (payload) {
                var people = payload.results || [];
                if (!people.length) {
                    showErrors(box, [NS.t("noAssignee")]);
                    return;
                }
                select.innerHTML = people
                    .map(function (person) {
                        return '<option value="' + NS.esc(person.id) + '">' + NS.esc(person.name) + "</option>";
                    })
                    .join("");
            })
            .catch(function () {
                showErrors(box, [NS.t("noAssignee")]);
            });
    }

    function sendAssign() {
        var box = dialog("assign");
        var select = box.querySelector("[data-apx-assignee]");
        if (!select.value) {
            showErrors(box, [NS.t("noAssignee")]);
            return;
        }
        NS.submitAction(box.__app.id, "assign", {
            assignee: select.value,
            text: box.querySelector("[data-apx-note]").value.trim(),
        })
            .then(function () {
                close("assign");
            })
            .catch(function (error) {
                showErrors(box, NS.errorList(error));
            });
    }

    /* ── Yekun əməllər üçün təsdiq ──────────────────────────────────────── */
    function confirm(title, text, onYes) {
        var box = open("confirm");
        if (!box) {
            return;
        }
        box.querySelector("[data-apx-confirm-title]").textContent = title;
        box.querySelector("[data-apx-confirm-text]").textContent = text;
        box.__yes = onYes;
    }

    function openForAction(action, app) {
        if (action === "forward") {
            openForward(app);
        } else if (action === "assign") {
            openAssign(app);
        } else if (action === "resubmit") {
            openCreate("resubmit", app);
        } else if (action === "close") {
            confirm(NS.t("confirmCloseTitle"), NS.t("confirmCloseText"), function () {
                NS.submitAction(app.id, "close", { text: "" }).then(function () {
                    close("confirm");
                });
            });
        } else if (REASON[action]) {
            openReason(action, app);
        }
    }

    NS.dialogs = {
        open: open,
        close: close,
        closeTop: closeTop,
        openCreate: openCreate,
        openForward: openForward,
        openReason: openReason,
        openAssign: openAssign,
        confirm: confirm,
        openForAction: openForAction,
    };

    /* ── Delegasiya (bir dəfə) ──────────────────────────────────────────── */
    function start() {
        if (NS.__dialogsWired) {
            return;
        }
        NS.__dialogsWired = true;

        window.EMSDelegate.on("click", "[data-apx-open-create]", function () {
            openCreate("create", null);
        });
        window.EMSDelegate.on("click", "[data-apx-dialog-close]", function (event, node) {
            node.closest("[data-apx-dialog]").hidden = true;
        });
        window.EMSDelegate.on("click", "[data-apx-dialog]", function (event, node) {
            // Yalnız overlay-in ÖZÜNƏ klik bağlayır (panelin içi qabarcıqlanmır).
            if (event.target === node) {
                node.hidden = true;
            }
        });
        window.EMSDelegate.on("click", "[data-apx-pick-kind]", function (event, node) {
            var box = node.closest("[data-apx-dialog]");
            box.__kind = node.getAttribute("data-apx-pick-kind");
            renderKindChoices(box);
        });
        window.EMSDelegate.on("click", "[data-apx-pick-unit]", function (event, node) {
            var box = node.closest("[data-apx-dialog]");
            box.__unit = node.getAttribute("data-apx-pick-unit");
            box.querySelectorAll("[data-apx-pick-unit]").forEach(function (option) {
                option.setAttribute("aria-selected", option === node ? "true" : "false");
            });
        });
        window.EMSDelegate.on("input", "[data-apx-body]", function (event, node) {
            counter(node.closest("[data-apx-dialog]"));
        });
        window.EMSDelegate.on("input", "[data-apx-note]", function (event, node) {
            var box = node.closest("[data-apx-dialog]");
            if (box && box.getAttribute("data-apx-dialog") === "reason") {
                var length = node.value.trim().length;
                var short = length < NS.rules.note;
                var target = box.querySelector("[data-apx-counter]");
                target.textContent = short
                    ? NS.t("counterShort", { min: NS.rules.note, n: length })
                    : NS.t("counterOk", { n: length });
                target.classList.toggle("is-short", short);
            }
        });
        window.EMSDelegate.on("click", "[data-apx-pick-files]", function (event, node) {
            var input = node.closest("[data-apx-dialog]").querySelector("[data-apx-files]");
            if (input) {
                input.click();
            }
        });
        window.EMSDelegate.on("change", "[data-apx-files]", function (event, node) {
            addFiles(node.closest("[data-apx-dialog]"), node.files);
            node.value = "";
        });
        window.EMSDelegate.on("click", "[data-apx-drop-file]", function (event, node) {
            var box = node.closest("[data-apx-dialog]");
            box.__files.splice(Number(node.getAttribute("data-apx-drop-file")), 1);
            renderPicked(box);
        });
        window.EMSDelegate.on("click", "[data-apx-create-send]", sendCreate);
        window.EMSDelegate.on("click", "[data-apx-forward-send]", sendForward);
        window.EMSDelegate.on("click", "[data-apx-reason-send]", sendReason);
        window.EMSDelegate.on("click", "[data-apx-assign-send]", sendAssign);
        window.EMSDelegate.on("click", "[data-apx-confirm-yes]", function (event, node) {
            var box = node.closest("[data-apx-dialog]");
            if (typeof box.__yes === "function") {
                box.__yes();
            }
        });
    }

    /* Panel script-ləri `<body>` içindədir və `ems_ajax_init.js`-dən ƏVVƏL
     * parse oluna bilər (AJAX swap-da isə dinamik script sırası zəmanətli
     * deyil), ona görə qeydiyyat primitivlər hazır olana qədər gözləyir.
     * `defer` ilk yüklənmədə bunu onsuz da tez edir — bu, ikinci qapıdır. */
    (function ready(attempt) {
        if (window.EMSDelegate && window.EMSReady && NS.api) {
            start();
            return;
        }
        if (attempt > 200) {
            return;
        }
        window.setTimeout(function () {
            ready(attempt + 1);
        }, 25);
    })(0);
})();
