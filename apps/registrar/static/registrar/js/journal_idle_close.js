/* Hərəkətsiz jurnalın bağlanması (sahib 2026-10-27: «müəllim açıq jurnalda bir müddət heç nə etməsə jurnal
   bağlansın»). Markup + mətnlər: registrar/partials/_jd_idle_close.html (`[data-jd-idle]`).

   AXIN
   * Klik, yazı, sürüşdürmə, toxunma, siçan hərəkəti — fəaliyyət. `data-minutes` dəqiqə fəaliyyət yoxdursa:
     1) gözləyən xanalar dərhal göndərilir (`EMSJournalAutosave.flush`) və cavab gözlənilir (≤ 15 san.);
     2) jurnal bağlanır: cədvəl gizlənir (`html.jd-idle-locked`), pəncərədə nəticə — hamısı yazılıb və ya
        «bəzi xanalar brauzerdə qaralama kimi qalıb» (journal_grid.js qaralaması; «Davam et» onu bərpa edir).
   * «Davam et» — səhifə TƏZƏ məlumatla yenidən açılır (başqa cihazda / RİM-in etdiyi dəyişikliklər görünür).
   * Kompüter yuxudan oyananda taymer gecikir — oyanan kimi yoxlanılır (boşluq da hərəkətsizlik sayılır).
   Heç bir məlumat səssizcə itmir: avtomatik yadda saxlama uğursuz olsa belə qaralama brauzerdə qalır.
   CSP/AJAX-safe: inline yoxdur; sənəd/pəncərə dinləyiciləri `EMSReady.once` ilə BİR dəfə qoşulur. */
(function () {
    "use strict";

    var ROOT = "[data-jd-idle]";
    var FORM = "form[data-jd-autosave]";
    var CHECK_MS = 15000;
    var FLUSH_WAIT_MS = 15000;
    var state = { last: Date.now(), closed: false };

    function root() {
        return document.querySelector(ROOT);
    }

    function idleMs() {
        var el = root();
        var minutes = el ? parseInt(el.getAttribute("data-minutes") || "0", 10) : 0;
        return minutes > 0 ? minutes * 60000 : 0;
    }

    function touch() {
        if (!state.closed) state.last = Date.now();
    }

    function forms() {
        return Array.prototype.slice.call(document.querySelectorAll(FORM));
    }

    function pending() {
        var api = window.EMSJournalAutosave;
        if (!api) return { busy: false, unsaved: 0 };
        var busy = false;
        var unsaved = 0;
        forms().forEach(function (form) {
            if (typeof api.busy === "function" && api.busy(form)) busy = true;
            if (typeof api.changed === "function") unsaved += api.changed(form, api.state(form)).length;
        });
        return { busy: busy, unsaved: unsaved };
    }

    function setStatus(key) {
        var el = root();
        var out = el && el.querySelector("[data-jd-idle-status]");
        if (out) out.textContent = el.getAttribute("data-msg-" + key) || "";
    }

    function settle(deadline, done) {
        var now = pending();
        if (!now.busy || Date.now() >= deadline) {
            done(pending());
            return;
        }
        window.setTimeout(function () {
            settle(deadline, done);
        }, 300);
    }

    function close() {
        var el = root();
        if (!el || state.closed) return;
        state.closed = true;
        // Açıq dərs modalı / dialoqlar arxada qalmasın — jurnal bütövlükdə bağlanır.
        el.hidden = false;
        document.documentElement.classList.add("jd-idle-locked");
        setStatus("saving");
        var api = window.EMSJournalAutosave;
        if (api && typeof api.flush === "function") {
            forms().forEach(function (form) {
                var st = api.state(form);
                st.stopped = false; // dayanmış autosave da son dəfə cəhd etsin
                api.flush(form);
            });
        }
        settle(Date.now() + FLUSH_WAIT_MS, function (result) {
            setStatus(result.unsaved > 0 || result.busy ? "unsaved" : "saved");
            if (result.unsaved === 0 && !result.busy && window.EMSJournalGrid && typeof window.EMSJournalGrid.clearDraft === "function") {
                window.EMSJournalGrid.clearDraft();
            }
            var resume = el.querySelector("[data-jd-idle-resume]");
            if (resume && typeof resume.focus === "function") resume.focus({ preventScroll: true });
        });
    }

    function check() {
        var ms = idleMs();
        if (!ms || state.closed) return;
        if (Date.now() - state.last >= ms) close();
    }

    function wire() {
        ["pointerdown", "keydown", "input", "change", "wheel", "touchstart", "scroll"].forEach(function (type) {
            document.addEventListener(type, touch, { capture: true, passive: true });
        });
        var lastMove = 0;
        document.addEventListener(
            "mousemove",
            function () {
                var now = Date.now();
                if (now - lastMove > 2000) {
                    lastMove = now;
                    touch();
                }
            },
            { passive: true }
        );
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "visible") check();
        });
        window.setInterval(check, CHECK_MS);
        window.EMSDelegate.on("click", "[data-jd-idle-resume]", function () {
            window.location.reload();
        });
    }

    if (!window.EMSReady || !window.EMSDelegate) return;
    window.EMSReady(function () {
        if (!root()) return;
        if (window.EMSReady.once) window.EMSReady.once("journal-idle-close", wire);
        else wire();
    });
})();
