/* «Müəllimlər» / «Tələbələr» kataloqu — 2/3: şəxs kartı + əməllər
 * (dialoq + ardıcıl POST). people_directory.js-dən SONRA, people_directory_setup.js-dən
 * ƏVVƏL yüklənir; köməkçiləri `window.EMSPeopleDirectory`-dən alır və oraya
 * `openDetail` / `runAction` qeyd edir. Bölgü: 2026-09-21 (modul ölçü büdcəsi).
 */
(function () {
    "use strict";

    var P = (window.EMSPeopleDirectory = window.EMSPeopleDirectory || {});
    var el = P.el;
    var toast = P.toast;
    var fmt = P.fmt;
    var messageOf = P.messageOf;

    /* ---- şəxs kartı --------------------------------------------------------- */

    function openDetail(ctx, userId, reloadList) {
        if (window.EMSPeopleDetail && typeof window.EMSPeopleDetail.open === "function") {
            window.EMSPeopleDetail.open(ctx.root, ctx.urls, userId, {
                runAction: function (action, id, onDone) {
                    runAction(ctx, action, [id], function () {
                        ctx.root.dispatchEvent(new CustomEvent("people:refresh"));
                        onDone();
                    });
                },
            });
            return;
        }
        reloadList();
    }

    /* ---- əməllər (dialoq + ardıcıl POST) ------------------------------------ */

    function dialogOf(ctx, kind) {
        return ctx.root.querySelector('[data-people-dialog="' + kind + '"]');
    }

    function renderTargets(dialog, ctx, ids) {
        var box = dialog.querySelector("[data-people-dialog-targets]");
        if (!box) {
            return;
        }
        box.textContent = "";
        var list = el("ul", "people-dialog__list");
        ids.slice(0, 8).forEach(function (id) {
            var person = ctx.state.rows[String(id)] || {};
            var item = el("li", "people-dialog__item");
            item.appendChild(el("span", "people-dialog__avatar", person.initials || "?"));
            var name = el("span", "people-dialog__name", [person.full_name, person.patronymic].filter(Boolean).join(" ") || person.username || id);
            item.appendChild(name);
            var meta = person.kind === "student" ? person.group_name || ctx.t("noGroup") : person.kafedra_name || person.unit_name || "";
            if (meta) {
                item.appendChild(el("span", "people-dialog__meta", meta));
            }
            list.appendChild(item);
        });
        if (ids.length > 8) {
            list.appendChild(el("li", "people-dialog__item people-dialog__item--more", "+" + (ids.length - 8)));
        }
        box.appendChild(list);
    }

    function showDialogError(dialog, message) {
        var box = dialog.querySelector("[data-people-dialog-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    function openOverlay(dialog) {
        if (window.EMSOverlay && typeof window.EMSOverlay.open === "function") {
            window.EMSOverlay.open(dialog);
        } else {
            dialog.hidden = false;
        }
    }

    function closeOverlay(dialog) {
        if (window.EMSOverlay && typeof window.EMSOverlay.close === "function") {
            window.EMSOverlay.close(dialog);
        } else {
            dialog.hidden = true;
        }
    }

    /** Hədəfləri ARDICIL göndərir; nəticə toast ilə, ilk xəta dialoqda qalır. */
    function runSequential(ctx, dialog, ids, buildPayload, onDone) {
        var submit = dialog.querySelector("[data-people-dialog-submit]");
        if (submit) {
            submit.disabled = true;
        }
        var ok = 0;
        var firstError = "";
        var chain = Promise.resolve();
        ids.forEach(function (id) {
            chain = chain.then(function () {
                var payload = buildPayload(id);
                if (!payload) {
                    return null;
                }
                return window.EMSCore.fetchJSON(ctx.urls.action, { method: "POST", data: payload })
                    .then(function () {
                        ok += 1;
                    })
                    .catch(function (error) {
                        if (!firstError) {
                            firstError = messageOf(error, ctx.t("failed"));
                        }
                    });
            });
        });
        chain.then(function () {
            if (submit) {
                submit.disabled = false;
            }
            if (ok > 0) {
                toast(fmt(ctx.t("done"), { a: ok, b: ids.length }), firstError ? "warning" : "success");
            }
            if (firstError && ok === 0) {
                showDialogError(dialog, firstError);
                return;
            }
            if (firstError) {
                toast(firstError, "error");
            }
            closeOverlay(dialog);
            onDone();
        });
    }

    function bindDialogSubmit(dialog, handler) {
        var form = dialog.querySelector("[data-people-dialog-form]");
        if (!form) {
            return;
        }
        form.onsubmit = function (event) {
            event.preventDefault();
            handler(form);
        };
    }

    function reasonFrom(form, ctx, required) {
        var field = form.querySelector('[name="reason"]');
        var reason = field ? String(field.value || "").trim() : "";
        if (required && reason.length < ctx.minReason) {
            return null;
        }
        return reason;
    }

    /* Səbəb / təsdiq dialoqu — block, unblock, revoke_teacher (tək və toplu). */
    function openReasonDialog(ctx, action, ids, onDone) {
        var dialog = dialogOf(ctx, "reason");
        if (!dialog) {
            return;
        }
        var meta = {
            block: { title: ctx.t("block"), sub: ctx.t("confirmBlock"), required: true, tone: "ems-btn--danger" },
            unblock: { title: ctx.t("unblock"), sub: ctx.t("confirmUnblock"), required: false, tone: "ems-btn--primary" },
            revoke_teacher: { title: ctx.t("revokeTeacher"), sub: ctx.t("confirmRevoke"), required: true, tone: "ems-btn--danger" },
        }[action];
        if (!meta) {
            return;
        }
        var title = dialog.querySelector("[data-people-dialog-title]");
        var sub = dialog.querySelector("[data-people-dialog-sub]");
        var submit = dialog.querySelector("[data-people-dialog-submit]");
        var req = dialog.querySelector("[data-people-dialog-req]");
        var hint = dialog.querySelector("[data-people-dialog-hint]");
        var form = dialog.querySelector("[data-people-dialog-form]");
        if (title) {
            title.textContent = meta.title;
        }
        if (sub) {
            sub.textContent = meta.sub;
        }
        if (submit) {
            submit.textContent = meta.title;
            submit.className = "ems-btn " + meta.tone;
        }
        if (req) {
            req.hidden = !meta.required;
        }
        if (hint) {
            hint.textContent = meta.required ? fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason)) : "";
        }
        if (form) {
            form.reset();
        }
        showDialogError(dialog, "");
        renderTargets(dialog, ctx, ids);
        bindDialogSubmit(dialog, function (frm) {
            var reason = reasonFrom(frm, ctx, meta.required);
            if (reason === null) {
                showDialogError(dialog, fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason)));
                return;
            }
            runSequential(ctx, dialog, ids, function (id) {
                return { action: action, user_id: id, reason: reason };
            }, onDone);
        });
        openOverlay(dialog);
    }

    /* Kafedraya təyin et — müəllimlər (tək və toplu). */
    function openUnitDialog(ctx, ids, onDone) {
        var dialog = dialogOf(ctx, "unit");
        if (!dialog) {
            return;
        }
        var form = dialog.querySelector("[data-people-dialog-form]");
        if (form) {
            form.reset();
            var select = form.querySelector('[name="unit_id"]');
            if (select && ids.length === 1) {
                var person = ctx.state.rows[String(ids[0])] || {};
                select.value = person.unit_id || "";
            }
            if (select && window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
        }
        showDialogError(dialog, "");
        renderTargets(dialog, ctx, ids);
        bindDialogSubmit(dialog, function (frm) {
            var unitField = frm.querySelector('[name="unit_id"]');
            var unitId = unitField ? unitField.value : "";
            if (!unitId) {
                showDialogError(dialog, ctx.t("pickUnit"));
                return;
            }
            var reason = reasonFrom(frm, ctx, false) || "";
            runSequential(ctx, dialog, ids, function (id) {
                return { action: "assign_unit", user_id: id, unit_id: unitId, reason: reason };
            }, onDone);
        });
        openOverlay(dialog);
    }

    /* Qrupa köçür — tələbələr (tək və toplu); hədəf QEYD id-si sətirdən gəlir. */
    function openGroupDialog(ctx, ids, onDone) {
        var dialog = dialogOf(ctx, "group");
        if (!dialog) {
            return;
        }
        var recordIds = ids
            .map(function (id) {
                var person = ctx.state.rows[String(id)] || {};
                return person.record_id || "";
            })
            .filter(Boolean);
        if (!recordIds.length) {
            toast(ctx.t("noRecord"), "error");
            return;
        }
        var form = dialog.querySelector("[data-people-dialog-form]");
        var hidden = form ? form.querySelector('[name="group_id"]') : null;
        if (form) {
            form.reset();
        }
        if (hidden) {
            hidden.value = "";
        }
        var hint = dialog.querySelector("[data-people-dialog-hint]");
        if (hint) {
            hint.textContent = fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason));
        }
        var host = dialog.querySelector("[data-people-group-picker]");
        var pickerRoot = host ? host.querySelector(".js-people-group-picker") : null;
        if (pickerRoot && window.EMSSearchableSelect && ctx.urls.groups) {
            var picker = window.EMSSearchableSelect.create(pickerRoot, {
                url: ctx.urls.groups,
                multi: false,
                skeleton: true,
                emptyText: host.getAttribute("data-empty") || "",
                onChange: function () {
                    if (hidden) {
                        hidden.value = picker ? picker.value() : "";
                    }
                },
            });
            if (picker) {
                picker.reset();
            }
        }
        showDialogError(dialog, "");
        renderTargets(dialog, ctx, ids);
        bindDialogSubmit(dialog, function (frm) {
            var groupId = hidden ? hidden.value : "";
            if (!groupId) {
                showDialogError(dialog, ctx.t("pickGroup"));
                return;
            }
            var reason = reasonFrom(frm, ctx, true);
            if (reason === null) {
                showDialogError(dialog, fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason)));
                return;
            }
            runSequential(ctx, dialog, recordIds, function (recordId) {
                return { action: "transfer_group", record_id: recordId, group_id: groupId, reason: reason };
            }, onDone);
        });
        openOverlay(dialog);
        window.setTimeout(function () {
            var input = pickerRoot ? pickerRoot.querySelector("input") : null;
            if (input) {
                input.focus();
            }
        }, 30);
    }

    function runAction(ctx, action, ids, onDone) {
        ids = (ids || []).map(String).filter(Boolean);
        if (!ids.length) {
            return;
        }
        if (action === "assign_unit") {
            openUnitDialog(ctx, ids, onDone);
            return;
        }
        if (action === "transfer_group") {
            openGroupDialog(ctx, ids, onDone);
            return;
        }
        if (action === "grant_teacher") {
            // Sahib (2026-09-07): tələbəyə müəllim statusu verilmir — bu səthdə düymə yoxdur.
            return;
        }
        openReasonDialog(ctx, action, ids, onDone);
    }

    P.openDetail = openDetail;
    P.runAction = runAction;
})();
