/* Tələbə idarəetmə çekməcəsi (psm-*) — qrup köçürməsi + akademik status.
 *
 * Kataloq cədvəlinin ÜSTÜNDƏ işləyir: `people_directory.js` sətirdə
 * `[data-psm-open]` düyməsini render edir, bu modul isə onu tutub çekməcəni
 * açır. İki fayl bir-birindən ASILI DEYİL — düymə yoxdursa modul sadəcə heç nə
 * etmir, modul yüklənməyibsə cədvəl işləməyə davam edir.
 *
 * Qaydalar (CLAUDE.md): inline JS yoxdur, dinamik mətnlər `data-i18n-*`
 * atributlarından oxunur, şəbəkə `EMSCore.fetchJSON` üzərindən (CSRF), boot
 * `EMSReady` ilə idempotentdir (SPA swap-dan sonra ikiqat qoşulmur).
 *
 * ALT MODUL: köçürmə ön baxışının SAF render-i `people_academic_preview.js`-də
 * (`window.EMSPeopleAcademicPreview`) — modul ölçüsü büdcəsinə (SOFT_CAP=600)
 * görə ayrılıb. O modul yüklənməsə bu fayl null-safe davranır.
 */
(function () {
    "use strict";

    var FOCUSABLE =
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

    function text(node, value) {
        if (node) {
            node.textContent = value == null ? "" : String(value);
        }
    }

    function el(tag, className, value) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (value !== undefined && value !== null) {
            node.textContent = String(value);
        }
        return node;
    }

    function toast(message, level) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level || "success");
        }
    }

    function boot() {
        var roots = document.querySelectorAll("[data-psm-root]");
        Array.prototype.forEach.call(roots, function (root) {
            if (root.dataset.psmInit === "1") {
                return;
            }
            root.dataset.psmInit = "1";
            setup(root);
        });
    }

    function setup(root) {
        var i18n = root.dataset;
        var panel = root.querySelector("[data-psm-panel]");
        var skeleton = root.querySelector("[data-psm-skeleton]");
        var content = root.querySelector("[data-psm-content]");
        var errorBox = root.querySelector("[data-psm-error]");
        var minReason = parseInt(root.dataset.minReasonLength || "3", 10);

        /* Vəziyyət: hansı tələbə, hansı AKADEMİK QEYD (bir tələbənin bir neçə
         * proqram qeydi ola bilər) və son ön baxış. Əməllərin hədəfi qeyddir. */
        var state = { card: null, recordIndex: 0, preview: null, opener: null };
        var picker = null;

        function label(key) {
            return i18n["i18n" + key.charAt(0).toUpperCase() + key.slice(1)] || "";
        }

        function record() {
            var records = (state.card && state.card.records) || [];
            return records[state.recordIndex] || null;
        }

        function showError(message) {
            if (!errorBox) {
                return;
            }
            errorBox.textContent = message || label("error");
            errorBox.hidden = !message;
        }

        // ── Açılış / bağlanış ────────────────────────────────────────────────
        function open(userId, opener) {
            state.opener = opener || null;
            state.card = null;
            state.recordIndex = 0;
            state.preview = null;
            root.hidden = false;
            document.body.classList.add("psm-open");
            if (content) {
                content.hidden = true;
            }
            if (skeleton) {
                skeleton.hidden = false;
            }
            showError("");
            if (panel) {
                panel.focus();
            }
            var url = (root.dataset.cardUrl || "").replace(/0\/card\/$/, userId + "/card/");
            window.EMSCore.fetchJSON(url)
                .then(function (payload) {
                    if (!payload || !payload.has_access) {
                        showError(label("error"));
                        return;
                    }
                    state.card = payload;
                    renderCard();
                })
                .catch(function (error) {
                    showError(messageOf(error));
                })
                .then(function () {
                    if (skeleton) {
                        skeleton.hidden = true;
                    }
                });
        }

        function close() {
            root.hidden = true;
            document.body.classList.remove("psm-open");
            if (picker) {
                picker.reset();
            }
            hidePreview();
            // Fokus çekməcəni AÇAN düyməyə qayıdır (klaviatura istifadəçisi
            // siyahının başına atılmır).
            if (state.opener && document.contains(state.opener)) {
                state.opener.focus();
            }
            state.opener = null;
        }

        function messageOf(error) {
            var payload = error && error.payload;
            return (payload && (payload.message || payload.error)) || label("error");
        }

        // ── Kartın render-i ──────────────────────────────────────────────────
        function renderCard() {
            var card = state.card;
            var person = card.person || {};
            var avatar = root.querySelector("[data-psm-avatar]");
            if (avatar) {
                avatar.textContent = "";
                if (person.avatar_url) {
                    var img = document.createElement("img");
                    img.src = person.avatar_url;
                    img.alt = "";
                    avatar.appendChild(img);
                } else {
                    avatar.textContent = person.initials || "?";
                }
            }
            text(root.querySelector("[data-psm-name]"), [person.full_name, person.patronymic].filter(Boolean).join(" "));
            text(root.querySelector("[data-psm-username]"), person.username || "");
            text(root.querySelector("[data-psm-period]"), (card.period && card.period.label) || "");

            renderRecordTabs();
            renderRecord();
            if (content) {
                content.hidden = false;
            }
        }

        function renderRecordTabs() {
            var tabs = root.querySelector("[data-psm-record-tabs]");
            var records = state.card.records || [];
            if (!tabs) {
                return;
            }
            tabs.textContent = "";
            // Bir qeyd varsa seçici GÖSTƏRİLMİR — süni addım yaratmasın.
            tabs.hidden = records.length < 2;
            records.forEach(function (row, index) {
                var tab = el("button", "psm__record-tab", row.program_label || row.group_name);
                tab.type = "button";
                tab.setAttribute("role", "tab");
                tab.setAttribute("aria-selected", index === state.recordIndex ? "true" : "false");
                tab.addEventListener("click", function () {
                    state.recordIndex = index;
                    hidePreview();
                    if (picker) {
                        picker.reset();
                    }
                    renderRecordTabs();
                    renderRecord();
                });
                tabs.appendChild(tab);
            });
        }

        function fact(list, term, valueNode) {
            list.appendChild(el("dt", null, term));
            var dd = document.createElement("dd");
            dd.appendChild(valueNode);
            list.appendChild(dd);
        }

        function renderRecord() {
            var row = record();
            var facts = root.querySelector("[data-psm-facts]");
            var list = root.querySelector("[data-psm-enrollments]");
            var count = root.querySelector("[data-psm-enroll-count]");
            if (facts) {
                facts.textContent = "";
            }
            if (list) {
                list.textContent = "";
            }
            if (!row) {
                if (facts) {
                    facts.appendChild(el("dd", "psm__empty", label("noRecords")));
                }
                text(count, "");
                setStatusOptions(null);
                return;
            }

            if (facts) {
                var program = el("span", null, row.program_label || "—");
                if (row.program_code) {
                    program.appendChild(el("span", "psm__code", row.program_code));
                }
                fact(facts, label("program"), program);
                fact(facts, label("group"), el("span", null, row.group_name || "—"));
                if (row.faculty_name) {
                    fact(facts, label("faculty"), el("span", null, row.faculty_name));
                }
                if (row.kafedra_name) {
                    fact(facts, label("kafedra"), el("span", null, row.kafedra_name));
                }
                var admission = String(row.admission_year || "—");
                if (row.course_label) {
                    admission += " · " + row.course_label + " " + label("course");
                }
                fact(facts, label("admission"), el("span", null, admission));
                fact(
                    facts,
                    label("statusTerm"),
                    el("span", "psm__pill psm__pill--" + (row.status_tone || "info"), row.status_label || row.status)
                );
            }

            var enrollments = row.enrollments || [];
            text(count, enrollments.length ? String(enrollments.length) : "");
            if (list) {
                if (!enrollments.length) {
                    list.appendChild(el("li", "psm__empty", label("noEnrollments")));
                } else {
                    enrollments.forEach(function (enrollment) {
                        list.appendChild(enrollmentRow(enrollment));
                    });
                }
            }
            setStatusOptions(row.status);
        }

        function enrollmentRow(enrollment) {
            var item = el("li", "psm__enrollment");
            item.appendChild(el("span", "psm__enrollment-code", enrollment.subject_code || "—"));
            item.appendChild(el("span", "psm__enrollment-name", enrollment.subject_name || ""));
            if (enrollment.is_guest) {
                var chip = el("span", "psm__guest-chip", label("guest"));
                if (enrollment.source_group_name) {
                    chip.title = enrollment.source_group_name;
                }
                item.appendChild(chip);
            }
            if (enrollment.absence_hours) {
                item.appendChild(
                    el("span", "psm__enrollment-absence", enrollment.absence_hours + " " + label("absenceHours"))
                );
            }
            return item;
        }

        // ── Köçürmənin ön baxışı ─────────────────────────────────────────────
        /* 2-ci addımın başlığı həmişə görünür; yalnız məzmun ↔ boş-vəziyyət
         * mətni yer dəyişir (addımlar «1 → 3» kimi oxunmasın). */
        function setPreviewVisible(visible) {
            var box = root.querySelector("[data-psm-preview]");
            var idle = root.querySelector("[data-psm-preview-idle]");
            if (box) {
                box.hidden = !visible;
            }
            if (idle) {
                idle.hidden = visible;
            }
        }

        function hidePreview() {
            state.preview = null;
            setPreviewVisible(false);
            syncTransferButton();
        }

        function loadPreview() {
            var row = record();
            var groupId = picker ? picker.value() : "";
            if (!row || !groupId) {
                hidePreview();
                return;
            }
            var url = root.dataset.previewUrl.replace(
                /00000000-0000-0000-0000-000000000000/,
                encodeURIComponent(row.id)
            );
            window.EMSCore.fetchJSON(url + "?group=" + encodeURIComponent(groupId))
                .then(function (payload) {
                    state.preview = payload;
                    renderPreview(payload);
                })
                .catch(function (error) {
                    hidePreview();
                    showError(messageOf(error));
                });
        }

        function renderPreview(preview) {
            if (!root.querySelector("[data-psm-preview]")) {
                return;
            }
            showError("");
            setPreviewVisible(true);
            // Saf render alt modulda (`people_academic_preview.js`). Modul
            // yüklənməyibsə çekməcənin qalanı işləyir — ön baxış sadəcə boş
            // qalır və təsdiq düyməsi aşağıdakı `syncTransferButton` ilə
            // onsuz da bağlı olur.
            if (window.EMSPeopleAcademicPreview) {
                window.EMSPeopleAcademicPreview.render(root, preview, label);
            }
            syncTransferButton();
        }

        // ── Əməllər ──────────────────────────────────────────────────────────
        function clearReasons() {
            Array.prototype.forEach.call(
                root.querySelectorAll("[data-psm-transfer-reason], [data-psm-status-reason]"),
                function (input) {
                    input.value = "";
                }
            );
        }

        function transferReason() {
            var input = root.querySelector("[data-psm-transfer-reason]");
            return input ? input.value.trim() : "";
        }

        function syncTransferButton() {
            var button = root.querySelector("[data-psm-transfer]");
            if (!button) {
                return;
            }
            var ready = !!(state.preview && state.preview.ok) && transferReason().length >= minReason;
            button.disabled = !ready;
        }

        function post(payload, successMessage, button) {
            if (button) {
                button.classList.add("is-busy");
            }
            return window.EMSCore.fetchJSON(root.dataset.actionUrl, { method: "POST", data: payload })
                .then(function () {
                    toast(successMessage, "success");
                    showError("");
                    // Cədvəl və kart eyni həqiqəti göstərsin: sətir yenilənir,
                    // çekməcə isə yeni vəziyyətlə yenidən yüklənir.
                    var peopleRoot = document.querySelector("[data-people-root]");
                    if (peopleRoot) {
                        peopleRoot.dispatchEvent(new CustomEvent("people:refresh"));
                    }
                    if (picker) {
                        picker.reset();
                    }
                    clearReasons();
                    var userId = state.card && state.card.person && state.card.person.id;
                    if (userId) {
                        open(userId, state.opener);
                    }
                })
                .catch(function (error) {
                    var message = messageOf(error);
                    showError(message);
                    toast(message, "error");
                })
                .then(function () {
                    if (button) {
                        button.classList.remove("is-busy");
                    }
                });
        }

        function submitTransfer(button) {
            var row = record();
            var groupId = picker ? picker.value() : "";
            if (!row || !groupId) {
                return;
            }
            var reason = transferReason();
            if (reason.length < minReason) {
                showError(label("reasonShort"));
                return;
            }
            post(
                { action: "transfer_group", record_id: row.id, group_id: groupId, reason: reason },
                label("transferred"),
                button
            );
        }

        function selectedStatus() {
            var active = root.querySelector('[data-psm-status][aria-checked="true"]');
            return active ? active.dataset.psmStatus : "";
        }

        function setStatusOptions(currentStatus) {
            var buttons = root.querySelectorAll("[data-psm-status]");
            Array.prototype.forEach.call(buttons, function (button) {
                var isCurrent = button.dataset.psmStatus === currentStatus;
                button.setAttribute("aria-checked", "false");
                // Cari status seçilə bilməz — server də onu 409 ilə rədd edir,
                // amma istifadəçi bunu KLİKDƏN ƏVVƏL görməlidir.
                button.disabled = isCurrent || !currentStatus;
                button.classList.toggle("is-current", isCurrent);
            });
            syncStatusButton();
        }

        function syncStatusButton() {
            var button = root.querySelector("[data-psm-status-save]");
            if (button) {
                button.disabled = !selectedStatus();
            }
        }

        function submitStatus(button) {
            var row = record();
            var status = selectedStatus();
            var input = root.querySelector("[data-psm-status-reason]");
            var reason = input ? input.value.trim() : "";
            if (!row || !status) {
                return;
            }
            post({ action: "set_academic_status", record_id: row.id, status: status, reason: reason }, label("statusSaved"), button);
        }

        // ── Bağlamalar ───────────────────────────────────────────────────────
        var pickerHost = root.querySelector(".js-psm-group");
        if (pickerHost && window.EMSSearchableSelect) {
            picker = window.EMSSearchableSelect.create(pickerHost, {
                url: root.dataset.groupsUrl,
                multi: false,
                placeholder: root.dataset.i18nGroupPlaceholder || "",
                emptyText: root.dataset.i18nGroupEmpty || "",
                skeleton: true,
                // Cari qrup siyahıdan ÇIXARILIR: «olduğu qrupa köçürmə» seçimi
                // yanlış gözlənti yaradırdı (server onsuz da bloklayır).
                dependParam: "exclude",
                getDependValue: function () {
                    var row = record();
                    return row ? row.group_id : "";
                },
                onChange: loadPreview
            });
        }

        root.addEventListener("click", function (event) {
            if (event.target.closest("[data-psm-close]")) {
                close();
                return;
            }
            var statusOption = event.target.closest("[data-psm-status]");
            if (statusOption && !statusOption.disabled) {
                Array.prototype.forEach.call(root.querySelectorAll("[data-psm-status]"), function (button) {
                    button.setAttribute("aria-checked", button === statusOption ? "true" : "false");
                });
                syncStatusButton();
                return;
            }
            var transfer = event.target.closest("[data-psm-transfer]");
            if (transfer) {
                submitTransfer(transfer);
                return;
            }
            var statusSave = event.target.closest("[data-psm-status-save]");
            if (statusSave) {
                submitStatus(statusSave);
            }
        });

        root.addEventListener("input", function (event) {
            if (event.target.matches("[data-psm-transfer-reason]")) {
                syncTransferButton();
            }
        });

        // Escape bağlayır; Tab fokusu çekməcə İÇİNDƏ dövr etdirir (fokus arxadakı
        // cədvələ «qaçmır» — modal müqaviləsi).
        root.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                event.stopPropagation();
                close();
                return;
            }
            if (event.key !== "Tab" || !panel) {
                return;
            }
            var items = Array.prototype.filter.call(panel.querySelectorAll(FOCUSABLE), function (node) {
                return node.offsetParent !== null;
            });
            if (!items.length) {
                return;
            }
            var first = items[0];
            var last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });

        // Sətirdəki «İdarə et» düyməsi cədvəl hər yeniləndə YENİDƏN qurulur,
        // ona görə bağlama sənəd səviyyəsində delegasiya olunur.
        document.addEventListener("click", function (event) {
            var opener = event.target.closest("[data-psm-open]");
            if (opener) {
                event.preventDefault();
                open(opener.dataset.psmOpen, opener);
            }
        });
    }

    if (window.EMSReady) {
        window.EMSReady(boot);
    } else {
        document.addEventListener("DOMContentLoaded", boot);
    }
})();
