/* Jurnalın AVTOMATİK yadda saxlanması (sahib 2026-10-14: «yadda saxla click etməyi unudulsa da
   avtomatik yadda saxlanılsın»). Davamiyyət/bal grid-i (`action=save_marks`) və Midterm/kollokvium
   formu — `form[data-jd-autosave]`.

   AXIN
   * Xananın seçimi dəyişəndə (`change`) ~800 ms gözlənilir (toplu «Hamısına i/e» onlarla `change`
     göndərir — hamısı BİR sorğuya yığılır), sonra YALNIZ dəyişən xanalar göndərilir.
   * Dərhal göndərmə: forma fokusu itirəndə, vərəq gizlənəndə (`visibilitychange`), səhifə
     bağlananda (`pagehide` / `beforeunload` → `navigator.sendBeacon`, yoxdursa `keepalive` fetch).
   * Eyni anda YALNIZ BİR sorğu; uçuşda gələn dəyişiklik cavabdan sonra ayrıca gedir. Şəbəkə / 5xx
     xətasında geri çəkilmə ilə təkrar (2 → 4 → … ≤ 30 san.); 4xx (kilid, pəncərə, icazə, sessiya)
     təkrar edilmir — mətn göstərilir, «Yenidən cəhd et» düyməsi qalır.
   * «Dəyişən xana» — `select`-in cari dəyəri son TƏSDİQLƏNMİŞ dəyərdən fərqlidir (ilkin dəyər =
     serverin render etdiyi `option[selected]`; brauzer qaralamasından bərpa olunan xana da dəyişmiş
     sayılır və yadda saxlanılır). Göndərilən — həmin xananın adlı sahələri (`att__/score__` gizli
     sahələri və ya `kscore__` select-i), üstəlik CSRF + `action` + `autosave=1`.

   SERVER həlledicidir: ünvan və qaydalar «Yadda saxla» ilə EYNİDİR (apps/registrar/journal_autosave.py);
   cavab JSON-dur. Dublikat yoxdur — xana (dərs, qeydiyyat) üzrə unikaldır, təkrar göndəriş eyni dəyəri
   yazır. «Yadda saxla» düyməsi ehtiyat yol kimi işləyir. Uğurdan sonra brauzer qaralaması silinir
   (`EMSJournalGrid.clearDraft`, journal_grid.js).
   CSP/AJAX-safe: inline yoxdur; mətnlər `[data-jd-autosave-status]` data-atributlarındadır;
   hadisələr `EMSDelegate.on` / `EMSReady.once` ilə BİR dəfə qoşulur. */
