/*
 * «Yük bölgüsü» — sətir siyahısı: tənbəl yükləmə + müəllimə görə süzgəc (`window.EMSWorkloadList`).
 *
 * 2026-10-25 (sahib):
 *   1. «Sağdakı hansı müəllimin üstünə vursam, ona görə filtr getsin» — sağ paneldəki müəllim kartı (düymə,
 *      `aria-pressed`) sol siyahını yalnız ona bölgüsü olan sətirlərə süzür; təkrar klik və ya «×» süzgəci
 *      götürür; vəziyyət URL-də (`?wl_teacher=<id>` / `vacant`) saxlanır və səhifə yenilənəndə qayıdır;
 *   2. «lazy loading» — kafedranın yüzlərlə sətri ilk açılışda 30-luq dilimlə gəlir, aşağı sürüşdükcə
 *      (IntersectionObserver; «Daha çox göstər» düyməsi ehtiyat/klaviatura yolu) növbəti dilim əlavə olunur.
 *
 * Əsas modul (`workload_distribution.js`) sorğunu `url()` ilə qurur və cavabı `afterLoad()`-a verir; bu modul
 * `window.EMSWorkloadDist` körpüsündən vəziyyəti oxuyur (ikinci STATE/fetch yoxdur). Null-safe: bu fayl
 * yüklənməsə əsas modul sətir yükləmir, amma səhifə çökmür. Dinləyicilər `EMSDelegate` ilə BİR dəfə qoşulur
 * (AJAX-safe); DOM axtarışı hər çağırışda yenidən aparılır.
 */
