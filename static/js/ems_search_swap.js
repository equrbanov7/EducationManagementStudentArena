/* ═══════════════════════════════════════════════════════════════════════════
   EMSSearchInput — swap qatı (static/js/ems_search_input.js-in davamı).
   Nəticə yenilənəndə input-un ÖZÜ əvəzlənmir: fokus, kursor, IME və yükləmə
   gedərkən yazılan hərflər yerində qalır (sahib 2026-10-14).

     EMSSearchInput.snapshot(scope)             → {el, id, name, value, start, end}
     EMSSearchInput.restore(snap, scope)        → yeni əkizə fokus + dəyər + kursor
     EMSSearchInput.morph(oldRoot, newRoot, keep) → bool — `keep` (input və ya
                                  forma) və valideyn zənciri QALIR, qalan hər
                                  şey `newRoot`-dan köçürülür; data-* nişanları
                                  (JS bağlama bayraqları) silinmir
     EMSSearchInput.submitForm(form, {input, soft}) — GET formanı göndərir:
                                  1) kabinet bölməsi → EMSProfileLoadSection(…, {quiet})
                                  2) `data-ems-soft-search="<konteyner>"` → fetch +
                                     morph (forma qalır, nəticələr yenilənir)
                                  3) əks halda adi göndəriş; fokus/kursor yeni
                                     səhifədə bərpa olunur (sessionStorage)
   ═══════════════════════════════════════════════════════════════════════════ */
