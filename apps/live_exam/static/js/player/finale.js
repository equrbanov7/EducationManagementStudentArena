// LX-FE-PLAYER (2026-09-29): telefonda final — öz yerin + xalın (sayma animasiyası).
//  * 1-ci: tac + rəqs edən avatar (tam bədən) + ekranın SOL və SAĞ kənarından konfetti + fanfar;
//  * 2-ci/3-cü: medal + rəqs; digərləri: «Əla oyun idi!» kartı + statistika (`my_stats`).
// Rəqs LX-FE-STAGE-in API-si ilə (data-dance, live_avatar.css); o CSS yoxdursa öz ehtiyat
// animasiyamız (.lxp-dance-fallback) işləyir. Yer/xal/statistika yalnız serverdən gəlir.
// 2026-10-19: «Rəsmi» üslubda (renderFormalFinal) — yer, xal, statistika və sakit sıralama siyahısı;
// tac, medal, rəqs, konfetti, fanfar və vibrasiya YOXDUR.
import { PODIUM_SIZE, PHASES, prefersReducedMotion } from './config.js?v=lx20261019s';
import { playSound } from './audio.js?v=lx20261019s';
import { UI } from './dom.js?v=lx20261019s';
import { buzz, HAPTIC } from './haptics.js?v=lx20261019s';
import { state } from './state.js?v=lx20261019s';
import { announce, setQuestionChip, setRank, setScore, setTimer, stopTimeBar } from './ui.js?v=lx20261019s';
import {
    esc,
    fmt,
    formatNumber,
    formatSeconds,
    hasNumber,
    isOwnRow,
    miniAvatar,
    normalizeTopRows,
    ordinal,
    pickFirst,
    toInt,
    tr,
} from './utils.js?v=lx20261019s';
import { mountView } from './views.js?v=lx20261019s';
import { isFormal } from '../host_lobby/style_mode.js?v=lx20261019s';

const CROWN_SVG =
    '<svg viewBox="0 0 64 44" aria-hidden="true" focusable="false"><path d="M6 14l13 11L32 5l13 20 13-11-5 26H11z" fill="#fcd34d" stroke="#b45309" stroke-width="3" stroke-linejoin="round"/><circle cx="32" cy="5" r="4" fill="#fb7185"/><circle cx="6" cy="14" r="3.5" fill="#38bdf8"/><circle cx="58" cy="14" r="3.5" fill="#34d399"/><rect x="11" y="34" width="42" height="6" rx="2" fill="#f59e0b"/></svg>';
const MEDAL_COLORS = { 1: ["#fde68a", "#d97706"], 2: ["#e5e7eb", "#6b7280"], 3: ["#fed7aa", "#b45309"] };

function medalSvg(place) {
    const [light, dark] = MEDAL_COLORS[place] || MEDAL_COLORS[3];
    return (
        `<svg viewBox="0 0 48 60" aria-hidden="true" focusable="false">` +
        `<path d="M12 2h9l6 16h-9zM36 2h-9l-6 16h9z" fill="#2563eb"/>` +
        `<circle cx="24" cy="38" r="18" fill="${light}" stroke="${dark}" stroke-width="3"/>` +
        `<text x="24" y="45" text-anchor="middle" font-family="Space Grotesk, Manrope, sans-serif" font-size="20" font-weight="800" fill="${dark}">${place}</text>` +
        `</svg>`
    );
}

function finalAvatar(player, size, dance) {
    const renderer = window.LiveAvatarRenderer;
    if (!renderer || typeof renderer.renderAvatarMarkup !== "function") return "";
    return renderer.renderAvatarMarkup(player || {}, {
        size,
        crop: "full",
        interactive: false,
        className: "lxp-final__art",
        dance,
    });
}