(function (window, document) {
    "use strict";

    var PAGE = 30; // ilk və sonrakı dilimlərin ölçüsü
    // Süzgəc açarı → URL parametri. `teacher` — sağ panel kartı / «Müəllim» seçicisi (SİNXRON), `status` — bölgü
    // vəziyyəti, `activity` — fəaliyyət növü (server tərəfi: `apps/workload/services/row_filters.py`).
    var URL_KEYS = { teacher: "wl_teacher", status: "wl_status", activity: "wl_activity" };

    var gettext = window.gettext || function (value) { return value; };

    var view = { teacher: "", status: "", activity: "" }; // teacher: "" | "vacant" | müəllim id-si
    var pool = { key: "", items: [] }; // kafedranın müəllimləri («Müəllim» seçicisi), kafedra/il üzrə bir dəfə
    var observer = null;
    var observed = null;

    function dist() {
        return window.EMSWorkloadDist || null;
    }

    function q(selector) {
        var d = dist();
        return d ? d.q(selector) : null;
    }

    function fmt(template, params) {
        if (typeof window.interpolate === "function") return window.interpolate(template, params, true);
        return template.replace(/%\((\w+)\)s/g, function (_, key) {
            return params[key] == null ? "" : String(params[key]);
        });
    }

    // ── URL vəziyyəti ───────────────────────────────────────────────────────
    function clean(value) {
        return /^[\w-]{1,64}$/.test(value || "") ? value : "";
    }

    function readUrl() {
        var found = { teacher: "", status: "", activity: "" };
        try {
            var params = new URLSearchParams(window.location.search);
            Object.keys(URL_KEYS).forEach(function (key) {
                found[key] = clean(params.get(URL_KEYS[key]));
            });
        } catch (err) {
            /* oxunmadısa süzgəc yoxdur */
        }
        return found;
    }

    function writeUrl(key, value) {
        try {
            var url = new URL(window.location.href);
            if (value) url.searchParams.set(URL_KEYS[key], value);
            else url.searchParams.delete(URL_KEYS[key]);
            window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
        } catch (err) {
            /* URL yazılmadısa süzgəc yenə işləyir — sadəcə yenilənəndə qalmır */
        }
    }

    // ── Sorğu ───────────────────────────────────────────────────────────────
    /**
     * `rows` endpoint-inin ünvanı. `opts.offset` — dilimin başlanğıcı; `opts.keep` — artıq yüklənmiş sətir sayı
     * (mutasiyadan sonra yenidən yükləmə HƏMİN qədəri qaytarsın ki, siyahı və sürüşmə yeri itməsin);
     * `opts.panel === false` — müəllim paneli gəlməsin (yalnız süzgəc dəyişib).
     */
    function url(base, params, opts) {
        opts = opts || {};
        var parts = ["chair", "year", "season", "q"].map(function (key) {
            return key + "=" + encodeURIComponent(params[key] || "");
        });
        Object.keys(view).forEach(function (key) {
            if (view[key]) parts.push(key + "=" + encodeURIComponent(view[key]));
        });
        parts.push("limit=" + Math.max(PAGE, opts.keep || 0));
        parts.push("offset=" + (opts.offset || 0));
        if (opts.panel === false) parts.push("panel=0");
        var d = dist();
        var host = d ? d.root() : null;
        var focus = host ? host.dataset.focusRow : "";
        if (focus && !opts.offset && d.state.focusedRow !== focus) parts.push("focus=" + encodeURIComponent(focus));
        return base + "?" + parts.join("&");
    }

    /** Təsdiq dialoqu üçün hazırlıq xülasəsi (sətirlər dilimlə gəldiyi üçün ayrıca, tapşırığın hamısı üzrə). */
    function loadReadiness(base, params) {
        var query = "chair=" + encodeURIComponent(params.chair || "") + "&year=" + encodeURIComponent(params.year || "");
        return window.EMSCore.fetchJSON(base + "?" + query + "&limit=0&readiness=1").then(function (payload) {
            return payload.readiness || null;
        });
    }

    // ── Süzgəclər (müəllim / vəziyyət / fəaliyyət) ──────────────────────────
    function refreshSelect(select) {
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    /** Seçicini cari süzgəcə uyğunlaşdır (kart klikindən / sıfırlamadan sonra; `change` hadisəsi YARATMIR). */
    function setSelect(select, value) {
        if (!select || select.value === value) return;
        select.value = value;
        refreshSelect(select);
    }

    function anyFilter() {
        var d = dist();
        var params = d ? d.filters() : {};
        return !!(view.teacher || view.status || view.activity || params.season || params.q);
    }

    function syncUi() {
        var host = q("[data-wl-teacher-panel]");
        var name = "";
        if (host) {
            host.querySelectorAll("[data-wl-teacher-id]").forEach(function (card) {
                var on = !!view.teacher && card.getAttribute("data-wl-teacher-id") === view.teacher;
                card.classList.toggle("is-active", on);
                card.setAttribute("aria-pressed", on ? "true" : "false");
                if (on) name = card.getAttribute("data-wl-teacher-name") || "";
            });
        }
        var select = q("[data-wl-teacher-select]");
        if (select && view.teacher) ensureOption(select, view.teacher, name || gettext("Seçilmiş müəllim"));
        setSelect(select, view.teacher);
        setSelect(q("[data-wl-status]"), view.status);
        setSelect(q("[data-wl-activity]"), view.activity);
        var reset = q("[data-wl-reset-filters]");
        if (reset) reset.hidden = !anyFilter();
        var bar = q("[data-wl-teacher-filter]");
        if (!bar) return;
        bar.hidden = !view.teacher;
        var label = bar.querySelector("[data-wl-teacher-filter-name]");
        if (label) label.textContent = name || gettext("Seçilmiş müəllim");
    }

    function setView(key, next) {
        next = clean(next);
        if (next === view[key]) return false;
        view[key] = next;
        writeUrl(key, next);
        syncUi();
        return true;
    }

    function setTeacher(next) {
        return setView("teacher", next);
    }

    // ── «Müəllim» seçicisi: tapşırıqda bölgüsü olanlar (sağ panel) + kafedranın müəllimləri ─────────────────
    function ensureOption(select, value, label) {
        var found = Array.prototype.some.call(select.options, function (option) {
            return option.value === value;
        });
        if (found) return;
        var option = select.ownerDocument.createElement("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
        refreshSelect(select);
    }

    function fillPicker() {
        var d = dist();
        var select = q("[data-wl-teacher-select]");
        if (!d || !select) return;
        var seen = {};
        var items = [];
        (d.state.teachers || []).forEach(function (card) {
            var id = card.is_vacant ? "vacant" : String(card.teacher_id);
            seen[id] = true;
            items.push({ id: id, label: card.name + " · " + card.hours + "s" });
        });
        pool.items.forEach(function (item) {
            var id = String(item.id);
            if (seen[id]) return;
            seen[id] = true;
            items.push({ id: id, label: item.full_name });
        });
        var doc = select.ownerDocument;
        select.innerHTML = "";
        var all = doc.createElement("option");
        all.value = "";
        all.textContent = gettext("Hamısı");
        select.appendChild(all);
        items.forEach(function (item) {
            var option = doc.createElement("option");
            option.value = item.id;
            option.textContent = item.label;
            select.appendChild(option);
        });
        refreshSelect(select);
        syncUi();
    }

    /** Kafedranın müəllim hovuzu (bölgüsü olmayanlar da seçilə bilsin); icazə yoxdursa səssiz — yalnız panel qalır. */
    function loadPool() {
        var d = dist();
        var host = d ? d.root() : null;
        if (!host || !host.dataset.teachersUrl) return;
        var params = d.filters();
        var key = params.chair + "|" + params.year;
        if (!params.chair || pool.key === key) return;
        pool = { key: key, items: [] };
        window.EMSCore.fetchJSON(
            host.dataset.teachersUrl + "?chair=" + encodeURIComponent(params.chair) + "&year=" + encodeURIComponent(params.year)
        )
            .then(function (payload) {
                if (pool.key !== key) return;
                pool.items = (payload && payload.results) || [];
                fillPicker();
            })
            .catch(function () {
                /* səssiz */
            });
    }

    /** «Filtrləri sıfırla»: müəllim, vəziyyət, fəaliyyət, semestr və axtarış — hamısı. */
    function resetAll() {
        Object.keys(view).forEach(function (key) {
            if (view[key]) {
                view[key] = "";
                writeUrl(key, "");
            }
        });
        var season = q("[data-wl-season]");
        if (season && season.value) {
            season.value = "";
            refreshSelect(season);
        }
        var search = q("[data-wl-search]");
        if (search) {
            if (window.EMSSearchInput && window.EMSSearchInput.cancel) window.EMSSearchInput.cancel(search);
            search.value = "";
        }
        syncUi();
        reload();
    }

    function reload() {
        var d = dist();
        if (!d) return;
        // Siyahı qısalacaq: başlığa qayıt (aşağıda sürüşmüş istifadəçi boş yerə düşməsin). `instant` — səhifənin
        // `scroll-behavior: smooth`-u sürüşmə davam edərkən siyahı qısalanda yeri pozurdu.
        var main = q(".wl__main");
        if (main && main.getBoundingClientRect().top < 0 && main.scrollIntoView) {
            main.scrollIntoView({ block: "start", behavior: "instant" });
        }
        d.loadRows({ fresh: true, panel: false });
    }

    // ── Sayğac, «daha çox» zolağı, boş vəziyyətlər ──────────────────────────
    function renderCount(state) {
        var node = q("[data-wl-count]");
        if (!node) return;
        node.hidden = !state.total;
        if (state.total) {
            node.textContent = fmt(gettext("Göstərilir: %(shown)s / %(total)s sətir"), {
                shown: state.rows.length,
                total: state.total,
            });
        }
    }

    function watch(node) {
        if (!node || typeof window.IntersectionObserver !== "function") return;
        if (!observer) {
            observer = new window.IntersectionObserver(
                function (entries) {
                    if (entries.some(function (entry) { return entry.isIntersecting; })) loadMore();
                },
                { rootMargin: "400px 0px" }
            );
        }
        if (observed && observed !== node) observer.unobserve(observed);
        // unobserve + observe: zolaq artıq görünürdürsə (böyük ekran) brauzer ilkin hesabatı YENİDƏN göndərsin.
        observer.unobserve(node);
        observer.observe(node);
        observed = node;
    }

    function renderMore(state, failed) {
        var more = q("[data-wl-more]");
        if (!more) return;
        more.hidden = !state.hasMore;
        var error = more.querySelector("[data-wl-more-error]");
        if (error) error.hidden = !failed;
        var button = more.querySelector("[data-wl-load-more]");
        if (button) {
            button.disabled = !!state.loadingMore;
            button.setAttribute("aria-busy", state.loadingMore ? "true" : "false");
        }
        more.classList.toggle("is-loading", !!state.loadingMore);
        if (state.hasMore && !failed) watch(more);
    }

    /** Hər dilim yükləndikdən sonra: say, boş vəziyyətlər, «daha çox» zolağı, müəllim vurğusu. */
    function afterLoad(payload) {
        var d = dist();
        if (!d) return;
        var state = d.state;
        state.total = payload.total || 0;
        state.nextOffset = payload.next_offset || 0;
        state.hasMore = !!payload.has_more;
        if (payload.teachers) {
            fillPicker(); // sağ panel yenilənib → «Müəllim» seçicisinin siyahısı da
            loadPool();
        }
        syncUi();
        var params = d.filters();
        var filtered = anyFilter();
        var none = state.rows.length === 0;
        var empty = q("[data-wl-empty]");
        var nomatch = q("[data-wl-nomatch]");
        if (empty) empty.hidden = !(none && (!state.task || !filtered));
        if (nomatch) nomatch.hidden = !(none && !!state.task && filtered);
        renderCount(state);
        renderMore(state, false);
    }

    function loadMore() {
        var d = dist();
        var host = d ? d.root() : null;
        var Render = window.EMSWorkloadRender;
        if (!host || !Render) return;
        var state = d.state;
        if (!state.hasMore || state.loading || state.loadingMore) return;
        state.loadingMore = true;
        renderMore(state, false);
        var mine = state.rowsSeq; // süzgəc dəyişibsə (yeni `loadRows`) köhnə cavab atılır
        window.EMSCore.fetchJSON(url(host.dataset.rowsUrl, d.filters(), { offset: state.nextOffset, panel: false }))
            .then(function (payload) {
                if (mine !== state.rowsSeq) return;
                var seen = {};
                state.rows.forEach(function (row) { seen[row.id] = true; });
                var added = (payload.rows || []).filter(function (row) { return !seen[row.id]; });
                state.rows = state.rows.concat(added);
                Render.rows(d.q("[data-wl-rows]"), added, d.labels(), { append: true, teacher: view.teacher });
                state.loadingMore = false;
                afterLoad(payload);
            })
            .catch(function () {
                state.loadingMore = false;
                // Xətada zolaq yenidən izlənmir (sonsuz cəhd yox); istifadəçi «Daha çox göstər» ilə təkrar cəhd edir.
                if (observer && observed) observer.unobserve(observed);
                renderMore(state, true);
            })
            .then(function () {
                state.loadingMore = false;
            });
    }

    function bind() {
        var EMSDelegate = window.EMSDelegate;
        if (!EMSDelegate) return;
        EMSDelegate.on("click", "[data-wl-teacher-id]", function (event, card) {
            var id = card.getAttribute("data-wl-teacher-id");
            setTeacher(id === view.teacher ? "" : id);
            reload();
        });
        EMSDelegate.on("click", "[data-wl-teacher-clear]", function () {
            if (setTeacher("")) reload();
        });
        EMSDelegate.on("click", "[data-wl-load-more]", loadMore);
        EMSDelegate.on("click", "[data-wl-reset-filters]", resetAll);
        // Müəllim seçicisi kart süzgəci ilə eyni vəziyyəti dəyişir; vəziyyət və fəaliyyət — server tərəfi süzgəc.
        [
            ["[data-wl-teacher-select]", "teacher"],
            ["[data-wl-status]", "status"],
            ["[data-wl-activity]", "activity"],
        ].forEach(function (pair) {
            EMSDelegate.on("change", pair[0], function (event, field) {
                if (setView(pair[1], field.value)) reload();
            });
        });
    }

    window.EMSWorkloadList = {
        PAGE: PAGE,
        url: url,
        loadReadiness: loadReadiness,
        afterLoad: afterLoad,
        teacher: function () { return view.teacher; },
        status: function () { return view.status; },
        activity: function () { return view.activity; },
        /** Süzgəci proqramla dəyiş (kafedra/il dəyişəndə təmizlənir) — YENİDƏN YÜKLƏMİR. */
        setTeacher: setTeacher,
        reset: resetAll,
        /** Bölmə hər açılanda: süzgəc URL-dən qayıdır. */
        restore: function () {
            view = readUrl();
            pool = { key: "", items: [] };
            observed = null;
            if (observer) observer.disconnect();
        },
        loadMore: loadMore,
    };

    if (window.EMSReady) window.EMSReady.once("workload-distribution-list-bind", bind);
})(window, document);
