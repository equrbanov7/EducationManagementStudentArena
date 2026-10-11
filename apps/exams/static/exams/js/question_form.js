/* =========================================================================
   question_form.js — sual formu (imtahan sualı modalı + bank sualı modalı +
   ehtiyat səhifə). API: window.ExamQuestionForm.init(root) — host səhifə
   (teacher_exam_detail.js, teacher_questions_bank.js) formanı AJAX ilə
   modal gövdəsinə qoyandan sonra çağırır; müstəqil səhifədə EMSReady.

   2026-10-10 redizayn (sahib «modern UX/UI»):
     • Fayl zonası: klik/klaviatura, sürükləyib-buraxma, önizləmə (şəkil),
       ad + ölçü, «×» ilə götürmə, növ/ölçü yoxlaması (10 MB / 30 MB) —
       native «Choose File / No file chosen» (brauzer dili) görünmür.
     • Mövcud media silinməsi EMSConfirm ilə; nəticə alert() əvəzinə sahədə.
     • Variant etiketi serverin «Variant %(n)s» nümunəsindən (əvvəl JS
       ingilis UI-da da «1-ci variant» yazırdı).
     • Tək cavab rejimində ikinci «düzgün» işarəsi bloklanır + izah.
   İdempotent: hər kök bir dəfə bağlanır (WeakSet).
   ========================================================================= */
