import { icon } from './icons.js?v=lx20260929';
import { tr } from './utils.js?v=lx20260929';
import { audioEnabled, audioStatus, onAudioStatus, setMuted, setMusicEnabled, setSfxVolume, soundPrefs, unlockAudio } from './audio.js?v=lx20260929';

/* Proyektor ekranında görünən səs idarəsi (sol aşağı küncdə):
 *   düymə → susdur/aç; ox → panel (səs səviyyəsi, fon musiqisi).
 * AudioContext brauzer tərəfindən bloklanıbsa «səsi aktivləşdir» ipucu görünür.
 * Seçimlər audio.js-də localStorage-a yazılır. */
let dock = null;

function render(detail) {
    if (!dock) return;
    const prefs = detail || soundPrefs();
    const status = detail?.status || audioStatus();
    const muted = prefs.muted || prefs.volume === 0;
    const btn = dock.querySelector("[data-sound-toggle]");
    btn.innerHTML = icon(muted ? "mute" : prefs.volume < 40 ? "volumeLow" : "volume");
    btn.setAttribute("aria-pressed", muted ? "true" : "false");
    const label = muted ? tr("soundOff", "Səs bağlıdır") : tr("soundOn", "Səs açıqdır");
    btn.setAttribute("aria-label", label);
    btn.title = label;
    dock.classList.toggle("is-muted", muted);
    const range = dock.querySelector("[data-sound-volume]");
    if (range && Number(range.value) !== prefs.volume) range.value = String(prefs.volume);
    const value = dock.querySelector("[data-sound-value]");
    if (value) value.textContent = `${prefs.volume}%`;
    const music = dock.querySelector("[data-sound-music]");
    if (music) music.checked = Boolean(prefs.music);
    dock.querySelector("[data-sound-hint]").hidden = status !== "suspended";
}

function setOpen(open) {
    if (!dock) return;
    dock.classList.toggle("is-open", open);
    dock.querySelector("[data-sound-more]").setAttribute("aria-expanded", open ? "true" : "false");
    dock.querySelector("[data-sound-panel]").hidden = !open;
}

export function mountSoundDock() {
    if (dock || !audioEnabled()) return;
    dock = document.createElement("div");
    dock.className = "hx-sound";
    dock.innerHTML = `
        <button type="button" class="hx-sound__btn" data-sound-toggle></button>
        <button type="button" class="hx-sound__more" data-sound-more aria-expanded="false" aria-controls="hxSoundPanel" aria-label="${tr("soundTitle", "Səs")}">${icon("sliders")}</button>
        <div class="hx-sound__panel" id="hxSoundPanel" data-sound-panel hidden>
            <label class="hx-sound__row">
                <span>${tr("soundVolume", "Səs səviyyəsi")}</span>
                <strong data-sound-value></strong>
            </label>
            <input class="hx-range" type="range" min="0" max="100" step="1" data-sound-volume aria-label="${tr("soundVolume", "Səs səviyyəsi")}">
            <label class="hx-sound__switch">
                <input type="checkbox" data-sound-music>
                <span class="hx-sound__switch-ui" aria-hidden="true"></span>
                <span>${icon("music")} ${tr("soundMusic", "Fon musiqisi")}</span>
            </label>
        </div>
        <button type="button" class="hx-sound__hint" data-sound-hint hidden>${icon("volume")} ${tr("soundEnable", "Səsi aktivləşdirmək üçün klikləyin")}</button>
    `;
    document.body.appendChild(dock);
    dock.querySelector("[data-sound-toggle]").addEventListener("click", () => {
        unlockAudio();
        const prefs = soundPrefs();
        if (prefs.volume === 0) {
            setSfxVolume(60);
            setMuted(false);
        } else {
            setMuted(!prefs.muted);
        }
    });
    dock.querySelector("[data-sound-more]").addEventListener("click", () => setOpen(!dock.classList.contains("is-open")));
    dock.querySelector("[data-sound-volume]").addEventListener("input", (event) => {
        setSfxVolume(Number(event.target.value) || 0);
        if (soundPrefs().muted && Number(event.target.value) > 0) setMuted(false);
    });
    dock.querySelector("[data-sound-music]").addEventListener("change", (event) => setMusicEnabled(event.target.checked));
    dock.querySelector("[data-sound-hint]").addEventListener("click", () => unlockAudio());
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setOpen(false);
        if ((event.key === "m" || event.key === "M") && !event.target.closest?.("input, textarea, [contenteditable]")) {
            setMuted(!soundPrefs().muted);
        }
    });
    document.addEventListener("pointerdown", (event) => {
        if (dock.classList.contains("is-open") && !dock.contains(event.target)) setOpen(false);
    });
    onAudioStatus(render);
    render();
}
