/**
 * accordion.js
 * ────────────
 * Kurs dashboard accordion-ının funksiyaları.
 * 
 * Nə edər:
 * - Accordion açıl/bağlan (Bootstrap 5 otomatik)
 * - Accordion state-ini localStorage-da saxla
 * - Animation effects
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeAccordion();
});

/**
 * Accordion-u inisializasiya et
 * LocalStorage-dan əvvəlki state yüklə
 */
function initializeAccordion() {
    const accordion = document.getElementById('courseDashboard');
    if (!accordion) return;
    
    // localStorage-dan əvvəlki state yüklə
    const savedStates = JSON.parse(localStorage.getItem('accordionStates') || '{}');
    const courseId = getCourseIdFromURL();
    
    if (savedStates[courseId]) {
        const states = savedStates[courseId];
        Object.keys(states).forEach(accordionId => {
            const button = accordion.querySelector(`[data-bs-target="#${accordionId}"]`);
            if (button && states[accordionId]) {
                // Bootstrap 5 Modal-u show et
                new bootstrap.Collapse(document.getElementById(accordionId), {
                    toggle: true
                });
            }
        });
    }
    
    // Accordion change event-ləri
    const accordionItems = accordion.querySelectorAll('.accordion-button');
    accordionItems.forEach(button => {
        button.addEventListener('click', function() {
            const targetId = this.getAttribute('data-bs-target').substring(1);
            saveAccordionState(courseId, targetId, !this.classList.contains('collapsed'));
        });
    });
}

/**
 * Accordion state-ini localStorage-da saxla
 */
function saveAccordionState(courseId, accordionId, isOpen) {
    const savedStates = JSON.parse(localStorage.getItem('accordionStates') || '{}');
    
    if (!savedStates[courseId]) {
        savedStates[courseId] = {};
    }
    
    savedStates[courseId][accordionId] = isOpen;
    localStorage.setItem('accordionStates', JSON.stringify(savedStates));
}

/**
 * URL-dən course ID çıxar
 */
function getCourseIdFromURL() {
    const match = window.location.pathname.match(/\/courses\/(\d+)\//);
    return match ? match[1] : null;
}

/**
 * Bütün accordion state-lərini silindir
 * (debug üçün)
 */
function clearAccordionStates() {
    localStorage.removeItem('accordionStates');
    location.reload();
}