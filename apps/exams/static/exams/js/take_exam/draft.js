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
        // 2026-10-21: həqiqi konfliktli suallar (başqa tab fərqli dəyişib) draft-a düşmür.
        var excluded = ctx.conflictQuestionIds || [];

        document.querySelectorAll('textarea.written-answer[name^="q_"]').forEach(function (textarea) {
            var questionId = getQuestionIdFromField(textarea);
            if (questionId && excluded.indexOf(String(questionId)) === -1) {
                textAnswers[questionId] = textarea.value;
            }
        });

        document.querySelectorAll('input[name^="q_"]').forEach(function (input) {
            var questionId = getQuestionIdFromField(input);
            if (!questionId || excluded.indexOf(String(questionId)) !== -1) {
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
            // EXAMQA 2026-10-01: draft hansı server revision-una nisbətən yazılıb
            // (bərpa zamanı OCC yoxlaması üçün — bax restoreLocalDraft).
            baseRevision: ctx.autosaveRevisionField ? String(ctx.autosaveRevisionField.value || "0") : null,
            writer: ctx.writerId || null,
            currentIndex: ctx.currentIndex,
            textAnswers: textAnswers,
            selectedAnswers: selectedAnswers
        };
    }

    // 2026-10-21: draft-dan sonrakı server yazılarının HAMISI bu tabın özününkü idisə (məs. autosave
    // yolda ikən səhifə yeniləndi) draft köhnəlməyib — bərpa olunur (writer.js / _autosave_writer.py).
    function ownLaterWrites(ctx, draft) {
        var field = ctx.autosaveRevisionField;
        var writer = field && field.dataset ? field.dataset.writer : "";
        var since = field && field.dataset ? parseInt(field.dataset.writerSince, 10) : NaN;
        return Boolean(
            draft.writer && ctx.writerId && draft.writer === ctx.writerId && writer === ctx.writerId &&
                !isNaN(since) && Number(draft.baseRevision) >= since
        );
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
            if (ctx.secondTabBlocked) {
                return; // 2026-10-21: bloklu ikinci tab heç nə bərpa etmir/yazmır
            }

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

            // EXAMQA 2026-10-01: draft yalnız yazıldığı server revision-una nisbətən
            // etibarlıdır. Başqa tab bu arada yazıbsa (revision irəliləyib), köhnə
            // tabın lokal draft-ı reload-dan sonra serverdəki daha yeni cavabları
            // silirdi (məs. digər tabda seçilmiş variantı «boş» edirdi) — EXAM-P1-06
            // OCC-si reload yolu ilə yan keçilirdi. Belə draft atılır, server
            // vəziyyəti göstərilir. baseRevision-suz köhnə draft əvvəlki kimi bərpa olunur.
            if (
                draft.baseRevision !== undefined &&
                draft.baseRevision !== null &&
                ctx.autosaveRevisionField &&
                String(draft.baseRevision) !== String(ctx.autosaveRevisionField.value || "0") &&
                !ownLaterWrites(ctx, draft)
            ) {
                ns.draft.clearLocalDraft(ctx);
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
            if (ctx.autosaveConflict) {
                return;
            }

            // Explicit per-field debounce (test: 1s, written: 3s) must win over
            // the low-frequency fallback interval. Otherwise a selected answer
            // can remain only in the browser for 60s+ and is invisible to the
            // live monitor or a replacement computer.
            var effectiveDelayMs = delayMs === undefined
                ? ctx.autoSaveDelayMs
                : Math.max(250, Number(delayMs) || 0);
            effectiveDelayMs = Math.max(effectiveDelayMs, ns.retry.remaining(ctx));
            var dueAt = Date.now() + effectiveDelayMs;
            if (ctx.autoSaveTimer) {
                // Prefer earlier answer debounce, while respecting server backoff.
                if (!ctx.autoSaveDueAt || ctx.autoSaveDueAt <= dueAt) {
                    return;
                }
                clearTimeout(ctx.autoSaveTimer);
            }
            ctx.autoSaveDueAt = dueAt;
            ctx.autoSaveTimer = setTimeout(function () {
                ctx.autoSaveTimer = null;
                ctx.autoSaveDueAt = 0;
                ns.draft.flushAutoSave(ctx);
            }, effectiveDelayMs);
        },

        flushAutoSave: function (ctx) {
            if (ctx.autosaveConflict || !ctx.hasUnsavedChanges) {
                return;
            }

            if (ctx.autoSaveRequestInFlight || ns.retry.remaining(ctx)) {
                // Backoff: retry when it ends (timers fire early), not after the 30 s fallback.
                ns.draft.queueAutoSave(ctx, ctx.autoSaveRequestInFlight ? undefined : ns.retry.remaining(ctx));
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


        // EXAM-P1-04 strict delivery: server-injected slide-lərin input-larına da
        // change listener-i qoşmaq üçün ayrıca (idempotent) bağlayıcı; init həm
        // də sonradan inject olunan gövdə üçün çağırılır.
        bindAnswerInputs: function (ctx, root) {
            var scope = root || document;
            // 2026-10-21: render/inject olunan dəyər = serverdə təsdiqlənmiş dəyər (resync base-i).
            if (ns.resync) {
                var boundIds = [];
                scope.querySelectorAll('input[name^="q_"], textarea.written-answer[name^="q_"]').forEach(function (field) {
                    var fieldQuestionId = getQuestionIdFromField(field);
                    if (fieldQuestionId && field.getAttribute("data-answer-bound") !== "1") boundIds.push(fieldQuestionId);
                });
                ns.resync.captureBase(ctx, boundIds);
            }
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