(function () {
    "use strict";

    var initialized = new WeakSet();
    var IMAGE_EXT = /\.(jpe?g|jfif|png|gif|webp)$/i;
    var VIDEO_EXT = /\.(mp4|webm|mov)$/i;

    function formatSize(bytes) {
        if (bytes >= 1024 * 1024) {
            return (bytes / (1024 * 1024)).toFixed(1).replace(/\.0$/, "") + " MB";
        }
        return Math.max(1, Math.round(bytes / 1024)) + " KB";
    }

    function fileAllowed(kind, file) {
        var type = String(file.type || "").toLowerCase();
        if (kind === "image") {
            return type.indexOf("image/") === 0 || IMAGE_EXT.test(file.name || "");
        }
        return ["video/mp4", "video/webm", "video/quicktime"].indexOf(type) !== -1 || VIDEO_EXT.test(file.name || "");
    }

    /* ── Fayl zonası ─────────────────────────────────────────────────────── */
    function initDropzone(root, drop) {
        var kind = drop.getAttribute("data-qf-drop");
        var input = drop.querySelector(".qf-drop__input");
        var zone = drop.querySelector(".qf-drop__zone");
        var box = drop.querySelector("[data-qf-file]");
        var nameEl = drop.querySelector("[data-qf-file-name]");
        var sizeEl = drop.querySelector("[data-qf-file-size]");
        var thumb = drop.querySelector("[data-qf-thumb]");
        var video = drop.querySelector("[data-qf-video]");
        var errorEl = drop.querySelector("[data-qf-file-error]");
        var current = drop.querySelector("[data-qf-current]");
        var clearInput = drop.querySelector(".qf-clear-input");
        var maxBytes = (parseFloat(drop.getAttribute("data-max-mb")) || 10) * 1024 * 1024;
        var objectUrl = null;
        if (!input || !zone) {
            return;
        }

        function setError(message) {
            if (!errorEl) {
                return;
            }
            errorEl.textContent = message || "";
            errorEl.hidden = !message;
        }

        function releaseUrl() {
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                objectUrl = null;
            }
        }

        function reset() {
            releaseUrl();
            input.value = "";
            drop.classList.remove("has-file");
            if (box) {
                box.hidden = true;
            }
            if (thumb) {
                thumb.removeAttribute("src");
            }
            if (video) {
                video.removeAttribute("src");
                video.load();
            }
            if (current) {
                current.classList.remove("is-pending");
            }
        }

        function show(file) {
            releaseUrl();
            objectUrl = URL.createObjectURL(file);
            if (thumb) {
                thumb.src = objectUrl;
            }
            if (video) {
                video.src = objectUrl;
            }
            if (nameEl) {
                nameEl.textContent = file.name;
            }
            if (sizeEl) {
                sizeEl.textContent = formatSize(file.size);
            }
            if (box) {
                box.hidden = false;
            }
            drop.classList.add("has-file");
            if (current) {
                current.classList.add("is-pending");
            }
            if (clearInput) {
                clearInput.checked = false;
            }
        }

        function handle() {
            var file = input.files && input.files[0];
            setError("");
            if (!file) {
                reset();
                return;
            }
            if (!fileAllowed(kind, file)) {
                reset();
                setError(root.getAttribute("data-file-wrong-type") || "");
                return;
            }
            if (file.size > maxBytes) {
                reset();
                setError((root.getAttribute("data-file-too-large") || "").replace("{max}", String(maxBytes / 1048576)));
                return;
            }
            show(file);
        }

        input.addEventListener("change", handle);

        var removeBtn = drop.querySelector("[data-qf-file-remove]");
        if (removeBtn) {
            removeBtn.addEventListener("click", function () {
                reset();
                setError("");
                input.focus();
            });
        }

        ["dragenter", "dragover"].forEach(function (type) {
            zone.addEventListener(type, function (event) {
                event.preventDefault();
                drop.classList.add("is-dragover");
            });
        });
        ["dragleave", "dragend"].forEach(function (type) {
            zone.addEventListener(type, function () {
                drop.classList.remove("is-dragover");
            });
        });
        zone.addEventListener("drop", function (event) {
            event.preventDefault();
            drop.classList.remove("is-dragover");
            var files = event.dataTransfer && event.dataTransfer.files;
            if (!files || !files.length) {
                return;
            }
            try {
                var transfer = new DataTransfer();
                transfer.items.add(files[0]);
                input.files = transfer.files;
            } catch (err) {
                return; // köhnə brauzer: klik ilə seçim işləməyə davam edir
            }
            handle();
        });

        var clearBtn = drop.querySelector("[data-qf-clear-current]");
        if (clearBtn && current) {
            clearBtn.addEventListener("click", function () {
                var message = root.getAttribute(kind === "image" ? "data-confirm-delete-image" : "data-confirm-delete-video");
                var confirmer = window.EMSConfirm ? window.EMSConfirm.open({ body: message || "", danger: true }) :
                    Promise.resolve(true);
                confirmer.then(function (ok) {
                    if (!ok) {
                        clearBtn.focus();
                        return;
                    }
                    if (clearInput) {
                        clearInput.checked = true;
                    }
                    reset();
                    current.classList.add("is-cleared");
                    var note = current.querySelector("[data-qf-clear-note]");
                    if (note) {
                        note.hidden = false;
                    }
                    input.focus();
                });
            });
        }
    }

    /* ── Variantlar ──────────────────────────────────────────────────────── */
    function initOptions(root) {
        var list = root.querySelector("[data-option-list]");
        var template = root.querySelector("[data-option-card-template]");
        var answerMode = root.querySelector('select[name="answer_mode"]');
        var warning = root.querySelector("[data-single-answer-warning]");
        var form = root.querySelector("form");
        var minCount = parseInt(root.getAttribute("data-min-option-count") || "2", 10);
        var pattern = root.getAttribute("data-option-label-pattern") || "Variant %(n)s";

        function label(index) {
            return pattern.replace("%(n)s", String(index));
        }

        function cards() {
            return list ? Array.prototype.slice.call(list.querySelectorAll("[data-option-card]")) : [];
        }

        function correctBoxes() {
            return Array.prototype.slice.call(root.querySelectorAll('input[name$="_is_correct"]'));
        }

        function checkedCount() {
            return correctBoxes().filter(function (box) { return box.checked; }).length;
        }

        function isSingle() {
            return !!answerMode && answerMode.value === "single";
        }

        function setWarning(show) {
            if (!warning) {
                return;
            }
            warning.textContent = show ? (root.getAttribute("data-single-answer-warning-message") || "") : "";
            warning.hidden = !show;
        }

        function syncWarning() {
            setWarning(isSingle() && checkedCount() > 1);
        }

        function focusAnswerMode() {
            if (!answerMode) {
                return;
            }
            var wrap = answerMode.closest(".bootstrap-single-select");
            var toggle = wrap ? wrap.querySelector(".bootstrap-single-select__toggle") : null;
            (answerMode.classList.contains("is-enhanced") && toggle ? toggle : answerMode).focus();
        }

        function renumber() {
            var all = cards();
            all.forEach(function (card, position) {
                var index = position + 1;
                var text = card.querySelector('input[type="text"]');
                var box = card.querySelector('input[type="checkbox"]');
                var title = card.querySelector("[data-option-text-label]");
                var srLabel = card.querySelector("[data-option-sr-label]");
                card.setAttribute("data-option-index", String(index));
                if (title) {
                    title.textContent = label(index);
                    title.setAttribute("for", "id_option" + index + "_text");
                }
                if (srLabel) {
                    srLabel.textContent = label(index) + ": ";
                }
                if (text) {
                    text.name = "option" + index + "_text";
                    text.id = "id_option" + index + "_text";
                }
                if (box) {
                    box.name = "option" + index + "_is_correct";
                    box.id = "id_option" + index + "_is_correct";
                }
                var remove = card.querySelector("[data-remove-option-btn]");
                if (remove) {
                    remove.hidden = all.length <= minCount;
                }
            });
            syncWarning();
        }

        function addCard() {
            if (!list || !template) {
                return;
            }
            var index = cards().length + 1;
            var holder = document.createElement("div");
            holder.innerHTML = template.innerHTML.replace(/__INDEX__/g, String(index))
                .replace(/__LABEL__/g, label(index)).trim();
            var card = holder.firstElementChild;
            if (!card) {
                return;
            }
            list.appendChild(card);
            renumber();
            var text = card.querySelector('input[type="text"]');
            if (text) {
                text.focus();
            }
        }

        root.addEventListener("click", function (event) {
            if (event.target.closest("[data-add-option-btn]")) {
                addCard();
                return;
            }
            var remove = event.target.closest("[data-remove-option-btn]");
            if (remove && cards().length > minCount) {
                var card = remove.closest("[data-option-card]");
                var next = card && (card.nextElementSibling || card.previousElementSibling);
                if (card) {
                    card.remove();
                }
                renumber();
                var focusTarget = next && next.querySelector('input[type="text"]');
                if (focusTarget) {
                    focusTarget.focus();
                }
            }
        });

        root.addEventListener("change", function (event) {
            var target = event.target;
            if (!target || !/_is_correct$/.test(target.name || "")) {
                return;
            }
            if (isSingle() && target.checked && checkedCount() > 1) {
                target.checked = false;
                setWarning(true);
                focusAnswerMode();
                return;
            }
            syncWarning();
        });

        if (answerMode) {
            answerMode.addEventListener("change", syncWarning);
        }
        if (form) {
            form.addEventListener("submit", function (event) {
                if (isSingle() && checkedCount() > 1) {
                    event.preventDefault();
                    setWarning(true);
                    focusAnswerMode();
                }
            });
        }
        renumber();
    }

    function initQuestionForm(root) {
        if (!root || initialized.has(root)) {
            return;
        }
        initialized.add(root);
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.init(root);
        }
        Array.prototype.forEach.call(root.querySelectorAll("[data-qf-drop]"), function (drop) {
            initDropzone(root, drop);
        });
        initOptions(root);
        // Modalda: ilk xətalı sahəyə, yoxdursa sual mətninə fokus (klaviatura istifadəçisi üçün).
        if (root.classList.contains("qf--modal")) {
            var first = root.querySelector('[aria-invalid="true"]:not([type="file"])') || root.querySelector("textarea");
            if (first) {
                first.focus({ preventScroll: true });
            }
        }
    }

    window.ExamQuestionForm = { init: initQuestionForm };

    if (window.EMSReady) {
        window.EMSReady(function () {
            Array.prototype.forEach.call(document.querySelectorAll(".js-exam-question-form-root"), initQuestionForm);
        });
    }
})();
