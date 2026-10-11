/* «Yeni dərs» modalı — ƏVVƏLCƏDƏN DOLDURMA (sahib 2026-10-10: «Aktivləşdir» yerinə dolu «Yeni dərs»).
 *
 * Mənbə: `#jdLessonPrefill` JSON adası (apps/registrar/journal_lesson_prefill.py) — bu günün açılmamış
 * cədvəl dərsi (indi gedən → 30 dəq. əvvəl bitən → növbəti → ən son keçmiş) və ya son dərsə görə
 * defoltlar; üstəlik hər tip üçün mövzu / müəllim / akademik saat xəritələri (`*_by_kind`) və zolaqdakı
 * hər açılmamış slotun öz dəyərləri (`slots`).
 *
 * QOŞULMA: journal_grid_lesson_modal.js `openModal` YENİ dərsdə `jd:lesson-modal-prepare` hadisəsini
 * `jd:lesson-modal-open`-dan ƏVVƏL, SİNXRON göndərir (`detail.slotId` — zolaqdakı slot düyməsi). Sahələr
 * məhz o anda doldurulur: müəllim seçicisi, otaq kaskadı (journal_lesson_room.js — `jdPrefillRoom`) və
 * «cədvəldən kənar» sahəsi (journal_activation.js) açılış hadisəsində artıq doğru dəyərləri oxuyur.
 *
 *  * Əvvəlki REDAKTƏNİN dəyərləri sıfırlanır (əvvəl «Yeni dərs» son redaktə olunmuş dərsin tarixi /
 *    tipi / mövzusu / saatı / müəllimi ilə açılırdı).
 *  * Mövzu seçimləri dərs tipinə görə süzülür (`data-kinds`; boşdursa — LMS mənbəyi — hər tipdə; seçilmiş
 *    mövzu gizlədilmir). Redaktədə də.
 *  * Müəllim tipi dəyişəndə mövzu / akademik saat / müəllim həmin tipin dəyərlərinə keçir — sahəni özü
 *    dəyişməyibsə (son avtomatik dəyərlə müqayisə olunur).
 *  * Gizli `slot_id` yalnız tarix + dərs saatı + tip slotla EYNİ olduqca göndərilir; dəyişən kimi boşalır
 *    və server əl ilə dərs qaydalarını (standart saat, cədvəldən kənar səbəb) tətbiq edir.
 *  * Slotun saatı standart siyahıda yoxdursa (təşkilatın öz zəng saatı) seçimə müvəqqəti variant düşür.
 *
 * Proqram dəyişiklikləri `applying` bayrağı altında gedir: bootstrap-select vidceti də sintetik `change`
 * göndərir, `isTrusted` müəllim seçimini ayırmır (journal_lesson_room.js ilə eyni üsul). Server qaydaları
 * həlledicidir — bu fayl yalnız UX-dir. CSP/AJAX-safe: inline yoxdur; dinləyicilər document-də, bir dəfə.
 */