// STAGE-in rəqs CSS-i yüklənməyibsə (animasiya yoxdur) öz ehtiyat animasiyamızı qoşuruq.
function ensureDance(root) {
    const art = root && root.querySelector(".live-avatar[data-dance]");
    if (!art || prefersReducedMotion()) return;
    window.requestAnimationFrame(() => {
        const name = window.getComputedStyle(art).animationName;
        if (!name || name === "none") root.classList.add("lxp-dance-fallback");
    });
}

function launchConfetti() {
    if (!UI.fx || prefersReducedMotion()) return;
    const colors = ["#f43f5e", "#f59e0b", "#22c55e", "#3b82f6", "#a855f7", "#14b8a6", "#fde047"];
    const burst = (delayBase) => {
        const fragment = document.createDocumentFragment();
        for (let i = 0; i < 44; i += 1) {
            const fromLeft = i % 2 === 0;
            const piece = document.createElement("i");
            piece.className = `lxp-confetti ${fromLeft ? "is-left" : "is-right"}${i % 3 === 0 ? " is-round" : ""}`;
            const reach = 35 + Math.random() * 55; // ekran eninin %-i
            piece.style.setProperty("--x", `${fromLeft ? reach : -reach}vw`);
            piece.style.setProperty("--y", `${-(28 + Math.random() * 42)}vh`);
            piece.style.setProperty("--fall", `${55 + Math.random() * 45}vh`);
            piece.style.setProperty("--r", `${Math.round(360 + Math.random() * 720) * (fromLeft ? 1 : -1)}deg`);
            piece.style.setProperty("--d", `${(delayBase + Math.random() * 0.35).toFixed(2)}s`);
            piece.style.setProperty("--c", colors[i % colors.length]);
            piece.style.setProperty("--top", `${58 + Math.random() * 30}%`);
            fragment.appendChild(piece);
        }
        UI.fx.appendChild(fragment);
    };
    burst(0);
    burst(1.1);
    window.setTimeout(() => {
        if (UI.fx) UI.fx.textContent = "";
    }, 4800);
}

function countUp(el, target) {
    if (!el) return;
    const to = Math.max(0, toInt(target, 0));
    if (prefersReducedMotion() || to === 0) {
        el.textContent = formatNumber(to);
        return;
    }
    const started = performance.now();
    const duration = 1400;
    const step = (now) => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 4);
        el.textContent = formatNumber(Math.round(to * eased));
        if (progress < 1 && el.isConnected) window.requestAnimationFrame(step);
    };
    window.requestAnimationFrame(step);
}

function statsMarkup(myStats) {
    if (!myStats) return "";
    const tiles = [];
    if (hasNumber(myStats.correct) && hasNumber(myStats.total) && Number(myStats.total) > 0) {
        tiles.push([tr("statCorrect", "Düzgün cavab"), `${toInt(myStats.correct)}/${toInt(myStats.total)}`]);
    }
    if (hasNumber(myStats.best_streak)) {
        tiles.push([tr("statBestStreak", "Ən uzun seriya"), `${isFormal() ? "" : "🔥 "}${toInt(myStats.best_streak)}`]);
    }
    if (hasNumber(myStats.avg_answer_ms) && Number(myStats.avg_answer_ms) > 0) {
        tiles.push([
            tr("statAvgTime", "Orta cavab vaxtı"),
            fmt(tr("resultSpeed", "{seconds} san"), { seconds: formatSeconds(myStats.avg_answer_ms) }),
        ]);
    }
    if (!tiles.length) return "";
    return (
        `<dl class="lxp-final__stats">` +
        tiles
            .map(([label, value]) => `<div class="lxp-stat"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`)
            .join("") +
        `</dl>`
    );
}

