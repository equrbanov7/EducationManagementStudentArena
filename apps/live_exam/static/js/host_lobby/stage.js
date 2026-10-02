import { UI } from './dom.js?v=lx20261002';
import { icon } from './icons.js?v=lx20261002';
import { createFx } from './fx.js?v=lx20261002';
import { audienceDelay, buildStageModel, danceFor, stageTimeline } from './stage_logic.js?v=lx20261002';
import {
    playCheer,
    playFanfare,
    playImpact,
    playRiser,
    startDanceBeat,
    startDrumroll,
    stopDanceBeat,
} from './audio.js?v=lx20261002';
import { avatarMarkup, countUp, esc, fmt, formatNumber, formatSeconds, reducedMotion, tr } from './utils.js?v=lx20261002';

/* FİNAL SƏHNƏSİ — qaranlıq zal, açılan pərdələr, süpürən projektorlar, qalxan
 * 3 pilləli podium; 3-cü → 2-ci → barabam → 1-ci (tac, fanfar, sol+sağ konfetti
 * topları, fişəng), sonra podium rəqs edir, 4–10-cu yerlər tamaşaçı kimi alqışlayır.
 * Hər işə salınma `run` nişanı alır: köhnə taymerlər (replay/teardown) heç nə etmir. */

const BEAT = 60 / 112;
const S = {
    model: null, payload: null, root: null, fx: null, timers: new Set(), run: 0,
    danceTimer: 0, phrase: 0, stopRoll: null, done: false, idleTimer: 0, bound: false, channel: null,
};

const placeLabel = (place) =>
    ({ 1: tr("stagePlace1", "1-ci yer"), 2: tr("stagePlace2", "2-ci yer"), 3: tr("stagePlace3", "3-cü yer") })[place] || `${place}`;

function crownSvg() {
    return `<svg class="hx-crown__svg" viewBox="0 0 64 44" aria-hidden="true" focusable="false"><path d="M4 14l13 11L32 3l15 22 13-11-5 25H9z" fill="#ffd34d" stroke="#a86b00" stroke-width="3" stroke-linejoin="round"/><rect x="9" y="34" width="46" height="8" rx="3" fill="#f5b400" stroke="#a86b00" stroke-width="3"/><circle cx="22" cy="38" r="2.4" fill="#e11d48"/><circle cx="32" cy="38" r="2.8" fill="#2563eb"/><circle cx="42" cy="38" r="2.4" fill="#059669"/><circle cx="4" cy="14" r="3" fill="#fff7cc"/><circle cx="32" cy="3" r="3.2" fill="#fff7cc"/><circle cx="60" cy="14" r="3" fill="#fff7cc"/></svg>`;
}

function plateExtra(player) {
    const bits = [];
    if (player?.answered_count != null && player?.correct_count != null) {
        bits.push(`${icon("check")}${esc(fmt(tr("stageCorrect", "{correct}/{answered} düzgün"), { correct: player.correct_count, answered: player.answered_count }))}`);
    }
    if (Number(player?.best_streak || 0) >= 2) bits.push(`${icon("flame")}${Number(player.best_streak)}`);
    return bits.length ? `<small class="hx-plate__extra">${bits.map((b) => `<span>${b}</span>`).join("")}</small>` : "";
}

/** Tac avatarın KÖKÜNÜN içinə qoyulur — rəqs (tullanma/fırlanma) zamanı başla birgə hərəkət edir. */
function dancerMarkup(entry) {
    const markup = avatarMarkup(entry.player, 220, "hx-dancer__avatar", { crop: "full", backdrop: false, label: entry.player?.nickname || "" });
    if (entry.place !== 1) return markup;
    const at = markup.lastIndexOf("</span>");
    return at < 0 ? markup : `${markup.slice(0, at)}<span class="hx-crown" aria-hidden="true">${crownSvg()}</span>${markup.slice(at)}`;
}

