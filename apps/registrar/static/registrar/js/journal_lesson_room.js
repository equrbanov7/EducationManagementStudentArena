/* Dərs modalı — KORPUS → OTAQ kaskadı.
 *
 * Korpus AYRICA model deyil: otağın öz `building` sahəsidir. Ona görə korpus
 * seçimi yalnız otaq siyahısını daraldan süzgəcdir və forma POST-una GETMİR —
 * saxlanan yeganə dəyər otaqdır (`lesson_room`). Hər ikisi opsionaldır: köhnə
 * dərslərdə otaq yoxdur və boş qala bilər.
 *
 * Otaq siyahısı `json_script` bloku ilə gəlir (#jd-lesson-rooms) — xarici JS
 * Django şablonundan keçmədiyi üçün dinamik data DOM-dan oxunur. Siyahı kiçik
 * olduğundan (universitetdə onlarla/yüzlərlə otaq) ayrıca AJAX kaskadı yoxdur:
 * süzgəc dərhal, gözləmədən işləyir.
 *
 * QOŞULMA: journal_grid.js dərs modalını açanda `jd:lesson-modal-open` hadisəsini
 * göndərir (detail = redaktə datası, əlavə rejimində null). Bu modul yalnız ona
 * qulaq asır — yəni jurnal şəbəkəsi otaq məntiqindən xəbərsizdir və modul
 * yüklənməsə modal otaqsız da işləyir.
 */
(function () {
    "use strict";

    function rooms() {
        var el = document.getElementById("jd-lesson-rooms");
        if (!el) return [];
        try {
            return JSON.parse(el.textContent) || [];
        } catch (e) {
            return [];
        }
    }

    function buildingSelect(modal) {
        return modal ? modal.querySelector("[data-jd-lesson-building]") : null;
    }

    function roomSelect(modal) {
        return modal ? modal.querySelector("[data-jd-lesson-room]") : null;
    }

    function roomById(id) {
        var all = rooms();
        for (var i = 0; i < all.length; i++) {
            if (all[i].id === id) return all[i];
        }
        return null;
    }

    /** Otaq seçimlərini seçilmiş korpusa görə yenidən qurur; `keepId` varsa saxlayır. */
    function renderOptions(modal, building, keepId, setSelectValue) {
        var sel = roomSelect(modal);
        if (!sel) return;
        var placeholder = sel.querySelector('option[value=""]');
        var emptyLabel = placeholder ? placeholder.textContent : "";
        sel.innerHTML = "";
        var opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = emptyLabel;
        sel.appendChild(opt0);
        var found = false;
        rooms().forEach(function (room) {
            // Korpus seçilməyibsə HAMISI göstərilir (korpusu boş otaqlar da).
            if (building && room.building !== building) return;
            var opt = document.createElement("option");
            opt.value = room.id;
            opt.textContent = room.capacity ? room.name + " · " + room.capacity : room.name;
            sel.appendChild(opt);
            if (room.id === keepId) found = true;
        });
        setSelectValue(sel, found ? keepId : "");
    }

    /** Dəyəri qoy + `data-bootstrap-select` vidcetini sinxronla. */
    function setSelectValue(select, value) {
        if (!select) return;
        select.value = value || "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function bind(modal) {
        var b = buildingSelect(modal);
        if (!b || b.dataset.jdRoomBound === "1") return;
        b.dataset.jdRoomBound = "1";
        b.addEventListener("change", function () {
            renderOptions(modal, b.value, "", setSelectValue);
        });
    }

    /** Redaktədə: otağın korpusunu tapıb əvvəlcə onu, sonra otağı seç. */
    function apply(modal, roomId) {
        var room = roomById(roomId || "");
        setSelectValue(buildingSelect(modal), room ? room.building : "");
        renderOptions(modal, room ? room.building : "", roomId || "", setSelectValue);
    }

    document.addEventListener("jd:lesson-modal-open", function (event) {
        var modal = event.target;
        if (!modal || !roomSelect(modal)) return; // otaq sahəsi yoxdursa heç nə etmə
        apply(modal, (event.detail && event.detail.room) || "");
        bind(modal);
    });

    window.EMSJournalLessonRoom = { bind: bind, apply: apply };
})();
