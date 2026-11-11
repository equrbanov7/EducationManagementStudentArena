/* powerups.js — güc rejimləri (sahib 2026-11-10): 💣 Bomba rejimi, ×2 Xal rejimi, final rəqs şousu.
 *
 *  • İdarə: sürətli düymələr (#hostQuickActions `[data-power-toggle]`) və sol paneldəki keçidlər
 *    (`[data-power-switch]`, host_lobby_shell.js eyni açarları çekməcə ilə sinxron saxlayır). Oyun
 *    gedərkən də dəyişir: server cavabsız cari suala dərhal tətbiq edir (`modifiers.applied`), cavab
 *    varsa növbəti sualdan — aparıcıya bildiriş (toast) və panel statusu ilə deyilir.
 *  • Səhnə: bomba sualında ürək döyüntüsü (vaxt azaldıqca sürətlənir), qırmızı nəbz vinyeti, üzən
 *    bomba; ×2-də qızıl aura. Reveal-də bomba partlayıbsa (`bomb_count > 0`) partlayış effekti + səs.
 *  • `question_modifiers` WS hadisəsi: cari sualın bayraqları dəyişir → səhnə yenidən çəkilir.
 *  Qayda yalnız serverdədir — bu modul heç bir bal hesablamır. */
import { UI } from './dom.js?v=lx20261111f';
import { PHASES } from './constants.js?v=lx20261111f';
import { state } from './state.js?v=lx20261111f';
import { postJson } from './api.js?v=lx20261111f';
import {
    playDoubleUp,
    playExplosion,
    playFuseHiss,
    playPowerArm,
    startHeartbeat,
    stopHeartbeat,
} from './audio.js?v=lx20261111f';
import { icon } from './icons.js?v=lx20261111f';
import { EXPLOSION_SHARDS, explosionMarkup, isBombQuestion, isDoubleQuestion, shardVars } from './power_markup.js?v=lx20261111f';
import { BOMB_SVG } from './power_art.js?v=lx20261111f';
import { showToast } from './toast.js?v=lx20261111f';
import { controlsEnabled, esc, nowMs, reducedMotion, tr } from './utils.js?v=lx20261111f';

const KEYS = ["bomb_mode", "double_mode"];
const pending = new Set();
// question.js qeyd edir: cari sual səhnəsini (eyni faza) yenidən çəkən funksiya (dövri import olmasın).
let rerenderQuestion = null;
export function setQuestionRerenderHook(fn) {
    rerenderQuestion = typeof fn === "function" ? fn : null;
}
let lastExplosionKey = "";
let lastFuseKey = "";

const settingOn = (key) => Boolean(state.sessionSettings?.[key]);
// Cari sualda qayda həqiqətən aktivdirmi (serverin dondurulmuş bayrağı).
const liveOn = (key) => (key === "bomb_mode" ? isBombQuestion(state.currentQuestion) : isDoubleQuestion(state.currentQuestion));
// Düymənin göstərdiyi vəziyyət: sual gedərkən — cari sual; lobbi/reveal-də — növbəti sual üçün silahlanıb.
// 2026-11-10 (sahib): rejim BİR sual üçündür — nəşrdə server bayrağı söndürür, hər sual yenidən basılır.
const effectiveOn = (key) => (state.sessionState === "question" ? liveOn(key) : settingOn(key));

/* ── Səhnə ambiyansı ─────────────────────────────────────────────── */