function stepMarkup(entry) {
    const p = entry.player;
    return `
        <div class="hx-step hx-step--${entry.slot} hx-step--p${entry.place}" data-place="${entry.place}">
            <span class="hx-step__spot" aria-hidden="true"></span>
            <div class="hx-dancer" data-dancer>${dancerMarkup(entry)}</div>
            <div class="hx-step__block">
                <span class="hx-step__medal" aria-hidden="true">${entry.place}</span>
                <div class="hx-plate">
                    <span class="hx-plate__place">${esc(placeLabel(entry.place))}</span>
                    <strong class="hx-plate__name" title="${esc(p?.nickname || "")}">${esc(p?.nickname || "")}</strong>
                    <span class="hx-plate__score"><b data-stage-score data-target="${entry.score}">0</b> ${esc(tr("points", "xal"))}</span>
                    ${entry.tie ? `<span class="hx-plate__tie">${esc(tr("stageTie", "Bərabər xal"))}</span>` : ""}
                    ${plateExtra(p)}
                </div>
            </div>
        </div>
    `;
}

function audienceMarkup(model) {
    if (!model.audience.length && !model.more) return "";
    const fans = model.audience
        .map(
            (entry, index) => `
            <li class="hx-fan" data-fan-index="${index}">
                <span class="hx-fan__rank">${entry.place}</span>
                ${avatarMarkup(entry.player, 96, "hx-fan__avatar", { crop: "full", backdrop: false, label: entry.player?.nickname || "" })}
                <span class="hx-fan__name" title="${esc(entry.player?.nickname || "")}">${esc(entry.player?.nickname || "")}</span>
                <span class="hx-fan__score">${formatNumber(entry.score)}</span>
            </li>`
        )
        .join("");
    const more = model.more > 0 ? `<li class="hx-fan hx-fan--more">${esc(fmt(tr("stageMore", "+{count} iştirakçı"), { count: formatNumber(model.more) }))}</li>` : "";
    return `
        <section class="hx-audience" aria-label="${esc(tr("stageAudience", "Digər iştirakçılar"))}">
            <ol class="hx-audience__list">${fans}${more}</ol>
        </section>
    `;
}

function statsMarkup(stats) {
    if (!stats || typeof stats !== "object") return "";
    const chips = [];
    if (stats.total_players != null) chips.push([icon("users"), formatNumber(stats.total_players), tr("stageStatsPlayers", "iştirakçı")]);
    if (stats.total_questions != null) chips.push([icon("sparkle"), formatNumber(stats.total_questions), tr("stageStatsQuestions", "sual")]);
    if (stats.correct_rate != null) chips.push([icon("check"), `${Math.round(Number(stats.correct_rate) * 100)}%`, tr("stageStatsAccuracy", "düzgünlük")]);
    if (stats.avg_answer_ms != null) chips.push([icon("timer"), `${formatSeconds(stats.avg_answer_ms)} ${tr("secondsShort", "san")}`, tr("stageStatsSpeed", "orta cavab")]);
    if (!chips.length) return "";
    return `<div class="hx-stats" data-stage-stats>${chips.map(([ic, value, label]) => `<span class="hx-stats__chip">${ic}<strong>${esc(value)}</strong><span>${esc(label)}</span></span>`).join("")}</div>`;
}

