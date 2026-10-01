/* proctor_signals.js — imtahan səhifəsinin EVRİSTİK anti-cheat qatı (2026-10-01, PROC).
 *
 * Sahib: «tələbənin extension qoşa bilmə ehtimalı … hər cür cheat-ə qarşı öncəm olsun».
 * Veb səhifə brauzer genişlənməsini TAM bağlaya bilməz (content script-lər ayrı
 * «isolated world»-də işləyir). Ona görə məqsəd: fırıldağı ÇƏTİN və GÖRÜNƏN etmək.
 *
 *   • genişlənmə / süni intellekt köməkçisi izləri (DOM-a əlavə olunan element,
 *     iframe, chrome-extension:// resursları, məlum AI-köməkçi adları);
 *   • DevTools evristikası (pəncərə ölçü fərqi + `debugger` gecikməsi) — «ehtimal»;
 *   • əlavə monitor (`screen.isExtended`), avtomatlaşdırılmış brauzer (`webdriver`);
 *   • mətn inyeksiyası: yapışdırma/sürükləmə, bir anda böyük mətn, skriptlə
 *     (isTrusted=false) dəyişiklik, qeyri-adi sürətli yazı;
 *   • çap cəhdi; Mac/Firefox DevTools qısayolları (mövcud modul yalnız Win/Linux-u tuturdu);
 *   • HEARTBEAT — skriptin canlı olduğunu serverə bildirir (kəsilsə monitorda görünür).
 *
 * Siqnallar YALNIZ qeyd edilir (server `ProctoringLog`, ciddiliyi server təyin edir) —
 * tələbəni kilidləmir. Mövcud ES modul (`exam_supervision/*.js`) toxunulmazdır; bu
 * KLASSİK skript onunla paralel işləyir və heç bir xətası imtahanı dayandırmır.
 * Konfiq: #proctor-signals-config (data-*), #supervision-config-data (JSON),
 * #supervision-bootstrap (incident URL / CSRF). */
