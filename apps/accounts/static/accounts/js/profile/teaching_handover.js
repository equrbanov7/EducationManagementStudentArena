/**
 * «Fənn təhvili» — seçim, xülasə və təsdiq axını.
 *
 * 2026-09-09: bölmə SPA-dan `ems_ui` server-render panelinə keçdi, ona görə bu
 * fayl ARTIQ cədvəl çəkmir. Serverin verdiyi markup üzərində yalnız dörd iş var:
 *
 *   1. SEÇİM      — hansı fənlər seçilib (səhifələr arasında saxlanılır);
 *   2. GÖSTƏRİCİ  — sabit zolaq, KPI kartları və mərhələ zolağı seçimlə yenilənir;
 *   3. XÜLASƏ     — təsdiqdən əvvəl NƏ KÖÇÜR / NƏ DƏYİŞMİR açıq yazılır;
 *   4. ÇEKMECƏ    — sətir detalı (paylaşılan tək çekmecə sətirlə doldurulur).
 *
 * GÖNDƏRİŞ BU FAYLDA DEYİL: təsdiq forması ortaq `teaching_office.js`
 * mexanizmindədir (`form[data-tof-form]` → JSON POST → bölməni yenidən yüklə).
 * Ona görə forma göndərilən anda əlavə JS lazım deyil — seçilmiş sətirlər
 * dialoq açılanda GİZLİ `offering_ids` sahələri kimi formaya yazılır və
 * «Yeni müəllim» seçicisinin adı birbaşa `new_instructor_id`-dir.
 *
 * AJAX-safe (docs/frontend/AJAX_SAFE_JS_PATTERN.md): `EMSDelegate` + `EMSReady`,
 * null-safe axtarışlar. Dinamik dəyərlər yalnız `data-*` atributlarından oxunur
 * (CSP: inline JS yoxdur).
 */
