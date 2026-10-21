(function (ns, window, document) {
    "use strict";

    // Take-exam yazı yolu (autosave / qaralama / bitir) — draft.js-dən ayrılıb (2026-10-21,
    // modul ölçüsü). Lokal draft, növbə və input bağlamaları draft.js-dədir.

    function appendFieldToFormData(formData, field) {
        if (!field || !field.name || field.disabled) {
            return;
        }

        if (field.type === "file") {
            Array.from(field.files || []).forEach(function (file) {
                formData.append(field.name, file);
            });
            return;
        }

        if ((field.type === "checkbox" || field.type === "radio") && !field.checked) {
            return;
        }

        formData.append(field.name, field.value);
    }

    function appendFieldsByName(ctx, formData, fieldName) {
        Array.from(ctx.examForm.elements).forEach(function (field) {
            if (field.name === fieldName) {
                appendFieldToFormData(formData, field);
            }
        });
    }

    function buildDraftFormData(ctx, action) {
        ns.progress.syncMarkedQuestionInput(ctx);
        ns.config.refreshFormCsrfToken(ctx);
        if (action !== "autosave") {
            var fullFormData = new FormData(ctx.examForm);
            if (ctx.markedQuestionIdsField) {
                fullFormData.set("marked_question_ids", ctx.markedQuestionIdsField.value);
            }
            fullFormData.set("csrfmiddlewaretoken", ns.config.getCsrfToken(ctx));
            fullFormData.append("submit_action", action);
            if (ns.writer) ns.writer.stamp(ctx, fullFormData);
            return fullFormData;
        }

        var formData = new FormData();
        formData.append("csrfmiddlewaretoken", ns.config.getCsrfToken(ctx));
        appendFieldsByName(ctx, formData, "return_to");
        appendFieldsByName(ctx, formData, "next");
        appendFieldsByName(ctx, formData, "from_section");
        appendFieldsByName(ctx, formData, "assigned_type");
        formData.append("submit_action", action);
        if (ctx.markedQuestionIdsField) {
            formData.append("marked_question_ids", ctx.markedQuestionIdsField.value);
        }
        // EXAM-P1-06: OCC — cari bildiyimiz server revision-u göndər.
        if (ctx.autosaveRevisionField) {
            formData.append("autosave_revision", ctx.autosaveRevisionField.value || "0");
        }
        if (ns.writer) ns.writer.stamp(ctx, formData);

        ctx.dirtyQuestionIds.forEach(function (questionId) {
            formData.append("changed_questions[]", questionId);
            appendFieldsByName(ctx, formData, "q_" + questionId);
            if (ctx.autoSaveBinaryUploadsEnabled) {
                appendFieldsByName(ctx, formData, "file_" + questionId + "[]");
                appendFieldsByName(ctx, formData, "paint_enabled_" + questionId);
                appendFieldsByName(ctx, formData, "paint_clear_" + questionId);
                appendFieldsByName(ctx, formData, "paint_data_" + questionId);
            }
        });

        return formData;
    }

    function noop() {}

    function track(ctx, request) {
        var tracked = request.then(noop, noop).then(function () {
            if (ctx.saveInFlight === tracked) ctx.saveInFlight = null;
        });
        ctx.saveInFlight = tracked;
        return tracked;
    }

    function allQuestionIds() {
        return Array.prototype.map.call(document.querySelectorAll(".question-slide[data-question-id]"), function (slide) {
            return String(slide.dataset.questionId);
        });
    }

    var sendApi = {
        // Bütün yazılar (autosave / qaralama / bitir) TƏK növbədən keçir: eyni tabın iki sorğusu eyni
        // base revision ilə paralel getmir (2026-10-21 — «Qaralama saxla»/«Bitir» fonda gedən autosave
        // ilə toqquşub özünə «başqa tab» 409-u alırdı). Qaralama/bitir yolda olan yazını gözləyir,
        // formanı ondan SONRA (yeni revision ilə) qurur.
        sendDraft: function (ctx, action, options) {
            var effectiveAction = action || "autosave";
            var effectiveOptions = options || {};
            if (ctx.autosaveConflict) {
                if (effectiveAction !== "autosave" && ns.resync && !ctx.secondTabBlocked) {
                    // Bloklu tabda «Bitir»/«Qaralama» — səbəbi və «Səhifəni yenilə» düyməsini yenidən göstər.
                    ns.resync.block(ctx, ctx.conflictQuestionIds);
                }
                return Promise.reject(new Error("autosave_conflict"));
            }
            if (effectiveAction === "autosave" && (ctx.finishRequestInFlight || ctx.fullSaveQueued)) {
                return Promise.resolve(null);
            }
            if (effectiveAction === "autosave" && !ctx.hasUnsavedChanges) {
                return Promise.resolve(null);
            }
            if (effectiveAction === "autosave" && (ctx.autoSaveRequestInFlight || ctx.saveInFlight || ns.retry.remaining(ctx))) {
                ns.draft.queueAutoSave(ctx, ctx.autoSaveRequestInFlight || ctx.saveInFlight ? undefined : ns.retry.remaining(ctx));
                return Promise.resolve(null);
            }
            if (effectiveAction !== "autosave" && ctx.saveInFlight) {
                ctx.fullSaveQueued = (ctx.fullSaveQueued || 0) + 1;
                return ctx.saveInFlight.then(noop, noop).then(function () {
                    ctx.fullSaveQueued -= 1;
                    return ns.draft.sendDraft(ctx, effectiveAction, effectiveOptions);
                });
            }

            var request = ns.draft.performSend(ctx, effectiveAction, effectiveOptions);
            var tracked = track(ctx, request);
            return request.then(function (result) {
                if (!result || !result.resync) {
                    return result;
                }
                return tracked.then(function () {
                    return ns.draft.afterResync(ctx, effectiveAction, effectiveOptions, result.resync);
                });
            });
        },

        afterResync: function (ctx, action, options, outcome) {
            if (outcome.finished) {
                ns.draft.clearLocalDraft(ctx);
                ns.navigation.prepareExamFinishNavigation(ctx);
                if (outcome.redirectUrl) window.location.href = outcome.redirectUrl;
                return null;
            }
            if (outcome.offline) {
                // Sinxron alınmadı — cavablar draft-dadır, autosave adi qaydada yenidən sınayır.
                ctx.hasUnsavedChanges = true;
                ns.draft.persistLocalDraft(ctx);
                if (action === "autosave") ns.draft.queueAutoSave(ctx);
                throw new Error("Draft save failed");
            }
            if (outcome.block) {
                // Əvvəlcə başqa tabın toxunmadığı (təhlükəsiz) cavabları göndər, sonra blokla.
                // (konfliktli suallar merge-də dirty-dən çıxarılıb — onlar göndərilmir).
                var flush = Promise.resolve(null);
                if (ctx.hasUnsavedChanges && !ctx.blockFlushDone) {
                    ctx.blockFlushDone = true;
                    flush = ns.draft.performSend(ctx, "autosave", { silent: true });
                    track(ctx, flush);
                }
                return flush.then(noop, noop).then(function () {
                    ns.resync.block(ctx, outcome.conflicts);
                    throw new Error("autosave_conflict");
                });
            }
            if (action === "autosave" && !ctx.hasUnsavedChanges) {
                return null;
            }
            return ns.draft.sendDraft(ctx, action, options);
        },

        performSend: function (ctx, effectiveAction, effectiveOptions) {
            var sentRevision = ctx.answerRevision;
            var sentDirtyQuestionIds = effectiveAction === "autosave" ? new Set(ctx.dirtyQuestionIds) : new Set();
            var formData = buildDraftFormData(ctx, effectiveAction);
            var sentValues = ns.resync
                ? ns.resync.snapshot(effectiveAction === "autosave" ? Array.from(sentDirtyQuestionIds) : allQuestionIds())
                : {};

            if (effectiveAction === "autosave") {
                ctx.autoSaveRequestInFlight = true;
            }

            var notification = null;
            if (effectiveAction === "autosave" && !effectiveOptions.silent) {
                notification = ns.notifications.show(ctx.i18n.autosaveSaving, "info");
            }

            return fetch(window.location.href, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": ns.config.getCsrfToken(ctx)
                },
                body: formData
            })
                .then(function (res) {
                    ns.retry.noteResponse(ctx, res);
                    // EXAM-P1-06: OCC konflikti — başqa tab daha yeni yazıb.
                    if (res.status === 409) {
                        return res.json().then(function (data) {
                            if (notification) {
                                ns.notifications.hide(notification);
                            }
                            if (data.error === "question_timer_not_started") {
                                return ns.timers.handleTimerNotStarted(ctx, data, effectiveAction, effectiveOptions);
                            }
                            if (ns.resync) ns.resync.unconfirmed(ctx, sentValues);
                            if (!ns.resync) {
                                throw new Error("autosave_conflict");
                            }
                            // 2026-10-21 (sahib): zal imtahanında başqa tab yazırsa bu tab tam bloklanır (birləşmə yox).
                            if (ctx.isCenterExam && data.reason === "foreign_writer") {
                                ns.resync.blockSecondTab(ctx);
                                throw new Error("autosave_conflict");
                            }
                            // 2026-10-21: donmaq yerinə serverlə sinxronlaş (bax resync.js).
                            return ns.resync.reconcile(ctx, effectiveAction, data).then(function (outcome) {
                                return { resync: outcome };
                            });
                        });
                    }
                    if (!res.ok) {
                        throw new Error(res.status === 403 ? "csrf_or_session" : "Draft save failed");
                    }
                    var contentType = res.headers.get("content-type") || "";
                    if (contentType.indexOf("application/json") === -1) {
                        ns.draft.persistLocalDraft(ctx);
                        if (res.redirected && res.url) {
                            ns.navigation.prepareExamFinishNavigation(ctx);
                            window.location.href = res.url;
                        }
                        throw new Error("Unexpected non-JSON response");
                    }
                    return res.json();
                })
                .then(function (data) {
                    if (data && data.resync) {
                        if (notification) ns.notifications.hide(notification);
                        return data;
                    }
                    // EXAM-P1-06: serverin yeni revision-unu qəbul et (növbəti OCC üçün).
                    if (ctx.autosaveRevisionField && typeof data.server_revision !== "undefined") {
                        ctx.autosaveRevisionField.value = String(data.server_revision);
                    }
                    if (ns.resync) ns.resync.confirm(ctx, sentValues);
                    if (sentRevision === ctx.answerRevision) {
                        if (effectiveAction === "autosave" && !ctx.autoSaveBinaryUploadsEnabled) {
                            sentDirtyQuestionIds.forEach(function (questionId) {
                                var normalizedQuestionId = String(questionId);
                                if (!ctx.binaryDirtyQuestionIds.has(normalizedQuestionId)) {
                                    ctx.dirtyQuestionIds.delete(normalizedQuestionId);
                                }
                            });
                            ctx.hasUnsavedChanges = ctx.dirtyQuestionIds.size > 0 || ctx.binaryDirtyQuestionIds.size > 0;
                            if (ctx.hasUnsavedChanges) {
                                ns.draft.persistLocalDraft(ctx);
                            } else {
                                ns.draft.clearLocalDraft(ctx);
                            }
                        } else {
                            ctx.hasUnsavedChanges = false;
                            ctx.dirtyQuestionIds.clear();
                            ctx.binaryDirtyQuestionIds.clear();
                            ns.draft.clearLocalDraft(ctx);
                        }
                    } else {
                        ctx.hasUnsavedChanges = true;
                        ns.draft.persistLocalDraft(ctx);
                        ns.draft.queueAutoSave(ctx);
                    }

                    if (notification) {
                        ns.notifications.hide(notification);
                    }
                    if (effectiveAction === "autosave" && !effectiveOptions.silent) {
                        ns.notifications.show(ctx.i18n.autosaveSaved, "success", 2000);
                    }

                    if (data.finished && data.redirect_url) {
                        localStorage.removeItem(ctx.storageKey);
                        localStorage.removeItem(ctx.markedStorageKey);
                        ns.draft.clearLocalDraft(ctx);
                        ns.navigation.prepareExamFinishNavigation(ctx);
                        window.location.href = data.redirect_url;
                        return undefined;
                    }

                    if (effectiveAction === "save_draft") {
                        var originalText = ctx.saveDraftBtn.innerHTML;
                        ctx.saveDraftBtn.innerHTML = '<i class="fas fa-check"></i> ' + ctx.i18n.draftSaved;
                        ctx.saveDraftBtn.disabled = true;
                        setTimeout(function () {
                            ctx.saveDraftBtn.innerHTML = originalText;
                            ctx.saveDraftBtn.disabled = false;
                        }, 2000);
                    }

                    return data;
                })
                .catch(function (err) {
                    if (notification) {
                        ns.notifications.hide(notification);
                    }
                    // EXAM-P1-06: OCC konflikti artıq öz mesajını göstərib —
                    // saveError göstərmə və auto-retry queue etmə (stale overwrite
                    // qarşısı; istifadəçi səhifəni yeniləyib davam etməlidir).
                    if (err && (err.message === "autosave_conflict" || err.message === "question_timer_sync_required")) {
                        throw err;
                    }
                    // Cavab gəlmədi — server yazmış ola bilər (resync bunu «bizimki» sayır).
                    if (ns.resync) ns.resync.unconfirmed(ctx, sentValues);
                    ctx.hasUnsavedChanges = true;
                    ns.draft.persistLocalDraft(ctx);
                    if (ns.syncStatus) ns.syncStatus.failed(ctx, err);

                    if (effectiveAction === "autosave") {
                        ns.draft.queueAutoSave(ctx);
                    }

                    if (!effectiveOptions.silent || effectiveAction === "save_draft") {
                        ns.notifications.show(ctx.i18n.saveError, "error", 3000);
                    }

                    if (effectiveAction === "save_draft") {
                        alert(ctx.i18n.saveErrorRetry);
                    }
                    throw err;
                })
                .finally(function () {
                    if (effectiveAction === "autosave") {
                        ctx.autoSaveRequestInFlight = false;
                        if (!ctx.autosaveConflict && ctx.hasUnsavedChanges) {
                            ns.draft.queueAutoSave(ctx);
                        }
                    }
                });
        }
    };

    Object.keys(sendApi).forEach(function (name) {
        ns.draft[name] = sendApi[name];
    });
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
