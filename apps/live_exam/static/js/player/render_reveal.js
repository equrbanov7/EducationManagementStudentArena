// LX-FE-PLAYER (2026-09-29): nəticə (düzgün/səhv/qismən/cavabsız) və liderlər görünüşü.
// Yalnız serverin göndərdiyi məlumat göstərilir: şəxsi nəticə (`player_answer`), `rank`,
// `gap_to_next`, `next_nickname`, `streak`, multi üçün `correct_selected/total_correct`,
// yazılı cavab üçün `your_text`/`accepted_answers`. Sahə yoxdursa — o hissə sadəcə göstərilmir.
import { LEADERBOARD_LIMIT, PHASES, prefersReducedMotion } from './config.js?v=lx20261002';
import { playSound } from './audio.js?v=lx20261002';
import { buzz, HAPTIC } from './haptics.js?v=lx20261002';
import { shapeKey, shapeLabel, shapeSvg, toneIndex } from './shapes.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';
import { previousRank, rememberRank } from './stats.js?v=lx20261002';
import { announce, setQuestionChip, setRank, setScore, setTimer, stopTimeBar } from './ui.js?v=lx20261002';
import {
    esc,
    fmt,
    formatNumber,
    formatSeconds,
    getRevealKey,
    hasNumber,
    isOwnRow,
    isTextQuestion,
    miniAvatar,
    normalizeTopRows,
    ordinal,
    pickFirst,
    showQuestionsOnDevices,
    toInt,
    tr,
} from './utils.js?v=lx20261002';
import { mountView } from './views.js?v=lx20261002';
import { CHECK_SVG } from './render_round.js?v=lx20261002';

const CROSS_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"/></svg>';
const HALF_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" opacity=".45"/><path d="M5 12.5l4.2 4.2 4.1-4.1" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const CLOCK_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="13" r="8" fill="none" stroke="currentColor" stroke-width="2.4"/><path d="M12 9v4.5l3 2M9.5 2.8h5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>';
const FLAME_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.5 2.5c.6 3.3-1.6 5-3 6.8-1.6 2-2.5 3.8-2.5 5.7A5 5 0 0 0 12 20a5 5 0 0 0 5-5c0-2.3-1.2-3.8-2-4.8.1 1.6-.5 2.7-1.5 3.2.5-3.4-.2-7.6-1-10.9z" fill="currentColor"/></svg>';
const BOLT_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M13.5 2 5 13.2h6l-1 8.8 8.5-11.4h-6z" fill="currentColor"/></svg>';

// Şəxsi nəticə: WS/snapshot `player_answer` → HTTP cavabından gələn tam nəticə (state.currentAnswer).
export function personalResult(payload) {
    const own = payload && payload.player_answer;
    if (own && (own.player_id == null || Number(own.player_id) === Number(state.player.id))) {
        return Object.assign({}, own);
    }
    const answer = state.currentAnswer;
    if (answer && answer.is_correct !== undefined) return Object.assign({}, answer);
    return null;
}

export function answeredButUnknown(payload) {
    return !personalResult(payload) && Boolean(state.currentAnswer && state.currentAnswer.saved);
}

function outcomeOf(result) {
    if (!result) return "none";
    if (result.is_correct) return "correct";
    const partialHits = toInt(pickFirst(result.correct_selected, 0), 0);
    if (partialHits > 0 || toInt(result.awarded_points, 0) > 0) return "partial";
    return "wrong";
}

// Server rank-ı: şəxsi mesajda yuxarı səviyyədə və ya player_answer-da ola bilər.
export function serverRankInfo(payload) {
    const own = (payload && payload.player_answer) || {};
    const rank = pickFirst(payload && payload.rank, own.rank);
    if (!hasNumber(rank) || Number(rank) <= 0) return null;
    return {
        rank: toInt(rank),
        gap: hasNumber(pickFirst(payload.gap_to_next, own.gap_to_next))
            ? toInt(pickFirst(payload.gap_to_next, own.gap_to_next))
            : null,
        nextNickname: String(pickFirst(payload.next_nickname, own.next_nickname) || ""),
    };
}

