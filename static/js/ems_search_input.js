/* ═══════════════════════════════════════════════════════════════════════════
   EMSSearchInput — yazdıqca axtarışın VAHİD qatı (sahib 2026-10-14: «bütün
   search-lərdə debounce düzgün işləmir, çox sürətli olur; yazmağa başlayarkən
   search gedir, render olur və axtardığım itir»).

   QAYDALAR (hər server axtarışı üçün eyni)
     • istifadəçi yazmağı DAYANDIRANDAN 1500 ms sonra (EMS_SEARCH_DEBOUNCE_MS)
       sorğu gedir — sahib: «0.5 saniyə azdır, 1500 ms edək»;
     • server axtarışı ən azı 2 simvoldan (MIN_CHARS); 1 simvolda heç nə
       getmir (köhnə nəticə qalır), sahə BOŞALANDA isə dərhal sıfırlanır;
     • Enter — gözləmədən dərhal (simvol sayından asılı olmayaraq);
     • IME (compositionstart … compositionend) bitənə qədər sorğu yoxdur;
     • dəyər dəyişməyibsə (ox, Shift, eyni mətni geri yazmaq) sorğu yoxdur;
     • köhnə yavaş cavab yeni nəticənin üstünə yazılmır — `latest()`;
     • nəticə yenilənəndə input-un özü əvəzlənmir — `morph()` fokuslu sahəni
       və onun valideyn zəncirini SAXLAYIR, ətrafdakı hər şeyi yeniləyir;
       tam əvəzləmə qaçılmazdırsa `snapshot()`/`restore()` fokus + dəyər +
       kursoru qaytarır;
     • «Axtarılır…» — input-un altında kiçik nişan (`busy()`), panel yanıb-
       sönmür.

   API
     EMSSearchInput.bind(input, opts)       — element üçün (dinləyici elementə
                                              yox, document-ə bağlıdır → təkrar
                                              çağırış yığılmır, AJAX-safe);
     EMSSearchInput.delegate(selector, opts) — gələcək (AJAX ilə gələn) bütün
                                              uyğun input-lar üçün;
        opts.onSearch(value, meta)  — məcburi; meta = {input, reason:
                                       "typing" | "enter" | "clear"}
        opts.delay (1500) · opts.minChars (2; klient süzgəci üçün 0/1)
        opts.trim (true) · opts.enter (true) · opts.allowEmpty (true)
        opts.fallback (false) — ümumi qayda; xüsusi qeydiyyat ona üstün gəlir
     EMSSearchInput.cancel(input) / flush(input) / sync(input[, value])
     EMSSearchInput.latest()  → {begin() → {id, signal, current()}, cancel()}
     EMSSearchInput.busy(input, on)
     EMSSearchInput.debounce(fn, ms) → f (+ f.cancel(), f.flush())
     EMSSearchInput.requeue(input, applied)  — əvəzlənmiş input-u planla
     EMSSearchInput.handles(input) / clear(input) — × düymələri üçün
   Swap qatı (snapshot/restore/morph/submitForm): static/js/ems_search_swap.js.
   Asılılıq yoxdur; <head>-də yüklənir; təkrar yüklənsə mövcud obyekt qalır.
   ═══════════════════════════════════════════════════════════════════════════ */
