import { PHASES, SCOREBOARD_ROWS } from './constants.js?v=lx20260930';
import { state } from './state.js?v=lx20260930';
import { playScoreboardSound } from './audio.js?v=lx20260930';
import { icon } from './icons.js?v=lx20260930';
import { setPresentationMarkup } from './presentation.js?v=lx20260930';
import { avatarImageMarkup, countUp, esc, fmt, formatNumber, progressLabel, reducedMotion, tr } from './utils.js?v=lx20260930';

/* Liderlər lövhəsi: sətirlər YENİ sırada render olunur, sonra hər biri köhnə
 * yerindən (previous_top) yeni yerinə «FLIP» ilə sürüşür; xal əvvəlki xaldan
 * sayılır; yer dəyişməsi oxları, «+xal» çipi, seriya alovu. Sıra SERVERİN
 * `top` sırasıdır — müştəridə yenidən sıralanmır. */

const rowId = (row) => Number(row?.player_id || row?.id || 0);

function rowMarkup(row, index, previousIndex, awarded, previousScore) {
    const id = rowId(row);
    const streak = Number(state.streaks.get(id) || 0);
    let move = "";
    if (previousIndex < 0) {
        move = `<span class="hx-lb__move hx-lb__move--new">${icon("star")}${esc(tr("newEntry", "Yeni"))}</span>`;
    } else if (previousIndex > index) {
        move = `<span class="hx-lb__move hx-lb__move--up">${icon("up")}${previousIndex - index}</span>`;
    } else if (previousIndex < index) {
        move = `<span class="hx-lb__move hx-lb__move--down">${icon("down")}${index - previousIndex}</span>`;
    }
    return `
        <li class="hx-lb__row ${index === 0 ? "is-first" : ""}" data-player-id="${id}" data-from="${previousIndex}" data-score="${Number(row?.score || 0)}" data-prev-score="${previousScore}">
            <span class="hx-lb__rank" aria-label="${index + 1}">${index + 1}</span>
            <span class="hx-lb__avatar">${avatarImageMarkup(row, 64, "hx-lb__img")}</span>
            <span class="hx-lb__name">${esc(row?.nickname || "")}</span>
            <span class="hx-lb__extras">
                ${streak >= 2 ? `<span class="hx-lb__streak" title="${esc(fmt(tr("streak", "{count} ardıcıl düzgün"), { count: streak }))}">${icon("flame")}${streak}</span>` : ""}
                ${awarded > 0 ? `<span class="hx-lb__gain">+${formatNumber(awarded)}</span>` : ""}
                ${move}
            </span>
            <strong class="hx-lb__score" data-lb-score>${formatNumber(previousScore)}</strong>
        </li>
    `;
}

function animateRows(root) {
    const rows = Array.from(root.querySelectorAll(".hx-lb__row"));
    if (!rows.length) return;
    const pitch = rows.length > 1 ? rows[1].offsetTop - rows[0].offsetTop : rows[0].offsetHeight + 12;
    rows.forEach((row, index) => {
        const from = Number(row.dataset.from);
        const offset = from < 0 ? (rows.length - index + 1) * pitch : (from - index) * pitch;
        row.style.setProperty("--from-y", `${offset}px`);
        row.style.setProperty("--i", String(index));
        row.classList.toggle("is-entering", from < 0);
        const scoreEl = row.querySelector("[data-lb-score]");
        const target = Number(row.dataset.score || 0);
        const start = Number(row.dataset.prevScore || 0);
        if (reducedMotion()) countUp(scoreEl, target, target, 0);
        else window.setTimeout(() => countUp(scoreEl, start, target, 900), 450 + index * 70);
    });
    root.classList.add("is-animating");
}

export function renderScoreboardStage(payload, question) {
    const signature = `${state.revealKey}:${PHASES.SCOREBOARD}`;
    if (state.phase === PHASES.SCOREBOARD && state.phaseSignature === signature) return;
    const top = (Array.isArray(payload?.top) ? payload.top : []).slice(0, SCOREBOARD_ROWS);
    const previous = Array.isArray(payload?.previous_top) ? payload.previous_top : [];
    const previousIds = previous.map(rowId);
    const awardedById = new Map((Array.isArray(payload?.results) ? payload.results : []).map((row) => [rowId(row), Number(row.awarded_points || 0)]));
    const isLast = question && Number(question.index || 0) >= Number(question.total || 0) && Number(question.total || 0) > 0;
    playScoreboardSound(`scoreboard:${state.revealKey}`);

    const rows = top
        .map((row, index) => {
            const id = rowId(row);
            const previousIndex = previousIds.indexOf(id);
            const awarded = awardedById.get(id) || 0;
            const previousRow = previous[previousIndex];
            const previousScore = previousRow ? Number(previousRow.score || 0) : Math.max(0, Number(row.score || 0) - awarded);
            return rowMarkup(row, index, previousIndex, awarded, previousScore);
        })
        .join("");

    setPresentationMarkup(
        PHASES.SCOREBOARD,
        signature,
        `
            <section class="hx-scene hx-leaderboard">
                <header class="hx-lb__head">
                    <span class="hx-lb__trophy">${icon("trophy")}</span>
                    <div>
                        <h2 class="hx-lb__title">${esc(tr("leaderboard", "Liderlər lövhəsi"))}</h2>
                        <p class="hx-lb__sub">${esc(isLast ? tr("leaderboardLast", "Son sual bitdi — final səhnəsi gəlir!") : question ? progressLabel(question) : "")}</p>
                    </div>
                </header>
                ${
                    rows
                        ? `<ol class="hx-lb__list" aria-live="polite">${rows}</ol>`
                        : `<p class="hx-lb__empty">${esc(tr("noAnswers", "Bu raundda cavab verilmədi"))}</p>`
                }
            </section>
        `,
        (root) => animateRows(root.querySelector(".hx-lb__list") || root)
    );
}