(function (root, document) {
    "use strict";
    var SI = root.EMSSearchInput;
    if (!SI || SI.morph) {
        return;
    }
    var isTextField = SI.isTextField;
    var busy = SI.busy;
    var latest = SI.latest;

    /* ---- fokus / dəyər / kursor ---------------------------------------- */
    function snapshot(scope) {
        var el = document.activeElement;
        if (!isTextField(el) || (scope && !scope.contains(el))) {
            return null;
        }
        var snap = { el: el, id: el.id || "", name: el.getAttribute("name") || "", value: el.value };
        try {
            snap.start = el.selectionStart;
            snap.end = el.selectionEnd;
            snap.dir = el.selectionDirection;
        } catch (err) { /* type=email və s. */ }
        return snap;
    }

    function findTwin(scope, snap) {
        if (!scope || !snap) {
            return null;
        }
        if (snap.id) {
            var byId = scope.querySelector("#" + (root.CSS && root.CSS.escape ? root.CSS.escape(snap.id) : snap.id));
            if (byId) {
                return byId;
            }
        }
        if (snap.name) {
            var list = scope.querySelectorAll(snap.el.tagName.toLowerCase() + "[name]");
            for (var i = 0; i < list.length; i += 1) {
                if (list[i].getAttribute("name") === snap.name) {
                    return list[i];
                }
            }
        }
        return null;
    }

    function restore(snap, scope) {
        if (!snap) {
            return null;
        }
        var el = document.documentElement.contains(snap.el) ? snap.el : findTwin(scope || document, snap);
        if (!el) {
            return null;
        }
        var rendered = el.value;
        if (document.activeElement !== el) {
            try {
                el.focus({ preventScroll: true });
            } catch (err) {
                el.focus();
            }
        }
        if (el !== snap.el && rendered !== snap.value) {
            // Yükləmə gedərkən yazılan hərflər itmir; sahə yenidən planlanır
            // (tətbiq olunmuş = serverin qaytardığı dəyər).
            el.value = snap.value;
            SI.requeue(el, rendered);
        }
        if (typeof snap.start === "number") {
            try {
                el.setSelectionRange(snap.start, snap.end, snap.dir || "none");
            } catch (err) { /* ignore */ }
        }
        return el;
    }

    /* ---- morph: fokuslu sahə + valideyn zənciri yerində qalır ----------- */
    function chainUp(scope, el) {
        var chain = [];
        var node = el;
        while (node && node !== scope) {
            chain.unshift(node);
            node = node.parentElement;
        }
        return node === scope ? chain : null;
    }

    function syncAttrs(target, source, keepValue) {
        var i;
        var attrs = source.attributes;
        for (i = 0; i < attrs.length; i += 1) {
            var name = attrs[i].name;
            if (keepValue && name === "value") {
                continue;
            }
            if (target.getAttribute(name) !== attrs[i].value) {
                target.setAttribute(name, attrs[i].value);
            }
        }
        var own = Array.prototype.slice.call(target.attributes);
        for (i = 0; i < own.length; i += 1) {
            var key = own[i].name;
            // data-* — JS bağlama nişanları (data-*-bound / data-applied …) qalır.
            if (key.indexOf("data-") !== 0 && key !== "value" && !source.hasAttribute(key)) {
                target.removeAttribute(key);
            }
        }
    }

    function morph(oldRoot, newRoot, keep) {
        if (!oldRoot || !newRoot || !keep || !oldRoot.contains(keep) || keep === oldRoot) {
            return false;
        }
        var oldChain = chainUp(oldRoot, keep);
        var twin = findTwin(newRoot, { el: keep, id: keep.id || "", name: keep.getAttribute("name") || "" });
        if (!twin) {
            // id/name-siz element (məs. forma): eyni teq üzrə sıra nömrəsi ilə.
            var tag = keep.tagName.toLowerCase();
            var at = Array.prototype.indexOf.call(oldRoot.querySelectorAll(tag), keep);
            twin = at >= 0 ? newRoot.querySelectorAll(tag)[at] || null : null;
        }
        var newChain = twin ? chainUp(newRoot, twin) : null;
        if (!oldChain || !newChain || oldChain.length !== newChain.length) {
            return false;
        }
        for (var i = 0; i < oldChain.length; i += 1) {
            if (oldChain[i].tagName !== newChain[i].tagName) {
                return false;
            }
        }
        var oldParents = [oldRoot].concat(oldChain.slice(0, -1));
        var newParents = [newRoot].concat(newChain.slice(0, -1));
        for (var k = 0; k < oldParents.length; k += 1) {
            var op = oldParents[k];
            var np = newParents[k];
            var stay = oldChain[k];
            var kids = Array.prototype.slice.call(np.childNodes);
            var at = kids.indexOf(newChain[k]);
            Array.prototype.slice.call(op.childNodes).forEach(function (child) {
                if (child !== stay) {
                    op.removeChild(child);
                }
            });
            for (var a = 0; a < at; a += 1) {
                op.insertBefore(kids[a], stay);
            }
            for (var b = at + 1; b < kids.length; b += 1) {
                op.appendChild(kids[b]);
            }
            syncAttrs(op, np, false);
        }
        syncAttrs(keep, twin, true);
        return true;
    }

    /* ---- formanı göndər: input-u əvəzləmədən ---------------------------
       1) kabinet bölməsi → EMSProfileLoadSection(..., {quiet}) (morph);
       2) `data-ems-soft-search="<konteyner>"` → fetch + morph (forma qalır);
       3) əks halda adi göndəriş; fokus/kursor yeni səhifədə bərpa olunur. */
    var FOCUS_KEY = "ems.search.focus";
    var soft = latest();

    function formUrl(form) {
        var url = new URL(form.getAttribute("action") || root.location.pathname, root.location.href);
        url.search = "";
        new root.FormData(form).forEach(function (value, key) {
            if (typeof value === "string") {
                url.searchParams.append(key, value);
            }
        });
        return url;
    }

    function rememberFocus(input) {
        if (!isTextField(input)) {
            return;
        }
        try {
            root.sessionStorage.setItem(FOCUS_KEY, JSON.stringify({
                path: root.location.pathname, name: input.getAttribute("name") || "", id: input.id || "",
            }));
        } catch (err) { /* private rejim */ }
    }

    function recallFocus() {
        var saved = null;
        try {
            saved = JSON.parse(root.sessionStorage.getItem(FOCUS_KEY) || "null");
            root.sessionStorage.removeItem(FOCUS_KEY);
        } catch (err) {
            return;
        }
        if (!saved || saved.path !== root.location.pathname) {
            return;
        }
        var el = findTwin(document, { el: { tagName: "INPUT" }, id: saved.id, name: saved.name });
        if (el && isTextField(el)) {
            var end = (el.value || "").length;
            restore({ el: el, id: saved.id, name: saved.name, value: el.value, start: end, end: end }, document);
        }
    }

    function finishSoft(container, url) {
        try {
            root.history.replaceState(root.history.state, "", url);
        } catch (err) { /* ignore */ }
        try {
            document.dispatchEvent(new root.CustomEvent("profile:section:loaded", {
                detail: { section: null, panel: container, soft: true },
            }));
        } catch (err) { /* ignore */ }
    }

    function softSubmit(form, selector, input) {
        var container = form.closest(selector) || document.querySelector(selector);
        var url = formUrl(form).toString();
        if (!container || typeof root.fetch !== "function" || typeof root.DOMParser !== "function") {
            return false;
        }
        var ticket = soft.begin();
        busy(input, true);
        var dimmed = Array.prototype.filter.call(container.children, function (child) {
            return !child.contains(form);
        });
        dimmed.forEach(function (child) {
            child.classList.add("ems-search-pending");
        });
        root.fetch(url, { credentials: "same-origin", headers: { Accept: "text/html" }, signal: ticket.signal })
            .then(function (resp) {
                if (!resp.ok) {
                    throw new Error("http_" + resp.status);
                }
                return resp.text();
            })
            .then(function (html) {
                if (!ticket.current()) {
                    return; // daha yeni sorğu var — köhnə cavab atılır
                }
                var doc = new root.DOMParser().parseFromString(html, "text/html");
                var fresh = doc.querySelector(selector);
                if (!fresh || !morph(container, fresh, form)) {
                    throw new Error("no_container");
                }
                busy(input, false);
                finishSoft(container, url);
            })
            .catch(function (err) {
                if (err && err.name === "AbortError") {
                    return;
                }
                if (ticket.current()) {
                    rememberFocus(input);
                    root.location.assign(url);
                }
            });
        return true;
    }

    function submitForm(form, opts) {
        if (!form) {
            return;
        }
        opts = opts || {};
        var input = opts.input || null;
        var method = (form.getAttribute("method") || "get").toLowerCase();
        // `soft` (opts və ya data-ems-soft-search) — formanın ÖZÜ qalır (məs. JS
        // seçiciləri olan filtr sətri); kabinet içində də üstünlük ona verilir.
        var selector = opts.soft || form.getAttribute("data-ems-soft-search");
        if (method === "get" && selector && softSubmit(form, selector, input)) {
            return;
        }
        var panel = form.closest("[data-profile-section-panel]");
        if (method === "get" && panel && typeof root.EMSProfileLoadSection === "function") {
            var url = formUrl(form);
            var section = url.searchParams.get("section") || panel.getAttribute("data-profile-section-panel");
            url.searchParams.set("section", section);
            busy(input, true);
            root.EMSProfileLoadSection(section, url.pathname + url.search, { quiet: true });
            return;
        }
        rememberFocus(input);
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", recallFocus);
    } else {
        recallFocus();
    }

    SI.snapshot = snapshot;
    SI.restore = restore;
    SI.morph = morph;
    SI.submitForm = submitForm;
    SI.formUrl = formUrl;
})(window, document);
