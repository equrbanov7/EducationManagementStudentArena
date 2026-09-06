/* Dərs modalı — KORPUS → OTAQ kaskadı.
 *
 * Korpus AYRICA model deyil: otağın öz `building` sahəsidir. Ona görə korpus
 * seçimi yalnız otaq siyahısını daraldan süzgəcdir və forma POST-una GETMİR —
 * saxlanan yeganə dəyər otaqdır (`lesson_room`). Hər ikisi opsionaldır: köhnə
 * dərslərdə otaq yoxdur və boş qala bilər.
 *
 * Otaq siyahısı əvvəllər `json_script` bloku ilə HƏR jurnal səhifəsi
 * yüklənməsində modala bişirilirdi (159 otağa qədər). QA 2026-09-05 P3-13:
 * indi modal İLK dəfə açılanda `data-rooms-url`-dan (bax
 * `_jd_lesson_modal.html`) AJAX ilə gətirilir və bu modulun ömrü boyu
 * keşlənir — kaskadın özü (korpus süzgəci) DƏYİŞMİR, dinamik olan yalnız
 * data mənbəyidir.
 *
 * QOŞULMA: journal_grid.js dərs modalını açanda `jd:lesson-modal-open` hadisəsini
 * göndərir (detail = redaktə datası, əlavə rejimində null). Bu modul yalnız ona
 * qulaq asır — yəni jurnal şəbəkəsi otaq məntiqindən xəbərsizdir və modul
 * yüklənməsə modal otaqsız da işləyir.
 */
(function () {
    "use strict";

    var _cache = null; // null = hələ gətirilməyib; [] = gətirilib, boşdur.
    var _pending = null;

    function rooms() {
        return _cache || [];
    }

    /** Otaq siyahısını (bir dəfə) gətirir, sonra keşdən qaytarır. */
    function ensureRooms(modal, callback) {
        if (_cache) {
            callback();
            return;
        }
        if (_pending) {
            _pending.push(callback);
            return;
        }
        _pending = [callback];
        var url = modal.dataset.roomsUrl;
        if (!url) {
            _cache = [];
            _pending.forEach(function (cb) {
                cb();
            });
            _pending = null;
            return;
        }
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (r) {
                return r.ok ? r.json() : [];
            })
            .then(function (data) {
                _cache = Array.isArray(data) ? data : [];
            })
            .catch(function () {
                _cache = [];
            })
            .finally(function () {
                var queued = _pending || [];
                _pending = null;
                queued.forEach(function (cb) {
                    cb();
                });
            });
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
        ensureRooms(modal, function () {
            apply(modal, (event.detail && event.detail.room) || "");
            bind(modal);
        });
    });

    window.EMSJournalLessonRoom = { bind: bind, apply: apply };
})();