function rankChange(info, question, payload) {
    if (!info) return null;
    const own = (payload && payload.player_answer) || {};
    const explicit = pickFirst(payload.rank_change, own.rank_change);
    if (hasNumber(explicit)) return toInt(explicit);
    const before = previousRank(question && question.index);
    return before ? before - info.rank : null;
}

function rankLineMarkup(info, change) {
    if (!info) return "";
    const place = ordinal(info.rank);
    const line = fmt(tr("rankLine", "Sən {place} yerdəsən"), { place, rank: info.rank });
    let arrow = "";
    if (change > 0) {
        arrow = `<span class="lxp-move is-up" aria-label="${esc(fmt(tr("rankUp", "{count} pillə yuxarı"), { count: change }))}">▲ ${change}</span>`;
    } else if (change < 0) {
        arrow = `<span class="lxp-move is-down" aria-label="${esc(fmt(tr("rankDown", "{count} pillə aşağı"), { count: -change }))}">▼ ${-change}</span>`;
    }
    let motivation = "";
    if (info.rank === 1) {
        motivation = tr("rankLeader", "Liderdəsən! Belə davam et 👑");
    } else if (info.nextNickname && info.gap !== null) {
        motivation =
            info.gap > 0
                ? fmt(tr("gapLine", "{name} səndən {gap} xal öndədir"), { name: info.nextNickname, gap: formatNumber(info.gap) })
                : fmt(tr("gapTie", "{name} ilə xalın bərabərdir"), { name: info.nextNickname });
    }
    return (
        `<div class="lxp-rankline">` +
        `<p class="lxp-rankline__place"><strong>${esc(line)}</strong>${arrow}</p>` +
        (motivation ? `<p class="lxp-rankline__gap">${esc(motivation)}</p>` : "") +
        `</div>`
    );
}

function correctAnswerMarkup(payload, question) {
    if (isTextQuestion(question) || String(payload.answer_input || "") === "text") {
        const accepted = (Array.isArray(payload.accepted_answers) ? payload.accepted_answers : [])
            .map((value) => String(value || "").trim())
            .filter(Boolean)
            .slice(0, 3);
        if (!accepted.length) return "";
        // Mətn textContent ilə doldurulur (renderResult) — HTML kimi şərh olunmur.
        return (
            `<div class="lxp-answerkey"><span class="lxp-answerkey__label">${esc(tr("resultAccepted", "Düzgün cavab"))}</span>` +
            `<p class="lxp-answerkey__text" data-lxp-accepted></p></div>`
        );
    }
    const ids = new Set((Array.isArray(payload.correct_option_ids) ? payload.correct_option_ids : []).map(Number));
    const options = Array.isArray(question && question.options) ? question.options : [];
    if (!ids.size || !options.length) return "";
    const show = showQuestionsOnDevices();
    const chips = options
        .map((option, index) => ({ option, index }))
        .filter(({ option }) => ids.has(Number(option.id)))
        .map(({ option, index }) => {
            const key = shapeKey(option, index);
            const label = show && option.text ? option.text : shapeLabel(key);
            return `<span class="lxp-chip" data-tone="${toneIndex(option, index)}">${shapeSvg(key, "lxp-chip__shape")}<span>${esc(label)}</span></span>`;
        })
        .join("");
    const label = ids.size > 1 ? tr("resultCorrectAnswers", "Düzgün cavablar") : tr("resultCorrectAnswer", "Düzgün cavab");
    return `<div class="lxp-answerkey"><span class="lxp-answerkey__label">${esc(label)}</span><div class="lxp-choice__chips">${chips}</div></div>`;
}