/** Hər kadrda çağırıla bilər (ucuz): siniflər + ürək döyüntüsü (bomba sualının cavab pəncərəsi). */
export function syncPowerAmbience() {
    const stage = UI.presentationStage;
    if (!stage) return;
    const question = state.currentQuestion;
    const inQuestion = state.sessionState === "question" && Boolean(question);
    const bomb = inQuestion && isBombQuestion(question);
    const double = inQuestion && isDoubleQuestion(question);
    stage.classList.toggle("is-bomb", bomb);
    stage.classList.toggle("is-double", double);
    document.body.classList.toggle("lx-bomb-armed", bomb);
    if (!bomb || state.phase !== PHASES.ANSWERS) {
        stopHeartbeat();
        delete stage.dataset.bombUrgency;
        if (bomb && state.phase === PHASES.QUESTION) {
            // Sual oxunur — fitil yanmağa başlayır (bir dəfə).
            const key = `fuse:${state.questionKey}`;
            if (lastFuseKey !== key) {
                lastFuseKey = key;
                playFuseHiss(key);
            }
        }
        return;
    }
    const plan = state.questionPlan;
    const left = plan ? Math.max(0, plan.endsAt - nowMs()) : 0;
    // 64 → 96 → 128 bpm: son 10 s / son 5 s. Dövrə id-si bpm-ə bağlıdır — eyni bpm ikinci dəfə başlamır.
    const bpm = left <= 5000 ? 128 : left <= 10000 ? 96 : 64;
    stage.dataset.bombUrgency = left <= 5000 ? "3" : left <= 10000 ? "2" : "1";
    startHeartbeat(bpm, left <= 10000 ? 1 : 0.8);
}

/** Reveal: bomba partladı → partlayış; ×2-də düzgün cavab varsa parıltı. */
export function handleRevealPower(payload) {
    stopHeartbeat();
    document.body.classList.remove("lx-bomb-armed");
    const key = `${payload?.question_id || 0}:${payload?.revealed_at || ""}`;
    const bombCount = Number(payload?.bomb_count || 0);
    if (bombCount > 0 && lastExplosionKey !== key) {
        lastExplosionKey = key;
        explode(key, bombCount);
    }
    if (payload?.is_double && Array.isArray(payload?.results) && payload.results.some((row) => row.awarded_points > 0)) {
        playDoubleUp(`double:${key}`);
    }
}

function explode(key, count) {
    playExplosion(`boom:${key}`);
    const stage = UI.presentationStage;
    if (!stage || reducedMotion()) return;
    stage.querySelector("[data-explosion]")?.remove();
    const wrap = document.createElement("div");
    wrap.innerHTML = explosionMarkup();
    const el = wrap.firstElementChild;
    el.querySelectorAll("[data-shard]").forEach((shard) => {
        const vars = shardVars(Number(shard.dataset.shard), EXPLOSION_SHARDS);
        Object.keys(vars).forEach((name) => shard.style.setProperty(name, vars[name]));
    });
    const label = document.createElement("span");
    label.className = "hx-explosion__label";
    label.textContent = count === 1 ? tr("bombExplodedOne", "Bomba partladı!") : tr("bombExplodedMany", "{count} bomba partladı!").replace("{count}", String(count));
    el.appendChild(label);
    stage.appendChild(el);
    document.body.classList.add("lx-shake");
    window.setTimeout(() => document.body.classList.remove("lx-shake"), 720);
    window.setTimeout(() => el.remove(), 2600);
}

/* ── `question_modifiers` (server rejimi cari suala tətbiq etdi) ───── */

export function handleQuestionModifiers(data) {
    const question = state.currentQuestion;
    if (!question || Number(data?.question_id || 0) !== Number(question.id || 0)) return false;
    const next = { is_bomb: Boolean(data.is_bomb), is_double: Boolean(data.is_double) };
    if (Boolean(question.is_bomb) === next.is_bomb && Boolean(question.is_double) === next.is_double) return false;
    state.currentQuestion = Object.assign({}, question, next);
    state.phaseSignature = ""; // cari faza yenidən çəkilsin (nişanlar, bomba, aura)
    lastFuseKey = "";
    if (rerenderQuestion) rerenderQuestion();
    syncPowerAmbience();
    renderControls();
    return true;
}

/* ── İdarə: sürətli düymələr + panel statusu ──────────────────────── */

function toastModifiers(modifiers, key, on) {
    if (!modifiers) {
        showToast(
            `${modeLabel(key)}: ${on ? tr("powerArmedNext", "növbəti sual üçün aktivləşdi") : tr("powerDisarmedNext", "növbəti sual üçün söndürüldü")}`,
            on ? "ok" : "info",
            2600
        );
        return;
    }
    if (modifiers.applied) {
        const label = key === "bomb_mode" ? tr("bombModeLabel", "Bomba rejimi") : tr("doubleModeLabel", "×2 Xal rejimi");
        showToast(
            `${label}: ${on ? tr("powerOnNow", "cari suala tətbiq olundu") : tr("powerOffNow", "cari sualdan götürüldü")}`,
            "ok",
            2600
        );
    } else {
        showToast(tr("powerDeferred", "Bu suala artıq cavab var — növbəti sual üçün aktivləşdi"), "info", 3400);
    }
}