(function () {
    "use strict";

    var MODAL = "[data-jd-lesson-modal]";
    var applying = false;
    var active = null; // cari YENİ dərs doldurması (redaktədə null)
    var auto = {}; // son avtomatik qoyulan dəyərlər: topic / hours / instructor

    function readPrefill() {
        var node = document.getElementById("jdLessonPrefill");
        if (!node) return null;
        try {
            var data = JSON.parse(node.textContent || "null");
            return data && typeof data === "object" ? data : null;
        } catch (e) {
            return null;
        }
    }

    function merge(base, extra) {
        var out = {};
        var key;
        for (key in base) {
            if (Object.prototype.hasOwnProperty.call(base, key)) out[key] = base[key];
        }
        for (key in extra || {}) {
            if (Object.prototype.hasOwnProperty.call(extra, key)) out[key] = extra[key];
        }
        return out;
    }

    function fields(modal) {
        return {
            action: modal.querySelector("[data-jd-lesson-action]"),
            date: modal.querySelector("[data-jd-lesson-date]"),
            kind: modal.querySelector("[name='lesson_kind']"),
            topic: modal.querySelector("[data-jd-lesson-topic]"),
            hours: modal.querySelector("[data-jd-lesson-hours]"),
            time: modal.querySelector("[data-jd-lesson-time]"),
            instructor: modal.querySelector("[data-jd-lesson-instructor]"),
            slot: modal.querySelector("[data-jd-lesson-slot]"),
            reason: modal.querySelector("[data-jd-offsched-reason]"),
        };
    }

    function isAdding(f) {
        return !f.action || f.action.value === "add_lesson";
    }

    function refreshWidget(select) {
        if (select && window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    function hasOption(select, value) {
        for (var i = 0; i < select.options.length; i++) {
            if (select.options[i].value === value) return true;
        }
        return false;
    }

    /** Dəyəri qoy; select-də vidcet sinxronlansın deyə `change` göndərilir (öz dinləyicimiz saymır). */
    function setValue(field, value) {
        if (!field) return;
        var text = value === null || value === undefined ? "" : String(value);
        var prev = applying;
        applying = true;
        try {
            if (field.tagName === "SELECT") {
                if (!hasOption(field, text)) text = field.options.length ? field.options[0].value : "";
                field.value = text;
                field.dispatchEvent(new Event("change", { bubbles: true }));
            } else {
                field.value = text;
            }
        } finally {
            applying = prev;
        }
    }

    /** Slotun saatı standart siyahıda yoxdursa — saat sırası ilə müvəqqəti seçim; köhnələri silinir. */
    function syncTimeOptions(select, value) {
        if (!select) return;
        var changed = false;
        Array.prototype.slice.call(select.querySelectorAll("option[data-jd-slot-time]")).forEach(function (opt) {
            if (opt.value !== value) {
                select.removeChild(opt);
                changed = true;
            }
        });
        if (value && !hasOption(select, value)) {
            var opt = document.createElement("option");
            opt.value = value;
            opt.textContent = value.replace("|", "–");
            opt.setAttribute("data-jd-slot-time", "");
            var before = null;
            for (var i = 0; i < select.options.length; i++) {
                if (select.options[i].value && select.options[i].value > value) {
                    before = select.options[i];
                    break;
                }
            }
            select.insertBefore(opt, before);
            changed = true;
        }
        if (changed) refreshWidget(select);
    }

    function optionKinds(option) {
        return (option.getAttribute("data-kinds") || "").split(/\s+/).filter(Boolean);
    }

    /** Mövzu bu tipdə keçirilə bilərmi (`data-kinds` boşdursa — bəli). */
    function topicAllowed(select, value, kind) {
        if (!select || select.tagName !== "SELECT" || !value || !kind) return true;
        for (var i = 0; i < select.options.length; i++) {
            if (select.options[i].value === value) {
                var kinds = optionKinds(select.options[i]);
                return !kinds.length || kinds.indexOf(kind) !== -1;
            }
        }
        return true;
    }

    /** Mövzu seçimlərini dərs tipinə görə süz; seçilmiş mövzu gizlənmir (redaktədə köhnə dərsin mövzusu). */
    function filterTopics(select, kind) {
        if (!select || select.tagName !== "SELECT") return;
        var current = select.value;
        var changed = false;
        Array.prototype.forEach.call(select.options, function (opt) {
            var kinds = optionKinds(opt);
            var hide = Boolean(kind && opt.value && kinds.length && kinds.indexOf(kind) === -1 && opt.value !== current);
            if (opt.hidden !== hide) {
                opt.hidden = hide;
                changed = true;
            }
        });
        if (changed) refreshWidget(select);
    }

    function setTopic(field, value) {
        if (!field) return;
        if (field.tagName === "SELECT") {
            setValue(field, value && hasOption(field, value) ? value : "");
        } else {
            field.value = value || "";
        }
    }

    function kindOf(f) {
        return f.kind ? f.kind.value : "";
    }

    /** Jurnal sahibindən başqa müəllimin adı (server `instructor_labels`: slot və dərs müəllimləri); sahib üçün
     *  boş — seçici özü tapır. Redaktədə də işlənir (journal_lesson_teacher_picker.js → `labelFor`). */
    function teacherLabel(id) {
        var labels = ((active || readPrefill() || {}).instructor_labels) || {};
        return (id && labels[id]) || "";
    }

    /** Tipin dəyərləri: doldurmanın ÖZ tipi — onun dəyərləri (slot / son dərs), başqa tip — tip xəritələri. */
    function valuesFor(kind) {
        var data = active || {};
        if (kind && kind === data.kind) return data;
        return {
            time: "",
            hours: (data.hours_by_kind || {})[kind],
            instructor: (data.instructor_by_kind || {})[kind],
            topic: (data.topic_by_kind || {})[kind],
            room: "",
        };
    }

    /** Gizli `slot_id` + mənbə ipucları: slot bağı yalnız tarix + saat + tip slotla eyni olduqca. */
    function syncSlot(modal) {
        var f = fields(modal);
        var data = active;
        var adding = isAdding(f);
        var bound = Boolean(
            data &&
                data.slot_id &&
                adding &&
                f.date &&
                f.date.value === data.date &&
                f.time &&
                f.time.value === data.time &&
                kindOf(f) === data.kind
        );
        if (f.slot) f.slot.value = bound ? data.slot_id : "";
        var slotHint = modal.querySelector('[data-jd-prefill-hint="slot"]');
        if (slotHint) {
            slotHint.hidden = !bound;
            var label = slotHint.querySelector("[data-jd-prefill-label]");
            if (label) label.textContent = bound ? data.label || "" : "";
        }
        var lastHint = modal.querySelector('[data-jd-prefill-hint="last"]');
        if (lastHint) lastHint.hidden = !(data && adding && data.source === "last");
    }

    /** YENİ dərs: bütün sahələri doldurmadan (yoxdursa standartdan) qur — köhnə redaktə dəyərləri qalmır. */
    function prepare(modal, slotId) {
        var f = fields(modal);
        var base = readPrefill() || {};
        var own = slotId && base.slots && base.slots[slotId] ? base.slots[slotId] : null;
        active = merge(base, own);
        var prev = applying;
        applying = true;
        try {
            if (f.date) f.date.value = active.date || f.date.defaultValue || "";
            if (f.kind && f.kind.tagName === "SELECT") setValue(f.kind, active.kind || "");
            var kind = kindOf(f);
            var values = valuesFor(kind);
            syncTimeOptions(f.time, values.time || "");
            setValue(f.time, values.time || "");
            setValue(f.hours, String(values.hours || 2));
            filterTopics(f.topic, kind);
            setTopic(f.topic, values.topic || "");
            filterTopics(f.topic, kind);
            if (f.instructor) {
                f.instructor.value = values.instructor || f.instructor.getAttribute("data-jd-default") || "";
                // Müəllim seçicisi (journal_lesson_teacher_picker.js) açılışda çipə bu adı yazır — slotun öz
                // müəllimi namizəd siyahısında olmasa da ad görünür.
                f.instructor.dataset.jdLabel = teacherLabel(f.instructor.value);
            }
            if (f.reason) f.reason.value = "";
            // Otaq kaskadı (journal_lesson_room.js) açılışda bunu yaddaşdan ÜSTÜN tutur — tarix + tip eyni qaldıqca.
            modal.dataset.jdPrefillRoom = values.room || "";
            modal.dataset.jdPrefillRoomKey = kind + "|" + (f.date ? f.date.value : "");
            auto = {
                topic: f.topic ? f.topic.value : "",
                hours: f.hours ? f.hours.value : "",
                instructor: f.instructor ? f.instructor.value : "",
            };
        } finally {
            applying = prev;
        }
        syncSlot(modal);
    }

    /** Müəllim tipi dəyişdi: mövzu süzgəci; YENİ dərsdə toxunulmamış sahələr yeni tipin dəyərlərinə keçir. */
    function onKindChange(modal) {
        var f = fields(modal);
        var kind = kindOf(f);
        if (isAdding(f) && active) {
            var values = valuesFor(kind);
            var prev = applying;
            applying = true;
            try {
                if (f.topic && (f.topic.value === auto.topic || !topicAllowed(f.topic, f.topic.value, kind))) {
                    setTopic(f.topic, values.topic || "");
                    auto.topic = f.topic.value;
                }
                if (f.hours && values.hours && f.hours.value === auto.hours) {
                    setValue(f.hours, String(values.hours));
                    auto.hours = f.hours.value;
                }
                if (f.instructor && values.instructor && f.instructor.value === auto.instructor) {
                    f.instructor.value = values.instructor;
                    auto.instructor = values.instructor;
                    if (window.EMSJournalLessonTeacher) {
                        window.EMSJournalLessonTeacher.show(values.instructor, teacherLabel(values.instructor));
                    }
                }
            } finally {
                applying = prev;
            }
        }
        filterTopics(f.topic, kind);
        syncSlot(modal);
    }

    function onOpen(event) {
        var modal = event.target;
        if (!modal || !modal.matches || !modal.matches(MODAL)) return;
        if (event.detail) {
            // Redaktə: doldurma bağı yoxdur; mövzular dərsin tipinə görə süzülür. Dərsin öz saatı standart siyahıda
            // yoxdursa (cədvəl slotunun zəng saatı) müvəqqəti seçim kimi görünür — «Seçilməyib» deyil; server onu
            // saxlayır (journal_lesson_prefill.own_lesson_time).
            active = null;
            var f = fields(modal);
            var own = event.detail.start && event.detail.end ? event.detail.start + "|" + event.detail.end : "";
            syncTimeOptions(f.time, own);
            if (own && f.time && f.time.value !== own) setValue(f.time, own);
            delete modal.dataset.jdPrefillRoom;
            delete modal.dataset.jdPrefillRoomKey;
            filterTopics(f.topic, kindOf(f));
        }
        syncSlot(modal);
    }

    function onField(event) {
        var target = event.target;
        if (applying || !target || !target.matches) return;
        if (!target.matches("[data-jd-lesson-kind], [data-jd-lesson-date], [data-jd-lesson-time]")) return;
        var modal = target.closest(MODAL);
        if (!modal) return;
        if (target.matches("[data-jd-lesson-kind]")) {
            onKindChange(modal);
        } else {
            syncSlot(modal);
        }
    }

    function bind() {
        document.addEventListener("jd:lesson-modal-prepare", function (event) {
            var modal = event.target;
            if (modal && modal.matches && modal.matches(MODAL)) prepare(modal, (event.detail && event.detail.slotId) || "");
        });
        document.addEventListener("jd:lesson-modal-open", onOpen);
        document.addEventListener("change", onField);
        document.addEventListener("input", onField);
    }

    // Dinləyicilər document-dədir (heç vaxt dəyişdirilmir) — bir dəfə qoşulur.
    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("jd-lesson-prefill", bind);
    } else {
        bind();
    }

    window.EMSJournalLessonPrefill = {
        prepare: prepare,
        syncSlot: syncSlot,
        filterTopics: filterTopics,
        labelFor: teacherLabel,
    };
})();
