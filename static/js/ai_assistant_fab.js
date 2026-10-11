/**
 * AI köməkçi düyməsi — gizlətmək, sürüşdürmək, geri qaytarmaq (sahib 2026-10-10: «AI buttonu
 * gizlətmə, yerini dəyişmək və s. də olsun — bəzən hansısa button üstündə dayana bilir, user
 * onun yerini tutaraq dəyişə bilsin»).
 *
 * Seçim istifadəçinin brauzerində saxlanılır (serverdə fərdi ayar yoxdur): localStorage
 * `ems.aiFab.v1:<user.id>` (şablondan `data-pref-key`) → `{hidden, side, y}`:
 *   side — "left" | "right";  y — düymə MƏRKƏZİNİN ekran hündürlüyünə nisbəti (0..1);
 *   y = null → defolt yer (sağ-alt; yapışqan alt panel ofseti YALNIZ onda).
 *
 *  • sürüşdürmə: pointer hadisələri + setPointerCapture; 6 px-dən az hərəkət adi klikdir;
 *    buraxanda ən yaxın yan kənara yapışır, ekran daxilində sıxılır (kənar boşluq, safe-area,
 *    yapışqan başlıq); ekran ölçüsü dəyişəndə yenidən sıxılır; Escape — ləğv;
 *  • klaviatura (düymə fokusda): Alt+←/→ — tərəf, Alt+↑/↓ — 10 %, Delete — gizlət;
 *    hər hərəkətdən sonra `#ai-fab-live` elan edir;
 *  • gizlədəndə: kənarda «AI köməkçi» nişanı (`#ai-fab-restore`), istifadəçi menyusunda açar
 *    (`[data-ai-fab-toggle]`) və «Geri qaytar» düyməli bildiriş; qaytaranda fokus düyməyə keçir;
 *  • inline style YOX (CSP): yer CSS dəyişənlərinə CSSOM ilə yazılır (`--ai-fab-y`, `--ai-fab-x`,
 *    `--ai-fab-tab-y`) + `#ai-fab` kökündə vəziyyət sinifləri (static/css/ai_assistant.css).
 *
 * Panel/mesaj məntiqi static/js/ai_assistant.js-dədir — o `EMSAiFab.create(...)` çağırır və
 * click-də `handleClick()`-dən soruşur (sürüşdürmənin sonu / «×» paneli açmamalıdır).
 */