(function () {
    "use strict";

    var FORM = "form[data-jd-autosave]";
    var CONTROL = "select[data-jd-semselect], select[data-jd-kscore]";
    var DEBOUNCE_MS = 800;
    var MAX_BACKOFF_MS = 30000;
    var states = new WeakMap();

    function grid() {
        return window.EMSJournalGrid || {};
    }

    function state(form) {
        var st = states.get(form);
        if (!st) {
            st = { saved: new WeakMap(), timer: 0, retryTimer: 0, inflight: false, attempts: 0, stopped: false };
            states.set(form, st);
        }
        return st;
    }

    function serverValue(select) {
        for (var i = 0; i < select.options.length; i += 1) {
            if (select.options[i].defaultSelected) return select.options[i].value;
        }
        return select.options.length ? select.options[0].value : "";
    }

    function confirmed(st, select) {
        return st.saved.has(select) ? st.saved.get(select) : serverValue(select);
    }

    function changed(form, st) {
        return Array.prototype.filter.call(form.querySelectorAll(CONTROL), function (select) {
            return !select.disabled && select.value !== confirmed(st, select);
        });
    }

    function payload(form, controls) {
        var body = new FormData();
        var token = form.querySelector("input[name='csrfmiddlewaretoken']");
        var action = form.querySelector("input[name='action']");
        if (token) body.append("csrfmiddlewaretoken", token.value);
        if (action) body.append("action", action.value);
        body.append("autosave", "1");
        controls.forEach(function (select) {
            var cell = select.closest("td") || select.parentElement;
            cell.querySelectorAll("input[name], select[name]").forEach(function (field) {
                body.append(field.name, field.value);
            });
        });
        return body;
    }

    // ── Vəziyyət mətni ────────────────────────────────────────────────────
    function status(form, kind, text) {
        var el = form.querySelector("[data-jd-autosave-status]");
        var retry = form.querySelector("[data-jd-autosave-retry]");
        if (retry) retry.hidden = kind !== "error";
        if (!el) return;
        var msg = text || el.getAttribute("data-msg-" + kind) || "";
        if (kind === "saved") {
            var now = new Date();
            msg += " · " + ("0" + now.getHours()).slice(-2) + ":" + ("0" + now.getMinutes()).slice(-2);
        }
        el.textContent = msg;
        el.classList.toggle("is-saving", kind === "saving");
        el.classList.toggle("is-saved", kind === "saved");
        el.classList.toggle("is-warning", kind === "partial");
        el.classList.toggle("is-error", kind === "error" || kind === "retrying");
    }

    function message(form, key) {
        var el = form.querySelector("[data-jd-autosave-status]");
        return (el && el.getAttribute("data-msg-" + key)) || "";
    }

    // ── Göndəriş ──────────────────────────────────────────────────────────
    function schedule(form) {
        var st = state(form);
        if (st.stopped) return;
        window.clearTimeout(st.timer);
        st.timer = window.setTimeout(function () {
            flush(form);
        }, DEBOUNCE_MS);
        if (!st.inflight) status(form, "saving");
    }

    function settleClean(form, st) {
        if (!changed(form, st).length && typeof grid().clearDraft === "function") grid().clearDraft();
    }

    function flush(form) {
        var st = state(form);
        window.clearTimeout(st.timer);
        st.timer = 0;
        if (st.inflight || st.stopped || !document.contains(form)) return;
        var controls = changed(form, st);
        if (!controls.length) {
            settleClean(form, st);
            return;
        }
        var sentValues = controls.map(function (select) {
            return [select, select.value];
        });
        var url = form.getAttribute("data-jd-autosave-url") || form.action;
        st.inflight = true;
        status(form, "saving");
        window.EMSCore.fetchJSON(url, { method: "POST", body: payload(form, controls) })
            .then(function (data) {
                if (!data || typeof data !== "object" || data.ok !== true) {
                    var bad = new Error("autosave: unexpected response");
                    bad.status = 400;
                    throw bad;
                }
                st.inflight = false;
                st.attempts = 0;
                sentValues.forEach(function (pair) {
                    st.saved.set(pair[0], pair[1]);
                });
                var lost = (data.skipped || 0) + (data.rejected || 0);
                if (lost > 0) status(form, "partial", message(form, "partial").replace("{n}", String(lost)));
                else status(form, "saved");
                if (changed(form, st).length) schedule(form);
                else settleClean(form, st);
            })
            .catch(function (err) {
                st.inflight = false;
                var code = err && err.status ? err.status : 0;
                if (code >= 400 && code < 500 && code !== 408 && code !== 429) {
                    // Kilid / bağlı pəncərə / icazə / sessiya — təkrar kömək etməz; qaralama brauzerdə qalır.
                    st.stopped = true;
                    var text = err.payload && typeof err.payload === "object" ? err.payload.message : "";
                    status(form, "error", text || message(form, "failed"));
                    return;
                }
                st.attempts += 1;
                var delay = Math.min(MAX_BACKOFF_MS, 1000 * Math.pow(2, st.attempts));
                window.clearTimeout(st.retryTimer);
                st.retryTimer = window.setTimeout(function () {
                    flush(form);
                }, delay);
                status(form, "retrying");
                var retry = form.querySelector("[data-jd-autosave-retry]");
                if (retry) retry.hidden = false;
            });
    }

    // Səhifə bağlanır: cavab gözlənilmir — `sendBeacon` (yoxdursa `keepalive` fetch). Uçuşdakı xanalar da
    // daxildir (təkrar yazı eyni dəyəridir). İkinci hadisə (beforeunload → pagehide) təkrar göndərməsin
    // deyə göndərilənlər təsdiqlənmiş sayılır.
    function beacon(form) {
        var st = state(form);
        window.clearTimeout(st.timer);
        if (st.stopped) return;
        var controls = changed(form, st);
        if (!controls.length) return;
        var url = form.getAttribute("data-jd-autosave-url") || form.action;
        var body = payload(form, controls);
        var sent = false;
        try {
            sent = !!(navigator.sendBeacon && navigator.sendBeacon(url, body));
        } catch (e) {
            sent = false;
        }
        if (!sent && window.fetch) {
            try {
                window.fetch(url, { method: "POST", body: body, credentials: "same-origin", keepalive: true });
                sent = true;
            } catch (e) {
                sent = false;
            }
        }
        if (sent) {
            controls.forEach(function (select) {
                st.saved.set(select, select.value);
            });
        }
    }

    function eachForm(fn) {
        Array.prototype.forEach.call(document.querySelectorAll(FORM), fn);
    }

    if (!window.EMSDelegate || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") return;

    window.EMSDelegate.on("change", FORM + " select", function (event, select) {
        if (!select.matches(CONTROL)) return;
        var form = select.closest(FORM);
        if (form) schedule(form);
    });

    window.EMSDelegate.on("focusout", FORM, function (event, form) {
        var next = event.relatedTarget;
        if (next && form.contains(next)) return;
        if (state(form).timer) flush(form);
    });

    window.EMSDelegate.on("click", "[data-jd-autosave-retry]", function (event, button) {
        var form = button.closest(FORM);
        if (!form) return;
        var st = state(form);
        st.stopped = false;
        st.attempts = 0;
        window.clearTimeout(st.retryTimer);
        flush(form);
    });

    // «Yadda saxla» (tam POST) — gözləyən avtomatik göndəriş ləğv olunur, forma hər şeyi özü aparır.
    window.EMSDelegate.on("submit", FORM, function (event, form) {
        if (event.defaultPrevented) return;
        var st = state(form);
        window.clearTimeout(st.timer);
        window.clearTimeout(st.retryTimer);
        st.stopped = true;
    });

    function init() {
        eachForm(function (form) {
            // Brauzer qaralamasından bərpa olunmuş (əvvəl yadda saxlanılmamış) xanalar da yazılsın.
            if (changed(form, state(form)).length) schedule(form);
        });
    }

    if (window.EMSReady) {
        window.EMSReady(init);
        var wire = function () {
            document.addEventListener("visibilitychange", function () {
                if (document.visibilityState === "hidden") eachForm(flush);
            });
            window.addEventListener("pagehide", function () {
                eachForm(beacon);
            });
            window.addEventListener("beforeunload", function () {
                eachForm(beacon);
            });
        };
        if (window.EMSReady.once) window.EMSReady.once("journal-grid-autosave", wire);
        else wire();
    }

    window.EMSJournalAutosave = { flush: flush, changed: changed, state: state };
})();
