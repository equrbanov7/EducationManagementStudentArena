/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus redaktoru — BÖLMƏ SAHƏLƏRİ (dizayn təhvili §3.2)
   ───────────────────────────────────────────────────────────────────────────
   Bu modul iki iş görür və başqa heç nə:

     1. `collect(el, sectionId)` — bölmənin DOM-unu autosave gövdəsinə çevirir.
        Nəticə `apps/syllabus/services/drafts.BLANK_SECTION_DATA` sxemi ilə
        EYNİ ADLARI işlətməlidir — server sahə adlarını burada gözləyir.

        ⚠️ TOPLAYICI DOM-da OLMAYAN AÇARI UYDURMUR.  `save_section` PATCH-dir:
        göndərilməyən açar serverdə TOXUNULMAZ qalır, göndərilən AÇIQ boş dəyər
        isə silmə niyyətidir.  `collectAssess` bu qaydanı pozurdu — qiymətləndirmə
        panelində `note` üçün input YOXDUR (yalnız bal sürüşdürücüsü var), amma
        toplayıcı hər saxlamada `note: ""` göndərirdi.  Nəticədə köçürülmüş
        sillabusun qiymətləndirmə mətni (canlı: 5,893 sillabus) müəllimin İLK
        avtosave-i ilə silinirdi.  İndi açar yalnız onu daşıyan input VARSA
        göndərilir.
     2. `refresh(el)` — yalnız TÖRƏMƏ göstəriciləri yeniləyir (simvol sayğacı,
        saat çipləri, aralıq/layihə balı). Biznes qərarı VERMİR: tamamlanma
        faizi və çatışmazlıq siyahısı yeganə mənbədən — serverin autosave
        cavabından — gəlir.

   Niyə ayrı fayl: `syllabus_editor.js` autosave mühərriki və naviqasiyadır;
   sahə sxemi isə domenlə birlikdə dəyişir. Modul ölçüsü qaydası (SOFT_CAP=600)
   da bu bölgünü tələb edir.

   Mətn YOXDUR — bütün etiketlər şablondakı `data-t-*` atributlarından oxunur.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    /* Dərs növləri — `apps.syllabus.constants.LESSON_HOUR_KINDS` ilə eynidir. */
    var HOUR_KINDS = ["lecture", "seminar", "lab"];

    /* Nömrəsiz (boş) nəticə sətrinin etiketi və «sil» düyməsinin işarəsi.
       İkisi də DURĞU İŞARƏSİDİR, tərcümə olunan mətn deyil — serverdəki
       `editor_panels.BLANK_OUTCOME_TAG` və şablondakı `&times;` ilə eynidir. */
    var BLANK_TAG = "\u2014";
    var REMOVE_GLYPH = "\u00d7";

    function panel(el, id) {
        return el ? el.querySelector("[data-syl-panel='" + id + "']") : null;
    }

    /* ═══ @collector-contract:begin ═══════════════════════════════════════
       Bu blok GÖNDƏRİLƏN müqavilədir: autosave gövdəsini məhz o qurur.
       `apps/syllabus/tests/editor_dom.py` onun Python güzgüsüdür və blokun
       SHA-256-sı `apps/syllabus/tests/test_editor_shipped_js.py`-də
       BƏRKİDİLİB.  Buranı dəyişən hər commit güzgünü də dəyişməli və həmin
       barmaq izini yeniləməlidir — əks halda qapı çökür.  Səbəb: əvvəllər
       güzgü müstəqil idi, göndərilən JS-dəki `carried()` çağırışlarını geri
       qaytardıqda 7 testin 7-si də YAŞIL qalırdı.
       ═════════════════════════════════════════════════════════════════════ */

    function text(node) {
        return node ? String(node.value == null ? "" : node.value) : "";
    }

    function int(value) {
        var parsed = parseInt(value, 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    /* Sətir-əsaslı SƏRBƏST MƏTN sahəsi (ədəbiyyat): ABZAS FASİLƏSİ QORUNUR.

       ⚠️ Əvvəlki `toLines` hər boş sətri atırdı.  `sillabus_derslikler`-də 556
       uniqid-in mətnində qəsdən qoyulmuş boş sətir (abzas) var — köçürmə onu
       `legacy_text._collapsed_blank_lines` ilə SAXLAYIR, oxu sənədi
       (`apps.syllabus.document._prose_lines`) da saxlayır.  Toplayıcı isə ilk
       avtosaxlamada onu silirdi: mətn qalır, struktur gedirdi.

       İndi resept təmizləyici ilə HƏRFƏN eynidir: baş/son boş sətirlər atılır,
       daxildəki hər boş seriya BİR sətrə sıxılır.  Funksiya idempotentdir —
       öz nəticəsini yenidən emal etmək dəyişiklik vermir. */
    function toProseLines(value) {
        var kept = [];
        String(value || "").split("\n").forEach(function (raw) {
            var line = raw.trim();
            if (line.length > 0) {
                kept.push(line);
            } else if (kept.length && kept[kept.length - 1].length > 0) {
                kept.push("");
            }
        });
        while (kept.length && kept[kept.length - 1].length === 0) {
            kept.pop();
        }
        return kept;
    }

    /* `fields` içində HƏQİQƏTƏN olan açarları `target`-ə köçürür.
       Olmayan açar köçürülmür — server onu dəyişməz saxlayır. */
    function assign(target, fields, keys) {
        keys.forEach(function (key) {
            if (Object.prototype.hasOwnProperty.call(fields, key)) {
                target[key] = fields[key];
            }
        });
        return target;
    }

    /* Sətir/yuvanın DOM-da İNPUTU OLMAYAN açarları (`data-extra` JSON-u).

       ⚠️ SİNİF QAYDASI: toplayıcı sətri SIFIRDAN qurmur — mənbənin qorunan
       açarlarından başlayır, sonra yalnız DOM-un idarə etdiyi açarları
       üstələyir.  Beləliklə `practical` / `note` (və sxemə SONRA əlavə olunan
       hər sahə) heç bir kod dəyişikliyi olmadan geri yazılır.  Əvvəllər
       `collectWeek` hər sətri `{topic, outcome, lecture, seminar, lab}` kimi
       yenidən qururdu və qalan açarları 8,220 sillabusun HƏR sətrindən silirdi. */
    function carried(node) {
        var raw = node ? node.getAttribute("data-extra") : "";
        if (!raw) {
            return {};
        }
        try {
            var parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
        } catch (err) {
            return {};
        }
    }

    /* `data-field` atributu olan hər input → {ad: dəyər}. */
    function plainFields(box) {
        var out = {};
        if (!box) {
            return out;
        }
        box.querySelectorAll("[data-field]").forEach(function (node) {
            out[node.getAttribute("data-field")] = text(node);
        });
        return out;
    }

    /* ── Bölmə-bölmə toplayıcılar ─────────────────────────────────────── */

    /* Yalnız panelin ÖZ input-ları — `welcome`, `research_interests`,
       `certificates`, `language`, `lesson_hours` bu redaktorda göstərilmir,
       ona görə göndərilmir də (server onları saxlayır). */
    function collectInfo(box) {
        return plainFields(box);
    }

    function collectDesc(box) {
        var data = plainFields(box);
        return { description: data.description || "", goal: data.goal || "" };
    }

    /* ⚠️ `[data-outcome]` `<textarea>` OLMALIDIR, `<input type="text">` yox.
       HTML-in «value sanitization algorithm»-i `<input>`-in dəyərindən CR/LF
       simvollarını SİLİR (boşluqla belə əvəzləmir) — brauzer probe-u ilə
       ölçülüb.  Köçürülmüş 4,790 sillabusun təlim nəticəsi ÇOX SƏTİRLİDİR
       («TN1. …\n2. …»), yəni `<input>`-də ilk avtosaxlama sətir sonlarını
       silib sözləri yapışdırırdı.  Qayda bütün sinfə aiddir; render
       tərəfindəki qapı `test_editor_shipped_js` içindədir. */
    function collectOut(box) {
        var outcomes = [];
        if (box) {
            box.querySelectorAll("[data-outcome]").forEach(function (node) {
                outcomes.push(text(node).trim());
            });
        }
        return { outcomes: outcomes };
    }

    function collectWeek(box) {
        var rows = [];
        if (!box) {
            return { rows: rows };
        }
        box.querySelectorAll("[data-syl-week-row]").forEach(function (tr) {
            /* Mənbənin qorunan açarları ƏSASDIR; DOM onları yalnız üstələyir. */
            var row = carried(tr);
            var topic = tr.querySelector("[data-week='topic']");
            var outcome = tr.querySelector("[data-week='outcome']");
            row.topic = text(topic).trim();
            row.outcome = text(outcome).trim();
            HOUR_KINDS.forEach(function (kind) {
                row[kind] = int(text(tr.querySelector("[data-week='" + kind + "']")));
            });
            rows.push(row);
        });
        return { rows: rows };
    }

    /* Metodlar: kataloq çipləri + «kataloqda olmayan» (köçürülmüş) çiplər.
       Hər ikisi `[data-syl-method]` daşıyır, ona görə seçici DƏYİŞMİR — dəyişən
       şablondur: köçürülmüş metod artıq RENDER OLUNUR, yəni `is-on` gəlir və
       burada toplanır.  Əvvəllər o çip ümumiyyətlə yox idi və ilk autosave
       `methods: []` göndərib mətni silirdi (canlı: 8,260 sillabus). */
    function collectMethod(box) {
        var methods = [];
        if (box) {
            box.querySelectorAll("[data-syl-method].is-on").forEach(function (node) {
                methods.push(node.getAttribute("data-syl-method"));
            });
        }
        var data = { methods: methods };
        assign(data, plainFields(box), ["note"]);
        return data;
    }

    /* Qiymətləndirmə: yalnız `midterm` sürüşdürülür — `project` ONDAN törəyir
       (cəm universitet siyasəti ilə sabitdir), ona görə burada hesablanır.

       ⚠️ `note` yalnız onun üçün input VARSA göndərilir.  Panelə hələ belə
       input əlavə edilməyib (`legacy_syllabus_assessment_note_unsurfaced`),
       ona görə açar adətən heç göndərilmir və serverdəki mətn qorunur.

       ⚠️ BAL AÇARLARI YALNIZ SÜRÜŞDÜRÜCÜYƏ TOXUNULANDAN SONRA GEDİR.  Əvvəllər
       panel render olunubsa hər saxlamada `project = data-flex − midterm`
       göndərilirdi.  Köçürmə isə qəsdən `midterm: 0, project: 0` yazır (=
       «bölgü YOXDUR») və oxu sənədi bu cütü `None` sayıb tələbəyə heç nə
       göstərmir.  Nəticə ölçülüb: müəllim «Qiymətləndirmə» addımına keçib
       sürüşdürücüyə TOXUNMADAN «Qaralama saxla» basanda sənədə heç kimin
       yazmadığı `project: 30` düşürdü.  İndi toxunma bayrağı şərtdir:
       redaktor onu `input`/`change` hadisəsində qoyur, yəni 0 SEÇMƏK də
       toxunmaqdır və silmə niyyəti kimi göndərilir; toxunulmayıbsa açar
       ümumiyyətlə göndərilmir və serverdəki bölgü toxunulmaz qalır.
       Bayraq yoxdursa (hadisə qatı sınıbsa) davranış TƏHLÜKƏSİZ tərəfə düşür:
       heç nə yazılmır.  Bal siyasəti/cəmi BURADA DEYİL — bax `_assessment`. */
    function collectAssess(box) {
        var slider = box ? box.querySelector("[data-syl-midterm]") : null;
        var data = {};
        if (slider && slider.getAttribute("data-touched") === "1") {
            var midterm = int(slider.value);
            data.midterm = midterm;
            data.project = Math.max(0, int(slider.getAttribute("data-flex")) - midterm);
        }
        assign(data, plainFields(box), ["note"]);
        return data;
    }

    /* Sərbəst iş: qiyməti OLAN tapşırığın `graded`/`graded_count` sahələri
       olduğu kimi geri yazılır — əks halda arxivləmə qadağası pozulardı.

       ⚠️ Yuva sayı SERVERDƏN gəlir və artıq `max(variant sayı, mövzu sayı)`-dır
       (bax `editor_panels.selfwork`).  Variant seçilməyəndə 0 yuva render
       olunurdu, yəni bu funksiya `topics: []` qururdu və köçürülmüş mövzuları
       silirdi (canlı: 8,258 sillabus). */
    function collectSelf(box) {
        var active = box ? box.querySelector("[data-syl-selfwork].is-on") : null;
        var topics = [];
        var archived = [];
        if (box) {
            box.querySelectorAll("[data-syl-slot]").forEach(function (slot) {
                var topic = carried(slot);
                /* `[data-selfwork-title]` də `<textarea>`-dir — eyni sinif:
                   mənbədə U+2028 daşıyan sətir var, təmizləyici onu `\n`-ə
                   çevirir və `<input>` həmin `\n`-i silirdi. */
                topic.title = text(slot.querySelector("[data-selfwork-title]")).trim();
                topic.graded = slot.getAttribute("data-graded") === "1";
                topic.graded_count = int(slot.getAttribute("data-graded-count"));
                topics.push(topic);
            });
            /* Arxiv sətri də EYNİ SİNİF QAYDASINA tabedir: lüğət sıfırdan
               qurulmur, `data-extra`-dan başlayır.  Bu gün arxivin yeganə
               açarları `title`/`note`-dur (köçürmə `archived: []` yazır), amma
               naxışı pozmaq həmin sinif səhvini geri gətirmək deməkdir. */
            box.querySelectorAll("[data-syl-archived-row]").forEach(function (row) {
                var entry = carried(row);
                entry.title = row.getAttribute("data-title") || "";
                entry.note = row.getAttribute("data-note") || "";
                archived.push(entry);
            });
        }
        return {
            option: active ? active.getAttribute("data-syl-selfwork") : "",
            topics: topics,
            archived: archived
        };
    }

    function collectLit(box) {
        var out = { primary: [], additional: [] };
        if (!box) {
            return out;
        }
        box.querySelectorAll("[data-field-lines]").forEach(function (node) {
            out[node.getAttribute("data-field-lines")] = toProseLines(text(node));
        });
        return out;
    }

    var COLLECTORS = {
        info: collectInfo,
        desc: collectDesc,
        out: collectOut,
        week: collectWeek,
        method: collectMethod,
        assess: collectAssess,
        self: collectSelf,
        lit: collectLit
    };
    /* ═══ @collector-contract:end ═════════════════════════════════════════ */

    /* `prev` / `send` qayda bölməsi deyil — məzmunu yoxdur, saxlanılmır. */
    function collect(el, sectionId) {
        var fn = COLLECTORS[sectionId];
        return fn ? fn(panel(el, sectionId), el) : null;
    }

    /* Hansı bölmənin sahəsi dəyişdi — autosave hədəfini tapmaq üçün. */
    function sectionOf(node) {
        var box = node && node.closest ? node.closest("[data-syl-panel]") : null;
        return box ? box.getAttribute("data-syl-panel") : null;
    }

    /* ── Törəmə göstəricilər (yalnız görüntü) ─────────────────────────── */

    function i18n(el, key) {
        var box = el ? el.querySelector("[data-syl-i18n]") : null;
        return (box && box.getAttribute("data-t-" + key)) || "";
    }

    /* «Ən azı %(min)s simvol — hazırda %(have)s» şablonunu doldurur. */
    function charNote(el, have, min) {
        if (have >= min) {
            return have + " " + i18n(el, "chars");
        }
        return i18n(el, "chars-min")
            .replace("%(min)s", String(min))
            .replace("%(have)s", String(have));
    }

    function refreshCounters(el) {
        el.querySelectorAll("[data-syl-counter]").forEach(function (note) {
            var input = document.getElementById(note.getAttribute("data-syl-counter"));
            if (!input) {
                return;
            }
            var min = int(input.getAttribute("data-min"));
            var have = text(input).trim().length;
            note.textContent = charNote(el, have, min);
            note.classList.toggle("is-bad", have < min);
            input.classList.toggle("is-bad", have < min);
        });
    }

    /* Saat çipləri: hər dərs növü tədris planı ilə AYRICA uyğunlaşmalıdır. */
    function refreshHours(el) {
        var box = panel(el, "week");
        var hours = el.querySelector("[data-syl-hours]");
        if (!box || !hours) {
            return;
        }
        var rows = collectWeek(box).rows;
        var allOk = true;
        HOUR_KINDS.forEach(function (kind) {
            var chip = hours.querySelector("[data-syl-hour-chip='" + kind + "']");
            if (!chip) {
                return;
            }
            var have = rows.reduce(function (sum, row) {
                return sum + row[kind];
            }, 0);
            var planNode = chip.querySelector("[data-syl-hour-plan]");
            var haveNode = chip.querySelector("[data-syl-hour-have]");
            var planned = planNode ? int(planNode.textContent) : 0;
            if (haveNode) {
                haveNode.textContent = String(have);
            }
            var bad = have !== planned;
            chip.classList.toggle("is-bad", bad);
            if (bad) {
                allOk = false;
            }
        });
        hours.classList.toggle("syl-hours--ok", allOk);
        hours.classList.toggle("syl-hours--warn", !allOk);
        var note = hours.querySelector("[data-syl-hours-note]");
        if (note) {
            note.textContent = note.getAttribute(allOk ? "data-t-ok" : "data-t-warn") || "";
        }
    }

    /* Aralıq imtahan sürüşdürüləndə semestr layihəsi əks istiqamətdə dəyişir. */
    function refreshMidterm(el) {
        var slider = el.querySelector("[data-syl-midterm]");
        if (!slider) {
            return;
        }
        var flex = int(slider.getAttribute("data-flex"));
        var midterm = int(slider.value);
        var midNode = el.querySelector("[data-syl-midterm-value]");
        var projNode = el.querySelector("[data-syl-project-value]");
        if (midNode) {
            midNode.textContent = String(midterm);
        }
        if (projNode) {
            projNode.textContent = String(Math.max(0, flex - midterm));
        }
    }

    /* TN etiketləri sıra nömrəsindən asılıdır — silinmədən sonra yenilənir.

       ⚠️ BOŞ sətir NÖMRƏ TUTMUR.  Toplayıcı boş sətri də göndərir (mid-yazı
       sətri itməsin deyə), `outcome_tags` — həftə panelinin açılış siyahısı —
       və `completion` isə yalnız DOLU olanları sayır.  Nəticədə iki panel
       bir-birini təkzib edirdi: redaktorda «TN2» görünən nəticə həftə
       cədvəlində «TN1» kimi seçilirdi.  İndi hər üç yer eyni qaydadadır —
       nömrəni yalnız dolu sətir alır, boş sətir `BLANK_TAG` daşıyır.
       Server tərəfi eyni qaydanı `editor_panels.outcome_rows`-da qurur. */
    function retagOutcomes(el) {
        var box = panel(el, "out");
        if (!box) {
            return;
        }
        var label = box.querySelector("[data-syl-outcomes]");
        var suffix = label ? label.getAttribute("data-t-label") : "";
        var removeText = label ? label.getAttribute("data-t-remove") : "";
        var number = 0;
        box.querySelectorAll("[data-syl-outcome]").forEach(function (row) {
            var tagNode = row.querySelector("[data-syl-outcome-tag]");
            var input = row.querySelector("[data-outcome]");
            var remove = row.querySelector("[data-syl-outcome-remove]");
            var filled = !!input && text(input).trim().length > 0;
            var tag = filled ? "TN" + (number += 1) : BLANK_TAG;
            if (tagNode) {
                tagNode.textContent = tag;
            }
            if (input) {
                input.setAttribute("aria-label", filled ? tag + " — " + suffix : suffix);
            }
            if (remove) {
                remove.setAttribute("aria-label", filled ? tag + " " + removeText : removeText);
            }
        });
    }

    /* «+ Təlim nəticəsi əlavə et» üçün BOŞ sətir qurur.

       ⚠️ Redaktor sətri əvvəllər YALNIZ mövcud sətri klonlayaraq əlavə edirdi,
       şablonda isə `{% empty %}` budağı yoxdur: `outcomes == []` olanda 0 sətir
       render olunur, klon mənbəyi tapılmır və düymə SƏSSİZCƏ heç nə etmirdi.
       Ölçülüb: 8,247 başlığın 2,157-si (26.2%) məhz bu formadadır, üstəlik HƏR
       yeni qaralama (`blank_section_data` → `outcomes: []`) da belə açılır.
       `out` qayda bölməsi olduğuna görə (MIN_OUTCOMES) tamamlanma 100%-ə heç
       vaxt çatmır, yəni həmin sillabuslar təsdiqə GÖNDƏRİLƏ BİLMİRDİ.

       Mətn BURADA YAZILMIR: yer tutucu qutunun `data-t-placeholder`-indən,
       etiket/aria isə `retagOutcomes`-dan gəlir (dörd dil pozulmur). */
    function makeOutcomeRow(box) {
        var doc = box.ownerDocument;
        var row = doc.createElement("div");
        var tag = doc.createElement("span");
        var input = doc.createElement("textarea");
        var remove = doc.createElement("button");
        row.className = "syl-outcome";
        row.setAttribute("data-syl-outcome", "");
        tag.className = "syl-outcome__tag";
        tag.setAttribute("data-syl-outcome-tag", "");
        input.className = "syl-textarea syl-textarea--outcome";
        input.setAttribute("rows", "2");
        input.setAttribute("data-outcome", "");
        input.setAttribute("placeholder", box.getAttribute("data-t-placeholder") || "");
        remove.className = "syl-iconbtn";
        remove.setAttribute("type", "button");
        remove.setAttribute("data-syl-outcome-remove", "");
        remove.textContent = REMOVE_GLYPH;
        row.appendChild(tag);
        row.appendChild(input);
        row.appendChild(remove);
        return row;
    }

    function refresh(el) {
        if (!el) {
            return;
        }
        refreshCounters(el);
        refreshHours(el);
        refreshMidterm(el);
        retagOutcomes(el);
    }

    /* ── Server vəziyyətinin render-i ─────────────────────────────────── */

    /* dizayn §3.2 `saveState` — altı vəziyyət, hər biri üçün çip + banner. */
    var SAVE_STATES = ["saving", "saved", "failed", "offline", "conflict", "stale"];

    function paintSaveState(el, state, suffix) {
        if (!el) {
            return;
        }
        var chip = el.querySelector("[data-syl-save]");
        if (chip) {
            SAVE_STATES.forEach(function (name) {
                chip.classList.toggle("syl-save--" + name, name === state);
            });
            var label = chip.querySelector("[data-syl-save-text]");
            if (label) {
                var base = chip.getAttribute("data-t-" + state) || "";
                label.textContent = suffix ? base + " — " + suffix : base;
            }
        }
        /* Eyni anda yalnız bir banner görünür; `saving`/`saved` bannersizdir. */
        el.querySelectorAll("[data-syl-banner]").forEach(function (banner) {
            banner.hidden = banner.getAttribute("data-syl-banner") !== state;
        });
        var retry = el.querySelector(".syl-savebox [data-syl-retry]");
        if (retry) {
            retry.hidden = state !== "failed";
        }
        el.setAttribute("data-save-state", state);
    }

    /* Tamamlanma hesabatı SERVERDƏN gəlir (`apps.syllabus.completion`) — burada
       yalnız çəkilir, yenidən hesablanmır. */
    function paintCompletion(el, report, readonly) {
        if (!el || !report) {
            return;
        }
        var sections = report.sections || {};
        var percent = Math.max(0, Math.min(int(report.percent), 100));
        var tone = percent >= 100 ? "success" : "primary";

        var fill = el.querySelector("[data-syl-progress-fill]");
        if (fill) {
            fill.style.width = percent + "%";
            fill.setAttribute("data-syl-percent", String(percent));
        }
        var value = el.querySelector("[data-syl-progress-value]");
        if (value) {
            value.textContent = percent + "%";
            value.className = "syl-bar__value syl-bar__value--" + tone;
        }
        var bar = el.querySelector(".syl-bar");
        if (bar) {
            bar.className = "syl-bar syl-bar--" + tone;
        }

        /* Bölmə başına çatışmazlıq sayı — sol naviqasiyanın «N xəta» rozetkası. */
        var counts = {};
        (report.issues || []).forEach(function (issue) {
            counts[issue.section] = (counts[issue.section] || 0) + 1;
        });

        el.querySelectorAll(".syl-step[data-syl-step]").forEach(function (button) {
            var id = button.getAttribute("data-syl-step");
            if (!(id in sections)) {
                return;
            }
            var done = !!sections[id];
            button.classList.toggle("syl-step--done", done);
            button.classList.toggle("syl-step--error", !done);
            button.classList.remove("syl-step--todo");
            var mark = button.querySelector(".syl-step__mark");
            if (mark) {
                mark.textContent = done ? "✓" : "!";
            }
            var warn = button.querySelector(".syl-step__warn");
            if (warn) {
                warn.hidden = !counts[id];
            }
        });

        /* Panel başlığındakı «tamamlanıb / çatışan tələblər var» rozetkası. */
        Object.keys(sections).forEach(function (id) {
            var state = el.querySelector("[data-syl-panel='" + id + "'] .syl-panel__state");
            if (state && !state.classList.contains("syl-panel__state--check")) {
                state.classList.toggle("syl-panel__state--done", !!sections[id]);
                state.classList.toggle("syl-panel__state--todo", !sections[id]);
            }
        });

        var canSubmit = percent >= 100 && !readonly;
        el.querySelectorAll("[data-syl-submit]").forEach(function (button) {
            button.disabled = !canSubmit;
        });
    }

    window.EMSSyllabusFields = {
        HOUR_KINDS: HOUR_KINDS,
        collect: collect,
        i18n: i18n,
        makeOutcomeRow: makeOutcomeRow,
        paintCompletion: paintCompletion,
        paintSaveState: paintSaveState,
        panel: panel,
        refresh: refresh,
        retagOutcomes: retagOutcomes,
        sectionOf: sectionOf
    };
})();