function podiumMarkup(rows) {
    const top = rows.slice(0, PODIUM_SIZE);
    if (!top.length) return "";
    const order = [top[1] && { row: top[1], place: 2 }, top[0] && { row: top[0], place: 1 }, top[2] && { row: top[2], place: 3 }].filter(Boolean);
    return (
        `<div class="lxp-podium" aria-label="${esc(tr("finalPodiumTitle", "Podium"))}">` +
        order
            .map(({ row, place }) => {
                const art = miniAvatar(row, place === 1 ? 52 : 44, "lxp-podium__img");
                return (
                    `<div class="lxp-podium__slot is-p${place}${isOwnRow(row) ? " is-me" : ""}">` +
                    `<span class="lxp-podium__art">${art}</span>` +
                    `<span class="lxp-podium__name">${esc(row.nickname || tr("playerFallback", "Oyunçu"))}</span>` +
                    `<span class="lxp-podium__score">${esc(formatNumber(row.score))}</span>` +
                    `<span class="lxp-podium__block">${place}</span>` +
                    `</div>`
                );
            })
            .join("") +
        `</div>`
    );
}

const FORMAL_LIST_LIMIT = 5;

function formalListMarkup(rows, ownIndex, rank) {
    const items = rows.slice(0, FORMAL_LIST_LIMIT).map((row, index) => ({ row, place: index + 1 }));
    if (ownIndex >= FORMAL_LIST_LIMIT) items.push({ row: rows[ownIndex], place: rank || ownIndex + 1, gap: true });
    if (!items.length) return "";
    return (
        `<ol class="lxp-board__list lxp-final__list" aria-label="${esc(tr("formalResultsTitle", "Yekun nəticələr"))}">` +
        items
            .map(({ row, place, gap }) => {
                const own = isOwnRow(row);
                return (
                    (gap ? `<li class="lxp-board__gap" aria-hidden="true">⋯</li>` : "") +
                    `<li class="lxp-lrow${own ? " is-me" : ""}">` +
                    `<span class="lxp-lrow__rank">${place}</span>` +
                    `<span class="lxp-lrow__avatar">${miniAvatar(row, 34, "lxp-lrow__art")}</span>` +
                    `<span class="lxp-lrow__name">${esc(row.nickname || tr("playerFallback", "Oyunçu"))}${own ? ` <em>(${esc(tr("youLabel", "Sən"))})</em>` : ""}</span>` +
                    `<span class="lxp-lrow__score">${esc(formatNumber(row.score))}</span>` +
                    `</li>`
                );
            })
            .join("") +
        `</ol>`
    );
}

