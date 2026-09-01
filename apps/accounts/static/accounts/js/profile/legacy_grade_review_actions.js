/**
 * Dəqiqləşdirmə ƏMƏLLƏRİ — `window.EMSLegacyReviewActions`.
 *
 * Üç əməl, üç fərqli təsdiq dərəcəsi (bilərəkdən asimmetrik):
 *   • «Təsdiqlə» — canlı bala toxunmur → sadə təsdiq sualı kifayətdir;
 *   • «Mübahisəli» — qərar deyil, işarədir → SƏBƏB məcburidir;
 *   • «Düzəlt» — canlı imtahan balını dəyişir → səbəb + qeyd + SƏNƏD üçü də
 *     məcburidir, çünki server tərəfdəki `exam_score_entry` müqaviləsi artıq
 *     yazılmış balın sənədsiz dəyişdirilməsini QƏBUL ETMİR. Formanı burada da
 *     yoxlayırıq ki, istifadəçi 400-ü fayl yükləyəndən SONRA görməsin.
 *
 * Yazı MULTIPART gedir (sənəd daşınır); CSRF `EMSCore.getCookie` ilə.
 * Ayrı fayl: modul ölçü büdcəsi + `legacy_grade_review.js` vəziyyət modulu olaraq
 * qalsın, dialoq idarəsi ilə qarışmasın.
 */
(function () {
    "use strict";

    function csrfToken() {
        if (window.EMSCore && window.EMSCore.getCookie) {
            return window.EMSCore.getCookie("csrftoken") || "";
        }
        return "";
    }

    function show(dialog) {
        if (!dialog) {
            return;
        }
        if (dialog.showModal) {
            dialog.showModal();
        } else {
            dialog.setAttribute("open", "open");
        }
    }

    function close(dialog) {
        if (!dialog) {
            return;
        }
        if (dialog.close) {
            dialog.close();
        } else {
            dialog.removeAttribute("open");
        }
    }

    function rowMeta(row) {
        if (!row) {
            return "";
        }
        return [row.student, row.subject, row.group, row.source_reference].filter(Boolean).join(" · ");
    }

    function bind(root, ctx) {
        var actionUrl = root.dataset.actionUrl;
        var minNote = parseInt(root.dataset.minNote || "3", 10);
        var correctDialog = root.querySelector("[data-lgr-correct-dialog]");
        var disputeDialog = root.querySelector("[data-lgr-dispute-dialog]");
        var correctForm = root.querySelector("[data-lgr-correct-form]");
        var disputeForm = root.querySelector("[data-lgr-dispute-form]");
        var pending = { factId: "" };

        function post(body, dialog, errorNode) {
            return fetch(actionUrl, {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
                body: body,
                credentials: "same-origin"
            })
                .then(function (response) {
                    return response.json().catch(function () {
                        return { ok: false, message: ctx.i18n.error || "" };
                    });
                })
                .then(function (data) {
                    if (!data || !data.ok) {
                        var text = (data && data.message) || ctx.i18n.error || "";
                        if (errorNode) {
                            errorNode.textContent = text;
                        } else {
                            ctx.toast(text, "error");
                        }
                        return;
                    }
                    close(dialog);
                    ctx.toast(ctx.i18n.saved || "");
                    ctx.onDone();
                })
                .catch(function () {
                    var text = ctx.i18n.error || "";
                    if (errorNode) {
                        errorNode.textContent = text;
                    } else {
                        ctx.toast(text, "error");
                    }
                });
        }

        // ── Sətir düymələri (delegated: sətirlər hər yükləmədə yenidən qurulur) ──
        root.addEventListener("click", function (event) {
            var button = event.target.closest ? event.target.closest("[data-lgr-action]") : null;
            if (!button || !root.contains(button)) {
                return;
            }
            var action = button.dataset.lgrAction;
            var factId = button.dataset.lgrFact;
            var row = ctx.getRow(factId);
            pending.factId = factId;

            if (action === "verify") {
                if (!window.confirm(ctx.i18n.verifyConfirm || "")) {
                    return;
                }
                var body = new FormData();
                body.append("action", "verify");
                body.append("fact_id", factId);
                post(body, null, null);
                return;
            }
            if (action === "dispute") {
                var disputeMeta = root.querySelector("[data-lgr-dispute-meta]");
                var disputeError = root.querySelector("[data-lgr-dispute-error]");
                if (disputeMeta) {
                    disputeMeta.textContent = rowMeta(row);
                }
                if (disputeError) {
                    disputeError.textContent = "";
                }
                show(disputeDialog);
                return;
            }
            if (action === "correct") {
                var correctMeta = root.querySelector("[data-lgr-correct-meta]");
                var correctError = root.querySelector("[data-lgr-correct-error]");
                if (correctMeta) {
                    correctMeta.textContent = rowMeta(row);
                }
                if (correctError) {
                    correctError.textContent = "";
                }
                var scoreInput = root.querySelector("#lgr-correct-score");
                if (scoreInput && row) {
                    // Başlanğıc dəyər KÖHNƏ sistemin xam imtahan balıdır: ən çox
                    // rast gəlinən düzəliş məhz onu canlıya köçürməkdir.
                    scoreInput.value = row.exam_score || "";
                }
                show(correctDialog);
            }
        });

        root.addEventListener("click", function (event) {
            var cancel = event.target.closest ? event.target.closest("[data-lgr-dialog-cancel]") : null;
            if (!cancel) {
                return;
            }
            close(cancel.closest("dialog"));
        });

        if (disputeForm) {
            disputeForm.addEventListener("submit", function (event) {
                event.preventDefault();
                var note = root.querySelector("#lgr-dispute-note");
                var errorNode = root.querySelector("[data-lgr-dispute-error]");
                var text = note && note.value ? note.value.trim() : "";
                if (text.length < minNote) {
                    if (errorNode) {
                        errorNode.textContent = ctx.i18n.noteShort || "";
                    }
                    return;
                }
                var body = new FormData();
                body.append("action", "dispute");
                body.append("fact_id", pending.factId);
                body.append("note", text);
                post(body, disputeDialog, errorNode);
            });
        }

        if (correctForm) {
            correctForm.addEventListener("submit", function (event) {
                event.preventDefault();
                var errorNode = root.querySelector("[data-lgr-correct-error]");
                var score = root.querySelector("#lgr-correct-score");
                var reason = root.querySelector("#lgr-correct-reason");
                var note = root.querySelector("#lgr-correct-note");
                var evidence = root.querySelector("#lgr-correct-evidence");
                var noteText = note && note.value ? note.value.trim() : "";
                if (noteText.length < minNote) {
                    if (errorNode) {
                        errorNode.textContent = ctx.i18n.noteShort || "";
                    }
                    return;
                }
                var body = new FormData();
                body.append("action", "correct");
                body.append("fact_id", pending.factId);
                body.append("score", score ? score.value : "");
                body.append("reason", reason ? reason.value : "");
                body.append("note", noteText);
                if (evidence && evidence.files && evidence.files[0]) {
                    body.append("evidence", evidence.files[0]);
                }
                post(body, correctDialog, errorNode);
            });
        }
    }

    window.EMSLegacyReviewActions = { bind: bind };
})();
