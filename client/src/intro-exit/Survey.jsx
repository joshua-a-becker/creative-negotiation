import React, { useEffect, useState } from "react";
import { usePlayer, useGame } from "@empirica/core/player/classic/react";

/**
 * Post-negotiation survey, defined in YAML (treatment factor surveyURL; the
 * server fetches and parses it into game.survey at game start):
 *
 *   scales:    { scaleId: ["1 — Not at all", "2", …, "N/A"] }
 *   questions: [{ id, n, page, section?, type, label, hint?, required?,
 *                 scale? (likert), options? (single/multi select),
 *                 max_selections? (multi), show_if? { question, equals | not_equals } }]
 *   optional:  title, intro, pages: [{ title, help }]  (one entry per page)
 *
 * Styled after SamQuinto/Creative-Negotiations-Materials
 * prolific_post_negotiation_survey_preview.html (sliders for likert items,
 * card choices, sticky progress bar and footer), minus the slider track fill.
 *
 * Answers are saved to player.surveyResponses ({ id: value }, option text
 * verbatim; multi_select → array) on every page change, so a refresh resumes
 * on the same page. Answers to hidden questions are dropped.
 */

const DEFAULT_TITLE = "Post-negotiation survey";
const DEFAULT_INTRO = "Please answer the following questions about the negotiation you just completed. Your responses are private.";

