/* =========================================================================
   ems_ajax_init.js — Universal AJAX-safe init + event-delegation helpers.

   PROBLEM
   -------
   EMSArena profile/dashboard sections are swapped into the DOM via AJAX
   (profile.js fetches a fragment and dispatches `profile:section:loaded`).
   Any script that wires handlers inside a one-time `DOMContentLoaded` using
   `querySelectorAll(...).forEach(el => el.addEventListener(...))` only ever
   sees the elements that existed at first paint. After an AJAX swap the new
   buttons/forms are unbound, so they look "dead" until a full page refresh.
   With our strict CSP (`script-src` uses NONCE, no `unsafe-inline`) inline
   `onclick=""` handlers are also blocked, so every interaction must go through
   JS — which makes the dead-binding problem worse.

   SOLUTION — two universal primitives. Use these EVERYWHERE in the dashboard.

   1) window.EMSDelegate.on(eventType, selector, handler)
      Registers ONE delegated listener on `document` (deduped by
      eventType+selector). Because the listener lives on `document` — which is
      never swapped out — it automatically covers all CURRENT and FUTURE
      AJAX-loaded elements. `this`/2nd arg = the matched element.
      → Preferred pattern for NEW code. Never stacks, never goes stale.

          EMSDelegate.on("click", ".js-edit-post", function (e, btn) {
              openEditModal(btn.dataset.postId);
          });

   2) window.EMSReady(fn)
      Runs `fn` once on initial DOMContentLoaded (or immediately if the DOM is
      already parsed) AND again after every AJAX section swap. Use it to make an
      EXISTING DOMContentLoaded-style init re-runnable without rewriting it —
      provided the init is null-safe (guards element lookups) and idempotent
      (does not stack listeners on stable nodes like document/window; see
      EMSReady.once below for that).

          window.EMSReady(function () { ...existing init body... });

   3) window.EMSReady.once(key, fn)
      Runs `fn` only the first time for a given string key — handy for
      document/window-level listeners that must be registered exactly once even
      though the surrounding init re-runs on every swap.
   ========================================================================= */
(function () {
    "use strict";

    if (window.EMSDelegate && window.EMSReady && !window.EMSReady.__emsStub) {
        return; // Already loaded (real implementation, not the ems_early.js stub).
    }

    /* ---- 1. Event delegation -------------------------------------------- */
    var delegated = Object.create(null); // "eventType|selector" -> { handler }

    function on(eventType, selector, handler) {
        if (typeof handler !== "function") {
            return;
        }
        var key = eventType + "|" + selector;
        var existing = delegated[key];
        if (existing) {
            // Same event+selector already delegated — just refresh the handler
            // so repeated registrations (e.g. from inside EMSReady) never stack
            // additional listeners on `document`.
            existing.handler = handler;
            return;
        }
        var record = { handler: handler };
        delegated[key] = record;
        document.addEventListener(eventType, function (event) {
            var origin = event.target;
            if (!origin || typeof origin.closest !== "function") {
                return;
            }
            var match = origin.closest(selector);
            if (match && document.contains(match)) {
                record.handler.call(match, event, match);
            }
        });
    }

    window.EMSDelegate = { on: on };

    /* ---- 2. AJAX-safe ready -------------------------------------------- */
    function safeRun(fn, detail) {
        try {
            fn(detail || null);
        } catch (err) {
            // One section's init must never break another's.
            if (window.console && console.error) {
                console.error("EMSReady init failed:", err);
            }
        }
    }

    function ready(fn) {
        if (typeof fn !== "function") {
            return;
        }
        // Initial run.
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", function () {
                safeRun(fn);
            });
        } else {
            safeRun(fn);
        }
        // Re-run after every AJAX section swap (profile.js dispatches this on
        // `document` once the new fragment is in the DOM).
        document.addEventListener("profile:section:loaded", function (event) {
            safeRun(fn, event && event.detail ? event.detail : null);
        });
    }

    var onceKeys = Object.create(null);
    ready.once = function (key, fn) {
        if (typeof fn !== "function" || onceKeys[key]) {
            return;
        }
        onceKeys[key] = true;
        fn();
    };

    window.EMSReady = ready;

    /* ---- 3. ems_early.js növbəsini boşalt ------------------------------ */
    // <head>-dəki stub (static/js/ems_early.js) bu fayl yüklənənə qədər edilən
    // qeydiyyatları yığır; eyni sıra ilə əsl implementasiyaya ötürürük.
    var early = window.__emsEarlyQueue;
    if (early) {
        (early.on || []).forEach(function (args) { on(args[0], args[1], args[2]); });
        (early.ready || []).forEach(function (fn) { ready(fn); });
        (early.once || []).forEach(function (pair) { ready.once(pair[0], pair[1]); });
        window.__emsEarlyQueue = null;
    }
})();
