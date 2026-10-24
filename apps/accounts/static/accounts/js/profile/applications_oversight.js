/* «Müraciətlərim» — «Bütün müraciətlər» (RİM nəzarəti) tabının ŞÖBƏ süzgəcləri.
 *
 * Niyə ayrı fayl? `applications.js` ölçü büdcəsinin (600 sətir) həddindədir. Bu fayl
 * yalnız DOM ↔ vəziyyət sinxronudur (`NS.state.unit` / `NS.state.senderUnit`); sorğunu
 * `applications.js`-in `loadList`-i göndərir, parametrləri isə `NS.api.list`
 * (`applications_core.js`) hər çağırışda `NS.oversight.params()`-dan götürür — ona
 * görə tab dəyişəndə (klik, KPI kartı) süzgəcin görünüşü də ELƏ ORADA yenilənir.
 *
 * Süzgəclər YALNIZ «Bütün müraciətlər» tabında göndərilir. Server onları yenə də
 * görünən dəstə tətbiq edir (`queries.list_applications`) — gizli dəyər heç nə açmır.
 * Partial yalnız nəzarətçiyə render olunur; DOM-da yoxdursa hər şey no-op-dur.
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    function box() {
        return NS.root && NS.root.querySelector("[data-apx-oversight]");
    }

    function control(which) {
        return NS.root && NS.root.querySelector("[data-apx-oversight-" + which + "]");
    }

    function isActive() {
        return !!(NS.state && NS.state.tab === "all" && box());
    }

    /* Native `<select>` → dəyər + `bootstrap-single-select` düyməsinin etiketi + «aktiv» tonu. */
    function paint(select, value) {
        if (!select) {
            return;
        }
        if (select.value !== value) {
            select.value = value;
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
        }
        var field = select.closest("[data-apx-oversight-field]");
        if (field) {
            field.classList.toggle("is-active", !!value);
        }
    }

    /* Vəziyyət → DOM: görünüş (yalnız «all» tabı) + seçilmiş dəyərlər. */
    function sync() {
        var host = box();
        if (!host || !NS.state) {
            return;
        }
        host.hidden = !isActive();
        paint(control("unit"), NS.state.unit || "");
        paint(control("sender"), NS.state.senderUnit || "");
    }

    /* `NS.api.list` bunu hər sorğudan əvvəl çağırır. */
    function params() {
        sync();
        if (!isActive()) {
            return {};
        }
        return { unit: NS.state.unit || "", sender_unit: NS.state.senderUnit || "" };
    }

    /* DOM → vəziyyət → yenidən yüklə. */
    function apply() {
        var unit = control("unit");
        var sender = control("sender");
        NS.state.unit = unit ? unit.value : "";
        NS.state.senderUnit = sender ? sender.value : "";
        NS.state.page = 1;
        NS.loadList();
    }

    function reset() {
        if (!NS.state) {
            return;
        }
        NS.state.unit = "";
        NS.state.senderUnit = "";
        sync();
    }

    NS.oversight = { params: params, reset: reset, sync: sync };

    function start() {
        if (NS.__oversightWired) {
            return;
        }
        NS.__oversightWired = true;

        window.EMSDelegate.on("change", "[data-apx-oversight-unit]", apply);
        window.EMSDelegate.on("change", "[data-apx-oversight-sender]", apply);
        // Swap-dan sonra panel yeni DOM-la gəlir — görünüş/seçim vəziyyətə uyğunlaşsın.
        window.EMSReady(function () {
            sync();
        });
    }

    /* Panel script-ləri `ems_ajax_init.js`-dən ƏVVƏL parse oluna bilər; qeydiyyat
     * primitivlər hazır olana qədər gözləyir (`applications_filters.js` ilə eyni). */
    (function ready(attempt) {
        if (window.EMSDelegate && window.EMSReady) {
            start();
            return;
        }
        if (attempt > 200) {
            return;
        }
        window.setTimeout(function () {
            ready(attempt + 1);
        }, 25);
    })(0);
})();