export function renderResult(payload) {
    const question = state.currentQuestion || {};
    const result = personalResult(payload);
    const outcome = outcomeOf(result);
    const revealKey = getRevealKey(payload);
    const info = serverRankInfo(payload);
    const signature = [outcome, result ? toInt(result.awarded_points, 0) : "-", info ? info.rank : "-"].join(":");
    const key = `result:${revealKey}:${signature}`;
    const points = result ? toInt(result.awarded_points, 0) : 0;
    const streak = result && result.is_correct ? toInt(result.streak, 0) : 0;
    const change = rankChange(info, question, payload);

    const titles = {
        correct: tr("resultCorrect", "Düzgün!"),
        partial: tr("resultPartial", "Qismən düzgün"),
        wrong: tr("resultWrong", "Səhv cavab"),
        none: tr("resultNoAnswer", "Cavab verilmədi"),
    };
    const icons = { correct: CHECK_SVG, partial: HALF_SVG, wrong: CROSS_SVG, none: CLOCK_SVG };
    const chips = [];
    if (result && hasNumber(result.total_correct) && Number(result.total_correct) > 0 && !isTextQuestion(question)) {
        let detail = fmt(tr("resultPartialDetail", "{correct}/{total} düzgün"), {
            correct: toInt(result.correct_selected, 0),
            total: toInt(result.total_correct, 0),
        });
        if (toInt(result.wrong_selected, 0) > 0) {
            detail += ` · ${fmt(tr("resultWrongPicked", "{count} səhv seçim"), { count: toInt(result.wrong_selected, 0) })}`;
        }
        chips.push(`<span class="lxp-pill">${esc(detail)}</span>`);
    }
    if (streak >= 2) {
        chips.push(
            `<span class="lxp-pill lxp-pill--streak">${FLAME_SVG}<span>${esc(fmt(tr("streakLabel", "{count} ardıcıl düzgün!"), { count: streak }))}</span></span>`
        );
    }
    if (result && hasNumber(result.answer_ms) && outcome !== "none") {
        chips.push(
            `<span class="lxp-pill">${BOLT_SVG}<span>${esc(fmt(tr("resultSpeed", "{seconds} san"), { seconds: formatSeconds(result.answer_ms) }))}</span></span>`
        );
    }
    const typedAnswer = result && isTextQuestion(question) ? String(result.your_text || result.text || "") : "";
    const yourText = typedAnswer ? `<p class="lxp-typed-echo" data-lxp-echo></p>` : "";
    const pointsMarkup =
        points > 0
            ? `<p class="lxp-result__points" data-lxp-points>+${esc(formatNumber(points))} <small>${esc(tr("pointsShort", "xal"))}</small></p>`
            : `<p class="lxp-result__points is-zero">${esc(outcome === "none" ? tr("resultMissed", "Bu sualı buraxdın") : tr("resultNoPoints", "Bu dəfə xal yoxdur"))}</p>`;

    const { el, created } = mountView(
        key,
        `<div class="lxp-result" data-outcome="${outcome}">` +
            `<div class="lxp-result__badge" aria-hidden="true">${icons[outcome]}</div>` +
            `<h1 class="lxp-result__title">${esc(titles[outcome])}</h1>` +
            pointsMarkup +
            (chips.length ? `<div class="lxp-result__chips">${chips.join("")}</div>` : "") +
            yourText +
            rankLineMarkup(info, change) +
            correctAnswerMarkup(payload, question) +
            `</div>`,
        { tone: outcome }
    );
    state.phase = PHASES.RESULT;
    if (!created) return;
    const echo = el.querySelector("[data-lxp-echo]");
    if (echo) echo.textContent = fmt(tr("yourAnswer", "Cavabın: «{text}»"), { text: typedAnswer });
    const acceptedEl = el.querySelector("[data-lxp-accepted]");
    if (acceptedEl) {
        acceptedEl.textContent = (Array.isArray(payload.accepted_answers) ? payload.accepted_answers : [])
            .map((value) => String(value || "").trim())
            .filter(Boolean)
            .slice(0, 3)
            .map((value) => `«${value}»`)
            .join(" · ");
    }

    setQuestionChip(question);
    setTimer(false);
    stopTimeBar();
    if (result && hasNumber(result.total_score)) {
        setScore(toInt(result.total_score), { animate: !prefersReducedMotion() });
    }
    if (info) {
        setRank(info.rank);
        rememberRank(question.index, info.rank);
    }
    const soundByOutcome = { correct: "correct", partial: "partial", wrong: "wrong", none: "timeup" };
    playSound(soundByOutcome[outcome], revealKey);
    if (streak >= 3) window.setTimeout(() => playSound("streak", revealKey), 520);
    buzz({ correct: HAPTIC.correct, partial: HAPTIC.partial, wrong: HAPTIC.wrong, none: HAPTIC.timeup }[outcome]);
    announce(points > 0 ? `${titles[outcome]} +${points} ${tr("pointsShort", "xal")}` : titles[outcome]);
}

