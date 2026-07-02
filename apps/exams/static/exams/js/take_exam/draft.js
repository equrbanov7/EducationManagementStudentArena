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
                localStorage.setItem(ctx.draftStorageKey, JSON.stringify(collectLocalDraft(ctx)));
            } catch (error) {
                // localStorage failure must not block the exam flow.
            }
        },

        clearLocalDraft: function (ctx) {
            localStorage.removeItem(ctx.draftStorageKey);
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
                draft = JSON.parse(localStorage.getItem(ctx.draftStorageKey) || "null");
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
            if (ctx.autoSaveTimer) {
                return;
            }

            var requestedDelayMs = delayMs === undefined ? ctx.autoSaveDelayMs : Number(delayMs) || 0;
            var effectiveDelayMs = Math.max(ctx.autoSaveDelayMs, requestedDelayMs);
            ctx.autoSaveTimer = setTimeout(function () {
                ctx.autoSaveTimer = null;
                ns.draft.flushAutoSave(ctx);
            }, effectiveDelayMs);
        },

        flushAutoSave: function (ctx) {
            if (!ctx.hasUnsavedChanges) {
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
                        if (ctx.hasUnsavedChanges) {
                            ns.draft.queueAutoSave(ctx);
                        }
                    }
                });
        },

        init: function (ctx) {
            window.markExamAnswerChanged = function (delayMs, questionId, options) {
                ns.draft.markAnswerChanged(ctx, delayMs, questionId, options);
            };

            document.querySelectorAll('input[name^="q_"]').forEach(function (input) {
                input.addEventListener("change", function () {
                    if (ctx.examType === "test") {
                        ns.draft.markAnswerChanged(ctx, 1000, getQuestionIdFromField(input));
                        return;
                    }

                    ns.progress.updateProgress(ctx);
                });
            });

            document.querySelectorAll("textarea.written-answer").forEach(function (textarea) {
                textarea.addEventListener("input", function () {
                    ns.draft.markAnswerChanged(ctx, 3000, getQuestionIdFromField(textarea));
                });
            });

            if (ctx.saveDraftBtn) {
                ctx.saveDraftBtn.addEventListener("click", function () {
                    var originalText = ctx.saveDraftBtn.innerHTML;
                    ctx.saveDraftBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + ctx.i18n.btnSaving;
                    ctx.saveDraftBtn.disabled = true;

                    var sentRevision = ctx.answerRevision;
                    var formData = buildDraftFormData(ctx, "save_draft");

                    fetch(window.location.href, {
                        method: "POST",
                        headers: {
                            "X-Requested-With": "XMLHttpRequest",
                            "X-CSRFToken": ns.config.getCsrfToken(ctx)
                        },
                        body: formData
                    })
                        .then(function (res) {
                            if (!res.ok) {
                                throw new Error("Draft save failed");
                            }
                            return res.json();
                        })
                        .then(function (data) {
                            if (sentRevision === ctx.answerRevision) {
                                ctx.hasUnsavedChanges = false;
                                ctx.dirtyQuestionIds.clear();
                                ctx.binaryDirtyQuestionIds.clear();
                                ns.draft.clearLocalDraft(ctx);
                            } else {
                                ctx.hasUnsavedChanges = true;
                                ns.draft.persistLocalDraft(ctx);
                                ns.draft.queueAutoSave(ctx);
                            }

                            if (data.finished && data.redirect_url) {
                                localStorage.removeItem(ctx.storageKey);
                                localStorage.removeItem(ctx.markedStorageKey);
                                ns.draft.clearLocalDraft(ctx);
                                ns.navigation.prepareExamFinishNavigation(ctx);
                                window.location.href = data.redirect_url;
                                return;
                            }

                            ctx.saveDraftBtn.innerHTML = '<i class="fas fa-check"></i> ' + ctx.i18n.btnSaved;
                            ns.notifications.show(ctx.i18n.draftSavedWithCheck, "success", 2000);

                            setTimeout(function () {
                                ctx.saveDraftBtn.innerHTML = originalText;
                                ctx.saveDraftBtn.disabled = false;
                            }, 2000);
                        })
                        .catch(function () {
                            ctx.hasUnsavedChanges = true;
                            ns.draft.persistLocalDraft(ctx);
                            ctx.saveDraftBtn.innerHTML = originalText;
                            ctx.saveDraftBtn.disabled = false;
                            ns.notifications.show(ctx.i18n.saveError, "error", 3000);
                        });
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
