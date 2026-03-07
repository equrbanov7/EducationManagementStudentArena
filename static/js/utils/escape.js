/**
 * escape.js
 * ─────────
 * Shared HTML escaping utility for XSS prevention
 *
 * Usage:
 * - Import this file in your HTML templates
 * - Use escapeHtml(userInput) before inserting into DOM
 *
 * Example:
 *   element.textContent = escapeHtml(userInput);
 *   // OR for innerHTML when needed:
 *   element.innerHTML = escapeHtml(userInput);
 */

/**
 * Escape HTML special characters to prevent XSS attacks
 *
 * This function converts potentially dangerous HTML characters into their
 * HTML entity equivalents, preventing them from being interpreted as HTML.
 *
 * @param {string} text - The text to escape
 * @returns {string} - The escaped text safe for HTML insertion
 *
 * @example
 * const userInput = '<script>alert("XSS")</script>';
 * const safe = escapeHtml(userInput);
 * // Result: '&lt;script&gt;alert("XSS")&lt;/script&gt;'
 */
function escapeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }

    // Convert to string if not already
    const str = String(text);

    // Use browser's built-in text node to escape HTML
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Alternative method using replace (for reference)
 * This is less preferred than the DOM method above, but included for completeness
 */
function escapeHtmlAlt(text) {
    if (text === null || text === undefined) {
        return '';
    }

    const str = String(text);
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '/': '&#x2F;',
    };

    return str.replace(/[&<>"'/]/g, (char) => map[char]);
}

/**
 * Sanitize HTML content using DOMParser
 * This is useful when you need to parse HTML but want to remove script tags
 *
 * @param {string} html - The HTML string to sanitize
 * @returns {string} - Sanitized HTML without script tags
 */
function sanitizeHtml(html) {
    if (!html) return '';

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Remove all script tags
    const scripts = doc.querySelectorAll('script');
    scripts.forEach(script => script.remove());

    // Remove event handlers (onclick, onerror, etc.)
    const allElements = doc.querySelectorAll('*');
    allElements.forEach(element => {
        // Remove all event handler attributes
        Array.from(element.attributes).forEach(attr => {
            if (attr.name.startsWith('on')) {
                element.removeAttribute(attr.name);
            }
        });

        // Remove javascript: URLs
        ['href', 'src', 'action', 'formaction'].forEach(attrName => {
            const attrValue = element.getAttribute(attrName);
            if (attrValue && attrValue.toLowerCase().trim().startsWith('javascript:')) {
                element.removeAttribute(attrName);
            }
        });
    });

    return doc.body.innerHTML;
}

// Export for use in modules (if using module system)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { escapeHtml, escapeHtmlAlt, sanitizeHtml };
}

// Also make available globally for non-module scripts
if (typeof window !== 'undefined') {
    window.escapeHtml = escapeHtml;
    window.escapeHtmlAlt = escapeHtmlAlt;
    window.sanitizeHtml = sanitizeHtml;
}
