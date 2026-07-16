(function (ns, window, document) {
    "use strict";

    function getQuestionIdFromField(field) {
        if (!field) {
            return null;
        }

        if (field.dataset && field.dataset.questionId) {
            return String(field.dataset.questionId);
        }

        var fieldName = field.getAttribute("name") || "";
        var match = fieldName.match(/^q_(\d+)$/);
        return match ? match[1] : null;
    }

    function markQuestionDirty(ctx, questionId, containsBinary) {
        if (questionId !== null && questionId !== undefined && questionId !== "") {
            var normalizedQuestionId = String(questionId);
            ctx.dirtyQuestionIds.add(normalizedQuestionId);
            if (containsBinary) {
                ctx.binaryDirtyQuestionIds.add(normalizedQuestionId);
            }
        }
    }

    function collectLocalDraft(ctx) {
        var textAnswers = {};
        var selectedAnswers = {};

        document.querySelectorAll('textarea.written-answer[name^="q_"]').forEach(function (textarea) {
            var questionId = getQuestionIdFromField(textarea);
            if (questionId) {
                textAnswers[questionId] = textarea.value;
            }
        });

        document.querySelectorAll('input[name^="q_"]').forEach(function (input) {
            var questionId = getQuestionIdFromField(input);
            if (!questionId) {
                return;
            }

            if (input.type === "radio") {
                if (!(questionId in selectedAnswers)) {
                    selectedAnswers[questionId] = null;
                }
                if (input.checked) {
                    selectedAnswers[questionId] = input.value;
                }
                return;
            }

            if (input.type === "checkbox") {
                if (!Array.isArray(selectedAnswers[questionId])) {
                    selectedAnswers[questionId] = [];
                }
                if (input.checked) {
                    selectedAnswers[questionId].push(input.value);
                }
            }
        });

        return {
            version: 1,
            updatedAt: Date.now(),
            currentIndex: ctx.currentIndex,
            textAnswers: textAnswers,
            selectedAnswers: selectedAnswers
        };
    }

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

    ns.draft = {
        getQuestionIdFromField: getQuestionIdFromField,

        persistLocalDraft: function (ctx) {
            try {
                // Cavab məzmunu paylaşılan cihazda brauzer sessiyasından sonra
                // qalmasın; naviqasiya state-indən fərqli olaraq tab-scope saxlanır.
                sessionStorage.setItem(ctx.draftStorageKey, JSON.stringify(collectLocalDraft(ctx)));
            } catch (error) {
                // Storage failure must not block the exam flow.
            }
        },

        clearLocalDraft: function (ctx) {
            try {
                sessionStorage.removeItem(ctx.draftStorageKey);
                // Əvvəlki versiyanın plaintext qalığını da təmizlə.
                localStorage.removeItem(ctx.draftStorageKey);
            } catch (error) {
                // Storage cleanup failure must not block finish/navigation.
            }
        },

        schedulePersistLocalDraft: function (ctx, delayMs) {
            var effectiveDelayMs = delayMs === undefined ? 400 : delayMs;
            if (ctx.persistDraftTimer) {
                return;
            }
            ctx.persistDraftTimer = setTimeout(function () {
                ctx.persistDraftTimer = null;
                ns.draft.persistLocalDraft(ctx);
            }, effectiveDelayMs);
        },

        scheduleProgressUpdate: function (ctx, delayMs) {
            var effectiveDelayMs = delayMs === undefined ? 150 : delayMs;
            if (ctx.progressUpdateTimer) {
                return;
            }
            ctx.progressUpdateTimer = setTimeout(function () {
                ctx.progressUpdateTimer = null;
                ns.progress.updateProgress(ctx);
            }, effectiveDelayMs);
        },

        restoreLocalDraft: function (ctx) {
            var draft = null;

            try {
                var serializedDraft = sessionStorage.getItem(ctx.draftStorageKey);
                if (!serializedDraft) {
                    // Bir-dəfəlik legacy miqrasiyası: cari tab-da draft-ı qoru,
                    // davamətlı localStorage nüsxəsini dərhal sil.
                    serializedDraft = localStorage.getItem(ctx.draftStorageKey);
                    if (serializedDraft) {
                        sessionStorage.setItem(ctx.draftStorageKey, serializedDraft);
                    }
                    localStorage.removeItem(ctx.draftStorageKey);
                }
                draft = JSON.parse(serializedDraft || "null");
            } catch (error) {
                ns.draft.clearLocalDraft(ctx);
                return;
            }

            if (!draft || draft.version !== 1) {
                return;
            }

            var restored = false;

            Object.entries(draft.textAnswers || {}).forEach(function (entry) {
                var questionId = entry[0];
                var value = entry[1];
                var textarea = document.querySelector('textarea.written-answer[name="q_' + questionId + '"]');
                if (textarea && textarea.value !== value) {
                    textarea.value = value;
                    markQuestionDirty(ctx, questionId);
                    restored = true;
                }
            });

            Object.entries(draft.selectedAnswers || {}).forEach(function (entry) {
                var questionId = entry[0];
                var value = entry[1];
                var inputs = document.querySelectorAll('input[name="q_' + questionId + '"]');
                if (!inputs.length) {
                    return;
                }

                var questionRestored = false;
                var selectedValues = Array.isArray(value) ? value.map(String) : [String(value)];
                inputs.forEach(function (input) {
                    var shouldCheck = value !== null && selectedValues.indexOf(String(input.value)) !== -1;
                    if (input.checked !== shouldCheck) {
                        input.checked = shouldCheck;
                        questionRestored = true;
                        restored = true;
                    }
                });

                if (questionRestored) {
                    markQuestionDirty(ctx, questionId);
                }
            });

            if (restored) {
                ctx.hasUnsavedChanges = true;
                ctx.answerRevision += 1;
                ns.progress.updateProgress(ctx);
                ns.draft.queueAutoSave(ctx);
            } else {
                ns.draft.clearLocalDraft(ctx);
            }
        },

        queueAutoSave: function (ctx, delayMs) {
            if (ctx.autosaveConflict || ctx.autoSaveTimer) {
                return;
            }

            // Explicit per-field debounce (test: 1s, written: 3s) must win over
            // the low-frequency fallback interval. Otherwise a selected answer
            // can remain only in the browser for 60s+ and is invisible to the
            // live monitor or a replacement computer.
            var effectiveDelayMs = delayMs === undefined
                ? ctx.autoSaveDelayMs
                : Math.max(250, Number(delayMs) || 0);
            ctx.autoSaveTimer = setTimeout(function () {
                ctx.autoSaveTimer = null;
                ns.draft.flushAutoSave(ctx);
            }, effectiveDelayMs);
        },

        flushAutoSave: function (ctx) {
            if (ctx.autosaveConflict || !ctx.hasUnsavedChanges) {
                return;
            }

            if (ctx.autoSaveRequestInFlight) {
                ns.draft.queueAutoSave(ctx);
                return;
            }

            ns.draft.sendDraft(ctx, "autosave", { silent: true }).catch(function () {});
        },

        markAnswerChanged: function (ctx, delayMs, questionId, options) {
            var effectiveOptions = options || {};
            ctx.hasUnsavedChanges = true;
            ctx.answerRevision += 1;
            markQuestionDirty(ctx, questionId, Boolean(effectiveOptions.containsBinary));
            ns.draft.schedulePersistLocalDraft(ctx);
            ns.draft.scheduleProgressUpdate(ctx);
            ns.draft.queueAutoSave(ctx, delayMs);
        },

        sendDraft: function (ctx, action, options) {
            var effectiveAction = action || "autosave";
            var effectiveOptions = options || {};
            if (ctx.autosaveConflict) {
                return Promise.reject(new Error("autosave_conflict"));
            }
            if (effectiveAction === "autosave" && ctx.finishRequestInFlight) {
                return Promise.resolve(null);
            }

            if (effectiveAction === "autosave" && !ctx.hasUnsavedChanges) {
                return Promise.resolve(null);
            }

            if (effectiveAction === "autosave" && ctx.autoSaveRequestInFlight) {
                ns.draft.queueAutoSave(ctx);
                return Promise.resolve(null);
            }

            var sentRevision = ctx.answerRevision;
            var sentDirtyQuestionIds = effectiveAction === "autosave" ? new Set(ctx.dirtyQuestionIds) : new Set();
            var formData = buildDraftFormData(ctx, effectiveAction);

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
                    // EXAM-P1-06: OCC konflikti — başqa tab daha yeni yazıb.
                    if (res.status === 409) {
                        return res.json().then(function (data) {
                            if (notification) {
                                ns.notifications.hide(notification);
                            }
                            if (data.error === "question_timer_not_started") {
                                ns.notifications.show(
                                    data.message || "Sual taymeri serverlə sinxronlaşmayıb; yenidən yoxlanılır.",
                                    "error",
                                    8000
                                );
                                ctx.hasUnsavedChanges = true;
                                ns.draft.persistLocalDraft(ctx);
                                var timerSlide = document.querySelector(
                                    '.question-slide[data-question-id="' + String(data.question_id || "") + '"]'
                                );
                                return ns.timers.syncQuestionTimerWithServer(ctx, timerSlide).then(function (syncData) {
                                    if (syncData && syncData.success) {
                                        // Server start-ı indi təsdiqlədi; dirty cavabı qısa
                                        // gecikmə ilə eyni revision-dan yenidən sına.
                                        if (effectiveAction === "autosave") {
                                            ctx.autoSaveTimer = setTimeout(function () {
                                                ctx.autoSaveTimer = null;
                                                ns.draft.flushAutoSave(ctx);
                                            }, 500);
                                        } else {
                                            setTimeout(function () {
                                                ns.draft.sendDraft(ctx, effectiveAction, effectiveOptions).catch(function () {});
                                            }, 500);
                                        }
                                    } else {
                                        ns.draft.queueAutoSave(ctx);
                                    }
                                    throw new Error("question_timer_sync_required");
                                });
                            }
                            ns.notifications.show(
                                data.message || ctx.i18n.autosaveConflict || "Bu imtahan başqa tabda yenilənib. Səhifəni yeniləyin.",
                                "error",
                                8000
                            );
                            // Konflikt həll edilmədən server revision-u qəbul etmək
                            // stale draft-ı növbəti retry-da legitim göstərərdi. Bütün
                            // avtomatik yazı yollarını reload-a qədər dondururuq.
                            ctx.autosaveConflict = true;
                            if (ctx.autoSaveTimer) {
                                clearTimeout(ctx.autoSaveTimer);
                                ctx.autoSaveTimer = null;
                            }
                            ctx.hasUnsavedChanges = true;
                            ns.draft.persistLocalDraft(ctx);
                            throw new Error("autosave_conflict");
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
                    // EXAM-P1-06: serverin yeni revision-unu qəbul et (növbəti OCC üçün).
                    if (ctx.autosaveRevisionField && typeof data.server_revision !== "undefined") {
                        ctx.autosaveRevisionField.value = String(data.server_revision);
                    }
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
                    ctx.hasUnsavedChanges = true;
                    ns.draft.persistLocalDraft(ctx);

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
        },

        // EXAM-P1-04 strict delivery: server-injected slide-lərin input-larına da
        // change listener-i qoşmaq üçün ayrıca (idempotent) bağlayıcı; init həm
        // də sonradan inject olunan gövdə üçün çağırılır.
        bindAnswerInputs: function (ctx, root) {
            var scope = root || document;
            scope.querySelectorAll('input[name^="q_"]').forEach(function (input) {
                if (input.getAttribute("data-answer-bound") === "1") {
                    return;
                }
                input.setAttribute("data-answer-bound", "1");
                input.addEventListener("change", function () {
                    if (ctx.examType === "test") {
                        ns.draft.markAnswerChanged(ctx, 1000, getQuestionIdFromField(input));
                        return;
                    }

                    ns.progress.updateProgress(ctx);
                });
            });

            scope.querySelectorAll("textarea.written-answer").forEach(function (textarea) {
                if (textarea.getAttribute("data-answer-bound") === "1") {
                    return;
                }
                textarea.setAttribute("data-answer-bound", "1");
                textarea.addEventListener("input", function () {
                    ns.draft.markAnswerChanged(ctx, 3000, getQuestionIdFromField(textarea));
                });
            });
        },

        init: function (ctx) {
            window.markExamAnswerChanged = function (delayMs, questionId, options) {
                ns.draft.markAnswerChanged(ctx, delayMs, questionId, options);
            };

            ns.draft.bindAnswerInputs(ctx, document);

            if (ctx.saveDraftBtn) {
                ctx.saveDraftBtn.addEventListener("click", function () {
                    ns.draft.sendDraft(ctx, "save_draft").catch(function () {});
                });
            }

            setInterval(function () {
                if (ctx.hasUnsavedChanges && !ctx.autoSaveTimer) {
                    ns.draft.flushAutoSave(ctx);
                }
            }, ctx.autoSaveDelayMs);

            window.addEventListener("online", function () {
                if (ctx.hasUnsavedChanges) {
                    ns.draft.flushAutoSave(ctx);
                }
            });
            window.addEventListener("offline", function () {
                ns.draft.persistLocalDraft(ctx);
            });
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