function stageMarkup(model, payload) {
    const order = [2, 1, 3].map((place) => model.podium.find((entry) => entry.place === place)).filter(Boolean);
    const closable = !CONFIG.presentationOnly;
    return `
        <div class="hx-stagebox" data-stage data-phase="intro">
            <div class="hx-hall" aria-hidden="true"><span class="hx-hall__wall"></span><span class="hx-hall__haze"></span><span class="hx-hall__floor"></span></div>
            <div class="hx-beams" aria-hidden="true">${[1, 2, 3, 4].map((n) => `<span class="hx-beam-rig hx-beam-rig--${n}"><span class="hx-beam"></span></span>`).join("")}</div>
            <header class="hx-marquee">
                <span class="hx-marquee__bulbs" aria-hidden="true"></span>
                <h1 class="hx-marquee__title">${icon("trophy")}<span>${esc(tr("stageTitle", "Final nəticələr"))}</span></h1>
                <p class="hx-marquee__sub">${esc(model.empty ? tr("stageNoPlayers", "Bu oyunda iştirakçı olmadı") : tr("stageSubtitle", "Qalibləri təbrik edirik!"))}</p>
                ${statsMarkup(payload?.stats)}
            </header>
            <div class="hx-podium" data-count="${model.podium.length}">${order.map(stepMarkup).join("")}</div>
            ${audienceMarkup(model)}
            <canvas class="hx-fx" aria-hidden="true"></canvas>
            <div class="hx-curtain hx-curtain--l" aria-hidden="true"></div>
            <span class="hx-curtain-spot" aria-hidden="true"></span>
            <div class="hx-curtain hx-curtain--r" aria-hidden="true"></div>
            <div class="hx-valance" aria-hidden="true"></div>
            <div class="hx-stage-controls">
                <button type="button" class="hx-btn hx-btn--ghost" data-stage-replay>${icon("replay")}<span>${esc(tr("stageReplay", "Yenidən göstər"))}</span></button>
                ${CONFIG.controlsEnabled !== false && CONFIG.resultsUrl ? `<a class="hx-btn hx-btn--ghost" href="${esc(CONFIG.resultsUrl)}" target="_blank" rel="noopener">${icon("trophy")}<span>${esc(tr("stageResults", "Ətraflı nəticələr"))}</span></a>` : ""}
                ${closable ? `<button type="button" class="hx-btn hx-btn--ghost hx-btn--icon" data-stage-close aria-label="${esc(tr("close", "Bağla"))}">${icon("close")}</button>` : ""}
            </div>
            <p class="hx-sr" aria-live="polite" data-stage-live></p>
        </div>
    `;
}

/* ── Zaman xətti ─────────────────────────────────────────────────── */
function later(at, fn, run) {
    const id = window.setTimeout(() => {
        S.timers.delete(id);
        if (run === S.run && S.root) fn();
    }, at);
    S.timers.add(id);
}

function clearTimers() {
    S.timers.forEach((id) => window.clearTimeout(id));
    S.timers.clear();
    window.clearInterval(S.danceTimer);
    S.danceTimer = 0;
    if (S.stopRoll) {
        S.stopRoll();
        S.stopRoll = null;
    }
}

const stepEl = (place) => S.root?.querySelector(`.hx-step[data-place="${place}"]`);

function announce(text) {
    const live = S.root?.querySelector("[data-stage-live]");
    if (live) live.textContent = text;
}

function aimBeams(place) {
    const target = stepEl(place)?.querySelector("[data-dancer]");
    if (!S.root) return;
    if (!target) {
        delete S.root.dataset.focus;
        return;
    }
    const t = target.getBoundingClientRect();
    const tx = t.left + t.width / 2;
    const ty = t.top + t.height * 0.75;
    S.root.querySelectorAll(".hx-beam-rig").forEach((rig) => {
        const r = rig.getBoundingClientRect();
        const deg = (-Math.atan2(tx - (r.left + r.width / 2), ty - r.top) * 180) / Math.PI;
        rig.style.setProperty("--aim", `${deg.toFixed(1)}deg`);
    });
    S.root.dataset.focus = String(place);
}

