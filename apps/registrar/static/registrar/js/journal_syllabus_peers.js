/* ═══════════════════════════════════════════════════════════════════════════
   Jurnal — «Bu fənn üzrə mövcud sillabuslar» + «dəyişmədən tətbiq et» (sahib 2026-11-08)
   ───────────────────────────────────────────────────────────────────────────
   Banner (`_jd_syllabus_notice.html` → `_jd_syllabus_peers.html`) göstəriləndə
   `registrar:journal_syllabus_peers` JSON-u BİR DƏFƏ oxunur:
     * `rows`  — siyahı (qrup · müəllif · status · «Aç»);
     * `reuse` — jurnalın müəllimi üçün paylaşıla bilən öz sillabusları.
   `reuse` boş deyilsə bannerin «Sillabus yarat» keçidi əvvəlcə təsdiq
   dialoqunu açır: «Bəli» → POST `accounts:syllabus_reuse_action`
   `{action: "share", source, offering}` → səhifə yenilənir; «Xeyr» → adi keçid.

   AJAX-safe (docs/frontend/AJAX_SAFE_JS_PATTERN.md): kliklər `EMSDelegate.on`
   ilə document-ə BİR DƏFƏ deleqasiya olunur; yükləmə `EMSReady` ilə, blok
   başına bir dəfə (`data-jd-syl-peers-loaded`). Mətnlər serverdən gəlir.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    var cache = { data: null, promise: null };

    function i18n(key) {
        var host = document.querySelector("[data-jd-syl-peers-i18n]");
        return (host && host.getAttribute("data-t-" + key)) || "";
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text) {
            node.textContent = text;
        }
        return node;
    }

    function renderRow(row) {
        var item = el("li", "jd2-sylpeers__item");
        var link = el("a", "jd2-sylpeers__row");
        link.href = row.url;
        var main = el("span", "jd2-sylpeers__main");
        main.appendChild(el("strong", "jd2-sylpeers__group", row.group_text));
        var who = el("span", "jd2-sylpeers__author", i18n("author") + ": " + row.author);
        if (row.by_instructor) {
            who.appendChild(el("span", "jd2-sylpeers__badge", i18n("by-instructor")));
        }
        main.appendChild(who);
        link.appendChild(main);
        var status = el("span", "jd2-sylpeers__status jd2-sylpeers__status--" + row.status_key, row.status_label);
        link.appendChild(status);
        if (row.approved_note) {
            link.appendChild(el("span", "jd2-sylpeers__note", row.approved_note));
        }
        var open = el("span", "jd2-sylpeers__open", i18n("open"));
        var arrow = el("i", "fas fa-arrow-right");
        arrow.setAttribute("aria-hidden", "true");
        open.appendChild(arrow);
        link.appendChild(open);
        item.appendChild(link);
        return item;
    }

    function renderList(block, data) {
        var rows = (data && data.rows) || [];
        var list = block.querySelector("[data-jd-syl-peers-list]");
        var count = block.querySelector("[data-jd-syl-peers-count]");
        if (!list || !rows.length) {
            block.hidden = true;
            return;
        }
        list.textContent = "";
        rows.forEach(function (row) {
            list.appendChild(renderRow(row));
        });
        if (count) {
            count.textContent = "(" + rows.length + ")";
        }
        block.hidden = false;
    }

    function load() {
        var block = document.querySelector("[data-jd-syl-peers]");
        if (!block || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
            return null;
        }
        if (block.getAttribute("data-jd-syl-peers-loaded") === "1" && cache.promise) {
            return cache.promise;
        }
        block.setAttribute("data-jd-syl-peers-loaded", "1");
        cache.promise = window.EMSCore.fetchJSON(block.getAttribute("data-url"))
            .then(function (data) {
                cache.data = data || {};
                renderList(block, cache.data);
                return cache.data;
            })
            .catch(function () {
                cache.data = {};
                block.hidden = true;
                return cache.data;
            });
        return cache.promise;
    }

    /* ── Təklif dialoqu ─────────────────────────────────────────────── */
    function dialog() {
        return document.querySelector("[data-jd-syl-reuse]");
    }

    function setStatus(modal, text) {
        var node = modal.querySelector("[data-jd-syl-reuse-status]");
        if (!node) {
            return;
        }
        node.textContent = text || "";
        node.hidden = !text;
    }

    function sourceCard(source) {
        var card = el("div", "jd2-sylreuse__source");
        card.appendChild(el("p", "jd2-sylreuse__question", source.question));
        card.appendChild(
            el("p", "jd2-sylreuse__meta", [source.group, source.author, source.status_label].filter(Boolean).join(" · "))
        );
        var yes = el("button", "jd2-sylreuse__yes", i18n("yes"));
        yes.type = "button";
        yes.setAttribute("data-jd-syl-reuse-apply", source.id);
        card.appendChild(yes);
        return card;
    }

    function openDialog(sources) {
        var modal = dialog();
        if (!modal) {
            return false;
        }
        var host = modal.querySelector("[data-jd-syl-reuse-sources]");
        host.textContent = "";
        sources.forEach(function (source) {
            host.appendChild(sourceCard(source));
        });
        setStatus(modal, "");
        modal.hidden = false;
        var box = modal.querySelector("[role='dialog']");
        var first = modal.querySelector("[data-jd-syl-reuse-apply]");
        (first || box).focus();
        return true;
    }

    function closeDialog() {
        var modal = dialog();
        if (modal && !modal.hidden) {
            modal.hidden = true;
            var cta = document.querySelector("[data-jd-syl-cta]");
            if (cta) {
                cta.focus();
            }
        }
    }

    function apply(button) {
        var modal = dialog();
        if (!modal || button.disabled) {
            return;
        }
        modal.querySelectorAll("[data-jd-syl-reuse-apply]").forEach(function (node) {
            node.disabled = true;
        });
        setStatus(modal, "");
        window.EMSCore.fetchJSON(modal.getAttribute("data-action-url"), {
            method: "POST",
            data: {
                action: "share",
                source: button.getAttribute("data-jd-syl-reuse-apply"),
                offering: modal.getAttribute("data-offering")
            }
        })
            .then(function (data) {
                setStatus(modal, (data && data.message) || "");
                window.setTimeout(function () {
                    window.location.reload();
                }, 900);
            })
            .catch(function (err) {
                modal.querySelectorAll("[data-jd-syl-reuse-apply]").forEach(function (node) {
                    node.disabled = false;
                });
                setStatus(modal, (err && err.payload && err.payload.error) || i18n("error"));
            });
    }

    function onCta(event, link) {
        if (!dialog()) {
            return; // müəllim deyil — adi keçid
        }
        var decide = function (data) {
            var sources = (data && data.reuse) || [];
            if (!sources.length || !openDialog(sources)) {
                window.location.href = link.href;
            }
        };
        event.preventDefault();
        if (cache.data) {
            decide(cache.data);
            return;
        }
        var pending = load();
        if (!pending) {
            window.location.href = link.href;
            return;
        }
        pending.then(decide);
    }

    function bindOnce() {
        if (!window.EMSDelegate || window.__emsJournalSyllabusPeersBound) {
            return;
        }
        window.__emsJournalSyllabusPeersBound = true;
        var on = window.EMSDelegate.on;
        on("click", "[data-jd-syl-cta]", onCta);
        on("click", "[data-jd-syl-reuse] [data-jd-syl-reuse-apply]", function (event, button) {
            event.preventDefault();
            apply(button);
        });
        on("click", "[data-jd-syl-reuse] [data-jd-syl-reuse-close]", function (event) {
            event.preventDefault();
            closeDialog();
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeDialog();
            }
        });
    }

    window.EMSReady(function () {
        bindOnce();
        load();
    });
})();