function leaderRowMarkup(row, rank, movement) {
    const own = isOwnRow(row);
    const move =
        movement > 0
            ? `<span class="lxp-move is-up" aria-hidden="true">▲${movement}</span>`
            : movement === "new"
              ? `<span class="lxp-move is-up" aria-hidden="true">▲</span>`
              : "";
    return (
        `<li class="lxp-lrow${own ? " is-me" : ""}">` +
        `<span class="lxp-lrow__rank">${rank}</span>` +
        `<span class="lxp-lrow__avatar">${miniAvatar(row, 34, "lxp-lrow__art")}</span>` +
        `<span class="lxp-lrow__name">${esc(row.nickname || tr("playerFallback", "Oyunçu"))}${own ? ` <em>(${esc(tr("youLabel", "Sən"))})</em>` : ""}</span>` +
        move +
        `<span class="lxp-lrow__score">${esc(formatNumber(row.score))}</span>` +
        `</li>`
    );
}

export function renderLeaderboard(payload) {
    const question = state.currentQuestion || {};
    const revealKey = getRevealKey(payload);
    const rows = normalizeTopRows(payload && payload.top);
    const previousRows = normalizeTopRows(payload && payload.previous_top);
    const previousRankByKey = new Map(previousRows.map((row, index) => [row._key, index + 1]));
    const info = serverRankInfo(payload);
    const ownIndex = rows.findIndex(isOwnRow);
    const key = `board:${revealKey}:${rows.map((row) => `${row._key}=${row.score}`).join(",")}:${info ? info.rank : "-"}`;

    // Əvvəlki cədvəldə hamının xalı 0 idisə (1-ci sual) sıra dəyişikliyi mənasızdır — ox göstərilmir.
    const hadScores = previousRows.some((row) => row.score > 0);
    const listRows = rows.slice(0, LEADERBOARD_LIMIT).map((row, index) => {
        const before = previousRankByKey.get(row._key);
        const movement = !hadScores ? 0 : before ? before - (index + 1) : previousRows.length >= 10 ? "new" : 0;
        return leaderRowMarkup(row, index + 1, movement);
    });
    let meRow = "";
    if (ownIndex >= LEADERBOARD_LIMIT) {
        meRow = leaderRowMarkup(rows[ownIndex], ownIndex + 1, 0);
    } else if (ownIndex < 0 && info) {
        meRow = leaderRowMarkup(
            {
                player_id: state.player.id,
                nickname: state.player.nickname,
                avatar_key: state.player.avatar_key,
                accessory_key: state.player.accessory_key,
                score: toInt(state.player.score, 0),
                _key: "me",
            },
            info.rank,
            0
        );
    }
    const isLast = toInt(question.index, 0) > 0 && toInt(question.index, 0) >= toInt(question.total, 0);
    const change = rankChange(info, question, payload);

    const { created } = mountView(
        key,
        `<div class="lxp-board">` +
            `<h1 class="lxp-board__title">${esc(tr("scoreboardTitle", "Liderlər"))}</h1>` +
            rankLineMarkup(info, change) +
            (listRows.length
                ? `<ol class="lxp-board__list">${listRows.join("")}${meRow ? `<li class="lxp-board__gap" aria-hidden="true">⋯</li>${meRow}` : ""}</ol>`
                : "") +
            (isLast
                ? `<p class="lxp-board__note">${esc(tr("lastQuestionNote", "Bu son sual idi — yekun nəticələr gəlir!"))}</p>`
                : `<p class="lxp-board__note">${esc(tr("nextQuestionSoon", "Növbəti sual tezliklə…"))}</p>`) +
            `</div>`,
        { tone: "board" }
    );
    state.phase = PHASES.LEADERBOARD;
    if (!created) return;
    setQuestionChip(question);
    setTimer(false);
    stopTimeBar();
    if (info) setRank(info.rank);
    else if (ownIndex >= 0) setRank(ownIndex + 1);
    playSound("leaderboard", revealKey);
    announce(
        info
            ? fmt(tr("rankLine", "Sən {place} yerdəsən"), { place: ordinal(info.rank), rank: info.rank })
            : tr("scoreboardTitle", "Liderlər")
    );
}