async function toggleSetting(key, button) {
    if (!controlsEnabled() || !CONFIG?.urls?.settings || pending.has(key)) return;
    const on = !effectiveOn(key);
    pending.add(key);
    renderControls();
    let result = null;
    try {
        result = await postJson(CONFIG.urls.settings, { [key]: on });
    } catch (_) {
        result = null;
    }
    pending.delete(key);
    if (result?.ok) {
        kick(button || document.querySelector(`[data-power-toggle="${key}"]`), key, on);
        toastModifiers(result.modifiers, key, on);
        if (result.modifiers?.applied) handleQuestionModifiers(result.modifiers);
    } else if (result?.message) {
        showToast(result.message, "error");
    } else {
        showToast(tr("saveError", "Yadda saxlanılmadı"), "error");
    }
    renderControls();
}

/** Klik hissi: bomba — fitil alışır, titrəyir, qığılcımlar; ×2 — sikkə çevrilir, qızıl parıltı. Səs də. */
function kick(button, key, on) {
    const stamp = Date.now();
    if (key === "bomb_mode") {
        playPowerArm(`arm:${key}:${stamp}`, on);
        if (on) playFuseHiss(`hiss:${stamp}`);
    } else if (on) {
        playDoubleUp(`arm:${key}:${stamp}`);
    } else {
        playPowerArm(`arm:${key}:${stamp}`, false);
    }
    if (!button || reducedMotion()) return;
    button.classList.remove("is-kick", "is-kick-off");
    void button.offsetWidth;
    button.classList.add(on ? "is-kick" : "is-kick-off");
    button.querySelectorAll(".hx-power__spark").forEach((node) => node.remove());
    if (on) {
        for (let i = 0; i < 10; i += 1) {
            const spark = document.createElement("i");
            spark.className = "hx-power__spark";
            spark.style.setProperty("--a", `${i * 36 + (i % 2) * 9}deg`);
            spark.style.setProperty("--d", `${54 + (i % 3) * 16}px`);
            button.appendChild(spark);
            spark.addEventListener("animationend", () => spark.remove(), { once: true });
        }
    }
    window.setTimeout(() => button.classList.remove("is-kick", "is-kick-off"), 1000);
}

function statusText() {
    const question = state.currentQuestion;
    const armed = KEYS.filter(settingOn);
    if (state.sessionState === "question" && question) {
        const current = KEYS.filter(liveOn).map((key) => (key === "bomb_mode" ? tr("bombBadge", "Bomba sualı") : tr("doubleBadge", "×2 xal")));
        const now = current.length
            ? tr("powerStatusCurrent", "Cari sual: {modes}").replace("{modes}", current.join(" · "))
            : tr("powerStatusCurrentNone", "Cari sual: rejim yoxdur");
        return armed.length ? `${now} · ${tr("powerStatusNext", "Növbəti sual: {modes}").replace("{modes}", armedLabel(armed))}` : now;
    }
    if (!armed.length) return tr("powerStatusOff", "Rejim seçilməyib — hər sual üçün ikona bas");
    return tr("powerStatusNext", "Növbəti sual: {modes}").replace("{modes}", armedLabel(armed));
}

function armedLabel(keys) {
    return keys
        .map((key) => (key === "bomb_mode" ? tr("bombModeLabel", "Bomba rejimi") : tr("doubleModeLabel", "×2 Xal rejimi")))
        .join(" · ");
}

const modeLabel = (key) => (key === "bomb_mode" ? tr("bombModeLabel", "Bomba rejimi") : tr("doubleModeLabel", "×2 Xal rejimi"));