(function (window, document) {
    "use strict";

    var STORE_KEY = "ems.handover.selection";
    var SECTION = "teaching-handover";

    /* ---- Seçim yaddaşı ---------------------------------------------------
       Seçim SƏHİFƏLƏR ARASINDA saxlanılır: toplu təhvildə 2-ci səhifəyə keçib
       qayıdanda seçimin itməsi ən əsəb pozucu haldır. Yaddaş sessiyalıqdır —
       brauzer bağlananda qalmır (köhnə seçim başqa gün «sürpriz» olmasın). */

    function readStore() {
        try {
            return JSON.parse(window.sessionStorage.getItem(STORE_KEY) || "{}") || {};
        } catch (err) {
            return {};
        }
    }

    function writeStore(value) {
        try {
            window.sessionStorage.setItem(STORE_KEY, JSON.stringify(value));
        } catch (err) {
            /* private mode / kvota — seçim yalnız bu səhifədə yaşayır */
        }
    }

    function clearStore() {
        try {
            window.sessionStorage.removeItem(STORE_KEY);
        } catch (err) {
            /* yuxarıdakı ilə eyni səbəb */
        }
    }

    function root() {
        return document.querySelector("[data-thx-root]");
    }

    function labels(host) {
        var node = host ? host.querySelector("[data-thx-i18n]") : null;
        return node ? node.dataset : {};
    }

    function num(value) {
        var parsed = parseInt(value, 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    /* ---- Göstəricilər ---------------------------------------------------- */

    function totals(store) {
        var sum = { count: 0, students: 0, lessons: 0, marks: 0 };
        Object.keys(store).forEach(function (id) {
            var row = store[id] || {};
            sum.count += 1;
            sum.students += num(row.students);
            sum.lessons += num(row.lessons);
            sum.marks += num(row.marks);
        });
        return sum;
    }

    function setKpi(host, key, value) {
        var tile = host.querySelector('[data-ems-kpi-key="' + key + '"] .ems-kpi__value');
        if (tile) {
            tile.textContent = String(value);
        }
    }

    /** Mərhələ zolağı seçimlə birlikdə irəliləyir — «hansı addımdayam» sualı
     *  cavabsız qalmasın. 2-ci addım seçim varsa «done», 3-cü isə «current». */
    function paintSteps(host, count) {
        var steps = host.querySelectorAll(".ems-steps .ems-step");
        if (steps.length < 4) {
            return;
        }
        setStep(steps[1], count ? "done" : "current");
        setStep(steps[2], count ? "current" : "todo");
        setStep(steps[3], "todo");
    }

    function setStep(el, state) {
        el.className = "ems-step ems-step--" + state;
    }

    function refresh(host) {
        host = host || root();
        if (!host) {
            return;
        }
        var store = readStore();
        var sum = totals(store);
        var text = labels(host);
        var bar = host.querySelector("[data-thx-bar]");
        var barText = host.querySelector("[data-thx-bar-text]");

        if (barText) {
            barText.textContent = sum.count + " " + (text.selectedOne || "");
        }
        if (bar) {
            bar.hidden = sum.count === 0;
        }
        setKpi(host, "selected", sum.count);
        setKpi(host, "students", sum.students);
        paintSteps(host, sum.count);

        var boxes = host.querySelectorAll("[data-thx-select]");
        for (var i = 0; i < boxes.length; i += 1) {
            boxes[i].checked = Object.prototype.hasOwnProperty.call(store, boxes[i].value);
        }
        var all = host.querySelector("[data-thx-select-all]");
        if (all) {
            var open = host.querySelectorAll("[data-thx-select]:not([disabled])");
            var picked = host.querySelectorAll("[data-thx-select]:not([disabled]):checked");
            all.checked = open.length > 0 && open.length === picked.length;
            all.indeterminate = picked.length > 0 && picked.length < open.length;
        }
    }

    function rowInfo(box) {
        return {
            name: box.getAttribute("data-thx-name") || "",
            group: box.getAttribute("data-thx-group") || "",
            students: num(box.getAttribute("data-thx-students")),
            lessons: num(box.getAttribute("data-thx-lessons")),
            marks: num(box.getAttribute("data-thx-marks")),
        };
    }

    function maxBulk(host) {
        var limit = num(host && host.getAttribute("data-thx-max-bulk"));
        return limit > 0 ? limit : 100;
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    /** Seçimi dəyişir; `false` qaytarırsa hədd səbəbindən qəbul edilmədi.
     *
     *  Toplu həddi (`MAX_BULK_ROWS`) SERVERDƏ də var və 400 verir — amma
     *  istifadəçi 120 sətir seçib «Təhvil ver» basandan SONRA xəta almamalıdır;
     *  hədd elə seçim anında deyilir. */
    function toggle(host, box, on) {
        var store = readStore();
        if (on) {
            if (!Object.prototype.hasOwnProperty.call(store, box.value)) {
                if (Object.keys(store).length >= maxBulk(host)) {
                    box.checked = false;
                    return false;
                }
            }
            store[box.value] = rowInfo(box);
        } else {
            delete store[box.value];
        }
        writeStore(store);
        return true;
    }

    /* ---- Təsdiq pəncərəsi ------------------------------------------------ */

    /** Seçilmiş sətirləri GİZLİ sahələr kimi formaya yazır.
     *
     *  Server müqaviləsi: `offering_ids` (təkrarlanan) + `new_instructor_id`.
     *  Beləcə göndəriş anında JS lazım olmur — ortaq `teaching_office.js`
     *  formanı olduğu kimi POST edir (bir dinləyici, bir yol). */
    function fillForm(form, store) {
        var old = form.querySelectorAll("[data-thx-item]");
        for (var i = 0; i < old.length; i += 1) {
            old[i].parentNode.removeChild(old[i]);
        }
        var anchor = form.querySelector(".ems-dialog__body") || form;
        Object.keys(store).forEach(function (id) {
            var input = document.createElement("input");
            input.type = "hidden";
            input.name = "offering_ids";
            input.value = id;
            input.setAttribute("data-thx-item", "1");
            anchor.appendChild(input);
        });
    }

    function paintSummary(host, form, store) {
        var list = form.querySelector("[data-thx-summary-list]");
        var total = form.querySelector("[data-thx-summary-total]");
        var text = labels(host);
        var sum = totals(store);
        if (list) {
            list.textContent = "";
            Object.keys(store).forEach(function (id) {
                var row = store[id] || {};
                var li = document.createElement("li");
                var name = document.createElement("b");
                name.textContent = row.name || id;
                li.appendChild(name);
                li.appendChild(
                    document.createTextNode(
                        (row.group ? " · " + row.group : "") +
                            " — " +
                            num(row.students) + " " + (text.students || "") + " · " +
                            num(row.lessons) + " " + (text.lessons || "") + " · " +
                            num(row.marks) + " " + (text.marks || "")
                    )
                );
                list.appendChild(li);
            });
        }
        if (total) {
            total.textContent =
                sum.count + " " + (text.selectedOne || "") + " — " +
                sum.students + " " + (text.students || "") + " · " +
                sum.lessons + " " + (text.lessons || "") + " · " +
                sum.marks + " " + (text.marks || "");
        }
    }

    function openConfirm(host) {
        var dialog = document.getElementById("thxConfirmDialog");
        var form = dialog ? dialog.querySelector("form") : null;
        if (!dialog || !form) {
            return;
        }
        var store = readStore();
        if (!Object.keys(store).length) {
            toast(labels(host).needsSelection, "warning");
            return;
        }
        var error = form.querySelector("[data-ems-form-error]");
        if (error) {
            error.hidden = true;
            error.textContent = "";
        }
        fillForm(form, store);
        paintSummary(host, form, store);
        if (window.EMSOverlay) {
            window.EMSOverlay.open(dialog);
        }
    }

    /* ---- Sətir çekmecəsi -------------------------------------------------- */

    function fillDrawer(host, payload) {
        var drawer = document.getElementById("thxRowDrawer");
        if (!drawer) {
            return null;
        }
        var map = {
            subject: payload.subject_name || "",
            group: payload.group || "—",
            period: payload.period || "—",
            instructor: payload.instructor || (labels(host).none || "—"),
            students: payload.students,
            lessons: payload.lessons,
            marks: payload.marks,
        };
        Object.keys(map).forEach(function (key) {
            var node = drawer.querySelector("[data-thx-d-" + key + "]");
            if (node) {
                node.textContent = String(map[key] === undefined || map[key] === "" ? "—" : map[key]);
            }
        });
        var why = drawer.querySelector("[data-thx-d-why]");
        var whyText = drawer.querySelector("[data-thx-d-why-text]");
        if (why && whyText) {
            whyText.textContent = payload.blocker_text || "";
            why.hidden = !payload.blocker_text;
        }
        var action = drawer.querySelector("[data-thx-drawer-transfer]");
        if (action) {
            action.hidden = !payload.can_transfer;
            action.value = payload.id || "";
        }
        return drawer;
    }

    function readPayload(btn) {
        try {
            return JSON.parse(btn.getAttribute("data-thx-payload") || "{}") || {};
        } catch (err) {
            return {};
        }
    }

    /** Tək sətri seçib təsdiq pəncərəsini açır (seçimi ƏVƏZ edir, üstünə
     *  yığmır — «bu fənni ver» düyməsi məhz BU fənni nəzərdə tutur). */
    function transferOnly(host, id) {
        var box = host.querySelector('[data-thx-select][value="' + id + '"]');
        if (!box || box.disabled) {
            return;
        }
        clearStore();
        toggle(host, box, true);
        refresh(host);
        openConfirm(host);
    }

    /* ---- Hadisələr -------------------------------------------------------- */

    window.EMSDelegate.on("change", "[data-thx-select]", function (event, box) {
        var host = box.closest("[data-thx-root]");
        if (!toggle(host, box, box.checked)) {
            toast(labels(host).maxBulk, "warning");
        }
        refresh(host);
    });

    /* «Bu səhifədə təhvilə açıq olanların hamısını seç» — BLOKLANMIŞ sətirlər
       qəsdən kənarda qalır (onların qutusu `disabled`-dır) və istifadəçiyə
       neçəsinin buraxıldığı deyilir; səssiz atlama «niyə 25 yox, 22 seçildi»
       sualını doğurardı. */
    window.EMSDelegate.on("change", "[data-thx-select-all]", function (event, box) {
        var host = box.closest("[data-thx-root]");
        if (!host) {
            return;
        }
        var open = host.querySelectorAll("[data-thx-select]:not([disabled])");
        var blocked = host.querySelectorAll("[data-thx-select][disabled]").length;
        var refused = false;
        for (var i = 0; i < open.length; i += 1) {
            if (!toggle(host, open[i], box.checked)) {
                refused = true;
            }
        }
        var text = labels(host);
        if (refused) {
            toast(text.maxBulk, "warning");
        } else if (box.checked && blocked) {
            toast(text.blockedSkip, "info");
        }
        refresh(host);
    });

    window.EMSDelegate.on("click", "[data-thx-clear-selection]", function (event, btn) {
        event.preventDefault();
        clearStore();
        refresh(btn.closest("[data-thx-root]"));
    });

    window.EMSDelegate.on("click", "[data-thx-confirm-open]", function (event, btn) {
        event.preventDefault();
        openConfirm(btn.closest("[data-thx-root]"));
    });

    window.EMSDelegate.on("click", "[data-thx-detail]", function (event, btn) {
        event.preventDefault();
        var host = btn.closest("[data-thx-root]");
        var drawer = fillDrawer(host, readPayload(btn));
        if (drawer && window.EMSOverlay) {
            window.EMSOverlay.open(drawer);
        }
    });

    window.EMSDelegate.on("click", "[data-thx-row-transfer]", function (event, btn) {
        event.preventDefault();
        transferOnly(btn.closest("[data-thx-root]"), btn.value);
    });

    window.EMSDelegate.on("click", "[data-thx-drawer-transfer]", function (event, btn) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.close(document.getElementById("thxRowDrawer"));
        }
        transferOnly(host, btn.value);
    });

    /* Tab keçidi SERVER tərəfdədir (lazy): «Tarixçə» açılana qədər tarixçə
       heç hesablanmır. `ems_ui/nav.js` panelləri dərhal dəyişir (skeleton
       görünür), biz isə bölməni doğru tabla yenidən yükləyirik. */
    document.addEventListener("ems:tab", function (event) {
        var host = root();
        var detail = event && event.detail ? event.detail : {};
        if (!host || !detail.tab || !host.contains(event.target)) {
            return;
        }
        if ((host.getAttribute("data-thx-tab") || "") === detail.tab) {
            return;
        }
        var param = host.getAttribute("data-thx-tab-param") || "handover_tab";
        var url = new URL(window.location.pathname, window.location.origin);
        var search = new URLSearchParams(window.location.search);
        search.set("section", SECTION);
        search.delete("th_page");
        if (detail.tab === "history") {
            search.set(param, "history");
        } else {
            search.delete(param);
        }
        url.search = search.toString();
        if (window.EMSProfileLoadSection) {
            window.EMSProfileLoadSection(SECTION, url.toString());
        } else {
            window.location.assign(url.toString());
        }
    });

    /* Təhvil BAŞ TUTANDAN sonra seçim yaddaşı təmizlənməlidir — əks halda
       bölmə yenidən yüklənəndə sabit zolaq artıq KÖÇMÜŞ fənləri «seçilib» kimi
       göstərərdi.

       Göndərişin özü ortaq `teaching_office.js`-dədir və uğur callback-i bizə
       görünmür; ona görə bayraq qoyulur və bölmə yenidən YÜKLƏNƏNDƏ (yalnız
       uğurlu POST bunu edir) yaddaş boşaldılır. Uğursuz göndərişdə dialoq açıq
       qalır, gizli `offering_ids` sahələri yerindədir — təkrar cəhd işləyir. */
    var pendingSubmit = false;

    window.EMSDelegate.on("submit", "#thxConfirmDialog form", function () {
        pendingSubmit = true;
    });

    document.addEventListener("profile:section:loaded", function (event) {
        var detail = (event && event.detail) || {};
        if (detail.section && detail.section !== SECTION) {
            return;
        }
        if (pendingSubmit) {
            pendingSubmit = false;
            clearStore();
        }
    });

    window.EMSReady(function () {
        var host = root();
        if (!host) {
            return;
        }
        // Seçim səhifələr arasında saxlanılır (bax yuxarıdakı «Seçim yaddaşı»);
        // swap-dan sonra qutular yaddaşdan geri işarələnir.
        refresh(host);
    });
})(window, document);