(function (root, document) {
    "use strict";
    if (root.EMSSearchInput && root.EMSSearchInput.__v === 1) {
        return;
    }

    // Sahib 2026-10-14: «0.5 saniyə azdır, 1500 ms edək» — TƏK tənzimləmə nöqtəsi.
    var EMS_SEARCH_DEBOUNCE_MS = 1500;
    var DELAY_MS = EMS_SEARCH_DEBOUNCE_MS;
    var MIN_CHARS = 2;
    var TEXT_TYPES = { text: 1, search: 1, email: 1, tel: 1, url: 1, "": 1 };

    var bound = new WeakMap(); // input → opts (bind)
    var states = new WeakMap(); // input → {timer, composing, last}
    var delegated = []; // [{selector, opts}]

    function t(text) {
        return typeof root.pgettext === "function" ? root.pgettext("ui.search", text) : text;
    }

    function isTextField(el) {
        if (!el || !el.tagName) {
            return false;
        }
        if (el.tagName === "TEXTAREA") {
            return true;
        }
        return el.tagName === "INPUT" && TEXT_TYPES[(el.getAttribute("type") || "").toLowerCase()] === 1;
    }

    function read(input, opts) {
        var value = input.value == null ? "" : String(input.value);
        return opts.trim === false ? value : value.trim();
    }

    function delayOf(opts) {
        return typeof opts.delay === "number" && opts.delay >= 0 ? opts.delay : DELAY_MS;
    }

    function minOf(opts) {
        return typeof opts.minChars === "number" && opts.minChars >= 0 ? opts.minChars : MIN_CHARS;
    }

    function optsFor(input) {
        var own = bound.get(input);
        if (own) {
            return own;
        }
        if (!input.matches) {
            return null;
        }
        // `fallback: true` (ümumi qayda, məs. debounced_search_forms.js) — yalnız heç
        // bir xüsusi qeydiyyat uyğun gəlmirsə; sıra (skript yüklənməsi) önəmsizdir.
        var spare = null;
        for (var i = 0; i < delegated.length; i += 1) {
            if (input.matches(delegated[i].selector)) {
                if (!delegated[i].opts.fallback) {
                    return delegated[i].opts;
                }
                spare = spare || delegated[i].opts;
            }
        }
        return spare;
    }

    function stateOf(input, opts, initial) {
        var st = states.get(input);
        if (!st) {
            var start = typeof initial === "string" ? initial : input.defaultValue || "";
            st = { timer: null, composing: false, last: opts.trim === false ? start : start.trim() };
            states.set(input, st);
        }
        return st;
    }

    function clearTimer(st) {
        if (st.timer) {
            root.clearTimeout(st.timer);
            st.timer = null;
        }
    }

    function fire(input, opts, st, reason) {
        clearTimer(st);
        var value = read(input, opts);
        if (value === st.last) {
            return false;
        }
        if (!document.documentElement.contains(input)) {
            return false; // AJAX swap bu input-u artıq DOM-dan çıxarıb
        }
        st.last = value;
        try {
            opts.onSearch.call(input, value, { input: input, reason: reason });
        } catch (err) {
            if (root.console && root.console.error) {
                root.console.error("EMSSearchInput onSearch failed:", err);
            }
        }
        return true;
    }

    function schedule(input, opts, st) {
        clearTimer(st);
        var value = read(input, opts);
        if (value === st.last) {
            return; // yazıb geri silib — eyni sorğunu təkrarlamırıq
        }
        if (!value.length) {
            if (opts.allowEmpty !== false) {
                fire(input, opts, st, "clear");
            }
            return;
        }
        if (value.length < minOf(opts)) {
            return; // 1 simvol: köhnə nəticə qalır, sorğu yoxdur
        }
        st.timer = root.setTimeout(function () {
            st.timer = null;
            fire(input, opts, st, "typing");
        }, delayOf(opts));
    }

    /* ---- document səviyyəli dinləyicilər (capture: komponentin öz
       stopPropagation-ı da bizi susdurmasın) ------------------------------ */
    function onInput(event) {
        var input = event.target;
        if (!isTextField(input)) {
            return;
        }
        var opts = optsFor(input);
        if (!opts) {
            return;
        }
        var st = stateOf(input, opts);
        if (st.composing || event.isComposing) {
            clearTimer(st);
            return;
        }
        schedule(input, opts, st);
    }

    function onKeydown(event) {
        if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) {
            return;
        }
        var input = event.target;
        if (!isTextField(input) || input.tagName === "TEXTAREA") {
            return;
        }
        var opts = optsFor(input);
        if (!opts || opts.enter === false) {
            return;
        }
        var st = stateOf(input, opts);
        if (st.composing || event.isComposing || event.keyCode === 229) {
            return; // IME namizədini təsdiqləyən Enter — axtarış deyil
        }
        event.preventDefault();
        var value = read(input, opts);
        if (value === st.last) {
            clearTimer(st);
            return;
        }
        st.last = null; // Enter minChars-ı keçir — mütləq göndər
        fire(input, opts, st, "enter");
    }

    function onComposition(event) {
        var input = event.target;
        if (!isTextField(input)) {
            return;
        }
        var opts = optsFor(input);
        if (!opts) {
            return;
        }
        var st = stateOf(input, opts);
        if (event.type === "compositionstart") {
            st.composing = true;
            clearTimer(st);
            return;
        }
        st.composing = false;
        schedule(input, opts, st);
    }

    function onFocusin(event) {
        var input = event.target;
        if (!isTextField(input)) {
            return;
        }
        var opts = optsFor(input);
        if (!opts) {
            return;
        }
        var st = stateOf(input, opts, input.value || "");
        // Proqram yolu ilə dəyişdirilmiş dəyər (modal yenidən açıldı, sahə
        // sıfırlandı) «tətbiq olunmuş» sayılır; gözləyən sorğu varsa toxunmuruq.
        if (!st.timer && !st.composing) {
            st.last = read(input, opts);
        }
    }

    document.addEventListener("input", onInput, true);
    document.addEventListener("keydown", onKeydown, true);
    document.addEventListener("compositionstart", onComposition, true);
    document.addEventListener("compositionend", onComposition, true);
    document.addEventListener("focusin", onFocusin, true);

    function normalizeOpts(opts) {
        if (!opts || typeof opts.onSearch !== "function") {
            throw new TypeError("EMSSearchInput: opts.onSearch is required");
        }
        return opts;
    }

    function bind(input, opts) {
        if (!input) {
            return null;
        }
        opts = normalizeOpts(opts);
        bound.set(input, opts);
        stateOf(input, opts, input.value || "");
        return input;
    }

    function delegate(selector, opts) {
        opts = normalizeOpts(opts);
        for (var i = 0; i < delegated.length; i += 1) {
            if (delegated[i].selector === selector) {
                delegated[i].opts = opts; // təkrar qeydiyyat yığılmır
                return;
            }
        }
        delegated.push({ selector: selector, opts: opts });
    }

    function cancel(input) {
        var st = input && states.get(input);
        if (st) {
            clearTimer(st);
        }
    }

    function flush(input) {
        var opts = input && optsFor(input);
        if (!opts) {
            return false;
        }
        return fire(input, opts, stateOf(input, opts), "enter");
    }

    /** Proqram yolu ilə qoyulmuş dəyəri «tətbiq olunmuş» say (sorğu yoxdur). */
    function sync(input, value) {
        var opts = input && optsFor(input);
        if (!opts) {
            return;
        }
        var st = stateOf(input, opts);
        clearTimer(st);
        var raw = typeof value === "string" ? value : input.value || "";
        st.last = opts.trim === false ? raw : raw.trim();
    }

    /* ---- köhnə cavabı at --------------------------------------------- */
    function latest() {
        var seq = 0;
        var ctrl = null;
        function abort() {
            if (ctrl) {
                try {
                    ctrl.abort();
                } catch (err) { /* ignore */ }
            }
            ctrl = null;
        }
        return {
            begin: function () {
                abort();
                seq += 1;
                var mine = seq;
                ctrl = typeof root.AbortController === "function" ? new root.AbortController() : null;
                return {
                    id: mine,
                    signal: ctrl ? ctrl.signal : undefined,
                    current: function () {
                        return mine === seq;
                    },
                };
            },
            cancel: function () {
                abort();
                seq += 1;
            },
        };
    }

    /* ---- «Axtarılır…» nişanı ------------------------------------------ */
    function busy(input, on) {
        if (!input || !input.classList) {
            return;
        }
        input.classList.toggle("is-searching", !!on);
        if (on) {
            input.setAttribute("aria-busy", "true");
        } else {
            input.removeAttribute("aria-busy");
        }
        var host = input.parentNode;
        var badge = host && host.querySelector ? host.querySelector(":scope > .ems-search-status") : null;
        if (!on) {
            if (badge) {
                badge.hidden = true;
            }
            return;
        }
        if (!host || !host.insertBefore) {
            return;
        }
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "ems-search-status";
            badge.setAttribute("role", "status");
            badge.setAttribute("aria-live", "polite");
            host.insertBefore(badge, input.nextSibling);
        }
        badge.textContent = t("Axtarılır…");
        // Layout-u itələmir: input-un sağ-alt küncünə asılır (CSSOM — CSP-safe).
        var positioned = root.getComputedStyle && root.getComputedStyle(host).position !== "static";
        if (positioned) {
            badge.style.top = input.offsetTop + input.offsetHeight + 2 + "px";
            badge.style.right = Math.max(host.clientWidth - (input.offsetLeft + input.offsetWidth), 0) + "px";
            badge.classList.remove("ems-search-status--sr");
        } else {
            badge.classList.add("ems-search-status--sr");
        }
        badge.hidden = false;
    }

    function debounce(fn, ms) {
        var timer = null;
        var lastArgs = null;
        var self = null;
        function run() {
            timer = null;
            var args = lastArgs;
            lastArgs = null;
            return fn.apply(self, args || []);
        }
        function wrapped() {
            self = this;
            lastArgs = arguments;
            if (timer) {
                root.clearTimeout(timer);
            }
            timer = root.setTimeout(run, typeof ms === "number" ? ms : DELAY_MS);
        }
        wrapped.cancel = function () {
            if (timer) {
                root.clearTimeout(timer);
            }
            timer = null;
            lastArgs = null;
        };
        wrapped.flush = function () {
            if (timer) {
                root.clearTimeout(timer);
                return run();
            }
            return undefined;
        };
        return wrapped;
    }

    /** Bu input vahid qayda ilə idarə olunurmu (bind/delegate)? */
    function handles(input) {
        return !!(input && optsFor(input));
    }

    /** Proqram yolu ilə təmizlə (× düyməsi): dəyəri boşaldıb dərhal sıfırlayır. */
    function clear(input) {
        if (!handles(input)) {
            return false;
        }
        input.value = "";
        input.dispatchEvent(new root.Event("input", { bubbles: true }));
        return true;
    }

    /** Yeni (əvəzlənmiş) input üçün: tətbiq olunmuş = `applied`; fərq varsa planla. */
    function requeue(input, applied) {
        var opts = input && optsFor(input);
        if (!opts) {
            return;
        }
        var st = stateOf(input, opts, applied || "");
        st.last = opts.trim === false ? applied || "" : (applied || "").trim();
        schedule(input, opts, st);
    }

    root.EMSSearchInput = {
        __v: 1,
        DELAY_MS: DELAY_MS,
        EMS_SEARCH_DEBOUNCE_MS: EMS_SEARCH_DEBOUNCE_MS,
        MIN_CHARS: MIN_CHARS,
        bind: bind,
        delegate: delegate,
        cancel: cancel,
        flush: flush,
        sync: sync,
        latest: latest,
        busy: busy,
        debounce: debounce,
        isTextField: isTextField,
        requeue: requeue,
        handles: handles,
        clear: clear,
    };
})(window, document);
