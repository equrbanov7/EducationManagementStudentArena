/*
 * create_question_bank.js
 * Source: exams/teacher/create_question_bank.html
 *         (extracted from partials/_create_question_bank_scripts.html)
 *
 * Written/coding question-bank builder: add/remove blocks, live block-title
 * mirroring, duplicate-name guard, and the per-block AI generation panel.
 *
 * Config + i18n come from JSON islands rendered by the template:
 *   #qbank-config           scalars/flags/URLs
 *   #qbank-i18n             workbench + AI-panel labels (I18N_QBANK)
 *   #ai-question-bank-i18n  AI status strings (bootstrapped onto window global)
 *
 * openDeleteModal / closeDeleteModal / confirmDelete stay GLOBAL — the shared
 * static/js/csp_event_handlers.js delegates the data-delete-block-* triggers to
 * them. Keep them as top-level function declarations so they remain on window.
 */
(function () {
    "use strict";

    function readIsland(id) {
        var el = document.getElementById(id);
        if (!el) { return {}; }
        try { return JSON.parse(el.textContent) || {}; }
        catch (err) { return {}; }
    }

    var CFG = readIsland("qbank-config");
    var I18N_QBANK = readIsland("qbank-i18n");

    var QBANK_DEFAULT_BLOCK_PAINT_ENABLED = Boolean(CFG.defaultBlockPaintEnabled);
    var QBANK_SHOW_BLOCK_PAINT = Boolean(CFG.showBlockPaint);
    var QBANK_AI_URL = CFG.aiUrl || "";
    var QBANK_EXTRACT_URL = CFG.extractUrl || "";

    var blockToDelete = null;
    var blockCounter = Number(CFG.blockCount);
    if (!blockCounter || blockCounter === 0) { blockCounter = 1; }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function renderAiBlockPanel(uniqueID, defaultTitle) {
        var fileInputId = "writtenAiSourceFile" + uniqueID;
        var promptPlaceholder = escapeHtml(
            (I18N_QBANK.aiDynamicPlaceholder || "").replace("{block_name}", defaultTitle)
        );

        return "" +
            '<div class="ai-block-panel"' +
            '     data-ai-question-form' +
            '     data-ai-context="written"' +
            '     data-ai-url="' + QBANK_AI_URL + '"' +
            '     data-extract-url="' + QBANK_EXTRACT_URL + '">' +
            '    <div class="ai-block-panel__head">' +
            '        <span class="ai-block-panel__icon"><i class="fas fa-robot"></i></span>' +
            '        <div>' +
            '            <h6>' + I18N_QBANK.aiBlockTitle + '</h6>' +
            '            <p>' + I18N_QBANK.aiBlockDesc + '</p>' +
            '        </div>' +
            '    </div>' +
            '    <div class="ai-block-grid">' +
            '        <label class="ai-block-field ai-block-field--wide">' +
            '            <span>' + I18N_QBANK.aiPromptTopic + '</span>' +
            '            <textarea name="prompt" rows="2" placeholder="' + promptPlaceholder + '"></textarea>' +
            '        </label>' +
            '        <label class="ai-block-field ai-file-field" for="' + fileInputId + '">' +
            '            <span>' + I18N_QBANK.aiLectureFile + '</span>' +
            '            <input id="' + fileInputId + '" class="ai-file-input" data-ai-file-input type="file" name="source_file" accept=".pdf,.txt,.png,.jpg,.jpeg">' +
            '            <span class="ai-file-picker">' +
            '                <i class="fas fa-upload"></i>' +
            '                <strong>' + I18N_QBANK.aiChooseFile + '</strong>' +
            '            </span>' +
            '            <small class="ai-file-name" data-ai-file-name-for="' + fileInputId + '">' + I18N_QBANK.aiNoFileSelected + '</small>' +
            '        </label>' +
            '        <label class="ai-block-field">' +
            '            <span>' + I18N_QBANK.aiQuestionCount + '</span>' +
            '            <input type="number" name="question_count" min="1" max="50" value="5">' +
            '        </label>' +
            '        <label class="ai-block-field">' +
            '            <span>' + I18N_QBANK.aiDifficulty + '</span>' +
            '            <div class="bootstrap-single-select ai-difficulty-select">' +
            '                <select name="difficulty" class="form-select bootstrap-single-select__native" data-bootstrap-select>' +
            '                    <option value="medium" selected>' + I18N_QBANK.aiMedium + '</option>' +
            '                    <option value="easy">' + I18N_QBANK.aiEasy + '</option>' +
            '                    <option value="hard">' + I18N_QBANK.aiHard + '</option>' +
            '                    <option value="mixed">' + I18N_QBANK.aiMixed + '</option>' +
            '                </select>' +
            '            </div>' +
            '        </label>' +
            '        <div class="ai-block-actions">' +
            '            <div class="ai-insert-toggle" aria-label="' + I18N_QBANK.aiInsertModeLabel + '">' +
            '                <label>' +
            '                    <input type="radio" name="ai_insert_mode_' + uniqueID + '" data-ai-insert-mode value="append" checked>' +
            '                    <span>' + I18N_QBANK.aiAppendMode + '</span>' +
            '                </label>' +
            '                <label>' +
            '                    <input type="radio" name="ai_insert_mode_' + uniqueID + '" data-ai-insert-mode value="replace">' +
            '                    <span>' + I18N_QBANK.aiReplaceMode + '</span>' +
            '                </label>' +
            '            </div>' +
            '            <button type="button" class="ai-generate-btn" data-ai-question-submit>' +
            '                <i class="fas fa-magic"></i> ' + I18N_QBANK.aiGenerate +
            '            </button>' +
            '            <span class="ai-question-status" data-ai-question-status role="status" aria-live="polite"></span>' +
            '        </div>' +
            '    </div>' +
            '</div>';
    }

    document.addEventListener('DOMContentLoaded', function() {
        var wrapper = document.getElementById('blocks-wrapper');
        var addBtn = document.getElementById('add-new-block-btn');
        if (!wrapper || !addBtn) { return; }

        function updateBlockTitle(block) {
            if (!block) return;

            var input = block.querySelector('.block-name-input');
            var title = block.querySelector('.block-title-text');
            if (!input || !title) return;

            var fallbackTitle = block.getAttribute('data-default-title') || I18N_QBANK.blockDefault;
            title.textContent = input.value.trim() || fallbackTitle;
        }

        addBtn.addEventListener('click', function() {
            blockCounter++;
            var uniqueID = Date.now();
            var defaultTitle = (I18N_QBANK.blockDefault || "") + " " + blockCounter;

            var newBlockHTML = "" +
                '<div class="block-card block-item" id="block-card-' + uniqueID + '" data-default-title="' + defaultTitle + '">' +
                '    <div class="block-header">' +
                '        <h5 class="block-title"><i class="fas fa-cube"></i> <span class="block-title-text">' + defaultTitle + '</span></h5>' +
                '        <input type="hidden" class="block-db-id" name="block_db_id_' + uniqueID + '" value="">' +
                '        <button type="button" class="btn-delete" data-delete-block-trigger>' +
                '            <i class="fas fa-trash"></i> ' + I18N_QBANK.actionDelete +
                '        </button>' +
                '    </div>' +
                '    <div class="block-body">' +
                '        <div class="form-group">' +
                '            <label>' + I18N_QBANK.labelBlockName + ':</label>' +
                '            <input type="text" name="block_name_' + uniqueID + '" value="' + defaultTitle + '"' +
                '                   class="form-control-custom block-name-input" required>' +
                '        </div>' +
                '        <div class="form-group time-input-group">' +
                '            <label><i class="far fa-clock"></i> ' + I18N_QBANK.labelBlockTimeMinutes + ':</label>' +
                '            <input type="number" name="block_time_' + uniqueID + '" class="form-control-custom" placeholder="' + I18N_QBANK.placeholderUnlimited + '">' +
                '        </div>' +
                (QBANK_SHOW_BLOCK_PAINT ? (
                '        <div class="form-group">' +
                '            <label class="paint-setting-row">' +
                '                <input type="checkbox" name="block_enable_paint_' + uniqueID + '" ' + (QBANK_DEFAULT_BLOCK_PAINT_ENABLED ? 'checked' : '') + '>' +
                '                <span class="paint-setting-check" aria-hidden="true">' +
                '                    <i class="fas fa-paint-brush"></i>' +
                '                </span>' +
                '                <span class="paint-setting-copy">' +
                '                    <span class="paint-setting-label">' + I18N_QBANK.labelBlockEnablePaint + '</span>' +
                '                    <span class="paint-setting-help">' + I18N_QBANK.helpBlockEnablePaint + '</span>' +
                '                </span>' +
                '            </label>' +
                '        </div>'
                ) : '') +
                renderAiBlockPanel(uniqueID, defaultTitle) +
                '        <div class="form-group">' +
                '            <label>' + I18N_QBANK.labelQuestionsCopyPaste + ':</label>' +
                '            <textarea name="block_content_' + uniqueID + '" class="form-control-custom"' +
                '                      data-written-question-textarea' +
                '                      placeholder="' + I18N_QBANK.placeholderQuestionText + '"></textarea>' +
                '            <small class="form-help-text">' + I18N_QBANK.helpQuestionFormats + '</small>' +
                '        </div>' +
                '    </div>' +
                '</div>';

            var tempDiv = document.createElement('div');
            tempDiv.innerHTML = newBlockHTML.trim();
            var newBlock = tempDiv.firstElementChild;
            wrapper.appendChild(newBlock);

            if (window.initAiQuestionBankPanel) {
                newBlock.querySelectorAll('[data-ai-question-form]').forEach(window.initAiQuestionBankPanel);
            }

            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        });

        wrapper.addEventListener('input', function(event) {
            if (event.target.classList.contains('block-name-input')) {
                updateBlockTitle(event.target.closest('.block-item'));
            }
        });

        wrapper.querySelectorAll('.block-item').forEach(updateBlockTitle);

        var bankForm = document.getElementById('bankForm');
        if (bankForm) {
            bankForm.addEventListener('submit', function(e) {
                var inputs = document.querySelectorAll('.block-name-input');
                var names = [];
                var hasDuplicate = false;
                var duplicateMessage = "";

                inputs.forEach(function(input) {
                    var parentBlock = input.closest('.block-item');
                    if (!parentBlock) return;

                    var val = input.value.trim().toLowerCase();
                    if (!val) return;

                    if (names.includes(val)) {
                        hasDuplicate = true;
                        input.style.borderColor = 'red';
                        duplicateMessage = duplicateMessage || (
                            (I18N_QBANK.alertDuplicateBlockName || "")
                                .replace("{block_name}", input.value)
                                .replace("{name}", input.value)
                        );
                    } else {
                        input.style.borderColor = '#dfe6e9';
                        names.push(val);
                    }
                });

                if (hasDuplicate) {
                    e.preventDefault();
                    window.EMSToast.show(duplicateMessage, "error");
                }
            });
        }
    });

    function openDeleteModal(btn) {
        blockToDelete = btn.closest('.block-item');
        document.getElementById('deleteModal').style.display = 'flex';
    }

    function closeDeleteModal() {
        document.getElementById('deleteModal').style.display = 'none';
        blockToDelete = null;
    }

    function confirmDelete() {
        if (!blockToDelete) return;

        var dbIdInput = blockToDelete.querySelector('.block-db-id');
        var dbId = dbIdInput ? dbIdInput.value : '';

        if (dbId) {
            var deletedInput = document.getElementById('deleted_block_ids');
            var currentIds = deletedInput.value ? deletedInput.value.split(',') : [];
            currentIds.push(dbId);
            deletedInput.value = currentIds.join(',');
        }

        blockToDelete.remove();
        closeDeleteModal();
    }

    window.addEventListener('click', function(event) {
        var modal = document.getElementById('deleteModal');
        if (event.target === modal) closeDeleteModal();
    });

    // Keep the delete helpers on the global scope for csp_event_handlers.js.
    window.openDeleteModal = openDeleteModal;
    window.closeDeleteModal = closeDeleteModal;
    window.confirmDelete = confirmDelete;
})();
