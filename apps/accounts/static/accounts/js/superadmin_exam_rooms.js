/* =========================================================================
   «İmtahan zalları» — bölmə-xas davranış (2026-09-11 redizayn).

   ORTAQ QATDA OLANLAR (burada TƏKRARLANMIR):
   * çekmecə/dialoq açılışı, fokus tələsi, Escape, scrim → `ems_ui/overlay.js`
   * dialoq sahələrinin sətir dəyərləri ilə doldurulması (`data-tof-open` +
     `data-tof-prefill`), başlığın `data-tof-title` ilə dəyişməsi
     → `profile/teaching_office.js` (qabıqdan yüklənir)
   * filtr paneli (avto rejim) → `ems_ui/filter_bar.js`; səhifələmə → `pagination.js`

   BURADA:
   * dialoq alt başlığı (`data-sar-subtitle`), təsdiq düyməsinin mətni
     (`data-sar-submit`) və «yalnız redaktədə» sahələr (`data-sar-edit-only`)
   * təşkilat seçicisi dəyişəndə GET formasının avto-göndərilməsi
   * MAC sahəsinin canlı formatlanması (AA:BB:CC:DD:EE:FF) və kopyalanması
   * destruktiv POST-lardan əvvəl təsdiq (EMSConfirm — layihə standartı)
   * dialoq formasının göndərişdən əvvəl HTML5 validasiyası (`novalidate`-dir)
   * POST-dan sonra: `hl_room` → sətir vurğusu, `hl_comp` / `#sar-room-<id>`
     → həmin zalın çekmecəsi yenidən açılır (istifadəçi kontekstini itirmir)

   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli) + `EMSReady`; seçicilər
   bu fayla xasdır (EMSDelegate açarı QLOBALDIR — bax
   apps/accounts/tests/test_static_js_delegate_keys.py).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSExamRooms) {
        return; // idempotent — panel swap-ında script yenidən icra oluna bilər
    }

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSReady) {
        return;
    }

    function root() {
        return document.querySelector("[data-sar-root]");
    }

    /* ---- Dialoq alt başlığı + rejimə görə sahələr ------------------------ */

    /* `teaching_office.js` başlığı və sahələri doldurur; alt başlıq («-101 ·
       ZAL-101») və əlavə/redaktə fərqi (məs. «Aktiv» yalnız redaktədə) bizimdir.
       Seçici qəsdən `[data-sar-subtitle]` ilə daraldılıb — çılpaq
       `[data-tof-open]` açarı teaching_office.js-ə məxsusdur. */
    DELEGATE.on("click", "[data-tof-open][data-sar-subtitle]", function (event, btn) {
        var dialog = document.getElementById(btn.getAttribute("data-tof-open") || "");
        if (!dialog) {
            return;
        }
        var sub = dialog.querySelector(".ems-dialog__sub");
        if (sub) {
            sub.textContent = btn.getAttribute("data-sar-subtitle") || "";
        }
        var values = {};
        try {
            values = JSON.parse(btn.getAttribute("data-tof-prefill") || "{}");
        } catch (err) {
            values = {};
        }
        var editing = Boolean(values.computer_id || (values.room_id && values.action === "update_room"));
        var editOnly = dialog.querySelectorAll("[data-sar-edit-only]");
        for (var i = 0; i < editOnly.length; i += 1) {
            editOnly[i].hidden = !editing;
        }
        // Təsdiq düyməsi: «Əlavə et» / «Zalı yarat» ↔ defolt «Yadda saxla».
        var submit = dialog.querySelector('.ems-dialog__foot [type="submit"]');
        if (submit) {
            if (!submit.dataset.sarDefaultLabel) {
                submit.dataset.sarDefaultLabel = submit.textContent.trim();
            }
            submit.textContent = btn.getAttribute("data-sar-submit") || submit.dataset.sarDefaultLabel;
        }
    });

    /* ---- Təşkilat seçicisi (superadmin) ---------------------------------- */

    DELEGATE.on("change", ".js-sar-orgselect", function (event, select) {
        var form = select.closest("form");
        if (form) {
            form.submit();
        }
    });

    /* ---- MAC: canlı format + kopyalama ----------------------------------- */

    DELEGATE.on("input", "input[data-mac-input]", function (event, input) {
        var hex = (input.value || "").replace(/[^0-9a-fA-F]/g, "").toUpperCase().slice(0, 12);
        var pairs = hex.match(/.{1,2}/g) || [];
        input.value = pairs.join(":");
    });

    DELEGATE.on("click", ".js-sar-copy", function (event, btn) {
        event.preventDefault();
        var value = btn.getAttribute("data-copy") || "";
        if (!value || !navigator.clipboard || !navigator.clipboard.writeText) {
            return;
        }
        navigator.clipboard.writeText(value).then(function () {
            btn.classList.add("is-copied");
            window.setTimeout(function () {
                btn.classList.remove("is-copied");
            }, 1200);
        });
    });

    /* ---- Destruktiv POST-lar: təsdiq ------------------------------------- */

    DELEGATE.on("click", ".js-sar-confirm", function (event, btn) {
        var message = btn.getAttribute("data-confirm") || "";
        if (!message || !btn.form) {
            return;
        }
        event.preventDefault();
        var ask = window.EMSConfirm && window.EMSConfirm.open
            ? window.EMSConfirm.open({ body: message, danger: true })
            : Promise.resolve(window.confirm(message));
        ask.then(function (ok) {
            if (!ok) {
                return;
            }
            if (typeof btn.form.requestSubmit === "function") {
                btn.form.requestSubmit(btn);
            } else {
                btn.form.submit();
            }
        });
    });

    /* ---- Dialoq forması: HTML5 validasiya -------------------------------- */

    /* `_form_dialog.html` `novalidate` yazır (JSON dialoqları öz xətasını
       göstərir); bizim formalar adi POST-dur — boş ad/MAC server dövrəsinə
       getməsin, brauzerin öz ipucu görünsün. */
    DELEGATE.on("submit", "form[data-sar-form]", function (event, form) {
        if (typeof form.checkValidity === "function" && !form.checkValidity()) {
            event.preventDefault();
            if (typeof form.reportValidity === "function") {
                form.reportValidity();
            }
        }
    });

    /* ---- POST-dan sonra: vurğu + çekmecənin yenidən açılması ------------- */

    function flashRow(row) {
        if (!row) {
            return;
        }
        row.classList.remove("sar-flash-row");
        void row.offsetWidth; // animasiyanı yenidən başlat
        row.classList.add("sar-flash-row");
    }

    function openDrawerFor(roomId) {
        var drawer = document.getElementById("sarRoomDrawer-" + roomId);
        if (drawer && window.EMSOverlay && drawer.hidden) {
            window.EMSOverlay.open(drawer);
        }
        return drawer;
    }

    /* Vurğu parametrləri URL-dən SİLİNİR — filtr paneli sorğunu yenidən
       qurarkən onları daşıyır və hər swap-da yenidən vurğulanardı. */
    function stripHighlightParams() {
        if (!window.history || !window.history.replaceState) {
            return;
        }
        var url = new URL(window.location.href);
        url.searchParams.delete("hl_room");
        url.searchParams.delete("hl_comp");
        url.hash = "";
        window.history.replaceState(window.history.state, "", url.pathname + url.search);
    }

    function afterPost() {
        var host = root();
        if (!host) {
            return;
        }
        var params = new URLSearchParams(window.location.search);
        var comp = params.get("hl_comp");
        var roomFromHash = (window.location.hash.match(/^#sar-room-(\d+)$/) || [])[1];
        var room = params.get("hl_room") || roomFromHash;
        if (!comp && !room) {
            return;
        }
        stripHighlightParams();

        if (comp) {
            // Kompüter əlavə/redaktə edilib → zalın çekmecəsi açılır, sətir vurğulanır.
            var compRow = host.querySelector('[data-comp-row="' + comp + '"]');
            var roomBox = compRow ? compRow.closest("[data-sar-room]") : null;
            var drawer = roomBox ? openDrawerFor(roomBox.getAttribute("data-sar-room")) : null;
            if (compRow && drawer) {
                window.setTimeout(function () {
                    flashRow(compRow);
                    try {
                        compRow.scrollIntoView({ block: "center" });
                    } catch (err) {
                        compRow.scrollIntoView();
                    }
                }, 60);
            }
            return;
        }
        if (params.get("hl_room")) {
            // Zal yaradılıb/yenilənib → cədvəldəki sətir vurğulanır.
            var cell = host.querySelector('[data-sar-room-row="' + room + '"]');
            var tr = cell ? cell.closest("tr") : null;
            if (tr) {
                flashRow(tr);
                try {
                    cell.scrollIntoView({ block: "center" });
                } catch (err) {
                    cell.scrollIntoView();
                }
            }
            return;
        }
        // Yalnız fraqment (toplu əlavə) → yeni kompüterlər görünsün deyə çekmecə açılır.
        openDrawerFor(room);
    }

    window.EMSReady(afterPost);

    window.EMSExamRooms = { afterPost: afterPost };
})(window, document);
