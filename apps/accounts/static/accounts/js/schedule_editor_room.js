/* Cədvəl redaktoru — «Xanaya dərs qoy» dialoqunun KORPUS → OTAQ seçiciləri (sahib 2026-10-17).
 *
 * «Korpusa uyğun otaqları düz seç»: otaq adları korpuslar arasında təkrarlanır («203» həm 1-ci, həm
 * 2-ci korpusda), ona görə otaq siyahısı YALNIZ seçilmiş korpusun otaqlarıdır. Siyahı SERVER-render-lidir
 * (`schedule/_cell_fields.html`, `registrar/schedule_rooms.py`): hər `<option>`-da `data-building` +
 * `data-text` («33 · 40 nəfər») var; süzgəc `option.hidden` + `EMSBootstrapSelect.refresh` ilə işləyir
 * (stilli menyu gizli variantları göstərmir). «Bütün korpuslar» seçiləndə mətnə korpus əlavə olunur.
 *
 * QAYDALAR
 *   · yeni xana → korpus qrupun ixtisas korpusu (`data-default-building`; müəllim görünüşündə qrup dialoqda
 *     seçildiyi üçün `action=plan` cavabının `campus`-u — `applyDefault`, planlayıcı çağırır);
 *   · redaktə → kartın otağının korpusu (eyni ad bir neçə korpusdadırsa əvvəl qrupun korpusu); otaq
 *     reyestrdə yoxdursa (köhnə idxal mətni) ayrıca variant kimi SAXLANILIR, korpusdan asılı olmadan görünür;
 *   · korpus dəyişəndə otaq həmin korpusda deyilsə sıfırlanır və otağa `change` gedir (adi yoxlama);
 *   · planlayıcının otaq təklifinə klik başqa korpusdandırsa korpus seçicisi də keçir (`pick`).
 *   POST-a yenə yalnız otaq MƏTNİ gedir (`room`); korpus (`room_building`) yalnız `plan` sıralamasındadır.
 *
 * AJAX-safe: `EMSDelegate` ilə document səviyyəsində; dialoq / seçici yoxdursa heç nə etmir (otaq reyestri
 * boş olanda dialoqda sərbəst mətn sahəsi qalır — bu modul ona toxunmur).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    var DIALOG_ID = "seditCell";
    var EXTRA = "data-sedit-room-extra";
    var state = { applying: false, touched: false, isNew: true, legacy: false };

    function dialog() {
        return document.getElementById(DIALOG_ID);
    }

    function buildingSelect() {
        var box = dialog();
        return box ? box.querySelector("select[data-sedit-room-building]") : null;
    }

    function roomSelect() {
        var box = dialog();
        return box ? box.querySelector("select[data-sedit-room]") : null;
    }

    function widget(select, rebuild) {
        var api = window.EMSBootstrapSelect;
        if (!select || !api) {
            return;
        }
        var fn = rebuild ? api.refresh : api.sync;
        if (typeof fn === "function") {
            fn(select);
        }
    }

    function notify(select) {
        if (!select) {
            return;
        }
        var prev = state.applying;
        state.applying = true;
        try {
            select.dispatchEvent(new Event("change", { bubbles: true }));
        } finally {
            state.applying = prev;
        }
    }

    function roomOptions(select) {
        return Array.prototype.filter.call(select.options, function (opt) {
            return Boolean(opt.value);
        });
    }

    function hasBuilding(value) {
        var select = buildingSelect();
        return Boolean(select) && Array.prototype.some.call(select.options, function (opt) {
            return opt.value === value;
        });
    }

    function defaultBuilding() {
        var select = buildingSelect();
        var value = select ? select.getAttribute("data-default-building") || "" : "";
        return hasBuilding(value) ? value : "";
    }

    /* Seçilmiş korpusun otaqları görünür; dəyər görünən variantdadırsa saxlanılır, yoxsa sıfırlanır.
       Qaytarır: otağın dəyəri dəyişdimi. Eyni adlı otaq bir neçə korpusdadırsa GÖRÜNƏN variant seçilir. */
    function filter(building) {
        var select = roomSelect();
        if (!select) {
            return false;
        }
        var keep = select.value;
        var match = null;
        roomOptions(select).forEach(function (opt) {
            var own = opt.getAttribute("data-building") || "";
            var text = opt.getAttribute("data-text") || opt.value;
            opt.hidden = !opt.hasAttribute(EXTRA) && Boolean(building) && own !== building;
            opt.textContent = building || !own ? text : text + " — " + own;
            if (!match && !opt.hidden && opt.value === keep) {
                match = opt;
            }
        });
        if (match) {
            match.selected = true;
        } else {
            select.value = "";
        }
        widget(select, true);
        return select.value !== keep;
    }

    function setBuilding(value) {
        var select = buildingSelect();
        if (!select) {
            return;
        }
        select.value = hasBuilding(value) ? value : "";
        widget(select, false);
    }

    /* Otağın korpusu: əvvəl `prefer` (qrupun korpusu / cari korpus), sonra siyahıdakı ilk. Reyestrdə yoxdursa null. */
    function buildingOf(room, prefer) {
        var select = roomSelect();
        var found = [];
        roomOptions(select).forEach(function (opt) {
            if (!opt.hasAttribute(EXTRA) && opt.value === room) {
                found.push(opt.getAttribute("data-building") || "");
            }
        });
        if (!found.length) {
            return null;
        }
        return found.indexOf(prefer) !== -1 ? prefer : found[0];
    }

    function dropLegacy(select) {
        select.querySelectorAll("option[" + EXTRA + "]").forEach(function (opt) {
            opt.remove();
        });
        state.legacy = false;
    }

    function addLegacy(select, room) {
        var opt = document.createElement("option");
        opt.value = room;
        opt.textContent = room;
        opt.setAttribute("data-text", room);
        opt.setAttribute(EXTRA, "1");
        var first = select.options[0];
        select.insertBefore(opt, first ? first.nextSibling : null);
        state.legacy = true;
    }

    function selectRoom(room) {
        var select = roomSelect();
        var match = roomOptions(select).filter(function (opt) {
            return !opt.hidden && opt.value === room;
        })[0];
        if (match) {
            match.selected = true;
        } else {
            select.value = "";
        }
        widget(select, false);
    }

    function updateHint() {
        var box = dialog();
        var node = box ? box.querySelector("[data-sedit-room-hint]") : null;
        var korpus = buildingSelect();
        if (!node || !korpus) {
            return;
        }
        var key = "";
        if (state.legacy) {
            key = "tLegacy";
        } else if (!korpus.value && korpus.options.length > 1) {
            key = "tPick";
        } else if (state.isNew && !state.touched && korpus.value && korpus.value === defaultBuilding()) {
            key = "tDefault";
        }
        node.textContent = key ? node.dataset[key] || "" : "";
        node.hidden = !node.textContent;
    }

    /* Dialoq açılışı: yeni xana → qrupun korpusu; redaktə → otağın korpusu + otağın özü. */
    function apply(room) {
        var select = roomSelect();
        if (!select || !buildingSelect()) {
            return;
        }
        dropLegacy(select);
        var home = defaultBuilding();
        var building = home;
        if (room) {
            var own = buildingOf(room, home);
            if (own === null) {
                addLegacy(select, room);
            } else {
                building = own;
            }
        }
        setBuilding(building);
        filter(buildingSelect().value);
        selectRoom(room || "");
        updateHint();
    }

    function slotRoom() {
        var box = dialog();
        var slot = box ? box.querySelector('[data-sedit-field="slot_id"]') : null;
        var id = slot ? slot.value : "";
        var card = id ? document.querySelector('[data-sedit-slot="' + id + '"]') : null;
        return { isNew: !id, room: card ? (card.getAttribute("data-room") || "").trim() : "" };
    }

    /* ⚠️ `EMSDelegate.on` açarı «hadisə|selektor»dur — eyni açar əvvəlkini ƏVƏZ edir; digər modullar
       `#seditCell` / `[id='seditCell']` işlədir, ona görə burada fərqli yazılış. */
    DELEGATE.on("ems:overlay:open", "div#" + DIALOG_ID, function () {
        if (!roomSelect()) {
            return;
        }
        var info = slotRoom();
        state.isNew = info.isNew;
        state.touched = false;
        apply(info.room);
    });

    DELEGATE.on("change", "select[data-sedit-room-building]", function (event, select) {
        if (state.applying) {
            return;
        }
        state.touched = true;
        if (filter(select.value)) {
            notify(roomSelect());
        }
        updateHint();
    });

    DELEGATE.on("change", "select[data-sedit-room]", function () {
        if (!state.applying) {
            state.touched = true;
            updateHint();
        }
    });

    /* Planlayıcının otaq təklifi: başqa korpusdandırsa korpusu da keçir. `true` — işlənib. */
    function pick(room, building) {
        var select = roomSelect();
        var korpus = buildingSelect();
        if (!select || !korpus) {
            return false;
        }
        var target = hasBuilding(building) ? building : "";
        if (korpus.value !== target) {
            setBuilding(target);
            filter(target);
            notify(korpus);
        }
        state.touched = true;
        selectRoom(room);
        notify(select);
        updateHint();
        return true;
    }

    /* `action=plan` cavabının qrup korpusu (müəllim görünüşü: qrup dialoqda seçilir). Yalnız YENİ xanada,
       istifadəçi korpus/otağa toxunmayıbsa və otaq boşdursa. */
    function applyDefault(building) {
        var korpus = buildingSelect();
        var select = roomSelect();
        if (!korpus || !select || !state.isNew || state.touched || select.value) {
            return;
        }
        if (!building || !hasBuilding(building) || korpus.value === building) {
            return;
        }
        korpus.setAttribute("data-default-building", building);
        setBuilding(building);
        filter(building);
        notify(korpus);
        updateHint();
    }

    window.EMSScheduleRoom = { apply: apply, pick: pick, applyDefault: applyDefault, filter: filter };
})(window, document);
