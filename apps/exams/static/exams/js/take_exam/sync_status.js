(function (ns, window, document) {
    "use strict";

    // Daimi «cavablar serverə yazılır?» göstəricisi (UX review 2026-10-05).
    // Autosave səssizdir (silent) — şəbəkə kəsiləndə, server 429/503 verəndə və ya başqa
    // tab konflikt yaradanda tələbə heç nə görmürdü və cavabların yalnız brauzerdə
    // qaldığını bilmirdi. Bu modul `#exam-sync-status` (aria-live) sətrini idarə edir:
    //   busy     — server yüklüdür (429/503), avtomatik yenidən cəhd edilir;
    //   offline  — bağlantı/server xətası, cavablar brauzerdə saxlanılır;
    //   conflict — başqa tab eyni sualı fərqli dəyişib, səhifə yenilənməlidir (daimi + düymə);
    //   shared   — 2026-10-21: başqa tab/kompüter də yazır, cavablar birləşdirilir (daimi xəbərdarlıq);
    //   secondTab — 2026-10-21: zal imtahanının İKİNCİ tabı — tam bloklanıb, heç nə yazmır (daimi + düymə);
    //   ok       — xətadan sonra bərpa («yenidən saxlanıldı», 3 s).
    var hideTimer = null;
    var KEYS = {
        busy: "autosaveBusy",
        offline: "autosaveOffline",
        conflict: "autosaveConflict",
        shared: "autosaveShared",
        secondTab: "autosaveSecondTab"
    };

    function paint(ctx, kind, text) {
        var el = document.getElementById("exam-sync-status");
        if (!el) return;
        window.clearTimeout(hideTimer);
        ctx.syncStatusKind = kind;
        if (kind === "shared") ctx.syncSharedWriter = true;
        el.textContent = text || "";
        el.className = "exam-sync-status" + (kind ? " exam-sync-status--" + kind : "");
        el.hidden = !text;
        var reload = document.getElementById("exam-sync-reload");
        if (reload) reload.hidden = kind !== "conflict" && kind !== "secondTab";
    }

    // Keçici xəbərdarlıq bitəndə daimi «başqa tab» xəbərdarlığına qayıt.
    function rest(ctx) {
        if (ctx.syncSharedWriter) {
            paint(ctx, "shared", text(ctx, KEYS.shared));
        } else {
            paint(ctx, "", "");
        }
    }

    function text(ctx, key) {
        return (ctx.i18n && ctx.i18n[key]) || "";
    }

    ns.syncStatus = {
        // kind: "busy" | "offline" | "conflict"
        show: function (ctx, kind) {
            paint(ctx, kind, text(ctx, KEYS[kind]));
        },

        // draft.js `.catch`-i: 429/503 artıq `retry.noteResponse`-da «busy» göstərib — üzərinə yazma.
        failed: function (ctx, err) {
            var message = err && err.message;
            if (message === "autosave_conflict" || message === "question_timer_sync_required") return;
            if (ctx.syncStatusKind === "conflict" || ctx.syncStatusKind === "secondTab") return;
            if (ctx.syncStatusKind === "busy" && ns.retry && ns.retry.remaining(ctx) > 0) return;
            ns.syncStatus.show(ctx, "offline");
        },

        // Uğurlu cavab: yalnız əvvəl xəta göstərilibsə qısa təsdiq.
        recovered: function (ctx) {
            var kind = ctx.syncStatusKind;
            if (kind !== "busy" && kind !== "offline") return;
            paint(ctx, "ok", text(ctx, "autosaveRecovered"));
            hideTimer = window.setTimeout(function () {
                rest(ctx);
            }, 3000);
        },

        // Brauzer oflayn olanda dərhal xəbər ver. (Yenidən onlayn olanda draft.js özü yazını sınayır;
        // «bərpa» təsdiqi real uğurlu cavabdan gəlir — «onlayn» hadisəsi yazının uğuru deyil.)
        init: function (ctx) {
            window.addEventListener("offline", function () {
                if (ctx.syncStatusKind !== "conflict" && ctx.syncStatusKind !== "secondTab") {
                    ns.syncStatus.show(ctx, "offline");
                }
            });
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