/** «Rəsmi» final: öz yerin + xalın + statistika + ilk 5 (sən siyahıdan kənardasansa — sən də). */
function renderFormalFinal({ rows, ownIndex, rank, score, myStats, key }) {
    const { el, created } = mountView(
        `formal:${key}`,
        `<div class="lxp-final lxp-final--formal" data-place="formal">` +
            `<p class="lxp-kicker">${esc(tr("formalFinalKicker", "Oyun başa çatdı"))}</p>` +
            `<div class="lxp-final__who">${miniAvatar(state.player, 56, "lxp-final__initials")}<strong>${esc(state.player.nickname || "")}</strong></div>` +
            `<div class="lxp-final__summary">` +
            (rank ? `<div class="lxp-final__place"><span>${esc(tr("finalYourPlace", "Sənin yerin"))}</span><strong>${esc(ordinal(rank) || `#${rank}`)}</strong></div>` : "") +
            `<div class="lxp-final__score"><strong>${esc(formatNumber(score))}</strong><span>${esc(tr("pointsShort", "xal"))}</span></div>` +
            `</div>` +
            statsMarkup(myStats) +
            formalListMarkup(rows, ownIndex, rank) +
            `</div>`,
        { tone: "final" }
    );
    state.phase = PHASES.FINAL;
    if (!created || !el) return;
    setQuestionChip(null);
    setTimer(false);
    stopTimeBar();
    setScore(score);
    setRank(rank || null);
    announce(`${tr("formalResultsTitle", "Yekun nəticələr")}. ${rank ? fmt(tr("rankLine", "Sən {place} yerdəsən"), { place: ordinal(rank), rank }) : ""}`);
}

export function renderFinal(payload) {
    const rows = normalizeTopRows(payload && payload.top);
    const ownIndex = rows.findIndex(isOwnRow);
    const serverRank = pickFirst(payload && payload.rank, payload && payload.my_stats && payload.my_stats.rank);
    const rank = hasNumber(serverRank) && Number(serverRank) > 0 ? toInt(serverRank) : ownIndex >= 0 ? ownIndex + 1 : 0;
    const score = ownIndex >= 0 ? rows[ownIndex].score : toInt(state.player.score, 0);
    const myStats = payload && payload.my_stats ? payload.my_stats : null;
    const key = `final:${(payload && payload.finished_at) || ""}:${rank}:${score}:${myStats ? "s" : "-"}:${rows.length}`;
    if (isFormal()) {
        renderFormalFinal({ rows, ownIndex, rank, score, myStats, key });
        return;
    }
    const place = rank >= 1 && rank <= 3 ? rank : 0;
    const name = state.player.nickname || tr("youLabel", "Sən");

    const titles = {
        1: tr("finalWinner", "Qalib sənsən!"),
        2: tr("finalSecond", "Gümüş medal!"),
        3: tr("finalThird", "Bürünc medal!"),
        0: fmt(tr("finalWellPlayed", "Əla oyun idi, {name}!"), { name }),
    };
    const dance = { 1: "jump", 2: "bounce", 3: "sway", 0: "wave" }[place];
    const hero =
        `<div class="lxp-final__stage">` +
        `<span class="lxp-final__spot" aria-hidden="true"></span>` +
        (place === 1 ? `<span class="lxp-final__crown">${CROWN_SVG}</span>` : "") +
        `<div class="lxp-final__dancer" data-lxp-dancer>${finalAvatar(state.player, place ? 150 : 124, dance)}</div>` +
        (place >= 2 ? `<span class="lxp-final__medal">${medalSvg(place)}</span>` : "") +
        `</div>`;
    const placeLine = rank
        ? `<div class="lxp-final__place"><span>${esc(tr("finalYourPlace", "Sənin yerin"))}</span><strong>${esc(ordinal(rank) || `#${rank}`)}</strong></div>`
        : "";

    const { el, created } = mountView(
        key,
        `<div class="lxp-final" data-place="${place || "other"}">` +
            `<p class="lxp-kicker">${esc(tr("finalTitle", "Oyun bitdi!"))}</p>` +
            hero +
            `<h1 class="lxp-final__title">${esc(titles[place])}</h1>` +
            `<div class="lxp-final__score"><strong data-lxp-countup>${place ? "0" : esc(formatNumber(score))}</strong><span>${esc(tr("pointsShort", "xal"))}</span></div>` +
            placeLine +
            statsMarkup(myStats) +
            (place ? "" : `<p class="lxp-final__cheer">${esc(tr("finalKeepGoing", "Hər oyun səni daha güclü edir — növbəti dəfə podiuma!"))}</p>`) +
            podiumMarkup(rows) +
            `</div>`,
        { tone: place ? `final-${place}` : "final" }
    );
    state.phase = PHASES.FINAL;
    if (!created) return;

    setQuestionChip(null);
    setTimer(false);
    stopTimeBar();
    setScore(score);
    setRank(rank || null);
    // Tac avatarın öz elementinə köçürülür — rəqs (tullanma) zamanı başla birgə hərəkət edir.
    const art = el.querySelector(".lxp-final__dancer .live-avatar");
    const crown = el.querySelector(".lxp-final__crown");
    if (art && crown) art.appendChild(crown);
    ensureDance(el);
    if (place) {
        countUp(el.querySelector("[data-lxp-countup]"), score);
        playSound("fanfare", key);
        buzz(HAPTIC.finale);
        if (place === 1) launchConfetti();
    } else {
        playSound("finale", key);
    }
    announce(`${titles[place]} ${rank ? fmt(tr("rankLine", "Sən {place} yerdəsən"), { place: ordinal(rank), rank }) : ""}`);
}
