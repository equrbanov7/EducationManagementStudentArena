/* pin_entry_config.js — PIN daxiletmə səhifəsinin i18n/konfiqi.
 * Mənbə: liveExam/pin_entry.html (inline nonce script, 2026-09-21-də xarici
 * fayla çıxarıldı — CSP `script-src` yalnız SELF + NONCE).
 *
 * `#pinEntryI18n` JSON data-adası: invalidPin, loading (mətn), pinLength,
 * minPinLength (rəqəm). KLASSİK, defer-siz skript — pin_entry.js-dən ƏVVƏL
 * `window.LIVE_PIN_ENTRY_I18N`-i inline blokla eyni formada qurur.
 */
(function () {
    "use strict";

    var el = document.getElementById("pinEntryI18n");
    if (!el) {
        return;
    }
    try {
        window.LIVE_PIN_ENTRY_I18N = JSON.parse(el.textContent);
    } catch (err) {
        window.LIVE_PIN_ENTRY_I18N = {};
    }
})();
