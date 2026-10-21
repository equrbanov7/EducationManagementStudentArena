(function (ns, window, document) {
    "use strict";

    // 2026-10-21: OCC konfliktindən (409) sonra serverlə sinxronlaşma — cavab itkisi yoxdur.
    //
    // Əvvəl 409 tabı «səhifəni yeniləyin» bannerı ilə donundururdu: sonrakı heç bir cavab
    // saxlanmırdı, «Bitir» də rədd olunurdu. Server indi eyni tabın öz yazılarını konflikt
    // saymır (`autosave_writer`), ona görə 409 yalnız (a) başqa tab/kompüter yazanda və ya
    // (b) server writer qeydi itəndə gəlir. Burada serverin cari cavabları alınır və hər sual
    // üçün üç tərəfli müqayisə edilir:
    //   ours   — DOM-dakı cari dəyər;  base — bu tabın serverdə SON təsdiqlənmiş dəyəri
    //   (+ cavabı itmiş, ola bilsin yazılmış göndərişlər);  theirs — serverdəki cari dəyər.
    //   theirs == ours            → sinxrondur;
    //   theirs ∈ base             → başqa tab bu suala toxunmayıb → bizimki yenidən göndərilir;
    //   ours == base              → yalnız başqa tab dəyişib → onunku DOM-a götürülür;
    //   hər ikisi fərqli dəyişib  → HƏQİQİ konflikt: tab bloklanır (kor-koranə üzərinə yazı yox),
    //                               əvvəlcə təhlükəsiz suallar göndərilir.
    // Uğurlu birləşmədən sonra orijinal əməliyyat (autosave / qaralama / bitir) yeni revision ilə
    // təkrarlanır.

    var MAX_RESYNCS = 3;
    var MAX_MAYBE = 8;

    function normalizeText(value) {
        return String(value || "").replace(/\r\n?/g, "\n").trim();
    }

    function questionValue(questionId) {
        var name = "q_" + questionId;
        var textarea = document.querySelector('textarea.written-answer[name="' + name + '"]');
        if (textarea) {
            return normalizeText(textarea.value);
        }
        var inputs = document.querySelectorAll('input[name="' + name + '"]');
        if (!inputs.length) {
            return undefined;
        }
        var checked = [];
        inputs.forEach(function (input) {
            if ((input.type === "radio" || input.type === "checkbox") && input.checked) {
                checked.push(String(input.value));
            }
        });
        return checked.sort().join(",");
    }

    function applyValue(questionId, value) {
        var name = "q_" + questionId;
        var textarea = document.querySelector('textarea.written-answer[name="' + name + '"]');
        if (textarea) {
            textarea.value = value;
            return;
        }
        var selected = value ? String(value).split(",") : [];
        document.querySelectorAll('input[name="' + name + '"]').forEach(function (input) {
            input.checked = selected.indexOf(String(input.value)) !== -1;
        });
    }

    function pageQuestionIds() {
        var ids = [];
        document.querySelectorAll(".question-slide[data-question-id]").forEach(function (slide) {
            ids.push(String(slide.dataset.questionId));
        });
        return ids;
    }

    function stores(ctx) {
        ctx.syncedValues = ctx.syncedValues || {};
        ctx.maybeAppliedValues = ctx.maybeAppliedValues || {};
        return ctx;
    }

    ns.resync = {
        questionValue: questionValue,

        // Səhifə yüklənəndə / gövdə inject olunanda DOM = server vəziyyəti → base.
        captureBase: function (ctx, questionIds) {
            stores(ctx);
            questionIds.forEach(function (questionId) {
                var key = String(questionId);
                if (ctx.syncedValues[key] !== undefined) return;
                var value = questionValue(key);
                if (value !== undefined) ctx.syncedValues[key] = value;
            });
        },

        snapshot: function (questionIds) {
            var values = {};
            questionIds.forEach(function (questionId) {
                var value = questionValue(questionId);
                if (value !== undefined) values[String(questionId)] = value;
            });
            return values;
        },

        confirm: function (ctx, sentValues) {
            stores(ctx);
            ctx.resyncCount = 0;
            Object.keys(sentValues || {}).forEach(function (key) {
                ctx.syncedValues[key] = sentValues[key];
                delete ctx.maybeAppliedValues[key];
            });
        },

        // Cavabı gəlməyən göndəriş serverdə yazılmış OLA BİLƏR — sonradan «bizimki» sayılsın.
        unconfirmed: function (ctx, sentValues) {
            stores(ctx);
            Object.keys(sentValues || {}).forEach(function (key) {
                var list = ctx.maybeAppliedValues[key] || (ctx.maybeAppliedValues[key] = []);
                if (list.indexOf(sentValues[key]) === -1) list.push(sentValues[key]);
                if (list.length > MAX_MAYBE) list.shift();
            });
        },

        // 409 → {retry:true} (yenidən göndər) | {block:true, conflicts:[...]} | {finished:true}.
        reconcile: function (ctx, action, conflictData) {
            stores(ctx);
            ctx.resyncCount = (ctx.resyncCount || 0) + 1;
            if (!ctx.answersStateUrl || typeof window.fetch !== "function" || ctx.resyncCount > MAX_RESYNCS) {
                return Promise.resolve({ block: true, conflicts: [] });
            }
            // Həmişə BÜTÜN suallar: başqa tabın dəyişdirdiyi, bu tabda toxunulmamış sual da DOM-a götürülməlidir —
            // yoxsa sonrakı «Bitir» (tam forma) onu köhnə dəyərlə yenidən yazardı.
            var ids = pageQuestionIds();
            var url = ctx.answersStateUrl + (ctx.answersStateUrl.indexOf("?") === -1 ? "?" : "&") + "q=" + ids.join(",");
            return window
                .fetch(url, {
                    method: "GET",
                    credentials: "same-origin",
                    headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" }
                })
                .then(function (res) {
                    if (!res.ok) throw new Error("resync_failed");
                    return res.json();
                })
                .then(function (state) {
                    if (state && state.finished) {
                        return { finished: true, redirectUrl: state.redirect_url || "" };
                    }
                    return ns.resync.merge(ctx, ids, state || {}, conflictData || {});
                })
                .catch(function () {
                    // Sinxron alınmadı (şəbəkə) — tab bloklanmır, autosave adi qaydada yenidən sınayır.
                    return { offline: true };
                });
        },

        merge: function (ctx, ids, state, conflictData) {
            var answers = state.answers || {};
            var conflicts = [];
            ids.forEach(function (key) {
                var theirs = answers[key];
                var ours = questionValue(key);
                if (theirs === undefined || ours === undefined) return;
                theirs = String(theirs);
                var base = ctx.syncedValues[key];
                var maybe = ctx.maybeAppliedValues[key] || [];
                if (theirs === ours) {
                    ctx.syncedValues[key] = theirs;
                    if (!ctx.binaryDirtyQuestionIds.has(key)) ctx.dirtyQuestionIds.delete(key);
                } else if (theirs === base || maybe.indexOf(theirs) !== -1) {
                    ctx.syncedValues[key] = theirs;
                    ctx.dirtyQuestionIds.add(key);
                } else if (ours === base) {
                    applyValue(key, theirs);
                    ctx.syncedValues[key] = theirs;
                    ctx.dirtyQuestionIds.delete(key);
                } else {
                    conflicts.push(key);
                    // Həqiqi konfliktli sual bu tabdan göndərilmir (başqa tabın cavabı qorunur).
                    ctx.dirtyQuestionIds.delete(key);
                }
                delete ctx.maybeAppliedValues[key];
            });
            if (ctx.autosaveRevisionField && state.server_revision !== undefined) {
                ctx.autosaveRevisionField.value = String(state.server_revision);
            }
            ctx.hasUnsavedChanges = ctx.dirtyQuestionIds.size > 0 || ctx.binaryDirtyQuestionIds.size > 0;
            var foreign =
                conflictData.reason === "foreign_writer" ||
                Boolean(state.writer && ctx.writerId && state.writer !== ctx.writerId);
            if (foreign && ns.syncStatus && ctx.syncStatusKind !== "conflict") {
                ns.syncStatus.show(ctx, "shared");
            }
            if (ns.progress && ns.progress.updateProgress) ns.progress.updateProgress(ctx);
            if (conflicts.length) {
                return { block: true, conflicts: conflicts };
            }
            return { retry: true };
        },

        // Həqiqi konflikt: avtomatik yazılar dayanır, banner + «Səhifəni yenilə» düyməsi.
        block: function (ctx, conflicts) {
            ctx.autosaveConflict = true;
            ctx.conflictQuestionIds = (conflicts || []).map(String);
            if (ctx.autoSaveTimer) {
                clearTimeout(ctx.autoSaveTimer);
                ctx.autoSaveTimer = null;
            }
            if (ns.syncStatus) ns.syncStatus.show(ctx, "conflict");
            ns.draft.persistLocalDraft(ctx);
            if (ns.notifications && ctx.i18n && ctx.i18n.autosaveConflict) {
                ns.notifications.show(ctx.i18n.autosaveConflict, "error", 8000);
            }
        },

        // 2026-10-21 (sahib): zal imtahanının HƏQİQİ ikinci tabı — birləşmə YOX, heç bir yazı YOX.
        // Cavab sahələri və bitirmə düymələri bağlanır; birinci tab adi qaydada davam edir.
        blockSecondTab: function (ctx) {
            if (ctx.secondTabBlocked) return;
            ctx.secondTabBlocked = true;
            ctx.autosaveConflict = true;
            ctx.hasUnsavedChanges = false;
            ctx.dirtyQuestionIds.clear();
            ctx.binaryDirtyQuestionIds.clear();
            if (ctx.autoSaveTimer) {
                clearTimeout(ctx.autoSaveTimer);
                ctx.autoSaveTimer = null;
            }
            if (ctx.examForm) {
                ctx.examForm.classList.add("exam-form--second-tab");
                ctx.examForm
                    .querySelectorAll('input[name^="q_"], textarea[name^="q_"], input[type="file"], #finish-btn, #save-draft-btn')
                    .forEach(function (field) {
                        field.disabled = true;
                    });
            }
            var finishBtn = document.getElementById("finish-btn");
            if (finishBtn) finishBtn.disabled = true;
            if (ns.syncStatus) ns.syncStatus.show(ctx, "secondTab");
        },

        init: function (ctx) {
            var button = document.getElementById("exam-sync-reload");
            if (!button || button.getAttribute("data-bound") === "1") return;
            button.setAttribute("data-bound", "1");
            button.addEventListener("click", function () {
                if (ctx.secondTabBlocked) {
                    // İkinci tab heç nə yazmayıb və yazmamalıdır — yalnız yenilə.
                    window.location.reload();
                    return;
                }
                // Konfliktli suallar draft-a düşmür — yenilənmədən sonra serverin (digər tabın) cavabı görünür;
                // qalan (təhlükəsiz) dəyişikliklər draft-dan bərpa olunur.
                ns.draft.persistLocalDraft(ctx);
                ctx.hasUnsavedChanges = false;
                window.location.reload();
            });
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