/** Səhnə dok-u: iki böyük ikon-düymə (bomba, ×2) — səhnənin özündə, idarə varsa kliklənir. */
function dockMarkup() {
    const interactive = controlsEnabled();
    const button = (key, art, extra) =>
        `<button type="button" class="hx-power hx-power--${key === "bomb_mode" ? "bomb" : "double"}${interactive ? "" : " is-readonly"}" data-power-toggle="${key}" aria-pressed="false"${interactive ? "" : " disabled tabindex=\"-1\""}>` +
        `<span class="hx-power__halo" aria-hidden="true"></span>` +
        `<span class="hx-power__ring" aria-hidden="true"></span>` +
        `<span class="hx-power__art" aria-hidden="true">${art}</span>` +
        `<span class="hx-power__text"><span class="hx-power__label">${esc(modeLabel(key))}</span><span class="hx-power__state" data-power-state></span></span>` +
        `${extra || ""}</button>`;
    return (
        `<div class="hx-power-dock" data-power-dock aria-label="${esc(tr("powerDockLabel", "Oyun effektləri"))}">` +
        button("bomb_mode", BOMB_SVG, `<span class="hx-power__fuse" aria-hidden="true"></span>`) +
        button("double_mode", `<span class="hx-power__coin">${icon("double")}</span>`) +
        `</div>`
    );
}

function ensureDock() {
    const stage = UI.presentationStage;
    if (!stage) return null;
    let dock = stage.querySelector("[data-power-dock]");
    if (!dock) {
        const wrap = document.createElement("div");
        wrap.innerHTML = dockMarkup();
        dock = wrap.firstElementChild;
        stage.appendChild(dock);
    }
    return dock;
}

export function renderControls() {
    const dock = ensureDock();
    if (dock) {
        const visible = ["lobby", "question", "reveal"].includes(state.sessionState);
        dock.hidden = !visible;
        dock.querySelectorAll("[data-power-toggle]").forEach((button) => {
            const key = button.dataset.powerToggle;
            const on = effectiveOn(key);
            const inQuestion = state.sessionState === "question";
            button.classList.toggle("is-on", on);
            button.classList.toggle("is-busy", pending.has(key));
            // Sual gedərkən növbəti sual üçün silahlanıb (cavab var idi) — kiçik «növbəti» nişanı.
            button.classList.toggle("is-armed-next", inQuestion && settingOn(key) && !liveOn(key));
            if (controlsEnabled()) button.disabled = pending.has(key);
            button.setAttribute("aria-pressed", on ? "true" : "false");
            const stateLabel = on
                ? inQuestion ? tr("powerOnCurrent", "bu sualda") : tr("powerOnNext", "növbəti sual")
                : inQuestion && settingOn(key) ? tr("powerOnNext", "növbəti sual") : tr("powerOff", "bağlı");
            button.setAttribute("aria-label", `${modeLabel(key)}: ${stateLabel}`);
            button.title = button.getAttribute("aria-label");
            const stateEl = button.querySelector("[data-power-state]");
            if (stateEl && stateEl.textContent !== stateLabel) stateEl.textContent = stateLabel;
            button.classList.toggle("is-live", inQuestion && liveOn(key));
        });
    }
    const status = document.querySelector("[data-power-status]");
    if (status) {
        const text = statusText();
        if (status.textContent !== text) status.textContent = text;
    }
    document.querySelectorAll("[data-power-switch]").forEach((input) => {
        input.closest(".control-power__item")?.classList.toggle("is-on", Boolean(input.checked));
    });
}

export function mountPowerControls() {
    ensureDock();
    document.addEventListener("click", (event) => {
        const button = event.target.closest?.("[data-power-toggle]");
        if (!button || button.disabled || !controlsEnabled()) return;
        event.preventDefault();
        toggleSetting(button.dataset.powerToggle, button);
    });
    // Sol paneldəki keçidlər host_lobby_shell.js ilə gedir (eyni endpoint); `question_modifiers` (WS)
    // səhnəni, `live-host-state` isə dok/status mətnini yeniləyir.
    window.addEventListener("live-host-state", renderControls);
    renderControls();
}

/** Səhnədə göstərilən «×2» və bomba sayğacı başlığı — reveal statistikası üçün. */
export function bombCountStatMarkup(payload) {
    const count = Number(payload?.bomb_count || 0);
    if (!count) return "";
    const text = count === 1 ? tr("bombExplodedOne", "Bomba partladı!") : tr("bombExplodedMany", "{count} bomba partladı!").replace("{count}", String(count));
    return `<span class="hx-stat hx-stat--bomb">${icon("bomb")}<span>${esc(text)}</span></span>`;
}