function revealPlace(place, run, instant) {
    const el = stepEl(place);
    if (!el) return;
    el.classList.add("is-revealed");
    const score = el.querySelector("[data-stage-score]");
    countUp(score, 0, Number(score?.dataset.target || 0), instant ? 0 : 1100);
    const entry = S.model.podium.find((item) => item.place === place);
    if (entry) announce(`${placeLabel(place)}: ${entry.player?.nickname || ""}, ${formatNumber(entry.score)} ${tr("points", "xal")}`);
    if (instant) return;
    if (S.stopRoll) {
        S.stopRoll();
        S.stopRoll = null;
    }
    playImpact(`stage:${run}:impact:${place}`, place === 1);
    if (place === 1) playFanfare(`stage:${run}:fanfare`);
    playCheer(`stage:${run}:cheer:${place}`, place === 1 ? 1.4 : 0.45);
}

function fireworks() {
    const winner = stepEl(1)?.querySelector("[data-dancer]");
    if (!winner || !S.fx) return;
    const rect = winner.getBoundingClientRect();
    const host = S.root.getBoundingClientRect();
    S.fx.burst(rect.left - host.left + rect.width / 2 + (Math.random() - 0.5) * rect.width, rect.top - host.top - rect.height * 0.15, 40);
}

function setDances(phraseIndex) {
    if (!S.root) return;
    S.model.podium.forEach((entry) => {
        const avatar = stepEl(entry.place)?.querySelector(".live-avatar");
        if (avatar) avatar.dataset.dance = danceFor(entry.place, phraseIndex + entry.place);
    });
    S.root.querySelectorAll(".hx-fan .live-avatar").forEach((avatar, index) => {
        avatar.dataset.dance = Math.floor(phraseIndex / 2) % 2 === 0 ? "cheer" : "bounce";
        avatar.style.setProperty("--lva-delay", `${audienceDelay(index).toFixed(3)}s`);
    });
}

function startParty(run) {
    if (!S.root) return;
    S.root.dataset.phase = "party";
    delete S.root.dataset.focus;
    S.phrase = 0;
    setDances(0);
    window.clearInterval(S.danceTimer);
    S.danceTimer = window.setInterval(() => {
        if (run !== S.run || !S.root) return;
        S.phrase += 1;
        setDances(S.phrase);
    }, BEAT * 8 * 1000);
    startDanceBeat(32, () => {
        if (run !== S.run || !S.root) return;
        window.clearInterval(S.danceTimer);
        S.danceTimer = 0;
        S.root.querySelectorAll(".live-avatar[data-dance]").forEach((avatar) => { avatar.dataset.dance = "idle"; });
    });
    S.done = true;
}

function applyStatic(run) {
    S.root.classList.add("is-open", "is-podium");
    S.model.podium.forEach((entry) => revealPlace(entry.place, run, true));
    S.root.querySelector(".hx-crown")?.classList.add("is-dropped");
    S.root.dataset.phase = "static";
    S.fx?.staticFrame();
    playFanfare(`stage:${run}:fanfare`);
    S.done = true;
}

function runAction(step, run) {
    const root = S.root;
    switch (step.action) {
        case "intro":
            root.dataset.phase = "intro";
            break;
        case "drumroll":
            S.stopRoll = startDrumroll(`stage:${run}:roll1`, step.seconds, 0.02, 0.09);
            break;
        case "curtains":
            root.classList.add("is-open");
            break;
        case "podium":
            root.classList.add("is-podium");
            root.dataset.phase = "reveal";
            break;
        case "focus":
            aimBeams(step.place);
            break;
        case "reveal":
            revealPlace(step.place, run, false);
            break;
        case "suspense":
            delete root.dataset.focus;
            root.dataset.phase = "suspense";
            S.stopRoll = startDrumroll(`stage:${run}:roll2`, step.seconds, 0.03, 0.17);
            playRiser(`stage:${run}:riser`, step.seconds);
            break;
        case "cannons":
            root.dataset.phase = "winner";
            S.fx?.cannons();
            break;
        case "crown":
            root.querySelector(".hx-crown")?.classList.add("is-dropped");
            break;
        case "fireworks":
            fireworks();
            break;
        case "party":
            startParty(run);
            break;
        case "empty":
            root.dataset.phase = "empty";
            S.done = true;
            break;
        case "static":
            applyStatic(run);
            break;
        default:
            break;
    }
}

