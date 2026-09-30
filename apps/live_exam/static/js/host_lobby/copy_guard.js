/* Sahib 2026-09-30: aparıcı ekranında sual/cavab mətni seçilmir, kopyalanmır, kontekst menyusu
 * açılmır (sual səhnələri: .hx-question / .hx-reveal). Lobbi (qoşulma keçidi, PIN) və idarə
 * paneli toxunulmaz qalır — müəllim keçidi kopyalaya bilər. Kliklər/toxunuşlar bloklanmır.
 * Dinləyicilər sənəd səviyyəsində bir dəfə (delegasiya) qoşulur. CSS: host_lobby/_part3.css. */

const PROTECTED = ".hx-question, .hx-reveal, .hx-suspense";
let bound = false;

function protectedTarget(target) {
    const element = target && (target.nodeType === 1 ? target : target.parentElement);
    return Boolean(element && element.closest && element.closest(PROTECTED));
}

function block(event) {
    // `copy`/`cut`-un hədəfi fokuslu elementdir — seçimin başlandığı yer də yoxlanılır.
    const anchor = window.getSelection ? window.getSelection()?.anchorNode : null;
    if (protectedTarget(event.target) || protectedTarget(anchor)) event.preventDefault();
}

export function bindCopyGuard() {
    if (bound) return;
    bound = true;
    ["copy", "cut", "contextmenu", "selectstart", "dragstart"].forEach((name) => {
        document.addEventListener(name, block, { capture: true });
    });
}
