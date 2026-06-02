document.addEventListener('DOMContentLoaded', function () {
    function callGlobal(name) {
        var fn = window[name];
        if (typeof fn !== 'function') {
            return undefined;
        }
        return fn.apply(window, Array.prototype.slice.call(arguments, 1));
    }

    document.addEventListener('error', function (event) {
        var target = event.target;
        if (!(target instanceof HTMLImageElement)) {
            return;
        }

        var fallbackSrc = target.getAttribute('data-fallback-src');
        var fallbackSelector = target.getAttribute('data-fallback-target');

        if (fallbackSrc && !target.dataset.fallbackApplied) {
            target.dataset.fallbackApplied = '1';
            target.src = fallbackSrc;
            return;
        }

        if (!fallbackSelector) {
            return;
        }

        target.classList.add('d-none');
        var scope = target.parentElement || document;
        var fallbackTarget = scope.querySelector(fallbackSelector) || document.querySelector(fallbackSelector);
        if (fallbackTarget) {
            fallbackTarget.classList.remove('d-none');
        }
    }, true);

    document.addEventListener('click', function (event) {
        var historyBackLink = event.target.closest('[data-history-back]');
        if (historyBackLink) {
            if (window.history.length > 1) {
                event.preventDefault();
                window.history.back();
            }
            return;
        }

        var openModalTrigger = event.target.closest('[data-open-modal-id]');
        if (openModalTrigger) {
            event.preventDefault();
            callGlobal('openModal', openModalTrigger.getAttribute('data-open-modal-id'));
            return;
        }

        var deleteCourseTrigger = event.target.closest('[data-delete-course-id]');
        if (deleteCourseTrigger) {
            event.preventDefault();
            callGlobal('deleteCourse', deleteCourseTrigger.getAttribute('data-delete-course-id'));
            return;
        }

        var deleteMemberTrigger = event.target.closest('[data-delete-member-id]');
        if (deleteMemberTrigger) {
            event.preventDefault();
            callGlobal(
                'deleteMember',
                deleteMemberTrigger.getAttribute('data-delete-member-id'),
                deleteMemberTrigger.getAttribute('data-delete-member-name') || ''
            );
            return;
        }

        var deleteResourceTrigger = event.target.closest('[data-delete-resource-course-id][data-delete-resource-id]');
        if (deleteResourceTrigger) {
            event.preventDefault();
            callGlobal(
                'deleteResource',
                deleteResourceTrigger.getAttribute('data-delete-resource-course-id'),
                deleteResourceTrigger.getAttribute('data-delete-resource-id')
            );
            return;
        }

        var editTopicTrigger = event.target.closest('[data-edit-topic-id]');
        if (editTopicTrigger) {
            event.preventDefault();
            callGlobal(
                'editTopic',
                editTopicTrigger.getAttribute('data-edit-topic-id'),
                editTopicTrigger.getAttribute('data-edit-topic-title') || '',
                editTopicTrigger.getAttribute('data-edit-topic-description') || ''
            );
            return;
        }

        var deleteTopicTrigger = event.target.closest('[data-delete-topic-course-id][data-delete-topic-id]');
        if (deleteTopicTrigger) {
            event.preventDefault();
            callGlobal(
                'deleteTopic',
                deleteTopicTrigger.getAttribute('data-delete-topic-course-id'),
                deleteTopicTrigger.getAttribute('data-delete-topic-id')
            );
            return;
        }

        var openResourceModalTrigger = event.target.closest('[data-open-resource-modal-topic-id]');
        if (openResourceModalTrigger) {
            event.preventDefault();
            callGlobal(
                'openResourceModal',
                openResourceModalTrigger.getAttribute('data-open-resource-modal-topic-id'),
                openResourceModalTrigger.getAttribute('data-open-resource-modal-title') || ''
            );
            return;
        }

        var openDeleteModalTrigger = event.target.closest('[data-delete-block-trigger]');
        if (openDeleteModalTrigger) {
            event.preventDefault();
            callGlobal('openDeleteModal', openDeleteModalTrigger);
            return;
        }

        var closeDeleteModalTrigger = event.target.closest('[data-delete-block-cancel]');
        if (closeDeleteModalTrigger) {
            event.preventDefault();
            callGlobal('closeDeleteModal');
            return;
        }

        var confirmDeleteTrigger = event.target.closest('[data-delete-block-confirm]');
        if (confirmDeleteTrigger) {
            event.preventDefault();
            callGlobal('confirmDelete');
            return;
        }

        var openExamCodeModalTrigger = event.target.closest('[data-open-exam-code-modal]');
        if (openExamCodeModalTrigger) {
            event.preventDefault();
            callGlobal('openExamCodeModal', openExamCodeModalTrigger);
            return;
        }

        var closeExamCodeModalTrigger = event.target.closest('[data-close-exam-code-modal]');
        if (closeExamCodeModalTrigger) {
            event.preventDefault();
            callGlobal('closeExamCodeModal');
            return;
        }

        var wizardNextTrigger = event.target.closest('[data-wizard-next]');
        if (wizardNextTrigger) {
            event.preventDefault();
            callGlobal('wizardNext', parseInt(wizardNextTrigger.getAttribute('data-wizard-next'), 10));
            return;
        }

        var wizardBackTrigger = event.target.closest('[data-wizard-back]');
        if (wizardBackTrigger) {
            event.preventDefault();
            callGlobal('wizardBack', parseInt(wizardBackTrigger.getAttribute('data-wizard-back'), 10));
            return;
        }

        var fileInputTrigger = event.target.closest('[data-file-input-target]');
        if (fileInputTrigger) {
            event.preventDefault();
            var targetSelector = fileInputTrigger.getAttribute('data-file-input-target');
            var fileInput = targetSelector ? document.querySelector(targetSelector) : null;
            if (fileInput) {
                fileInput.click();
            }
            return;
        }

        var removeFileTrigger = event.target.closest('[data-remove-file-question]');
        if (removeFileTrigger) {
            event.preventDefault();
            var questionId = removeFileTrigger.getAttribute('data-remove-file-question');
            var fileIndex = removeFileTrigger.getAttribute('data-remove-file-index');
            if (fileIndex !== null) {
                callGlobal('removeFile', questionId, parseInt(fileIndex, 10));
            } else {
                callGlobal('removeFile', questionId);
            }
            return;
        }

        var toggleAllTrigger = event.target.closest('[data-toggle-all]');
        if (toggleAllTrigger) {
            event.preventDefault();
            callGlobal('toggleAll', toggleAllTrigger.getAttribute('data-toggle-all') === 'true');
            return;
        }

        var rowToggleTrigger = event.target.closest('[data-toggle-row-card]');
        if (rowToggleTrigger) {
            if (event.target.closest('button, a, textarea, select, details, summary, .warning-box')) {
                return;
            }
            if (event.target.closest('input') && event.target.type !== 'checkbox') {
                return;
            }
            callGlobal('toggleRow', rowToggleTrigger, event);
            return;
        }

        var gradeNextTrigger = event.target.closest('[data-submit-grade-next]');
        if (gradeNextTrigger) {
            event.preventDefault();
            callGlobal(
                'submitGrade',
                { preventDefault: function () {}, target: gradeNextTrigger },
                gradeNextTrigger.getAttribute('data-submit-grade-next'),
                true
            );
        }
    });

    document.addEventListener('change', function (event) {
        var submitOnChangeField = event.target.closest('[data-submit-on-change]');
        if (submitOnChangeField) {
            var parentForm = submitOnChangeField.form || submitOnChangeField.closest('form');
            if (parentForm) {
                parentForm.submit();
            }
            return;
        }

        if (event.target.matches('[data-file-selected-callback]')) {
            callGlobal(event.target.getAttribute('data-file-selected-callback'), event.target);
            return;
        }

        if (event.target.matches('[data-take-exam-file-input]')) {
            callGlobal('handleFiles', event, event.target.getAttribute('data-take-exam-file-input'));
        }
    });

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        if (form.hasAttribute('data-sync-bank-settings')) {
            var syncResult = callGlobal('syncBankSettings');
            if (syncResult === false) {
                event.preventDefault();
                return;
            }
        }

        if (form.hasAttribute('data-submit-grade-id')) {
            event.preventDefault();
            callGlobal('submitGrade', event, form.getAttribute('data-submit-grade-id'), false);
            return;
        }

        var confirmMessage = form.getAttribute('data-confirm-message');
        if (confirmMessage && !window.confirm(confirmMessage)) {
            event.preventDefault();
        }
    });

    document.addEventListener('dragover', function (event) {
        var dropZone = event.target.closest('[data-exam-dropzone-qid]');
        if (!dropZone) {
            return;
        }
        event.preventDefault();
        dropZone.classList.add('hover');
    });

    document.addEventListener('dragleave', function (event) {
        var dropZone = event.target.closest('[data-exam-dropzone-qid]');
        if (!dropZone) {
            return;
        }
        if (event.relatedTarget && dropZone.contains(event.relatedTarget)) {
            return;
        }
        dropZone.classList.remove('hover');
    });

    document.addEventListener('drop', function (event) {
        var dropZone = event.target.closest('[data-exam-dropzone-qid]');
        if (!dropZone) {
            return;
        }
        event.preventDefault();
        dropZone.classList.remove('hover');
        callGlobal('handleDrop', event, dropZone.getAttribute('data-exam-dropzone-qid'));
    });
});
