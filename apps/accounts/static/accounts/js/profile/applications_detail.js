/* «Müraciətlərim» — DETAL paneli (dizayn §4.7).
 *
 * Başlıq + SLA zolağı + mətn + sənədlər + zaman xətti + cavab qutusu.
 * Düymələr YALNIZ server-in `allowed_actions` siyahısından doğulur — UI-da
 * rol/status məntiqi yoxdur (backend müqaviləsi §8.2). Mətn tələb edən üç
 * düymə (həll / məlumat istə / rədd) cavab mətni normadan qısa olduqda
 * deaktivdir (dizayn §4.7); qalanları öz dialoqunu açır.
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    //: Hadisə növü → (nişan, palitra sinfi). Dizayn §3.4-ün altı nişanı +
    //: backend-in əlavə hadisələri (təyinat, qaytarma, təkrar göndəriş, …).
    var MARKS = {
        submitted: ["↑", "primary"],
        seen: ["👁", "neutral"],
        comment: ["💬", "neutral"],
        assigned: ["⚑", "primary"],
        info_requested: ["?", "warning"],
        info_provided: ["!", "warning"],
        forwarded: ["→", "neutral"],
        returned: ["↩", "warning"],
        resubmitted: ["⟳", "primary"],
        resolved: ["✓", "success"],
        rejected: ["✕", "danger"],
        closed: ["✓", "neutral"],
        cancelled: ["✕", "neutral"],
    };

    //: Cavab qutusunun mətnini İSTİFADƏ EDƏN əməllər (dizayn §4.7) — qalanları
    //: dialoq açır. Dəyər: minimum simvol (server `rules`-u ilə üst-üstə düşür).
    var INLINE_ACTIONS = { resolve: "note", request_info: "note", reject: "note", add_comment: "one" };

    //: Əməl → (etiket açarı, düymə sinfi). Sıra dizayn §4.7-dəki sıradır.
    var BUTTONS = [
        ["resolve", "actResolve", "apx-btn apx-btn--primary"],
        ["request_info", "actRequestInfo", "apx-btn"],
        ["forward", "actForward", "apx-btn apx-btn--outline"],
        ["return_for_correction", "actReturn", "apx-btn"],
        ["reject", "actReject", "apx-btn apx-btn--danger"],
        ["assign", "actAssign", "apx-btn"],
        ["add_comment", "actComment", "apx-btn"],
        ["provide_info", "actProvideInfo", "apx-btn apx-btn--primary"],
        ["resubmit", "actResubmit", "apx-btn apx-btn--primary"],
        ["close", "actClose", "apx-btn apx-btn--primary"],
        ["cancel", "actCancel", "apx-btn apx-btn--danger"],
    ];

    function slaText(sla) {
        if (!sla) {
            return "";
        }
        if (sla.tone === "closed") {
            return NS.t("slaClosed", { status: String(sla.status_label || "").toLocaleLowerCase("az") });
        }
        if (sla.tone === "overdue") {
            return NS.t("slaOverdue", { n: sla.days, m: sla.sla_days });
        }
        return NS.t("slaOntime", { n: sla.days, m: sla.sla_days });
    }

    function filesHtml(app) {
        if (!app.attachments || !app.attachments.length) {
            return "";
        }
        var rows = app.attachments
            .map(function (file) {
                return (
                    '<a class="apx-file" href="' +
                    NS.esc(file.download_url) +
                    '" rel="nofollow">' +
                    '<i class="fas fa-file-lines" aria-hidden="true"></i>' +
                    '<span class="apx-file__name">' + NS.esc(file.name) + "</span>" +
                    '<span class="apx-file__size">' + NS.esc(NS.size(file.size)) + "</span></a>"
                );
            })
            .join("");
        return (
            '<div><div class="apx-label">' + NS.esc(NS.t("secFiles")) + "</div>" +
            '<div class="apx-files">' + rows + "</div></div>"
        );
    }

    function timelineHtml(app) {
        var items = (app.events || [])
            .map(function (event) {
                var mark = MARKS[event.kind] || MARKS.comment;
                var who = event.actor || "";
                if (event.kind === "forwarded" && event.to_unit) {
                    who = who + " → " + event.to_unit;
                }
                var what = event.text || event.kind_label || "";
                return (
                    '<div class="apx-tl__item"><div class="apx-tl__gutter">' +
                    '<span class="apx-mark apx-mark--' + mark[1] + '" aria-hidden="true">' + mark[0] + "</span>" +
                    '<span class="apx-tl__line"></span></div>' +
                    '<div class="apx-tl__main"><div class="apx-tl__head">' +
                    '<span class="apx-tl__who">' + NS.esc(who) + "</span>" +
                    '<span class="apx-tl__when">' + NS.esc(NS.dateTime(event.created_at)) + "</span>" +
                    (event.is_internal
                        ? '<span class="apx-tl__internal">' + NS.esc(NS.t("internal")) + "</span>"
                        : "") +
                    "</div>" +
                    '<div class="apx-tl__what">' + NS.esc(event.kind_label) +
                    (what && what !== event.kind_label ? " — " + NS.esc(what) : "") +
                    "</div></div></div>"
                );
            })
            .join("");
        return (
            '<div><div class="apx-label">' + NS.esc(NS.t("secTimeline")) + "</div>" +
            '<div class="apx-tl">' + items + "</div></div>"
        );
    }

    function actionsHtml(app) {
        var allowed = app.allowed_actions || [];
        var buttons = BUTTONS.filter(function (entry) {
            return allowed.indexOf(entry[0]) !== -1;
        });
        if (!buttons.length) {
            return noteHtml(app);
        }
        var needsText = buttons.some(function (entry) {
            return INLINE_ACTIONS[entry[0]] === "note";
        });
        // Cavab qutusu YALNIZ mətn tələb edən əməl varsa göstərilir. Sahibin
        // «ləğv et» / «bağla» kimi əməlləri öz dialoqunu açır — onlara boş
        // textarea vermək dizaynın «yalnız-oxu qeyd» qaydasını pozardı (§4.7).
        var inline = buttons.some(function (entry) {
            return !!INLINE_ACTIONS[entry[0]];
        });
        var html =
            '<div class="apx-act">' +
            (inline
                ? '<label class="apx-act__label" for="apx-reply">' + NS.esc(NS.t("replyLabel")) + "</label>" +
                  '<textarea id="apx-reply" rows="3" class="apx-act__input" data-apx-reply placeholder="' +
                  NS.esc(NS.t("replyPlaceholder")) + '"></textarea>'
                : noteHtml(app)) +
            '<div class="apx-act__buttons">' +
            buttons
                .map(function (entry) {
                    var gated = !!INLINE_ACTIONS[entry[0]];
                    return (
                        '<button type="button" class="' + entry[2] + '" data-apx-action="' + entry[0] + '"' +
                        (gated ? " disabled" : "") + ">" + NS.esc(NS.t(entry[1])) + "</button>"
                    );
                })
                .join("") +
            "</div>";
        if (needsText) {
            html += '<div class="apx-act__hint" data-apx-reply-hint>' + NS.esc(NS.t("replyHint")) + "</div>";
        }
        return html + "</div>";
    }

    function noteHtml(app) {
        var viewer = app.viewer || {};
        var unit = (app.current_unit && app.current_unit.name) || "";
        var text;
        if (viewer.is_sender) {
            text = app.is_open ? NS.t("noteSenderOpen", { unit: unit }) : NS.t("noteSenderClosed");
        } else if (!app.is_open) {
            text = NS.t("noteHandlerClosed");
        } else {
            text = NS.t("noteHandlerWatching", { unit: unit });
        }
        return (
            '<div class="apx-note"><i class="fas fa-eye" aria-hidden="true"></i>' +
            '<span class="apx-note__text">' + NS.esc(text) + "</span></div>"
        );
    }

    function render(app) {
        var host = NS.root && NS.root.querySelector("[data-apx-detail]");
        if (!host) {
            return;
        }
        NS.current = app;
        var sla = app.sla || {};
        var tone = sla.tone === "overdue" ? "apx-sla--overdue" : sla.tone === "closed" ? "apx-sla--closed" : "";
        var fromLine = NS.esc(app.requester.name) + (app.requester_scope ? " · " + NS.esc(app.requester_scope) : "");
        host.innerHTML =
            '<div class="apx-detail__head"><div class="apx-detail__top">' +
            '<span class="apx-no">' + NS.esc(app.number) + "</span>" +
            '<span class="apx-badge" data-bg="' + NS.esc(app.kind.bg) + '" data-fg="' + NS.esc(app.kind.fg) + '">' +
            NS.esc(app.kind.label) + "</span>" +
            '<span class="apx-pill" data-bg="' + NS.esc(app.status.bg) + '" data-fg="' + NS.esc(app.status.fg) + '">' +
            NS.esc(app.status.label) + "</span>" +
            '<button type="button" class="apx-detail__close" data-apx-detail-close>' +
            '<i class="fas fa-xmark" aria-hidden="true"></i>' + NS.esc(NS.t("closeDetail")) + "</button>" +
            "</div>" +
            '<h2 class="apx-detail__title">' + NS.esc(app.subject) + "</h2>" +
            '<div class="apx-detail__from"><span>' + fromLine + "</span>" +
            '<span class="apx-ctx__dot" aria-hidden="true">·</span>' +
            "<span>" + NS.esc(NS.dateTime(app.submitted_at)) + "</span></div>" +
            '<div class="apx-sla ' + tone + '"><i class="fas fa-clock" aria-hidden="true"></i>' +
            '<span class="apx-sla__text">' + NS.esc(slaText(sla)) + "</span></div></div>" +
            '<div class="apx-detail__body">' +
            '<div><div class="apx-label">' + NS.esc(NS.t("secBody")) + "</div>" +
            '<p class="apx-text">' + NS.esc(app.body) + "</p></div>" +
            filesHtml(app) +
            timelineHtml(app) +
            actionsHtml(app) +
            "</div>";
        host.hidden = false;
        NS.paintSwatches(host);
    }

    function clear() {
        var host = NS.root && NS.root.querySelector("[data-apx-detail]");
        if (!host) {
            return;
        }
        NS.current = null;
        host.innerHTML = "";
        host.hidden = true;
    }

    NS.detail = { render: render, clear: clear, MARKS: MARKS, INLINE_ACTIONS: INLINE_ACTIONS };

    /* ── Delegasiya (bir dəfə) ──────────────────────────────────────────── */
    function start() {
        if (NS.__detailWired) {
            return;
        }
        NS.__detailWired = true;

        window.EMSDelegate.on("input", "[data-apx-reply]", function (event, node) {
            var length = node.value.trim().length;
            var box = node.closest(".apx-act");
            if (!box) {
                return;
            }
            box.querySelectorAll("[data-apx-action]").forEach(function (button) {
                var need = INLINE_ACTIONS[button.getAttribute("data-apx-action")];
                if (!need) {
                    return;
                }
                button.disabled = need === "one" ? length < 1 : length < NS.rules.note;
            });
        });

        window.EMSDelegate.on("click", "[data-apx-detail-close]", function () {
            clear();
            NS.state.selectedId = "";
            NS.renderList();
        });

        window.EMSDelegate.on("click", "[data-apx-action]", function (event, node) {
            var action = node.getAttribute("data-apx-action");
            var app = NS.current;
            if (!app) {
                return;
            }
            if (INLINE_ACTIONS[action]) {
                var field = NS.root.querySelector("[data-apx-reply]");
                var text = field ? field.value.trim() : "";
                NS.submitAction(app.id, action, { text: text }).catch(function (error) {
                    NS.toast(NS.errorList(error)[0], "error");
                });
                return;
            }
            NS.dialogs.openForAction(action, app);
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

    /* Əməli göndərir və cavabdakı DETAL payload-unu yerində tətbiq edir. */
    NS.submitAction = function (id, action, fields, files) {
        var form = new FormData();
        form.append("action", action);
        Object.keys(fields || {}).forEach(function (key) {
            form.append(key, fields[key]);
        });
        (files || []).forEach(function (file) {
            form.append("files", file);
        });
        return NS.api.action(id, form).then(function (payload) {
            var app = payload.application;
            NS.applyDetail(app);
            NS.toast(NS.t("toastDone", { no: app.number, status: app.status.label }));
            return app;
        });
    };
})();
