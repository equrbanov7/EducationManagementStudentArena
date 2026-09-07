/* «Müraciətlərim» — DETAL MODALININ İÇİ: başlıq, YAZIŞMA və cavab qutusu.
 *
 * Niyə ayrı fayl? `applications_detail.js` modalın QABIĞIDIR (aç/bağla, fokus,
 * kilid, əməl göndərişi); burada isə yalnız MARKUP qurulur. Bölgü ölçü büdcəsinə
 * də xidmət edir (`check_module_size.py`, 600 sətir).
 *
 * Yazışma (thread) köhnə «zaman xətti»ni əvəz edir: mətn kiçik boz sətirdə deyil,
 * oxunaqlı mesaj kartındadır — müraciətin özü birinci mesaj, hər cavab ardınca
 * gəlir, statusa aid mexaniki hadisələr (baxıldı, təyin edildi) isə aralarda
 * NAZİK sətirdir. Modal açılanda son mesaja sürüşür ki, «ən son nə yazılıb, cavab
 * nə gəlib» dərhal görünsün.
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    //: Hadisə növü → (nişan, palitra sinfi) — mexaniki sətirlərin ikonu.
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
        reopened: ["⟲", "warning"],
        rejected: ["✕", "danger"],
        closed: ["✓", "neutral"],
        cancelled: ["✕", "neutral"],
    };

    //: Həmişə NAZİK sətir kimi göstərilən hadisələr — mətn daşısalar da bu bir
    //: prosedur addımıdır, yazışma repliği deyil.
    var STEP_KINDS = { submitted: 1, seen: 1, assigned: 1, closed: 1 };

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
        ["reopen", "actReopen", "apx-btn apx-btn--outline"],
        ["cancel", "actCancel", "apx-btn apx-btn--danger"],
    ];

    /* ── Kiçik köməkçilər ───────────────────────────────────────────────── */
    function initials(name) {
        var words = String(name || "")
            .trim()
            .split(/\s+/)
            .filter(Boolean);
        if (!words.length) {
            return "—";
        }
        var first = words[0].charAt(0);
        var second = words.length > 1 ? words[words.length - 1].charAt(0) : "";
        return (first + second).toLocaleUpperCase("az");
    }

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

    //: Uzantıya görə ikon — ZIP/şəkil/PDF fərqi siyahıda dərhal görünsün.
    function fileIcon(name) {
        var lower = String(name || "").toLowerCase();
        if (/\.(zip)$/.test(lower)) {
            return "fa-file-zipper";
        }
        if (/\.(png|jpe?g|webp)$/.test(lower)) {
            return "fa-file-image";
        }
        if (/\.pdf$/.test(lower)) {
            return "fa-file-pdf";
        }
        return "fa-file-lines";
    }

    function filesHtml(files, modifier) {
        if (!files || !files.length) {
            return "";
        }
        return (
            '<div class="apx-files' + (modifier ? " " + modifier : "") + '">' +
            files
                .map(function (file) {
                    return (
                        '<a class="apx-file" href="' + NS.esc(file.download_url) + '" rel="nofollow">' +
                        '<i class="fas ' + fileIcon(file.name) + '" aria-hidden="true"></i>' +
                        '<span class="apx-file__name">' + NS.esc(file.name) + "</span>" +
                        '<span class="apx-file__size">' + NS.esc(NS.size(file.size)) + "</span></a>"
                    );
                })
                .join("") +
            "</div>"
        );
    }

    function tagHtml(text, tone) {
        return '<span class="apx-tag apx-tag--' + tone + '">' + NS.esc(text) + "</span>";
    }

    /* ── Yazışma ────────────────────────────────────────────────────────── */
    //: Hadisə REPLİKdir, yoxsa prosedur addımı? Mətni olmayan, mexaniki və ya
    //: mətni mövzunun eynisi olan (göndərildi / yenidən göndərildi) → addım.
    function isMessage(event, app) {
        var text = String(event.text || "").trim();
        if (!text || STEP_KINDS[event.kind]) {
            return false;
        }
        return text !== String(app.subject || "").trim();
    }

    function messageHtml(message) {
        var tags = (message.tags || []).join("");
        return (
            '<article class="apx-msg apx-msg--' + message.side + (message.latest ? " is-latest" : "") + '">' +
            '<span class="apx-msg__avatar" aria-hidden="true">' + NS.esc(initials(message.who)) + "</span>" +
            '<div class="apx-msg__main"><div class="apx-msg__head">' +
            '<span class="apx-msg__who">' + NS.esc(message.who) + "</span>" +
            (message.role ? '<span class="apx-msg__role">' + NS.esc(message.role) + "</span>" : "") +
            '<span class="apx-msg__when">' + NS.esc(NS.dateTime(message.when)) + "</span></div>" +
            (tags ? '<div class="apx-msg__tags">' + tags + "</div>" : "") +
            '<div class="apx-msg__text">' + NS.esc(message.text) + "</div>" +
            filesHtml(message.files, "apx-files--msg") +
            "</div></article>"
        );
    }

    function stepHtml(event) {
        var mark = MARKS[event.kind] || MARKS.comment;
        var text = String(event.text || "").trim();
        var line = event.kind_label + (event.actor ? " · " + event.actor : "");
        if (event.kind === "forwarded" && event.to_unit) {
            line += " → " + event.to_unit;
        }
        return (
            '<div class="apx-step">' +
            '<span class="apx-mark apx-mark--' + mark[1] + '" aria-hidden="true">' + mark[0] + "</span>" +
            '<span class="apx-step__text">' + NS.esc(line) +
            (text ? ' <span class="apx-step__note">— ' + NS.esc(text) + "</span>" : "") +
            "</span>" +
            '<span class="apx-step__when">' + NS.esc(NS.dateTime(event.created_at)) + "</span>" +
            filesHtml(event.attachments, "apx-files--step") +
            "</div>"
        );
    }

    //: Hadisənin növ etiketi — mesaj kartının üstündəki rəngli çip.
    function kindTag(event) {
        var mark = MARKS[event.kind] || MARKS.comment;
        return tagHtml(event.kind_label, mark[1]);
    }

    function eventTags(event) {
        var tags = [kindTag(event)];
        if (event.kind === "forwarded" && event.to_unit) {
            tags.push(tagHtml("→ " + event.to_unit, "neutral"));
        }
        if (event.is_internal) {
            tags.push(tagHtml(NS.t("internal"), "warning"));
        }
        return tags;
    }

    function threadHtml(app) {
        var events = app.events || [];
        var opening = events.filter(function (event) {
            return event.kind === "submitted";
        })[0];
        // Birinci mesaj = müraciətin ÖZÜ. Mətni `app.body`-dən gəlir (düzəlişdən
        // sonra yenilənmiş variant), sənədləri isə «göndərildi» hadisəsinə bağlı
        // olanlardır.
        var messages = [
            {
                side: "sender",
                who: app.requester.name,
                role: app.requester_scope,
                when: app.submitted_at,
                text: app.body,
                files: opening ? opening.attachments : [],
                tags: [tagHtml(NS.t("secBody"), "primary")],
            },
        ];
        var rows = [];
        events.forEach(function (event) {
            if (event.kind === "submitted") {
                return;
            }
            if (!isMessage(event, app)) {
                rows.push({ step: event });
                return;
            }
            var message = {
                side: event.actor_is_sender ? "sender" : "staff",
                who: event.actor,
                role: event.actor_role,
                when: event.created_at,
                text: event.text,
                files: event.attachments,
                tags: eventTags(event),
            };
            messages.push(message);
            rows.push({ message: message });
        });
        // «Ən son» nişanı YALNIZ cavab varsa: tək mesaj müraciətin özüdür.
        if (messages.length > 1) {
            var last = messages[messages.length - 1];
            last.latest = true;
            last.tags = (last.tags || []).concat(tagHtml(NS.t("msgLatest"), "primary"));
        }
        var html = messageHtml(messages[0]);
        rows.forEach(function (row) {
            html += row.step ? stepHtml(row.step) : messageHtml(row.message);
        });
        return '<div class="apx-thread" data-apx-thread>' + html + "</div>";
    }

    /* ── Cavab qutusu (dizayn §4.7) ─────────────────────────────────────── */
    function noteHtml(app) {
        var viewer = app.viewer || {};
        var unit = (app.current_unit && app.current_unit.name) || "";
        var text;
        if (viewer.is_sender) {
            // «Həll olundu» BAĞLI statusdur, amma sahib üçün hələ QƏRAR anıdır:
            // təsdiqləmək və ya razı qalmayıb qaytarmaq. `reopen` icazəsi məhz
            // bu anı göstərir — «bağlanıb» qeydi orada yanlış olardı.
            var canReopen = (app.allowed_actions || []).indexOf("reopen") !== -1;
            text = canReopen
                ? NS.t("noteSenderResolved")
                : app.is_open
                  ? NS.t("noteSenderOpen", { unit: unit })
                  : NS.t("noteSenderClosed");
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

    function pickerHtml() {
        var rules = NS.rules || {};
        return (
            '<div class="apx-act__files">' +
            '<button type="button" class="apx-act__attach" data-apx-pick-files>' +
            '<i class="fas fa-paperclip" aria-hidden="true"></i>' + NS.esc(NS.t("attachLabel")) + "</button>" +
            '<span class="apx-act__filehint">' +
            NS.esc(NS.t("attachHint", { mb: rules.maxMb || 10, n: rules.maxFiles || 5 })) + "</span>" +
            '<input type="file" class="apx__sr" data-apx-files multiple accept="' +
            NS.esc((rules.accept || []).join(",")) + '"></div>' +
            '<div class="apx-picked" data-apx-picked></div>'
        );
    }

    function actionsHtml(app, inlineActions) {
        var allowed = app.allowed_actions || [];
        var buttons = BUTTONS.filter(function (entry) {
            return allowed.indexOf(entry[0]) !== -1;
        });
        if (!buttons.length) {
            return '<div class="apx-act">' + noteHtml(app) + "</div>";
        }
        // Cavab qutusu YALNIZ mətn tələb edən əməl varsa göstərilir. Sahibin
        // «ləğv et» / «bağla» kimi əməlləri öz dialoqunu açır — onlara boş
        // textarea vermək dizaynın «yalnız-oxu qeyd» qaydasını pozardı (§4.7).
        var inline = buttons.filter(function (entry) {
            return !!inlineActions[entry[0]];
        });
        var needsText = inline.some(function (entry) {
            return inlineActions[entry[0]].min === "note";
        });
        var takesFiles = inline.some(function (entry) {
            return inlineActions[entry[0]].files;
        });
        var html = '<div class="apx-act"><ul class="apx-errors" data-apx-errors hidden></ul>';
        if (inline.length) {
            html +=
                '<label class="apx-act__label" for="apx-reply">' + NS.esc(NS.t("replyLabel")) + "</label>" +
                '<textarea id="apx-reply" rows="3" class="apx-act__input" data-apx-reply placeholder="' +
                NS.esc(NS.t("replyPlaceholder")) + '"></textarea>' +
                (takesFiles ? pickerHtml() : "");
        } else {
            html += noteHtml(app);
        }
        html +=
            '<div class="apx-act__buttons">' +
            buttons
                .map(function (entry) {
                    var gated = !!inlineActions[entry[0]];
                    return (
                        '<button type="button" class="' + entry[2] + '" data-apx-action="' + entry[0] + '"' +
                        (gated ? " disabled" : "") + ">" + NS.esc(NS.t(entry[1])) + "</button>"
                    );
                })
                .join("") +
            "</div>";
        if (needsText) {
            html +=
                '<div class="apx-act__hint" data-apx-reply-hint>' +
                NS.esc(NS.t("replyHint", { n: (NS.rules && NS.rules.note) || 10 })) + "</div>";
        }
        return html + "</div>";
    }

    /* ── Modalın tam markup-u ───────────────────────────────────────────── */
    function headHtml(app) {
        var sla = app.sla || {};
        var tone = sla.tone === "overdue" ? "apx-sla--overdue" : sla.tone === "closed" ? "apx-sla--closed" : "";
        var fromLine = NS.esc(app.requester.name) + (app.requester_scope ? " · " + NS.esc(app.requester_scope) : "");
        return (
            '<div class="apx-modal__head"><div class="apx-modal__top">' +
            '<span class="apx-no">' + NS.esc(app.number) + "</span>" +
            '<span class="apx-badge" data-bg="' + NS.esc(app.kind.bg) + '" data-fg="' + NS.esc(app.kind.fg) + '">' +
            NS.esc(app.kind.label) + "</span>" +
            '<span class="apx-pill" data-bg="' + NS.esc(app.status.bg) + '" data-fg="' + NS.esc(app.status.fg) + '">' +
            NS.esc(app.status.label) + "</span>" +
            '<button type="button" class="apx-modal__close" data-apx-detail-close aria-label="' +
            NS.esc(NS.t("closeDetail")) + '"><i class="fas fa-xmark" aria-hidden="true"></i>' +
            '<span class="apx-modal__closetext">' + NS.esc(NS.t("closeDetail")) + "</span></button></div>" +
            '<h2 class="apx-modal__title">' + NS.esc(app.subject) + "</h2>" +
            '<div class="apx-modal__from"><span>' + fromLine + "</span>" +
            '<span class="apx-ctx__dot" aria-hidden="true">·</span>' +
            "<span>" + NS.esc(NS.dateTime(app.submitted_at)) + "</span></div>" +
            '<div class="apx-sla ' + tone + '"><i class="fas fa-clock" aria-hidden="true"></i>' +
            '<span class="apx-sla__text">' + NS.esc(slaText(sla)) + "</span></div></div>"
        );
    }

    function html(app, inlineActions) {
        var files = app.attachments || [];
        return (
            headHtml(app) +
            '<div class="apx-modal__body" data-apx-modal-body>' +
            threadHtml(app) +
            (files.length
                ? '<div class="apx-modal__files"><div class="apx-label">' + NS.esc(NS.t("secFiles")) + "</div>" +
                  filesHtml(files) + "</div>"
                : "") +
            "</div>" +
            '<div class="apx-modal__foot">' + actionsHtml(app, inlineActions) + "</div>"
        );
    }

    /* Yükləmə skeleti — sorğu gedərkən modal boş qalmır (dizayn: gözləmə görünür). */
    function skeleton() {
        return (
            '<div class="apx-modal__head"><div class="apx-mskel apx-mskel--chips"></div>' +
            '<div class="apx-mskel apx-mskel--title"></div>' +
            '<div class="apx-mskel apx-mskel--line"></div></div>' +
            '<div class="apx-modal__body"><div class="apx-mskel apx-mskel--msg"></div>' +
            '<div class="apx-mskel apx-mskel--msg apx-mskel--short"></div>' +
            '<div class="apx-mskel apx-mskel--msg"></div></div>' +
            '<div class="apx-modal__foot"><div class="apx-mskel apx-mskel--foot"></div></div>'
        );
    }

    /* Son mesaja sürüşdürür — SƏHİFƏNİ deyil, yalnız modalın öz gövdəsini
     * (`scrollIntoView` əcdad scroller-ləri də tərpədir). Cavab yoxdursa
     * yazışmanın başında qalır. */
    function scrollToLatest(panel) {
        var body = panel && panel.querySelector("[data-apx-modal-body]");
        var latest = body && body.querySelector(".apx-msg.is-latest");
        if (!body || !latest) {
            return;
        }
        body.scrollTop += latest.getBoundingClientRect().top - body.getBoundingClientRect().top - 12;
    }

    NS.thread = {
        html: html,
        skeleton: skeleton,
        scrollToLatest: scrollToLatest,
        MARKS: MARKS,
        BUTTONS: BUTTONS,
    };
})();
