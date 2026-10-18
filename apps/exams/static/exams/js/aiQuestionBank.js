(function () {
    "use strict";

    var i18n = window.AI_QUESTION_BANK_I18N || {};

    function t(key, fallback) {
        return i18n[key] || fallback;
    }

    function getCsrfToken() {
        var tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
        if (tokenInput && tokenInput.value) return tokenInput.value;

        var cookieMatch = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return cookieMatch ? decodeURIComponent(cookieMatch[1]) : "";
    }

    function setStatus(panel, message, state) {
        if (!panel || typeof panel.querySelector !== "function") return;
        var status = panel.querySelector("[data-ai-question-status]");
        if (!status) return;
        status.textContent = message || "";
        status.classList.remove("is-error", "is-success", "is-loading");
        if (state) status.classList.add("is-" + state);
    }

    function setBusy(panel, busy) {
        var button = panel.querySelector("[data-ai-question-submit]");
        if (!button) return;

        if (!button.dataset.defaultLabel) {
            button.dataset.defaultLabel = button.innerHTML;
        }

        // 2026-10-19: yüklənmə vəziyyəti — düymə söndürülür, panel aria-busy, ikinci klik yoxdur.
        button.disabled = busy;
        button.classList.toggle("is-loading", Boolean(busy));
        button.setAttribute("aria-busy", busy ? "true" : "false");
        panel.classList.toggle("is-busy", Boolean(busy));
        panel.setAttribute("aria-busy", busy ? "true" : "false");
        if (busy) {
            button.textContent = "";
            var spinner = document.createElement("i");
            spinner.className = "fas fa-circle-notch fa-spin";
            spinner.setAttribute("aria-hidden", "true");
            var label = document.createElement("span");
            label.textContent = t("generating", gettext("Yaradılır..."));
            button.appendChild(spinner);
            button.appendChild(label);
        } else {
            button.innerHTML = button.dataset.defaultLabel;
        }
    }

    function appendField(formData, field) {
        if (!field.name || field.disabled) return;

        var type = (field.type || "").toLowerCase();
        if (type === "file") {
            if (field.files && field.files[0]) {
                formData.append(field.name, field.files[0]);
            }
            return;
        }

        if ((type === "checkbox" || type === "radio") && !field.checked) {
            return;
        }

        formData.append(field.name, field.value || "");
    }

    function buildFormData(panel) {
        var formData = new FormData();
        panel.querySelectorAll("input, textarea, select").forEach(function (field) {
            appendField(formData, field);
        });

        var block = panel.closest(".block-item");
        if (block && !formData.has("block_name")) {
            var blockNameInput = block.querySelector(".block-name-input");
            if (blockNameInput) {
                formData.append("block_name", blockNameInput.value || "");
            }
        }

        if (!formData.has("insert_mode")) {
            var checkedMode = panel.querySelector("[data-ai-insert-mode]:checked");
            if (checkedMode) {
                formData.append("insert_mode", checkedMode.value || "append");
            }
        }

        if (!formData.has("csrfmiddlewaretoken")) {
            formData.append("csrfmiddlewaretoken", getCsrfToken());
        }

        return formData;
    }

    function findTarget(panel) {
        var targetSelector = panel.getAttribute("data-ai-target");
        if (targetSelector) {
            return document.querySelector(targetSelector);
        }

        var block = panel.closest(".block-item");
        if (block) {
            return block.querySelector("[data-written-question-textarea], textarea[name^='block_content_']");
        }

        return null;
    }

    function insertGeneratedText(panel, generatedText, insertMode) {
        var target = findTarget(panel);
        if (!target) {
            setStatus(panel, t("targetMissing", gettext("Mətn sahəsi tapılmadı.")), "error");
            return;
        }

        var text = (generatedText || "").trim();
        if (!text) {
            setStatus(panel, t("emptyResponse", gettext("AI boş cavab qaytardı.")), "error");
            return;
        }

        var current = target.value.trim();
        if (insertMode === "replace" || !current) {
            target.value = text;
        } else {
            target.value = current + "\n\n" + text;
        }

        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.focus({ preventScroll: true });

        var staleResults = document.querySelector(".results-container");
        if (panel.getAttribute("data-ai-context") === "test" && staleResults) {
            staleResults.remove();
        }
    }


    // P3 (2026-07-02): fayl varsa AI sorğusundan ƏVVƏL mətn worker-də çıxarılır
    // (start + status-poll). OCR-lı PDF-lər sinxron sorğunu dəqiqələrlə tuturdu.
    // Endpoint yoxdursa/404-dürsə köhnə davranışa (faylı birbaşa göndər) qayıdır.
    // Tutum 2026-10-06: start və status endpointləri DƏRHAL cavab verir (server
    // yatmır) — poll geri çəkilmə ilə: 1 s → ×1.5 → 5 s tavan, büdcə ~10 dəq.
    var EXTRACT_POLL_START_MS = 1000;
    var EXTRACT_POLL_MAX_MS = 5000;
    var EXTRACT_POLL_BUDGET_MS = 10 * 60 * 1000;

    function pollDelay(attempt) {
        return Math.min(EXTRACT_POLL_MAX_MS, Math.round(EXTRACT_POLL_START_MS * Math.pow(1.5, attempt)));
    }

    function pollJob(statusUrl, attempt, failFallback, startedAt) {
        startedAt = startedAt || Date.now();
        return fetch(statusUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        })
            .then(function (response) { return response.json(); })
            .then(function (json) {
                if (json.status === "success") return json;
                if (json.status === "failed") {
                    var meta = json.meta || {};
                    throw new Error(json.error || meta.error || failFallback);
                }
                if (Date.now() - startedAt >= EXTRACT_POLL_BUDGET_MS) {
                    throw new Error(t("extractTimeout", gettext("Mətn çıxarma çox uzun çəkdi. Yenidən cəhd edin.")));
                }
                return new Promise(function (resolve) {
                    setTimeout(resolve, pollDelay(attempt));
                }).then(function () {
                    return pollJob(statusUrl, attempt + 1, failFallback, startedAt);
                });
            });
    }

    function pollExtraction(statusUrl, attempt) {
        return pollJob(statusUrl, attempt, t("extractFailed", gettext("Fayldan mətn çıxarıla bilmədi."))).then(function (json) {
            return json.text || "";
        });
    }

    function extractFileTextIfNeeded(panel, formData) {
        var extractUrl = panel.getAttribute("data-extract-url");
        var file = formData.get("source_file");
        if (!extractUrl || !file || typeof file === "string" || !file.name || !file.size) {
            return Promise.resolve(formData);
        }

        var fd = new FormData();
        fd.append("source_file", file);
        setStatus(panel, t("extracting", gettext("Fayldan mətn çıxarılır...")), "loading");

        return fetch(extractUrl, {
            method: "POST",
            body: fd,
            headers: {
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin"
        })
            .then(function (response) {
                if (response.status === 404) return null; // endpoint yoxdur → köhnə yol
                return response.text().then(function (body) {
                    var json = {};
                    try { json = body ? JSON.parse(body) : {}; } catch (e) { json = {}; }
                    if (!response.ok || !json.ok) {
                        throw new Error(json.error || t("extractFailed", gettext("Fayldan mətn çıxarıla bilmədi.")));
                    }
                    return json;
                });
            })
            .then(function (json) {
                if (json === null) return formData;
                var textPromise = json.status === "success"
                    ? Promise.resolve(json.text || "")
                    : pollExtraction(extractUrl + json.job_id + "/", 0);
                return textPromise.then(function (text) {
                    var prev = String(formData.get("source_text") || "").trim();
                    formData.set("source_text", prev ? prev + "\n\n" + text : text);
                    formData.delete("source_file");
                    setStatus(panel, t("loading", gettext("Gemini 2.5 Pro sualları hazırlayır...")), "loading");
                    return formData;
                });
            });
    }

    function handleGenerate(panel) {
        var url = panel.getAttribute("data-ai-url");
        if (!url) {
            setStatus(panel, t("endpointMissing", gettext("AI endpoint tapılmadı.")), "error");
            return;
        }

        var formData = buildFormData(panel);
        var prompt = String(formData.get("prompt") || "").trim();
        var hasSourceFile = Boolean(formData.get("source_file"));
        var sourceText = String(formData.get("source_text") || "").trim();

        if (panel.classList.contains("is-busy")) return;

        if (!prompt && !hasSourceFile && !sourceText) {
            setStatus(panel, t("emptyInput", gettext("Prompt yazın və ya fayl yükləyin.")), "error");
            return;
        }

        setBusy(panel, true);
        setStatus(panel, t("loading", gettext("Gemini 2.5 Pro sualları hazırlayır...")), "loading");

        extractFileTextIfNeeded(panel, formData).then(function (preparedFormData) {
        return fetch(url, {
            method: "POST",
            body: preparedFormData,
            headers: {
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            }
        })
            .then(function (response) {
                return response.text().then(function (body) {
                    var json = {};
                    try {
                        json = body ? JSON.parse(body) : {};
                    } catch (error) {
                        throw new Error(t("generateFailed", gettext("AI sual yaratma alınmadı.")));
                    }
                    if (!response.ok || !json.ok) {
                        throw new Error(json.error || t("generateFailed", gettext("AI sual yaratma alınmadı.")));
                    }
                    return json;
                });
            })
            .then(function (json) {
                // P4: real broker rejimində 202 + job_id gəlir → status poll.
                if (json.job_id && json.status && json.status !== "success") {
                    var extractUrl = panel.getAttribute("data-extract-url") || "";
                    return pollJob(
                        extractUrl + json.job_id + "/",
                        0,
                        t("generateFailed", gettext("AI sual yaratma alınmadı."))
                    ).then(function (done) {
                        var meta = done.meta || {};
                        return {
                            ok: true,
                            text: done.text || "",
                            question_count: meta.question_count,
                            remaining: meta.remaining,
                            limit: meta.limit
                        };
                    });
                }
                return json;
            })
            .then(function (json) {
                insertGeneratedText(panel, json.text || "", String(formData.get("insert_mode") || "append"));
                var count = json.question_count || 0;
                var quota = "";
                if (json.remaining !== undefined && json.limit !== undefined) {
                    quota = " " + t("remainingRequests", gettext("Qalan sorğu")) + ": " + json.remaining + "/" + json.limit + ".";
                }
                setStatus(
                    panel,
                    t("readyTemplate", gettext("{count} sual hazırdır. Önizləmə ilə yoxlayın."))
                        .replace("{count}", String(count)) + quota,
                    "success"
                );
            })
            .catch(function (error) {
                setStatus(panel, error.message || t("generateFailed", gettext("AI sual yaratma alınmadı.")), "error");
            })
            .finally(function () {
                setBusy(panel, false);
            });
        }).catch(function (error) {
            setStatus(panel, error.message || t("extractFailed", gettext("Fayldan mətn çıxarıla bilmədi.")), "error");
            setBusy(panel, false);
        });
    }

    // ── Fayl drop zone (2026-10-19): seçilmiş adın göstərilməsi, «çıxar» düyməsi, sürüklə-burax ──
    var ACCEPTED_EXT = [".pdf", ".txt", ".png", ".jpg", ".jpeg"];

    function isAcceptedFile(file) {
        var name = String((file && file.name) || "").toLowerCase();
        for (var i = 0; i < ACCEPTED_EXT.length; i += 1) {
            if (name.slice(-ACCEPTED_EXT[i].length) === ACCEPTED_EXT[i]) return true;
        }
        return false;
    }

    function formatSize(bytes) {
        var size = Number(bytes) || 0;
        if (size >= 1024 * 1024) return (size / (1024 * 1024)).toFixed(1) + " MB";
        return Math.max(1, Math.round(size / 1024)) + " KB";
    }

    function renderFileState(panel, input) {
        var file = input.files && input.files[0] ? input.files[0] : null;
        var nameEl = panel.querySelector('[data-ai-file-name-for="' + input.id + '"]');
        var zone = input.closest("[data-ai-dropzone]");
        var clearBtn = zone ? zone.querySelector("[data-ai-file-clear]") : null;
        var hint = zone ? zone.querySelector("[data-ai-file-hint]") : null;
        if (nameEl) {
            var emptyLabel = nameEl.getAttribute("data-empty-label") || t("noFileSelected", gettext("Fayl seçilməyib"));
            nameEl.textContent = file ? file.name : emptyLabel;
            nameEl.classList.toggle("has-file", Boolean(file));
            nameEl.title = file ? file.name : "";
        }
        if (hint) {
            if (!hint.dataset.defaultHint) hint.dataset.defaultHint = hint.textContent;
            hint.textContent = file ? formatSize(file.size) : hint.dataset.defaultHint;
        }
        if (zone) zone.classList.toggle("has-file", Boolean(file));
        if (clearBtn) clearBtn.hidden = !file;
    }

    function bindFileInput(panel, input) {
        var zone = input.closest("[data-ai-dropzone]");
        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            if (file && !isAcceptedFile(file)) {
                input.value = "";
                setStatus(panel, t("fileTypeInvalid", gettext("Bu fayl növü dəstəklənmir — PDF, TXT, PNG və ya JPG seçin.")), "error");
            }
            // Növbəti tick: testQuestionBank_upload.js ölçü yoxlamasında input-u sıfırlaya bilər.
            window.setTimeout(function () { renderFileState(panel, input); }, 0);
        });
        renderFileState(panel, input);
        if (!zone) return;

        var clearBtn = zone.querySelector("[data-ai-file-clear]");
        if (clearBtn) {
            clearBtn.addEventListener("click", function (event) {
                event.preventDefault();
                input.value = "";
                renderFileState(panel, input);
                setStatus(panel, t("fileRemoved", gettext("Fayl çıxarıldı.")), "");
                input.focus({ preventScroll: true });
            });
        }

        function stop(event) {
            event.preventDefault();
            event.stopPropagation();
        }
        zone.addEventListener("dragenter", function (event) {
            stop(event);
            zone.classList.add("is-dragover");
        });
        zone.addEventListener("dragover", function (event) {
            stop(event);
            if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
            zone.classList.add("is-dragover");
        });
        zone.addEventListener("dragleave", function (event) {
            if (event.relatedTarget && zone.contains(event.relatedTarget)) return;
            zone.classList.remove("is-dragover");
        });
        zone.addEventListener("drop", function (event) {
            stop(event);
            zone.classList.remove("is-dragover");
            var files = event.dataTransfer && event.dataTransfer.files;
            if (!files || !files.length) return;
            if (!isAcceptedFile(files[0])) {
                setStatus(panel, t("fileTypeInvalid", gettext("Bu fayl növü dəstəklənmir — PDF, TXT, PNG və ya JPG seçin.")), "error");
                return;
            }
            try {
                var dt = new DataTransfer();
                dt.items.add(files[0]);
                input.files = dt.files;
            } catch (err) {
                return; // köhnə brauzer: yalnız «Fayl seçin» düyməsi işləyir
            }
            // testQuestionBank_upload.js-in ölçü yoxlaması da `change`-ə qulaq asır.
            input.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }

    function initPanel(panel) {
        if (!panel || panel.dataset.aiQuestionPanelReady === "true") return;
        var button = panel.querySelector("[data-ai-question-submit]");
        if (!button) return;
        panel.dataset.aiQuestionPanelReady = "true";

        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.init(panel);
        }

        panel.querySelectorAll("[data-ai-file-input]").forEach(function (input) {
            bindFileInput(panel, input);
        });

        button.addEventListener("click", function (event) {
            event.preventDefault();
            handleGenerate(panel);
        });

        panel.addEventListener("keydown", function (event) {
            var tagName = event.target && event.target.tagName ? event.target.tagName.toUpperCase() : "";
            var type = String((event.target && event.target.type) || "").toLowerCase();
            // Yalnız mətn/rəqəm sahəsində Enter generasiya edir — düymə, fayl, radio və
            // seçici menyusunda Enter öz işini görsün (əvvəl «Fayl seç»-də Enter sorğu atırdı).
            if (event.key === "Enter" && tagName === "INPUT" && (type === "number" || type === "text")) {
                event.preventDefault();
                handleGenerate(panel);
            }
        });
    }

    // AJAX-safe: EMSReady hər bölmə swap-ından sonra da işləyir; initPanel idempotentdir
    // (data-ai-question-panel-ready). Köhnə səhifələr üçün DOMContentLoaded ehtiyatı.
    function initAll(root) {
        var scope = root && typeof root.querySelectorAll === "function" ? root : document;
        scope.querySelectorAll("[data-ai-question-form]").forEach(initPanel);
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(function () { initAll(document); });
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { initAll(document); });
    } else {
        initAll(document);
    }

    window.initAiQuestionBankPanel = initPanel;
})();
