/*
 * «Yük bölgüsü» — YER SAXLANMASI (`window.EMSWorkloadAnchor`, sahib 2026-11-19).
 *
 * Sahib: «Kiminsə yükündə bir hissəni dəyişəndən sonra yuxarı scroll gedir, sonra düşüb həmin adamı axtarıb tapası
 * oluram, yorur». Hər yazıdan sonra siyahı və sağdakı müəllim paneli YENİDƏN çəkilir; bu modul həmin anda:
 *
 *   • üzərində işlənən fənn kartını (son klik) ekranda EYNİ yerdə saxlayır və qısa vurğulayır;
 *   • kartın açıq «Tapşırıq sətirləri» hissəsini açıq saxlayır (əvvəl hər yazıdan sonra bağlanırdı);
 *   • sağ panelin öz sürüşmə yerini saxlayır, saatı dəyişən müəllimi vurğulayır («+7 s») və panelin içində
 *     görünən yerə gətirir (səhifəni tərpətmədən);
 *   • sağ paneldə ad ilə axtarış («Müəllim axtar…») — süzgəc yenidən çəkilişdən sonra da qalır.
 *
 * Əsas modul (`workload_distribution.js → loadRows`) render-dən ƏVVƏL `capture()`, SONRA `restore()` çağırır.
 * Null-safe: bu fayl yüklənməsə siyahı əvvəlki kimi işləyir. Dinləyicilər BİR dəfə qoşulur (AJAX-safe).
 */