(function () {
    "use strict";

    if (window.EMSAiFab) return;

    const DRAG_THRESHOLD = 6; // px — bundan az hərəkət sürüşdürmə deyil, klikdir
    const EDGE_MARGIN = 12; // px — ekran kənarından minimal boşluq
    const KEY_STEP = 0.1; // Alt+↑/↓ — ekran hündürlüyünün 10 %-i
    const CLICK_GUARD_MS = 400; // buraxmanın ardınca gələn click paneli açmasın
    const FALLBACK_SIZE = 56;
    const KEY_MOVES = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };

    function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    /** Saxlanmış dəyər yoxlanılır: tanınmayan forma → defolt (görünür, sağ, defolt hündürlük). */
    function normalize(raw) {
        const src = raw && typeof raw === "object" ? raw : {};
        const y = typeof src.y === "number" && Number.isFinite(src.y) ? clamp(src.y, 0, 1) : null;
        return {
            hidden: src.hidden === true,
            side: src.side === "left" ? "left" : "right",
            y: y === null ? null : Math.round(y * 1000) / 1000,
        };
    }

    function readPrefs(key) {
        try {
            const raw = window.localStorage.getItem(key);
            return normalize(raw ? JSON.parse(raw) : null);
        } catch (err) {
            return normalize(null); // gizli rejim / bloklanmış saxlama / pozulmuş JSON
        }
    }

    function writePrefs(key, prefs) {
        try {
            window.localStorage.setItem(key, JSON.stringify(prefs));
        } catch (err) {
            /* saxlama bloklanıb — seçim yalnız bu səhifədə qalır */
        }
    }

    function nextFrame(fn) {
        if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(fn);
        else window.setTimeout(fn, 16);
    }

    function closestIn(target, selector) {
        return Boolean(target && typeof target.closest === "function" && target.closest(selector));
    }

    function create(options) {
        const opts = options || {};
        const root = opts.root;
        const button = opts.button;
        if (!root || !button) return null;
        const doc = button.ownerDocument || document;
        const tooltip = opts.tooltip || null;
        const restoreTab = doc.getElementById("ai-fab-restore");
        const panelHideBtn = doc.getElementById("ai-chat-hide");
        const live = doc.getElementById("ai-fab-live");
        const safeProbe = root.querySelector("[data-ai-fab-safe]");
        const menuToggles = Array.prototype.slice.call(doc.querySelectorAll("[data-ai-fab-toggle]"));
        const key = root.dataset.prefKey || "ems.aiFab.v1:anon";
        const text = {
            hidden: root.dataset.hiddenMessage || "",
            undo: root.dataset.undoLabel || "",
            left: root.dataset.movedLeft || "",
            right: root.dataset.movedRight || "",
            up: root.dataset.movedUp || "",
            down: root.dataset.movedDown || "",
        };

        let prefs = readPrefs(key);
        let drag = null;
        let clickGuardUntil = 0;

        // ── Ölçülər ─────────────────────────────────────────────────────────
        function viewport() {
            const el = doc.documentElement;
            return { width: el.clientWidth || window.innerWidth || 0, height: window.innerHeight || el.clientHeight || 0 };
        }
        function heightOf(el, fallback) {
            return (el && el.offsetHeight) || fallback;
        }
        function safeInsets() {
            // `env(safe-area-inset-*)` JS-dən birbaşa oxunmur — CSS zondu onu padding kimi daşıyır.
            if (!safeProbe || typeof window.getComputedStyle !== "function") return { top: 0, bottom: 0 };
            const style = window.getComputedStyle(safeProbe);
            return { top: parseFloat(style.paddingTop) || 0, bottom: parseFloat(style.paddingBottom) || 0 };
        }
        function stickyHeaderBottom() {
            // Yapışqan başlığın düymələrini (axtarış, istifadəçi menyusu) örtməsin.
            const header = doc.querySelector(".blog-header");
            if (!header || typeof window.getComputedStyle !== "function") return 0;
            const position = window.getComputedStyle(header).position;
            if (position !== "sticky" && position !== "fixed") return 0;
            return Math.max(0, header.getBoundingClientRect().bottom);
        }
        /** Mərkəz nisbəti (0..1) → ekran daxilində sıxılmış `top` (px). */
        function topFor(fraction, height) {
            const vh = viewport().height;
            const safe = safeInsets();
            const minTop = Math.max(safe.top, stickyHeaderBottom()) + EDGE_MARGIN;
            const maxTop = Math.max(minTop, vh - safe.bottom - EDGE_MARGIN - height);
            return clamp(fraction * vh - height / 2, minTop, maxTop);
        }
        function fractionOf(top, height) {
            const vh = viewport().height;
            return vh ? clamp((top + height / 2) / vh, 0, 1) : 1;
        }
        /** Nisbət sıxılmış yerə çevrilib geri qaytarılır — saxlanan dəyər həmişə əlçatan yer olsun. */
        function settle(fraction, height) {
            return fractionOf(topFor(clamp(fraction, 0, 1), height), height);
        }
        function currentFraction(height) {
            if (prefs.y !== null) return settle(prefs.y, height);
            return fractionOf(button.getBoundingClientRect().top, height); // defolt yer — real mövqedən
        }

        // ── Vəziyyət → DOM ──────────────────────────────────────────────────
        function apply() {
            const placed = prefs.y !== null;
            root.classList.toggle("ai-fab--left", prefs.side === "left");
            root.classList.toggle("ai-fab--right", prefs.side !== "left");
            root.classList.toggle("ai-fab--placed", placed);
            root.classList.toggle("ai-fab--hidden", prefs.hidden);
            button.hidden = prefs.hidden;
            if (restoreTab) restoreTab.hidden = !prefs.hidden;
            if (prefs.hidden && tooltip) tooltip.classList.remove("ai-bot-tooltip--visible");
            if (placed) {
                root.style.setProperty("--ai-fab-y", Math.round(topFor(prefs.y, heightOf(button, FALLBACK_SIZE))) + "px");
                if (restoreTab) {
                    root.style.setProperty("--ai-fab-tab-y", Math.round(topFor(prefs.y, heightOf(restoreTab, 96))) + "px");
                }
            } else {
                root.style.removeProperty("--ai-fab-y");
                root.style.removeProperty("--ai-fab-tab-y");
            }
            menuToggles.forEach((item) => item.setAttribute("aria-checked", prefs.hidden ? "false" : "true"));
        }
        function commit(next) {
            prefs = normalize(Object.assign({}, prefs, next));
            writePrefs(key, prefs);
            apply();
        }
        function announce(message) {
            if (!live || !message) return;
            // Eyni mətn ardıcıl gələndə də oxunsun — sonuna görünməz boşluq.
            live.textContent = live.textContent === message ? message + "\u00a0" : message;
        }

        // ── Gizlət / göstər ─────────────────────────────────────────────────
        function closeHeaderMenus() {
            // Başlıq menyusu açıqkən düymə CSS ilə gizlidir (fokus ala bilməz) — burgerMenu.js protokolu ilə bağlanır.
            if (typeof window.CustomEvent !== "function") return;
            doc.dispatchEvent(new window.CustomEvent("ems:popover:open", { detail: { source: "ai-assistant" } }));
        }
        function offerUndo() {
            const toastApi = window.EMSToast;
            if (!text.hidden || !toastApi || typeof toastApi.show !== "function") return;
            const toast = toastApi.show(text.hidden, "info", 7000);
            if (!toast || !text.undo || typeof toast.querySelector !== "function") return;
            const undo = doc.createElement("button");
            undo.type = "button";
            undo.className = "ai-fab-undo";
            undo.textContent = text.undo;
            undo.addEventListener("click", () => {
                show({ focus: true });
                const dismiss = toast.querySelector("[data-toast-dismiss]");
                if (dismiss) dismiss.click();
                else toast.remove();
            });
            const row = doc.createElement("span");
            row.className = "ai-fab-undo-row";
            row.appendChild(undo);
            (toast.querySelector(".app-toast__body") || toast).appendChild(row);
        }
        function hide(options) {
            if (prefs.hidden) return;
            const hadFocus = root.contains(doc.activeElement);
            if (typeof opts.onHide === "function") opts.onHide(); // açıq panel bağlanır
            commit({ hidden: true });
            if (hadFocus && restoreTab) restoreTab.focus(); // fokus itməsin — düymənin yerini tutan nişana
            if (!options || options.undo !== false) offerUndo();
        }
        function show(options) {
            if (!prefs.hidden) return;
            commit({ hidden: false });
            if (!options || options.focus !== false) {
                closeHeaderMenus();
                button.focus();
            }
        }

        // ── Sürüşdürmə ──────────────────────────────────────────────────────
        function samePointer(event) {
            if (!drag) return false;
            const id = event ? event.pointerId : undefined;
            return drag.id === undefined || id === undefined || id === drag.id;
        }
        function onPointerDown(event) {
            if (drag || prefs.hidden || (typeof event.button === "number" && event.button !== 0)) return;
            if (button.classList.contains("ai-bot-btn--hidden") || closestIn(event.target, "[data-ai-fab-hide]")) return;
            const rect = button.getBoundingClientRect();
            drag = {
                id: event.pointerId,
                startX: event.clientX,
                startY: event.clientY,
                left: rect.left,
                top: rect.top,
                width: rect.width || button.offsetWidth || FALLBACK_SIZE,
                height: rect.height || button.offsetHeight || FALLBACK_SIZE,
                x: rect.left,
                y: rect.top,
                moved: false,
            };
            if (event.pointerId !== undefined && typeof button.setPointerCapture === "function") {
                try {
                    button.setPointerCapture(event.pointerId);
                } catch (err) {
                    /* göstərici artıq aktiv deyil — sənəd dinləyiciləri yenə işləyir */
                }
            }
        }
        function onPointerMove(event) {
            if (!samePointer(event)) return;
            const dx = event.clientX - drag.startX;
            const dy = event.clientY - drag.startY;
            if (!drag.moved) {
                if (Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
                drag.moved = true;
                root.classList.add("ai-fab--dragging");
                if (tooltip) tooltip.classList.remove("ai-bot-tooltip--visible");
            }
            const vp = viewport();
            drag.x = clamp(drag.left + dx, 0, Math.max(0, vp.width - drag.width));
            drag.y = clamp(drag.top + dy, 0, Math.max(0, vp.height - drag.height));
            root.style.setProperty("--ai-fab-x", Math.round(drag.x) + "px");
            root.style.setProperty("--ai-fab-y", Math.round(drag.y) + "px");
        }
        function finishDrag(event, cancelled) {
            if (!samePointer(event)) return;
            const done = drag;
            drag = null;
            if (!done.moved) return; // adi klik — click hadisəsi paneli açacaq
            root.classList.remove("ai-fab--dragging");
            root.style.removeProperty("--ai-fab-x");
            clickGuardUntil = Date.now() + CLICK_GUARD_MS;
            if (cancelled) {
                apply(); // əvvəlki yerə qayıt
                return;
            }
            const side = done.x + done.width / 2 < viewport().width / 2 ? "left" : "right";
            commit({ side, y: settle(fractionOf(done.y, done.height), done.height) });
            announce(text[side]);
        }

        // ── Klaviatura (düymə fokusda) ──────────────────────────────────────
        function onKeyDown(event) {
            const plain = !event.ctrlKey && !event.metaKey && !event.shiftKey;
            const move = KEY_MOVES[event.key];
            if (move && event.altKey && plain) {
                event.preventDefault(); // Alt+← brauzerdə «geri»dir — düymə fokusdaykən yox
                const height = heightOf(button, FALLBACK_SIZE);
                let fraction = currentFraction(height);
                if (move === "up") fraction -= KEY_STEP;
                if (move === "down") fraction += KEY_STEP;
                const side = move === "left" || move === "right" ? move : prefs.side;
                commit({ side, y: settle(fraction, height) });
                announce(text[move]);
            } else if ((event.key === "Delete" || event.key === "Backspace") && !event.altKey && plain) {
                event.preventDefault();
                hide();
            }
        }

        /** ai_assistant.js-in click dinləyicisi soruşur: true → paneli AÇMA. */
        function handleClick(event) {
            if (Date.now() < clickGuardUntil) {
                clickGuardUntil = 0; // sürüşdürmənin sonu
                return true;
            }
            if (closestIn(event && event.target, "[data-ai-fab-hide]")) {
                hide();
                return true;
            }
            return false;
        }

        button.addEventListener("pointerdown", onPointerDown);
        button.addEventListener("keydown", onKeyDown);
        // Tutulma itəndə (element gizləndi və s.) sürüşdürmə buraxılmış sayılır.
        button.addEventListener("lostpointercapture", (event) => finishDrag(event, false));
        doc.addEventListener("pointermove", onPointerMove);
        doc.addEventListener("pointerup", (event) => finishDrag(event, false));
        doc.addEventListener("pointercancel", (event) => finishDrag(event, true));
        doc.addEventListener("keydown", (event) => {
            if (drag && event.key === "Escape") {
                event.preventDefault();
                finishDrag(null, true);
            }
        });
        if (restoreTab) restoreTab.addEventListener("click", () => show({ focus: true }));
        if (panelHideBtn) {
            panelHideBtn.hidden = false; // skript yoxdursa görünmür
            panelHideBtn.addEventListener("click", () => hide());
        }
        menuToggles.forEach((item) => {
            item.hidden = false; // skript yoxdursa görünmür
            item.addEventListener("click", () => (prefs.hidden ? show({ focus: true }) : hide()));
        });

        let resizeQueued = false;
        window.addEventListener("resize", () => {
            if (resizeQueued) return;
            resizeQueued = true;
            nextFrame(() => {
                resizeQueued = false;
                if (!drag) apply();
            });
        });
        // Başqa tabda dəyişəndə bu tab da uyğunlaşır.
        window.addEventListener("storage", (event) => {
            if (event.key !== key && event.key !== null) return;
            const wasHidden = prefs.hidden;
            prefs = readPrefs(key);
            if (prefs.hidden && !wasHidden && typeof opts.onHide === "function") opts.onHide();
            apply();
        });

        apply();
        // Saxlanmış yer/gizlətmə tətbiq olunana qədər düymə görünmür (defolt küncdə «sıçramasın»).
        root.classList.add("ai-fab--ready");
        return {
            handleClick,
            hide,
            show,
            isHidden: () => prefs.hidden,
            prefs: () => Object.assign({}, prefs),
        };
    }

    window.EMSAiFab = { create, normalize, DRAG_THRESHOLD, KEY_STEP };
})();
