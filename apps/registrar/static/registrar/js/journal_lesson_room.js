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
 * OTAQ YADDAŞI (sahib 2026-09-27): YENİ dərsdə bu qrupun EYNİ növ + həftə günü dərsində
 * əvvəl seçilmiş otaq (yoxdursa eyni növün son otağı) avtomatik dolur — mənbə serverdə
 * `lesson_rooms.remembered_rooms`, JSON adası `#jdRoomMemory`. Tarix/növ dəyişəndə
 * yenidən hesablanır, AMMA müəllim korpus/otağı özü seçibsə daha toxunulmur.
 * Yaddaş yoxdursa əvvəlki qayda: qrupun ixtisasına görə korpus defoltu.
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
            // Yalnız otaq NÖMRƏSİ (köhnə sistemdəki kimi) — tutum yazılmır: «11 · 18» iki
            // otaq kimi oxunurdu (sahib 2026-09-20).
            opt.textContent = room.name;
            sel.appendChild(opt);
            if (room.id === keepId) found = true;
        });
        // ⚠️ Native <option>-lar dəyişdi — `data-bootstrap-select` vidceti menyunu
        // YALNIZ ilkin qurulanda oxuyur; `refresh` olmasa müəllim korpus seçəndə
        // otaq siyahısı boş qalırdı (sahib şikayəti 2026-09-20).
        refreshWidget(sel);
        setSelectValue(sel, found ? keepId : "");
    }

    function refreshWidget(select) {
        if (select && window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    // Proqram dəyişikliyi gedərkən true — bu vaxt gələn `change` müəllimin seçimi sayılmır
    // (bootstrap-select vidceti də sintetik `change` göndərir, `isTrusted` fərqləndirmir).
    var _applying = false;

    /** Dəyəri qoy + `data-bootstrap-select` vidcetini sinxronla. */
    function setSelectValue(select, value) {
        if (!select) return;
        var prev = _applying;
        _applying = true;
        try {
            select.value = value || "";
            select.dispatchEvent(new Event("change", { bubbles: true }));
        } finally {
            _applying = prev;
        }
    }

    function bind(modal) {
        var b = buildingSelect(modal);
        if (!b || b.dataset.jdRoomBound === "1") return;
        b.dataset.jdRoomBound = "1";
        b.addEventListener("change", function () {
            if (!_applying) modal.dataset.jdRoomTouched = "1";
            renderOptions(modal, b.value, "", setSelectValue);
        });
        var r = roomSelect(modal);
        if (r) {
            r.addEventListener("change", function () {
                if (!_applying) modal.dataset.jdRoomTouched = "1";
            });
        }
        // Tarix / dərs tipi dəyişdi → yaddaşdan yenidən doldur (yalnız yeni dərsdə və toxunulmayıbsa).
        modal.addEventListener("change", function (event) {
            var t = event.target;
            if (_applying || !t || !t.matches("[data-jd-lesson-date], [name='lesson_kind']")) return;
            if (modal.dataset.jdRoomMode !== "add" || modal.dataset.jdRoomTouched === "1") return;
            apply(modal, "");
        });
    }

    function memory() {
        var node = document.getElementById("jdRoomMemory");
        if (!node) return {};
        try {
            var data = JSON.parse(node.textContent || "{}");
            return data && typeof data === "object" ? data : {};
        } catch (e) {
            return {};
        }
    }

    /** Yeni dərs üçün yaddaşdakı otaq: əvvəl «növ|həftə günü», sonra yalnız «növ». */
    function rememberedRoom(modal) {
        var mem = memory();
        var kindField = modal.querySelector("[name='lesson_kind']");
        var kind = kindField ? kindField.value : "";
        var dateField = modal.querySelector("[data-jd-lesson-date]");
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateField ? dateField.value : "");
        if (!kind) return "";
        if (m) {
            var iso = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay() || 7; // 1=B.e. … 7=Bazar
            var exact = mem[kind + "|" + iso];
            if (exact && roomById(exact)) return exact;
        }
        var byKind = mem[kind];
        return byKind && roomById(byKind) ? byKind : "";
    }

    function showMemoryHint(modal, on) {
        var memHint = modal.querySelector("[data-jd-room-memory-hint]");
        var hint = modal.querySelector("[data-jd-room-hint]");
        if (memHint) memHint.hidden = !on;
        if (hint) hint.hidden = Boolean(on && memHint);
    }

    /** Korpus seçimində mövcud olan defolt (yoxdursa boş). */
    function defaultBuilding(modal) {
        var wanted = (modal.dataset.defaultBuilding || "").trim();
        var sel = buildingSelect(modal);
        if (!wanted || !sel) return "";
        for (var i = 0; i < sel.options.length; i++) {
            if (sel.options[i].value === wanted) return wanted;
        }
        return "";
    }

    /** Redaktədə: otağın korpusunu tapıb əvvəlcə onu, sonra otağı seç.
     *  Əlavə rejimində (otaq yoxdur): qrupun ixtisasına görə korpus defoltu
     *  (`data-default-building`, sahib qərarı 2026-09-20) — müəllim dəyişə bilər. */
    function apply(modal, roomId) {
        var fromMemory = "";
        if (!roomId && modal.dataset.jdRoomMode === "add") {
            fromMemory = rememberedRoom(modal);
            roomId = fromMemory;
        }
        var room = roomById(roomId || "");
        var building = room ? room.building : defaultBuilding(modal);
        setSelectValue(buildingSelect(modal), building);
        renderOptions(modal, building, roomId || "", setSelectValue);
        showMemoryHint(modal, Boolean(fromMemory));
    }

    document.addEventListener("jd:lesson-modal-open", function (event) {
        var modal = event.target;
        if (!modal || !roomSelect(modal)) return; // otaq sahəsi yoxdursa heç nə etmə
        modal.dataset.jdRoomMode = event.detail ? "edit" : "add";
        delete modal.dataset.jdRoomTouched;
        ensureRooms(modal, function () {
            apply(modal, (event.detail && event.detail.room) || "");
            bind(modal);
        });
    });

    window.EMSJournalLessonRoom = { bind: bind, apply: apply };
})();
