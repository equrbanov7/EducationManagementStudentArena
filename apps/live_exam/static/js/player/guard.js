// Sahib 2026-09-30: köçürmə / süni intellekt köməyinə qarşı qoruma (oyunçu ekranı).
// Sual və cavab mətni seçilmir, kopyalanmır, uzun basmada menyu (Android «smart text
// selection» → Google/Gemini, Lens, Tərcümə) açılmır; yazılı cavab xanasına YAPIŞDIRMAQ
// olmaz. Yazılı cavab xanasının özü tam işləyir (kursor, seçim, klaviatura, avtodüzəliş).
//
// Toxunuşlara TOXUNULMUR: `touchstart` / `pointerdown` / `click` bloklanmır — cavab düymələri
// iOS və Android-də ilk toxunuşda işləyir. Bütün dinləyicilər sənəd səviyyəsində bir dəfə
// (delegasiya) qoşulur — görünüşlər dəyişəndə yenidən bağlamaq lazım deyil.
//
// Veb səhifə ƏS səviyyəsindəki funksiyaları bağlaya bilməz: Android «Circle to Search»,
// Gemini ekran köməkçisi (ekran görüntüsünü oxuyur) və adi ekran görüntüsü işləməyə davam edir.

const EDITABLE = "input, textarea, [contenteditable='true']";
let bound = false;

function elementOf(target) {
    if (!target) return null;
    return target.nodeType === 1 ? target : target.parentElement;
}

function inEditable(target) {
    const element = elementOf(target);
    return Boolean(element && element.closest && element.closest(EDITABLE));
}

function blockOutsideEditable(event) {
    if (!inEditable(event.target)) event.preventDefault();
}

function blockAlways(event) {
    event.preventDefault();
}

// Yapışdırma/sürükləyib-atma ilə mətn daxil etmək (xanada da) — yalnız bu növlər bloklanır;
// adi yazı, silmə və klaviaturanın avtodüzəlişi toxunulmaz qalır.
function blockPastedInput(event) {
    const kind = String(event.inputType || "");
    if (kind === "insertFromPaste" || kind === "insertFromDrop" || kind === "insertFromPasteAsQuotation") {
        event.preventDefault();
    }
}

function clearStraySelection() {
    const selection = window.getSelection ? window.getSelection() : null;
    if (!selection || selection.isCollapsed || !selection.rangeCount) return;
    if (inEditable(selection.anchorNode) || inEditable(document.activeElement)) return;
    selection.removeAllRanges();
}

export function bindCopyGuard() {
    if (bound) return;
    bound = true;
    ["copy", "cut", "contextmenu", "selectstart"].forEach((name) => {
        document.addEventListener(name, blockOutsideEditable, { capture: true });
    });
    ["paste", "drop", "dragstart"].forEach((name) => {
        document.addEventListener(name, blockAlways, { capture: true });
    });
    document.addEventListener("beforeinput", blockPastedInput, { capture: true });
    document.addEventListener("selectionchange", clearStraySelection);
}