(function () {
    "use strict";

    if (window.EMSProctorSignals && window.EMSProctorSignals._booted) return;

    var AI_TOKENS = [
        "grammarly", "monica", "sider", "maxai", "chatgpt", "openai", "gpt", "merlin", "quillbot",
        "harpa", "wordtune", "perplexity", "copilot", "gemini", "claude", "deepseek", "chatbot", "aitopia"
    ];
    var OWN_PREFIX = /^(supervision|exam|ems|proctor|confirm|modal|toast|notification|auto-save|route|tooltip|popover|dropdown|bootstrap|bs-|select|katex|coding|paint|cm-|codemirror|skeleton|question|file|sr-only|visually-hidden|u-|fxc|ew-|swal|flatpickr|choices|ui-|global-search|view-as|page-)/i;
    var EXT_URL = /^(chrome|moz|safari-web|ms-browser|edge)-extension:\/\//i;
    var PASTE_TYPES = { insertFromPaste: 1, insertFromPasteAsQuotation: 1, insertFromDrop: 1, insertFromYank: 1 };
    var BULK_CHARS = 25;
    var FAST_WINDOW_MS = 10000;
    var FAST_CHARS = 150;
    var DEVTOOLS_W = 200;
    var DEVTOOLS_H = 250;
    var KIND_CAP = 6;
    var DOM_CAP = 12;

    var api = {
        _booted: true,
        _started: false,
        cfg: null,
        sent: [],
        _sigs: {},
        _kindCount: {},
        _domCount: 0,
        _timers: [],
        _observer: null,
        _devtoolsSuspected: false,
        _fast: typeof WeakMap === "function" ? new WeakMap() : null
    };

    function safe(fn) {
        return function () {
            try { return fn.apply(this, arguments); } catch (err) { return undefined; }
        };
    }

    function flag(value) { return value === "1" || value === "true" || value === true; }

    function readConfig() {
        var el = document.getElementById("proctor-signals-config");
        if (!el) return null;
        var boot = document.getElementById("supervision-bootstrap");
        var sup = {};
        var supEl = document.getElementById("supervision-config-data");
        if (supEl) {
            try { sup = JSON.parse(supEl.textContent) || {}; } catch (err) { sup = {}; }
        }
        var d = el.dataset;
        return {
            supervised: flag(d.supervised),
            attemptId: d.attemptId,
            signalUrl: d.signalUrl || "",
            heartbeatUrl: d.heartbeatUrl || "",
            logUrl: (boot && boot.dataset.logEndpoint) || d.logUrl || "",
            csrf: (boot && boot.dataset.csrfToken) || "",
            heartbeatMs: Math.max(5, parseInt(d.heartbeatInterval || "30", 10) || 30) * 1000,
            devtoolsMs: Math.max(1, parseInt(d.devtoolsInterval || "5", 10) || 5) * 1000,
            antiAi: flag(d.antiAi),
            detectDevtools: flag(d.detectDevtools),
            detectMultiMonitor: flag(d.detectMultiMonitor),
            detectTextInjection: flag(d.detectTextInjection),
            blockCopyPaste: !!sup.block_copy_paste,
            restrictShortcuts: !!sup.restrict_keyboard_shortcuts
        };
    }

    function csrfToken() {
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (m) return decodeURIComponent(m[1]);
        return (api.cfg && api.cfg.csrf) || "";
    }

    function post(url, body) {
        if (!url || typeof window.fetch !== "function") return null;
        try {
            return window.fetch(url, {
                method: "POST",
                credentials: "same-origin",
                keepalive: true,
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest"
                },
                body: JSON.stringify(body)
            }).catch(function () { return null; });
        } catch (err) {
            return null;
        }
    }

    /** Siqnal göndər (imza üzrə təkrarsız, növ başına tavan). */
    api.signal = safe(function (kind, detail, signature) {
        var sig = kind + "|" + (signature || "");
        if (api._sigs[sig]) return false;
        var count = api._kindCount[kind] || 0;
        if (count >= KIND_CAP) return false;
        api._sigs[sig] = true;
        api._kindCount[kind] = count + 1;
        api.sent.push({ kind: kind, detail: detail || {} });
        post(api.cfg.signalUrl, { kind: kind, detail: detail || {} });
        return true;
    });

    /** Mövcud incident endpoint-i (qayda pozuntusu taksonomiyası). */
    api.incident = safe(function (eventType, metadata) {
        api.sent.push({ incident: eventType, detail: metadata || {} });
        post(api.cfg.logUrl, { event_type: eventType, metadata: metadata || {} });
    });

    // ── Genişlənmə / DOM inyeksiyası ────────────────────────────────────────
    function tokensOf(text) {
        return String(text || "").toLowerCase().split(/[^a-z0-9]+/);
    }

    // Bizim özümüzün qoyduğu «yazı köməkçisini söndür» atributları (hardenField) sayılmır.
    var OWN_ATTRS = { "data-gramm": 1, "data-gramm_editor": 1, "data-enable-grammarly": 1, writingsuggestions: 1 };

    api.aiMatch = function (el) {
        var names = [el.tagName, el.id, typeof el.className === "string" ? el.className : ""];
        if (el.getAttributeNames) {
            names = names.concat(el.getAttributeNames().filter(function (n) { return !OWN_ATTRS[n]; }));
        }
        for (var i = 0; i < names.length; i++) {
            var tokens = tokensOf(names[i]);
            for (var j = 0; j < tokens.length; j++) {
                if (tokens[j] && AI_TOKENS.indexOf(tokens[j]) !== -1) return tokens[j];
            }
        }
        return "";
    };

    function isOwn(el) {
        if (el.hasAttribute && el.hasAttribute("data-proctor-allow")) return true;
        var cls = typeof el.className === "string" ? el.className.trim().split(/\s+/)[0] : "";
        return OWN_PREFIX.test(el.id || "") || OWN_PREFIX.test(cls || "");
    }

    function extUrlOf(el) {
        var attrs = ["src", "href", "data"];
        for (var i = 0; i < attrs.length; i++) {
            var v = el.getAttribute && el.getAttribute(attrs[i]);
            if (v && EXT_URL.test(v)) return v.split("/").slice(0, 3).join("/");
        }
        return "";
    }

    /** Elementi təsnif edir: {kind, sig, detail} və ya null. `initial` — səhifə açılışında
     *  artıq olan elementlər: adi naməlum blok (navbar, footer …) şübhəli SAYILMIR. */
    api.classify = function (el, initial) {
        if (!el || el.nodeType !== 1) return null;
        var tag = String(el.tagName || "").toLowerCase();
        if (tag === "script" && !extUrlOf(el)) return null;
        var ai = api.aiMatch(el);
        if (ai) return { kind: "ai_extension", sig: ai, detail: { token: ai, tag: tag } };
        var ext = extUrlOf(el);
        if (ext) return { kind: "extension_resource", sig: ext, detail: { origin: ext, tag: tag } };
        if ((tag === "iframe" || tag === "frame" || tag === "object" || tag === "embed") && !isOwn(el) &&
            el.id !== "codingPreviewFrame") {
            var src = String(el.getAttribute("src") || "about:blank");
            return { kind: "extension_frame", sig: tag + ":" + src.slice(0, 40), detail: { tag: tag, src: src.slice(0, 120) } };
        }
        var parent = el.parentNode;
        var topLevel = parent === document.body || parent === document.documentElement;
        var html = !el.namespaceURI || el.namespaceURI === "http://www.w3.org/1999/xhtml";
        if (html && tag.indexOf("-") !== -1 && !isOwn(el)) {
            return { kind: "dom_injection", sig: "ce:" + tag, detail: { tag: tag, where: topLevel ? "top" : "inner" } };
        }
        if (!initial && topLevel && tag !== "head" && tag !== "body" && tag !== "style" && tag !== "link" &&
            tag !== "script" && !isOwn(el)) {
            var cls = typeof el.className === "string" ? el.className.trim().split(/\s+/)[0] : "";
            var sig = tag + "#" + (el.id || "").slice(0, 30) + "." + (cls || "").slice(0, 30);
            return { kind: "dom_injection", sig: sig, detail: { tag: tag, id: (el.id || "").slice(0, 60), cls: cls.slice(0, 60), shadow: !!el.shadowRoot } };
        }
        return null;
    };

    api.inspect = safe(function (el, initial) {
        var hit = api.classify(el, initial === true);
        if (!hit) return;
        if (hit.kind === "dom_injection") {
            if (api._domCount >= DOM_CAP) return;
            if (api.signal(hit.kind, hit.detail, hit.sig)) api._domCount += 1;
            return;
        }
        api.signal(hit.kind, hit.detail, hit.sig);
    });

    function inspectTree(root) {
        api.inspect(root);
        if (isEditable(root)) hardenField(root);
        if (!root.querySelectorAll) return;
        var all = root.querySelectorAll("*");
        for (var i = 0; i < all.length && i < 150; i++) {
            api.inspect(all[i]);
            if (isEditable(all[i])) hardenField(all[i]);
        }
    }

    function startDomWatch() {
        var top = Array.prototype.slice.call(document.documentElement.children);
        if (document.body) top = top.concat(Array.prototype.slice.call(document.body.children));
        top.forEach(function (el) { api.inspect(el, true); });
        var named = document.querySelectorAll("[id],[class]");
        for (var i = 0; i < named.length && i < 4000; i++) {
            if (api.aiMatch(named[i])) api.inspect(named[i], true);
        }
        var framed = document.querySelectorAll("iframe, frame, object, embed, [src], [href]");
        for (var k = 0; k < framed.length && k < 2000; k++) api.inspect(framed[k], true);
        if (typeof MutationObserver !== "function") return;
        api._observer = new MutationObserver(safe(function (records) {
            records.forEach(function (rec) {
                Array.prototype.forEach.call(rec.addedNodes || [], function (node) {
                    if (node.nodeType === 1) inspectTree(node);
                });
            });
        }));
        api._observer.observe(document.documentElement, { childList: true, subtree: true });
    }

    // ── Mətn inyeksiyası ────────────────────────────────────────────────────
    function isEditable(t) {
        if (!t || t.nodeType !== 1) return false;
        var tag = t.tagName;
        if (tag === "TEXTAREA") return true;
        if (tag === "INPUT") {
            var type = String(t.type || "text").toLowerCase();
            return type === "text" || type === "search" || type === "number" || type === "";
        }
        return !!t.isContentEditable;
    }

    function fieldName(t) {
        return String(t.name || t.id || t.tagName || "").slice(0, 40);
    }

    function trackFast(t, chars) {
        if (!api._fast) return;
        var now = Date.now();
        var list = (api._fast.get(t) || []).filter(function (e) { return now - e[0] < FAST_WINDOW_MS; });
        list.push([now, chars]);
        api._fast.set(t, list);
        var total = list.reduce(function (sum, e) { return sum + e[1]; }, 0);
        if (total > FAST_CHARS) {
            api.signal("fast_input", { field: fieldName(t), chars: total, seconds: FAST_WINDOW_MS / 1000 },
                fieldName(t) + ":" + Math.floor(now / 60000));
        }
    }

    api.onBeforeInput = safe(function (e) {
        var t = e.target;
        if (!isEditable(t)) return;
        var type = String(e.inputType || "");
        var data = e.data == null ? "" : String(e.data);
        if (!e.isTrusted) {
            api.signal("programmatic_input", { field: fieldName(t), via: "beforeinput", type: type }, "bi:" + fieldName(t));
            if (api.cfg.blockCopyPaste) e.preventDefault();
            return;
        }
        if (PASTE_TYPES[type]) {
            // Müəllim yapışdırmaya icazə veribsə (block_copy_paste söndürülüb) bu, qərardır — siqnal yoxdur.
            if (!api.cfg.blockCopyPaste) return;
            e.preventDefault();
            api.signal("paste_input", { field: fieldName(t), type: type, blocked: true },
                type + ":" + fieldName(t) + ":" + Math.floor(Date.now() / 30000));
            return;
        }
        if ((type === "insertText" || type === "insertReplacementText") && data.length > BULK_CHARS) {
            api.signal("bulk_insert", { field: fieldName(t), type: type, chars: data.length },
                fieldName(t) + ":" + Math.floor(Date.now() / 30000));
            if (api.cfg.blockCopyPaste && type === "insertText") e.preventDefault();
            return;
        }
        if (type === "insertText" && data.length) trackFast(t, data.length);
    });

    api.onInput = safe(function (e) {
        if (e.isTrusted || !isEditable(e.target)) return;
        api.signal("programmatic_input", { field: fieldName(e.target), via: "input" }, "in:" + fieldName(e.target));
    });

    api.onKeyDown = safe(function (e) {
        if (!e.isTrusted && isEditable(e.target)) {
            api.signal("programmatic_input", { field: fieldName(e.target), via: "keydown" }, "kd:" + fieldName(e.target));
        }
        if (!api.cfg.restrictShortcuts) return;
        var code = String(e.code || "");
        var mod = e.metaKey || e.ctrlKey;
        var combo = "";
        // Mac Chrome/Safari: ⌘⌥I/J/C/U — mövcud modul `e.key` ilə baxdığı üçün (⌥ ilə «ˆ» gəlir) tutmurdu.
        if (mod && e.altKey && /^Key[IJCU]$/.test(code)) combo = "mac_devtools";
        // Firefox: Ctrl+Shift+K (konsol) / E (şəbəkə) / M (responsiv rejim).
        else if (e.ctrlKey && e.shiftKey && /^Key[KEM]$/.test(code)) combo = "firefox_devtools";
        if (!combo) return;
        e.preventDefault();
        e.stopPropagation();
        api.incident("keyboard_shortcut", { code: code, combo: combo, meta: !!e.metaKey, alt: !!e.altKey });
    });

    function blockOutsideEditable(e) {
        var t = e.target && e.target.nodeType === 1 ? e.target : (e.target && e.target.parentElement);
        if (!t || isEditable(t) || (t.closest && t.closest(".CodeMirror"))) return;
        if (e.type === "drop") {
            // Fayl yükləmə zonası (yazılı cavab) və OS-dan fayl sürükləmə toxunulmaz qalır.
            var types = e.dataTransfer && e.dataTransfer.types ? Array.prototype.slice.call(e.dataTransfer.types) : [];
            if (types.indexOf("Files") !== -1 || (t.closest && t.closest("[data-exam-dropzone-qid]"))) return;
        }
        e.preventDefault();
    }

    function hardenField(f) {
        // Grammarly və s. yazı köməkçiləri bu atributlara hörmət edir; brauzerin
        // «yazmağa kömək et» təklifləri də `writingsuggestions=false` ilə söndürülür.
        if (f.getAttribute("data-gramm") === "false") return;
        f.setAttribute("data-gramm", "false");
        f.setAttribute("data-gramm_editor", "false");
        f.setAttribute("data-enable-grammarly", "false");
        f.setAttribute("writingsuggestions", "false");
    }

    function hardenFields() {
        var fields = document.querySelectorAll("textarea, input[type=text], [contenteditable=true]");
        for (var i = 0; i < fields.length; i++) hardenField(fields[i]);
    }

    // ── DevTools / monitor / avtomatlaşdırma ────────────────────────────────
    var baseline = null;
    api.checkDevtoolsSize = safe(function () {
        var dpr = window.devicePixelRatio || 1;
        var dw = (window.outerWidth || 0) - (window.innerWidth || 0);
        var dh = (window.outerHeight || 0) - (window.innerHeight || 0);
        if (!window.outerWidth || !window.outerHeight) return false;
        if (!baseline || baseline.dpr !== dpr) {
            baseline = { dpr: dpr, dw: dw, dh: dh, hits: 0 };
            return false;
        }
        var open = dw - baseline.dw > DEVTOOLS_W || dh - baseline.dh > DEVTOOLS_H;
        baseline.hits = open ? baseline.hits + 1 : 0;
        if (baseline.hits >= 2) {
            api._devtoolsSuspected = true;
            api.signal("devtools_open", { method: "size", dw: dw - baseline.dw, dh: dh - baseline.dh },
                "size:" + Math.floor(Date.now() / 300000));
            return true;
        }
        return false;
    });

    api.checkDevtoolsTiming = safe(function () {
        var t0 = (window.performance && performance.now()) || Date.now();
        // DevTools açıqdırsa icra burada dayanır (fasilə) — gecikmə ölçülür. Bağlıdırsa no-op.
        // eslint-disable-next-line no-debugger
        debugger;
        var dt = ((window.performance && performance.now()) || Date.now()) - t0;
        if (dt > 150) {
            api._devtoolsSuspected = true;
            api.signal("devtools_open", { method: "debugger", ms: Math.round(dt) }, "dbg:" + Math.floor(Date.now() / 300000));
            return true;
        }
        return false;
    });

    function screenExtended() {
        return window.screen && typeof window.screen.isExtended === "boolean" ? window.screen.isExtended : null;
    }

    api.checkScreens = safe(function () {
        if (screenExtended() === true) api.signal("multi_monitor", { extended: true }, "ext");
    });

    // ── Heartbeat ───────────────────────────────────────────────────────────
    api.heartbeatState = function () {
        var state = {
            fs: !!(document.fullscreenElement || document.webkitFullscreenElement),
            vis: document.visibilityState !== "hidden",
            foc: typeof document.hasFocus === "function" ? document.hasFocus() : true,
            dt: !!api._devtoolsSuspected,
            w: Math.round(window.innerWidth || 0),
            h: Math.round(window.innerHeight || 0)
        };
        var ext = screenExtended();
        if (ext !== null) state.ext = ext;
        return state;
    };

    api.beat = safe(function () {
        var req = post(api.cfg.heartbeatUrl, { state: api.heartbeatState() });
        if (req && typeof req.then === "function") {
            req.then(function (resp) {
                if (resp && resp.status === 409) api.stop();
            });
        }
    });

    function every(ms, fn) {
        api._timers.push(window.setInterval(fn, ms));
    }

    api.start = safe(function (cfg) {
        if (api._started) return;
        api.cfg = cfg || readConfig();
        if (!api.cfg || !api.cfg.supervised) return;
        api._started = true;
        var root = document.documentElement;
        root.classList.add("proctor-on");
        if (api.cfg.antiAi) root.classList.add("proctor-guard");

        document.addEventListener("keydown", api.onKeyDown, true);
        // Başlıqdakı kimlik şəkli yüklənməsə baş hərflər görünsün (inline onerror yox — CSP).
        document.addEventListener("error", function (evt) {
            var img = evt.target;
            if (!img || img.tagName !== "IMG" || !img.classList.contains("proctor-id__img")) return;
            if (img.parentNode) img.parentNode.classList.remove("proctor-id__ava--photo");
            img.remove();
        }, true);
        window.addEventListener("beforeprint", safe(function () {
            api.signal("print_attempt", {}, "print:" + Math.floor(Date.now() / 60000));
        }));
        if (api.cfg.detectTextInjection) {
            document.addEventListener("beforeinput", api.onBeforeInput, true);
            document.addEventListener("input", api.onInput, true);
        }
        if (api.cfg.antiAi) {
            hardenFields();
            document.addEventListener("selectstart", blockOutsideEditable, true);
            document.addEventListener("dragstart", blockOutsideEditable, true);
            document.addEventListener("drop", blockOutsideEditable, true);
            startDomWatch();
        }
        if (navigator.webdriver === true) api.signal("automation", { webdriver: true }, "webdriver");
        if (api.cfg.detectMultiMonitor) {
            api.checkScreens();
            if (window.screen && typeof window.screen.addEventListener === "function") {
                window.screen.addEventListener("change", api.checkScreens);
            }
        }
        if (api.cfg.detectDevtools) {
            api.checkDevtoolsSize();
            every(3000, api.checkDevtoolsSize);
            every(api.cfg.devtoolsMs, api.checkDevtoolsTiming);
        }
        if (api.cfg.heartbeatUrl) {
            window.setTimeout(api.beat, 1500);
            every(api.cfg.heartbeatMs, api.beat);
            document.addEventListener("visibilitychange", function () {
                if (document.visibilityState === "visible") api.beat();
            });
        }
    });

    api.stop = function () {
        api._timers.forEach(function (id) { window.clearInterval(id); });
        api._timers = [];
        if (api._observer) api._observer.disconnect();
        api._observer = null;
    };

    window.EMSProctorSignals = api;

    function boot() { api.start(); }
    if (typeof window.EMSReady === "function") {
        window.EMSReady(boot);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