export function Survey({ next }) {
  const player = usePlayer();
  const game = useGame();
  const survey = game?.get("survey");
  const questions = survey?.questions || [];
  const pages = [...new Set(questions.map((q) => q.page ?? 1))].sort((a, b) => a - b);

  const [pageIndex, setPageIndex] = useState(() => player.get("surveyPageIndex") || 0);
  const [answers, setAnswers] = useState(() => player.get("surveyResponses") || {});
  const [showErrors, setShowErrors] = useState(false);

  // No survey (none configured, or it failed to load): skip this step.
  useEffect(() => {
    if (questions.length === 0) next();
  }, [questions.length]);
  if (questions.length === 0) return null;

  // A question whose condition refers to an unanswered question stays hidden.
  const isVisible = (q) => {
    const cond = q.show_if;
    if (!cond) return true;
    const a = answers[cond.question];
    if (a === undefined || a === null || a === "") return false;
    if ("equals" in cond) return a === cond.equals;
    if ("not_equals" in cond) return a !== cond.not_equals;
    return true;
  };
  const isAnswered = (q) => {
    const a = answers[q.id];
    if (q.type === "multi_select") return Array.isArray(a) && a.length > 0;
    if (q.type === "open_text") return typeof a === "string" && a.trim() !== "";
    return a !== undefined && a !== null && a !== "";
  };

  const safeIndex = Math.min(pageIndex, pages.length - 1);
  const page = pages[safeIndex];
  const isLastPage = safeIndex >= pages.length - 1;
  const pageMeta = survey.pages?.[safeIndex] || {};
  const pageQuestions = questions.filter((q) => (q.page ?? 1) === page && isVisible(q));
  const required = pageQuestions.filter((q) => q.required);
  const missing = required.filter((q) => !isAnswered(q));

  const setAnswer = (id, value) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  };

  // Keep only answers to questions that are currently shown.
  const saveResponses = () => {
    const responses = {};
    questions.forEach((q) => {
      if (isVisible(q) && answers[q.id] !== undefined) responses[q.id] = answers[q.id];
    });
    player.set("surveyResponses", responses);
  };

  const goToPage = (index) => {
    saveResponses();
    player.set("surveyPageIndex", index);
    setPageIndex(index);
    setShowErrors(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleNext = () => {
    if (missing.length > 0) {
      setShowErrors(true);
      document.getElementById(`survey-${missing[0].id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (isLastPage) {
      saveResponses();
      player.set("surveyCompletedAt", Date.now());
      next();
    } else {
      goToPage(safeIndex + 1);
    }
  };

  let lastSection = null;

  return (
    <div className="cn-survey">
      <style>{SURVEY_CSS}</style>
      <div className="sheet">
        <header className="survey-head">
          <h1>{survey.title || DEFAULT_TITLE}</h1>
          <p className="intro">{survey.intro || DEFAULT_INTRO}</p>
        </header>

        <div className="toolbar">
          <div className="toolbar-top">
            <span className="page-label">Page {safeIndex + 1} of {pages.length}</span>
          </div>
          <div className="progress" aria-hidden="true">
            <span style={{ width: `${((safeIndex + 1) / pages.length) * 100}%` }} />
          </div>
        </div>

        <main>
          {pageMeta.title && <h2 className="page-title">{pageMeta.title}</h2>}
          {pageMeta.help && <p className="page-help">{pageMeta.help}</p>}

          {pageQuestions.map((q) => {
            const heading = q.section && q.section !== lastSection ? q.section : null;
            if (q.section) lastSection = q.section;
            const unanswered = showErrors && q.required && !isAnswered(q);
            return (
              <React.Fragment key={q.id}>
                {heading && <h3 className="section-title">{heading}</h3>}
                <section id={`survey-${q.id}`} className={`question ${unanswered ? "unanswered" : ""}`}>
                  <p className="question-label">
                    {q.n && <span className="number">{q.n}.</span>}
                    <span>
                      {q.label}
                      {q.required && <span className="required" aria-hidden="true">*</span>}
                    </span>
                  </p>
                  {q.hint && <div className="hint">{q.hint}</div>}
                  <QuestionInput
                    question={q}
                    scale={survey.scales?.[q.scale]}
                    value={answers[q.id]}
                    onChange={(v) => setAnswer(q.id, v)}
                  />
                </section>
              </React.Fragment>
            );
          })}

          {showErrors && missing.length > 0 && (
            <p className="validation">Please answer the highlighted questions before continuing.</p>
          )}
        </main>

        <footer className="actions">
          <button
            className="nav secondary"
            type="button"
            disabled={safeIndex === 0}
            onClick={() => goToPage(safeIndex - 1)}
          >
            Back
          </button>
          <span className="answered-count">
            {required.length - missing.length} of {required.length} required responses completed
          </span>
          <button className="nav primary" type="button" onClick={handleNext}>
            {isLastPage ? "Submit survey" : "Continue"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// "4 — Moderately" → "Moderately"; options without a dash keep their text.
const anchorText = (option) => {
  const parts = String(option).split(" — ");
  return parts.length > 1 ? parts.slice(1).join(" — ") : parts[0];
};

function QuestionInput({ question: q, scale, value, onChange }) {
  if (q.type === "likert") {
    const options = (scale || []).filter((o) => o !== "N/A");
    const hasNA = (scale || []).includes("N/A");
    const index = options.indexOf(value); // -1 when unanswered or N/A
    const answered = index >= 0;
    // Blank by default: the thumb is invisible until a value is picked (the
    // input still needs a value, so it sits unseen in the middle).
    const sliderValue = answered ? index + 1 : Math.ceil(options.length / 2);
    const middle = options[Math.floor(options.length / 2)];
    // Any interaction counts, including a click on the hidden thumb's
    // position (which fires no change event).
    const pick = (e) => onChange(options[Number(e.target.value) - 1]);
    return (
      <div className="slider-box">
        <div className="slider-top">
          <span className={`answer-value ${value ? "selected" : ""}`}>
            {value || "Click on the scale to answer"}
          </span>
          {hasNA && (
            <button
              type="button"
              className={`na-button ${value === "N/A" ? "active" : ""}`}
              onClick={() => onChange("N/A")}
            >
              Not applicable
            </button>
          )}
        </div>
        <input
          type="range"
          min={1}
          max={options.length}
          step={1}
          value={sliderValue}
          onChange={pick}
          onPointerUp={pick}
          onKeyUp={(e) => {
            // Only value keys answer (tabbing onto the slider mustn't).
            if (/^(Arrow|Home$|End$|Page)/.test(e.key)) pick(e);
          }}
          className={answered ? "answered" : ""}
          aria-label={`Response to question ${q.n || q.id}`}
        />
        <div className="ticks">
          {options.map((_, i) => <span key={i}>{i + 1}</span>)}
        </div>
        <div className="anchors">
          <span>{anchorText(options[0])}</span>
          <span>{anchorText(middle)}</span>
          <span>{anchorText(options[options.length - 1])}</span>
        </div>
      </div>
    );
  }

  if (q.type === "single_select") {
    const options = q.options || [];
    return (
      <div className={`choices ${options.length > 2 ? "four" : ""}`}>
        {options.map((opt) => (
          <label key={opt} className={`choice ${value === opt ? "checked" : ""}`}>
            <input type="radio" name={q.id} checked={value === opt} onChange={() => onChange(opt)} />
            <span>{opt}</span>
          </label>
        ))}
      </div>
    );
  }

  if (q.type === "multi_select") {
    const selected = Array.isArray(value) ? value : [];
    const max = q.max_selections || Infinity;
    const toggle = (opt) => {
      if (selected.includes(opt)) onChange(selected.filter((o) => o !== opt));
      else if (selected.length < max) onChange([...selected, opt]);
    };
    return (
      <div className="choices many">
        {(q.options || []).map((opt) => (
          <label key={opt} className={`choice ${selected.includes(opt) ? "checked" : ""}`}>
            <input type="checkbox" name={q.id} checked={selected.includes(opt)} onChange={() => toggle(opt)} />
            <span>{opt}</span>
          </label>
        ))}
      </div>
    );
  }

  // open_text (and any unknown type)
  return (
    <textarea
      value={value || ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={q.required ? "Write a short response" : "Optional response"}
    />
  );
}

// Scoped port of the preview's stylesheet. The slider track is a plain grey
// line (no fill up to the chosen value); the thumb is invisible until answered.
const SURVEY_CSS = `
.cn-survey {
  --blue:#2563eb; --blue-dark:#173d91; --blue-soft:#edf4ff; --ink:#151922;
  --muted:#606875; --line:#d9dee7; --paper:#fff; --wash:#eef1f5; --error:#b42318;
  min-height:100vh; background:var(--wash); color:var(--ink); font:16px/1.48 Arial, Helvetica, sans-serif;
}
.cn-survey * { box-sizing:border-box; }
.cn-survey button, .cn-survey input, .cn-survey textarea { font:inherit; }
.cn-survey .sheet { width:min(920px,100%); min-height:100vh; margin:0 auto; background:var(--paper); box-shadow:0 0 0 1px #d7dbe2; }
.cn-survey .survey-head { padding:30px 40px 23px; border-bottom:1px solid var(--line); }
.cn-survey h1 { margin:7px 0 8px; font-size:30px; line-height:1.15; font-weight:700; }
.cn-survey .intro { max-width:700px; margin:0; color:var(--muted); }
.cn-survey .toolbar { position:sticky; top:0; z-index:5; padding:12px 40px; background:rgba(255,255,255,.97); border-bottom:1px solid var(--line); box-shadow:0 5px 16px rgba(15,23,42,.05); }
.cn-survey .toolbar-top { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:8px; }
.cn-survey .page-label { color:var(--blue-dark); font-weight:800; }
.cn-survey .progress { height:7px; overflow:hidden; border-radius:99px; background:#e5e9ef; }
.cn-survey .progress span { display:block; height:100%; border-radius:inherit; background:var(--blue); transition:width .2s ease; }
.cn-survey main { padding:30px 40px 18px; }
.cn-survey .page-title { margin:0 0 5px; font-size:24px; font-weight:700; }
.cn-survey .page-help { margin:0 0 26px; color:var(--muted); }
.cn-survey .section-title { margin:32px 0 0; padding:11px 14px; border-left:4px solid var(--blue); background:var(--blue-soft); color:var(--blue-dark); font-size:17px; font-weight:700; }
.cn-survey main > .section-title:first-child, .cn-survey .page-help + .section-title { margin-top:8px; }
.cn-survey .question { padding:24px 2px 25px; border-bottom:1px solid var(--line); }
.cn-survey .question.unanswered { margin-left:-13px; margin-right:-13px; padding-left:13px; padding-right:13px; background:#fff8f7; border-radius:6px; }
.cn-survey .question-label { display:flex; align-items:flex-start; gap:10px; margin:0 0 17px; font-size:17px; font-weight:700; }
.cn-survey .number { flex:0 0 auto; min-width:31px; color:var(--blue-dark); }
.cn-survey .required { margin-left:3px; color:var(--error); }
.cn-survey .hint { margin:-7px 0 15px 41px; padding:9px 12px; color:var(--muted); background:#f7f8fa; border-left:3px solid #9bb7ee; }
.cn-survey .slider-box { margin-left:41px; padding:14px 16px 13px; border:1px solid #ccd4e0; border-radius:7px; background:#fbfcfe; }
.cn-survey .slider-top { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
.cn-survey .answer-value { color:var(--muted); font-size:14px; font-weight:700; }
.cn-survey .answer-value.selected { color:var(--blue-dark); }
.cn-survey .na-button { padding:6px 10px; border:1px solid #aeb8c7; border-radius:5px; color:#3e4652; background:#fff; cursor:pointer; font-size:13px; font-weight:700; }
.cn-survey .na-button:hover, .cn-survey .na-button.active { color:#fff; background:#3e4652; border-color:#3e4652; }
.cn-survey input[type="range"] { width:100%; height:28px; margin:0; background:transparent; cursor:pointer; -webkit-appearance:none; appearance:none; }
.cn-survey input[type="range"]::-webkit-slider-runnable-track { height:7px; border-radius:99px; background:#d7deea; }
.cn-survey input[type="range"]::-webkit-slider-thumb { width:20px; height:20px; margin-top:-6.5px; border:3px solid transparent; border-radius:50%; background:transparent; box-shadow:none; -webkit-appearance:none; appearance:none; }
.cn-survey input[type="range"].answered::-webkit-slider-thumb { border-color:#fff; background:var(--blue); box-shadow:0 0 0 1px var(--blue-dark),0 2px 5px rgba(0,0,0,.16); }
.cn-survey input[type="range"]::-moz-range-track { height:7px; border-radius:99px; background:#d7deea; }
.cn-survey input[type="range"]::-moz-range-progress { background:transparent; }
.cn-survey input[type="range"]::-moz-range-thumb { width:17px; height:17px; border:3px solid transparent; border-radius:50%; background:transparent; box-shadow:none; }
.cn-survey input[type="range"].answered::-moz-range-thumb { border-color:#fff; background:var(--blue); box-shadow:0 0 0 1px var(--blue-dark); }
.cn-survey .ticks { display:flex; justify-content:space-between; padding:0 5px; color:#747d8a; font-size:12px; }
.cn-survey .anchors { display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; margin-top:7px; color:#4e5866; font-size:12px; line-height:1.25; }
.cn-survey .anchors span:nth-child(2) { text-align:center; }
.cn-survey .anchors span:last-child { text-align:right; }
.cn-survey .choices { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; margin-left:41px; }
.cn-survey .choices.many { grid-template-columns:1fr; }
.cn-survey .choice { display:flex; align-items:flex-start; gap:9px; min-height:47px; padding:11px 13px; border:1px solid var(--line); border-radius:6px; background:#fff; cursor:pointer; }
.cn-survey .choice:hover { border-color:#8fa9dc; background:#f8faff; }
.cn-survey .choice.checked { border-color:var(--blue); background:var(--blue-soft); box-shadow:inset 0 0 0 1px var(--blue); }
.cn-survey .choice input { margin-top:3px; accent-color:var(--blue); }
.cn-survey textarea { display:block; width:calc(100% - 41px); min-height:126px; margin-left:41px; padding:12px; resize:vertical; border:1px solid #aeb8c7; border-radius:6px; background:#fff; }
.cn-survey textarea:focus, .cn-survey button:focus-visible, .cn-survey input:focus-visible { outline:3px solid rgba(37,99,235,.20); outline-offset:2px; }
.cn-survey .validation { margin:14px 0 0; padding:11px 14px; border-left:4px solid var(--error); color:var(--error); background:#fff3f2; font-weight:700; }
.cn-survey .actions { position:sticky; bottom:0; z-index:4; display:flex; align-items:center; gap:12px; padding:15px 40px; border-top:1px solid var(--line); background:rgba(255,255,255,.98); box-shadow:0 -8px 20px rgba(15,23,42,.06); }
.cn-survey .answered-count { color:var(--muted); font-size:14px; }
.cn-survey button.nav { padding:11px 20px; border:0; border-radius:5px; cursor:pointer; font-weight:700; }
.cn-survey .secondary { color:var(--blue-dark); background:#e8effc; }
.cn-survey .primary { margin-left:auto; color:#fff; background:var(--blue); }
.cn-survey button:disabled { opacity:.45; cursor:not-allowed; }
@media(max-width:700px) {
  .cn-survey .survey-head, .cn-survey main, .cn-survey .toolbar, .cn-survey .actions { padding-left:18px; padding-right:18px; }
  .cn-survey h1 { font-size:26px; }
  .cn-survey .slider-box, .cn-survey .choices, .cn-survey textarea { width:100%; margin-left:0; }
  .cn-survey .hint { margin-left:0; }
  .cn-survey .question-label { gap:6px; }
  .cn-survey .choices { grid-template-columns:1fr; }
  .cn-survey .anchors { gap:6px; font-size:11px; }
  .cn-survey .answered-count { display:none; }
}
`;
