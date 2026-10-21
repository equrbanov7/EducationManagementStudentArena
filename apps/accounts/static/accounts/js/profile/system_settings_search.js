/* «Sistem tənzimləmələri» — alt səhifələr: BÜTÜN qruplar üzrə axtarış + açarın vurğulanması (sahib 2026-10-21).
 * Şablon: sections/system_settings/_search.html (indeks server-render olunur), _group_form.html (`is-target`).
 *
 * • Süzgəc brauzerdədir, sorğu yoxdur: EMSSearch (static/js/search_fold.js — core/search_text.py-nin əkizi)
 *   ilə az/ing hərf qatlama (ə/e, ı/i, ö/o, ü/u, ş/s, ç/c, ğ/g, İ/I) və tokenlər (söz sırası fərq etmir).
 * • Sorğu yazılanda nəticələr (qrup → açar → keçid) görünür, səhifənin məzmunu GİZLƏNİR (silinmir — saxlanmamış
 *   dəyərlər itmir); Esc və ya boş sorğu geri qaytarır.
 * • Nəticə CARİ qrupdadırsa səhifə yenidən yüklənmir — sətir vurğulanır və görünən sahəyə gəlir; başqa qrupdadırsa
 *   link adi panel keçididir (ajax.js → `?section=system-settings&ss_group=…&ss_key=…`, tarixçə işləyir).
 * • `data-ss-focus-key` (deep link / qlobal axtarış) — swap-dan sonra həmin sətir görünən sahəyə gətirilir.
 * AJAX-safe: sənəd səviyyəli dinləyicilər bir dəfə qeyd olunur; EMSReady hər swap-da idempotentdir.
 */
(function (root) {
    "use strict";

    if (root.EMSSystemSettingsSearch) {
        return;
    }

    function matcherFor(query) {
        if (root.EMSSearch && typeof root.EMSSearch.matcher === "function") {
            // Server (`tolerant_match`) ilə eyni: adi rejim — etiketlər kod deyil.
            return root.EMSSearch.matcher(query, { compact: false });
        }
        var needle = String(query || "").toLowerCase();
        return function (text) {
            return String(text || "").toLowerCase().indexOf(needle) !== -1;
        };
    }

    function statusText(status, total) {
        if (!total) {
            return status.getAttribute("data-empty-text") || "";
        }
        return (status.getAttribute("data-count-text") || "{n}").replace("{n}", String(total));
    }

    /** Sorğunu `[data-ss-root]` daxilində tətbiq edir; görünən nəticə sayını qaytarır (boş sorğu → -1). */
    function apply(ssRoot, query) {
        if (!ssRoot) {
            return -1;
        }
        var results = ssRoot.querySelector("[data-ss-results]");
        var main = ssRoot.querySelector("[data-ss-main]");
        var text = String(query || "").trim();
        if (!results) {
            return -1;
        }
        if (!text) {
            results.hidden = true;
            if (main) {
                main.hidden = false;
            }
            return -1;
        }
        var match = matcherFor(text);
        var total = 0;
        results.querySelectorAll("[data-ss-result-group]").forEach(function (group) {
            var visible = 0;
            group.querySelectorAll("[data-ss-hit]").forEach(function (hit) {
                var ok = !!match(hit.getAttribute("data-ss-text") || "");
                hit.hidden = !ok;
                if (ok) {
                    visible += 1;
                }
            });
            group.hidden = visible === 0;
            total += visible;
        });
        results.hidden = false;
        if (main) {
            main.hidden = true;
        }
        var status = results.querySelector("[data-ss-results-status]");
        if (status) {
            status.textContent = statusText(status, total);
        }
        return total;
    }

    function rowFor(ssRoot, key) {
        var rows = ssRoot.querySelectorAll("[data-ss-field]");
        for (var i = 0; i < rows.length; i += 1) {
            if (rows[i].getAttribute("data-ss-field") === key) {
                return rows[i];
            }
        }
        return null;
    }

    /** Açarı vurğulayır və görünən sahəyə gətirir; `focus` → ilk sahəyə fokus. */
    function focusKey(ssRoot, key, options) {
        var row = ssRoot && key ? rowFor(ssRoot, key) : null;
        if (!row) {
            return false;
        }
        ssRoot.querySelectorAll("[data-ss-field].is-target").forEach(function (node) {
            if (node !== row) {
                node.classList.remove("is-target");
            }
        });
        row.classList.add("is-target");
        if (typeof row.scrollIntoView === "function") {
            try {
                row.scrollIntoView({ block: "center", behavior: "smooth" });
            } catch (e) {
                row.scrollIntoView();
            }
        }
        if (options && options.focus) {
            var field = row.querySelector("input:not([type=hidden]), select");
            if (field && typeof field.focus === "function") {
                try {
                    field.focus({ preventScroll: true });
                } catch (e) {
                    field.focus();
                }
            }
        }
        return true;
    }

    function clearSearch(ssRoot) {
        var input = ssRoot.querySelector("[data-ss-search]");
        if (input) {
            input.value = "";
        }
        apply(ssRoot, "");
    }

    document.addEventListener("input", function (event) {
        var input = event.target;
        if (!input || !input.matches || !input.matches("[data-ss-search]")) {
            return;
        }
        apply(input.closest("[data-ss-root]"), input.value);
    });

    document.addEventListener("keydown", function (event) {
        var input = event.target;
        if (event.key !== "Escape" || !input || !input.matches || !input.matches("[data-ss-search]")) {
            return;
        }
        if (input.value) {
            event.preventDefault();
            clearSearch(input.closest("[data-ss-root]"));
        }
    });

    /* CAPTURE fazası: ajax.js-in sənəd dinləyicisindən ƏVVƏL — cari qrupdakı nəticə üçün panel yenidən yüklənmir. */
    document.addEventListener(
        "click",
        function (event) {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }
            var link = event.target && event.target.closest ? event.target.closest("[data-ss-hit-link]") : null;
            if (!link) {
                return;
            }
            var hit = link.closest("[data-ss-hit]");
            var ssRoot = link.closest("[data-ss-root]");
            if (!hit || !ssRoot || hit.getAttribute("data-ss-hit-group") !== ssRoot.getAttribute("data-ss-group")) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            clearSearch(ssRoot);
            focusKey(ssRoot, hit.getAttribute("data-ss-hit-key"), { focus: true });
        },
        true
    );

    function init() {
        var ssRoot = document.querySelector("[data-ss-root]");
        if (!ssRoot) {
            return;
        }
        // Mobil: üfüqi qrup çiplərində CARİ qrup görünən sahədə olsun.
        var nav = ssRoot.querySelector(".sysset-nav");
        var current = nav ? nav.querySelector(".is-current") : null;
        if (current && nav.scrollWidth > nav.clientWidth) {
            var shift = current.getBoundingClientRect().left - nav.getBoundingClientRect().left;
            nav.scrollLeft = Math.max(0, nav.scrollLeft + shift - 16);
        }
        var key = ssRoot.getAttribute("data-ss-focus-key") || "";
        if (!key || ssRoot.getAttribute("data-ss-focused") === key) {
            return;
        }
        ssRoot.setAttribute("data-ss-focused", key);
        // Swap-dan sonra qabıq fokusu başlığa aparır (section_loader.js) — sürüşdürmə ondan SONRA.
        root.setTimeout(function () {
            focusKey(ssRoot, key, { focus: false });
        }, 80);
    }

    root.EMSSystemSettingsSearch = { apply: apply, focusKey: focusKey, clear: clearSearch, init: init };

    if (typeof root.EMSReady === "function") {
        root.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})(window);