(function (window, document) {
    "use strict";

    var CLICK_TTL = 3 * 60 * 1000; // klik anındakı yer bu müddət etibarlıdır (modal açıq qalan vaxt)
    var SETTLE = [0, 120, 400]; // render-dən sonra təkrar düzləndirmə (modal bağlanışı, şriftlər, şəkillər)

    var last = { key: "", top: 0, at: 0, moved: false }; // son klik: kart açarı + ekrandakı yuxarı kənarı
    var selfUntil = 0; // öz `scrollBy`-ımızın yaratdığı scroll hadisələri bu ana qədər sayılmır
    var pending = null; // { key, top, until } — istifadəçi özü sürüşdürənə qədər qorunan yer
    var search = ""; // sağ panel axtarışı

    function dist() {
        return window.EMSWorkloadDist || null;
    }

    function q(selector) {
        var D = dist();
        return D ? D.q(selector) : null;
    }

    function cards() {
        var host = q("[data-wl-rows]");
        return host ? Array.prototype.slice.call(host.querySelectorAll("[data-wl-card]")) : [];
    }

    function cardByKey(key) {
        if (!key) return null;
        return cards().filter(function (card) { return card.getAttribute("data-card-key") === key; })[0] || null;
    }

    function onScreen(card) {
        var rect = card.getBoundingClientRect();
        return rect.bottom > 0 && rect.top < (window.innerHeight || 0);
    }

    function firstVisible() {
        return cards().filter(function (card) { return card.getBoundingClientRect().bottom > 8; })[0] || null;
    }

    function teacherKey(card) {
        return card.is_vacant ? "vacant" : String(card.teacher_id);
    }

    // ── Vəziyyətin çəkilməsi (render-dən ƏVVƏL) ─────────────────────────────
    function capture(fresh) {
        var D = dist();
        if (!D) return null;
        var panel = q("[data-wl-teacher-panel]");
        var loads = {};
        (D.state.teachers || []).forEach(function (card) { loads[teacherKey(card)] = Number(card.hours) || 0; });
        var snap = { fresh: !!fresh, key: "", top: 0, edited: false, open: [], panelTop: panel ? panel.scrollTop : 0, loads: loads };
        if (fresh) return snap; // süzgəc dəyişib — siyahı başqadır, yalnız panel saxlanır
        // Klikdən sonra istifadəçi özü sürüşdürübsə klik anındakı yer köhnəlib — ekrandakı ilk kart götürülür.
        var recent = last.key && !last.moved && Date.now() - last.at < CLICK_TTL;
        var anchor = recent ? cardByKey(last.key) : null;
        if (anchor) {
            snap.edited = true;
            snap.key = last.key;
            snap.top = last.top; // klik anındakı yer — modal açılıb-bağlanarkən səhifə tərpənsə də hədəf odur
        } else {
            anchor = firstVisible();
            if (anchor) {
                snap.key = anchor.getAttribute("data-card-key") || "";
                snap.top = anchor.getBoundingClientRect().top;
            }
        }
        var host = q("[data-wl-rows]");
        if (host) {
            Array.prototype.forEach.call(host.querySelectorAll("[data-wl-card-rows][open]"), function (details) {
                var card = details.closest ? details.closest("[data-wl-card]") : null;
                if (card) snap.open.push(card.getAttribute("data-card-key"));
            });
        }
        return snap;
    }

    // ── Bərpa (render-dən SONRA) ────────────────────────────────────────────
    function align() {
        if (!pending) return;
        if (Date.now() > pending.until) {
            pending = null;
            return;
        }
        var card = cardByKey(pending.key);
        if (!card) return;
        var delta = card.getBoundingClientRect().top - pending.top;
        if (Math.abs(delta) > 1 && typeof window.scrollBy === "function") {
            selfUntil = Date.now() + 300;
            window.scrollBy({ top: delta, left: 0, behavior: "instant" });
        }
    }

    function flash(node, cls) {
        if (!node) return;
        node.classList.remove(cls);
        void node.offsetWidth; // animasiyanı yenidən başlat
        node.classList.add(cls);
        window.setTimeout(function () { node.classList.remove(cls); }, 2600);
    }

    function markTeachers(snap) {
        var D = dist();
        var panel = q("[data-wl-teacher-panel]");
        if (!D || !panel) return;
        applySearch();
        panel.scrollTop = snap.panelTop;
        if (snap.fresh) return;
        var firstChanged = null;
        (D.state.teachers || []).forEach(function (card) {
            var key = teacherKey(card);
            var before = snap.loads[key];
            var now = Number(card.hours) || 0;
            if (before === now || (before == null && !Object.keys(snap.loads).length)) return;
            var tile = Array.prototype.filter.call(panel.querySelectorAll("[data-wl-teacher-id]"), function (node) {
                return node.getAttribute("data-wl-teacher-id") === key;
            })[0];
            if (!tile) return;
            var diff = now - (before || 0);
            var numbers = tile.querySelector(".wl-teacher__numbers");
            if (numbers && diff) {
                var delta = document.createElement("span");
                delta.className = "wl-teacher__delta";
                delta.textContent = (diff > 0 ? "+" : "−") + Math.abs(diff) + " s";
                numbers.appendChild(delta);
            }
            flash(tile, "is-changed");
            firstChanged = firstChanged || tile;
        });
        if (!firstChanged) return;
        // Paneldə görünməyən dəyişmiş müəllim — panelin ÖZ sürüşməsi ilə görünən yerə (səhifə tərpənmir).
        var box = panel.getBoundingClientRect();
        var rect = firstChanged.getBoundingClientRect();
        if (rect.top < box.top || rect.bottom > box.bottom) panel.scrollTop += rect.top - box.top - 8;
    }

    function restore(snap) {
        if (!snap) return;
        if (!snap.fresh) {
            snap.open.forEach(function (key) {
                var card = cardByKey(key);
                var details = card ? card.querySelector("[data-wl-card-rows]") : null;
                if (details) details.open = true;
            });
            if (snap.key && cardByKey(snap.key)) {
                pending = { key: snap.key, top: snap.top, until: Date.now() + 2500 };
                SETTLE.forEach(function (delay) {
                    if (delay) window.setTimeout(align, delay);
                    else align();
                });
                if (snap.edited) flash(cardByKey(snap.key), "is-updated");
            }
        }
        markTeachers(snap);
    }

    // ── Sağ panel axtarışı ──────────────────────────────────────────────────
    function fold(text) {
        var value = String(text || "").toLowerCase();
        if (value.normalize) value = value.normalize("NFD").replace(/[̀-ͯ]/g, "");
        return value.replace(/ə/g, "e").replace(/ı/g, "i");
    }

    function applySearch() {
        var panel = q("[data-wl-teacher-panel]");
        if (!panel) return;
        var needle = fold(search).trim();
        var shown = 0;
        Array.prototype.forEach.call(panel.querySelectorAll("[data-wl-teacher-id]"), function (tile) {
            var hit = !needle || fold(tile.getAttribute("data-wl-teacher-name")).indexOf(needle) >= 0;
            tile.classList.toggle("is-filtered-out", !hit);
            if (hit) shown += 1;
        });
        var none = q("[data-wl-teacher-none]");
        if (none) none.hidden = !(needle && !shown);
    }

    function bind() {
        // Son klik edilən kart + onun ekrandakı yeri (capture mərhələsi: modal/dinləyicilərdən ƏVVƏL).
        document.addEventListener(
            "click",
            function (event) {
                var card = event.target && event.target.closest ? event.target.closest("[data-wl-card]") : null;
                if (!card || !onScreen(card)) return;
                last = {
                    key: card.getAttribute("data-card-key") || "",
                    top: card.getBoundingClientRect().top,
                    at: Date.now(),
                    moved: false,
                };
            },
            true
        );
        // İstifadəçi özü sürüşdürdü — qorunan yer buraxılır (onunla «dartışma» olmasın). Modal açıq ikən səhifə
        // kilidlidir: oradakı düymə/çarx hərəkəti siyahının yerini dəyişmir.
        var modalOpen = function () {
            return !!(document.body && document.body.classList.contains("modal-open"));
        };
        ["wheel", "touchmove", "keydown"].forEach(function (name) {
            document.addEventListener(
                name,
                function () {
                    if (modalOpen()) return;
                    pending = null;
                    last.moved = true;
                },
                { passive: true, capture: true }
            );
        });
        // Sürüşdürmə zolağı ilə hərəkət (çarx/düymə hadisəsi vermir) — öz düzləndirməmiz sayılmır.
        window.addEventListener(
            "scroll",
            function () {
                if (Date.now() < selfUntil || modalOpen()) return; // modal bağlanışı da `selfUntil`-i uzadır
                last.moved = true;
            },
            { passive: true }
        );
        // Modal tam bağlananda brauzer səhifəni tərpədə bilər — yer bir daha düzləndirilir.
        ["hide.bs.modal", "hidden.bs.modal"].forEach(function (name) {
            document.addEventListener(name, function () {
                selfUntil = Math.max(selfUntil, Date.now() + 600); // bağlanışın yaratdığı scroll istifadəçininki deyil
                if (name === "hidden.bs.modal") window.setTimeout(align, 0);
            });
        });
        document.addEventListener("input", function (event) {
            var field = event.target;
            if (!field || !field.matches || !field.matches("[data-wl-teacher-search]")) return;
            search = field.value || "";
            applySearch();
        });
    }

    window.EMSWorkloadAnchor = {
        capture: capture,
        restore: restore,
        applySearch: applySearch,
        /** Bölmə hər açılanda: axtarış və son klik sıfırlanır. */
        reset: function () {
            last = { key: "", top: 0, at: 0, moved: false };
            pending = null;
            search = "";
        },
    };

    if (window.EMSReady) {
        window.EMSReady.once("workload-distribution-anchor-bind", bind);
        window.EMSReady(function () { window.EMSWorkloadAnchor.reset(); });
    }
})(window, document);