function start() {
    S.run += 1;
    const run = S.run;
    S.done = false;
    const container = UI.finalPodium;
    container.innerHTML = stageMarkup(S.model, S.payload);
    S.root = container.querySelector("[data-stage]");
    S.fx?.destroy();
    S.fx = createFx(S.root.querySelector(".hx-fx"));
    const steps = stageTimeline(S.model, { reduced: reducedMotion() });
    steps.forEach((step) => {
        if (step.at <= 0) runAction(step, run);
        else later(step.at, () => runAction(step, run), run);
    });
    pokeControls();
}

/** Gizli tabdan qayıdanda və ya sürətləndirmə lazım olanda — dərhal final kadrı. */
function finishNow() {
    if (!S.root || S.done) return;
    clearTimers();
    const run = S.run;
    S.root.classList.add("is-open", "is-podium");
    S.model.podium.forEach((entry) => revealPlace(entry.place, run, true));
    S.root.querySelector(".hx-crown")?.classList.add("is-dropped");
    if (S.model.empty) {
        S.root.dataset.phase = "empty";
        S.done = true;
    } else if (reducedMotion()) {
        applyStatic(run);
    } else {
        startParty(run);
    }
}

function pokeControls() {
    if (!S.root) return;
    S.root.classList.remove("is-idle");
    window.clearTimeout(S.idleTimer);
    S.idleTimer = window.setTimeout(() => S.root?.classList.add("is-idle"), 2600);
}

function bindOnce() {
    if (S.bound) return;
    S.bound = true;
    document.addEventListener("click", (event) => {
        if (!S.root || !S.root.contains(event.target)) return;
        if (event.target.closest("[data-stage-replay]")) {
            replayStage(true);
        } else if (event.target.closest("[data-stage-close]")) {
            teardownStage();
            if (typeof window.closePodium === "function") window.closePodium();
        }
    });
    document.addEventListener("pointermove", pokeControls, { passive: true });
    document.addEventListener("keydown", (event) => {
        if (!S.root || event.target.closest?.("input, textarea, select, [contenteditable]")) return;
        if (event.key === "r" || event.key === "R") replayStage(true);
    });
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) finishNow();
    });
    try {
        S.channel = new BroadcastChannel(`live-host-stage-${CONFIG.pin}`);
        S.channel.onmessage = (event) => {
            if (event?.data?.type === "replay" && S.model) replayStage(false);
        };
    } catch (error) {
        S.channel = null;
    }
}

export function renderStage(top, payload = {}) {
    bindOnce();
    const model = buildStageModel(top, { totalPlayers: payload.total_players ?? payload.totalPlayers });
    if (S.root && S.model && S.model.signature === model.signature) {
        // Eyni nəticə təkrar gəldi (WS + snapshot) — səhnəni yenidən başlatma; yalnız statistikanı tamamla.
        if (!S.payload?.stats && payload?.stats) S.payload = Object.assign({}, S.payload, { stats: payload.stats });
        return;
    }
    S.model = model;
    S.payload = payload || {};
    clearTimers();
    stopDanceBeat();
    start();
}

export function replayStage(broadcast) {
    if (!S.model) return;
    clearTimers();
    stopDanceBeat();
    start();
    if (broadcast && S.channel) {
        try {
            S.channel.postMessage({ type: "replay" });
        } catch (error) { /* kanal bağlıdır */ }
    }
}

export function teardownStage() {
    clearTimers();
    stopDanceBeat();
    window.clearTimeout(S.idleTimer);
    S.fx?.destroy();
    S.fx = null;
    S.root = null;
    S.model = null;
    S.payload = null;
    S.done = false;
    if (UI.finalPodium) UI.finalPodium.innerHTML = "";
}
