(function (ns, window) {
    "use strict";

    // 2026-10-21: tabın autosave «writer» kimliyi (bax apps/exams/views/student/_autosave_writer.py).
    // Hər POST `autosave_writer` (tab id) + artan `autosave_seq` daşıyır. Server base revision geridə
    // olan yazını aradakı bütün yazılar BU tabındırsa qəbul edir — tək tab öz yazısı ilə konfliktə
    // düşmür (fonda autosave + «Qaralama saxla»/«Bitir», cavabı itən autosave, yazı yolda ikən reload).
    //
    // Kimlik sessionStorage-dədir (yenilənmədən sonra eyni tab eyni qalır). «Tabı dublikat et»
    // sessionStorage-i KOPYALAYIR — ona görə yeni səhifə BroadcastChannel ilə «bu id kimindir?»
    // soruşur; canlı sahib cavab verirsə yeni səhifə öz id-sini yaradır (həqiqi ikinci tab
    // başqa writer olur və OCC onu qoruyur).
    //
    // 2026-10-21 (sahib): ZAL (final/midterm) imtahanında eyni brauzerin HƏQİQİ ikinci tabı tam
    // bloklanır: yeni səhifə «hello» göndərir, köhnə AKTİV səhifə «present» cavabı verir → yeni tab
    // heç nə yazmır (resync.blockSecondTab), birinci tab adi qaydada davam edir. Bloklu tab cavab
    // vermir — o yenilənəndə (birinci tab bağlanıbsa) normal işləyir. Eyni anda açılan iki tabda
    // daha əvvəl yüklənən (bərabərlikdə kiçik nonce) qalır.

    function randomId() {
        var bytes = new Uint8Array(12);
        var crypto = window.crypto || window.msCrypto;
        if (crypto && crypto.getRandomValues) {
            crypto.getRandomValues(bytes);
        } else {
            for (var i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
        }
        return Array.prototype.map.call(bytes, function (b) {
            return ("0" + b.toString(16)).slice(-2);
        }).join("");
    }

    function storageKey(ctx) {
        return "exam_" + ctx.examId + "_attempt_" + ctx.attemptId + "_writer";
    }

    function save(ctx) {
        try {
            window.sessionStorage.setItem(storageKey(ctx), JSON.stringify({ id: ctx.writerId, seq: ctx.writerSeq }));
        } catch (error) {
            // Storage olmadan da işləyir (yalnız reload davamlılığı itir).
        }
    }

    function load(ctx) {
        try {
            var raw = JSON.parse(window.sessionStorage.getItem(storageKey(ctx)) || "null");
            if (raw && typeof raw.id === "string" && /^[A-Za-z0-9_-]{8,64}$/.test(raw.id)) {
                return { id: raw.id, seq: Math.max(0, parseInt(raw.seq, 10) || 0) };
            }
        } catch (error) {
            // korlanmış qeyd — yenisi yaradılır
        }
        return null;
    }

    function regenerate(ctx) {
        ctx.writerId = randomId();
        ctx.writerSeq = 0;
        save(ctx);
    }

    function olderThan(ctx, msg) {
        var theirs = Number(msg.loadedAt) || 0;
        if (ctx.writerLoadedAt !== theirs) return ctx.writerLoadedAt < theirs;
        return String(ctx.writerNonce) < String(msg.nonce);
    }

    ns.writer = {
        // Zal imtahanında başqa tabın «present» cavabını qısa gözlə ki, ikinci tab ilk sual taymerini də
        // başlatmasın (naviqasiya init-i bundan sonra). Kanal yoxdursa dərhal.
        settled: function (ctx, waitMs) {
            if (!ctx.isCenterExam || !ctx.writerChannel) return Promise.resolve();
            return new Promise(function (resolve) {
                window.setTimeout(resolve, waitMs === undefined ? 150 : waitMs);
            });
        },

        init: function (ctx) {
            var stored = load(ctx);
            if (stored) {
                ctx.writerId = stored.id;
                ctx.writerSeq = stored.seq;
            } else {
                regenerate(ctx);
            }
            ctx.writerNonce = randomId();
            ctx.writerLoadedAt = Date.now();
            if (typeof window.BroadcastChannel !== "function") {
                return;
            }
            var channel;
            try {
                channel = new window.BroadcastChannel("ems-take-exam-" + ctx.attemptId);
            } catch (error) {
                return;
            }
            ctx.writerChannel = channel;
            channel.onmessage = function (event) {
                var msg = event && event.data;
                if (!msg || msg.nonce === ctx.writerNonce) return;
                if (msg.type === "hello") {
                    if (msg.id === ctx.writerId) {
                        // Bizim id-ni başqa (dublikat) səhifə iddia edir — o, yenisini yaratsın.
                        channel.postMessage({ type: "taken", id: msg.id, to: msg.nonce, nonce: ctx.writerNonce });
                    }
                    if (ctx.isCenterExam && !ctx.secondTabBlocked && olderThan(ctx, msg)) {
                        channel.postMessage({ type: "present", to: msg.nonce, nonce: ctx.writerNonce });
                    }
                } else if (msg.type === "taken" && msg.to === ctx.writerNonce && msg.id === ctx.writerId) {
                    regenerate(ctx);
                } else if (msg.type === "present" && msg.to === ctx.writerNonce && ctx.isCenterExam) {
                    if (ns.resync && ns.resync.blockSecondTab) ns.resync.blockSecondTab(ctx);
                }
            };
            channel.postMessage({
                type: "hello",
                id: ctx.writerId,
                nonce: ctx.writerNonce,
                loadedAt: ctx.writerLoadedAt
            });
        },

        // Hər POST-a: tab id + növbəti seq (seq əvvəlcə saxlanır — reload-dan sonra geri qayıtmır).
        stamp: function (ctx, formData) {
            if (!ctx.writerId) return;
            ctx.writerSeq = (ctx.writerSeq || 0) + 1;
            save(ctx);
            formData.set("autosave_writer", ctx.writerId);
            formData.set("autosave_seq", String(ctx.writerSeq));
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window);
