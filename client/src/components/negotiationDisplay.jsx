// ---------------------------------------------------------------------------
// Negotiation display + value logic for free-text proposals.
//
// A proposal is plain text the player types. "Calculate" sends it to the
// server, which runs server/src/score_offer/score_offer.py and returns the
// scorer's structured JSON. The pieces of that JSON the UI relies on:
//
//   decision            "scorable" | "rejected" | "clarification_needed"
//   lines               ["- PersonalBudget: $5,000  [-1.16]"]  proposer's
//                       breakdown. Present (partially) even when rejected.
//   lines_for_receiver  same, valued for the other side (scorable only)
//   total_for_proposer  number | null (null unless scorable)
//   total_for_receiver  number | null
//   proposal_allowed    boolean   scorer's own submit gate
//   findings            [{ decision, code, message, issue?, missing? }]
//   messages            [string]  the findings' messages (fallback)
//   missing_required    ["Salary", …] required issues not yet given
//   novel_terms         [string]  recorded but not scored
//   relative_revision   true when the text was applied on top of the previous
//                       offer ("same offer but…"); revision_confirmation.prompt
//   display_text        plain-text rendering (fallback if lines are absent)
//
// Optional forward-compatible shape for >2 roles: totals_by_role / lines_by_role
// keyed by role name. viewerScore() prefers those when present.
//
// "value" is the single unifying concept: never accept a deal worth < 0.
// ---------------------------------------------------------------------------

import React from "react";

export const SCORABLE = "scorable";
export const REJECTED = "rejected";
export const CLARIFICATION_NEEDED = "clarification_needed";

// ---------------------------------------------------------------------------
// Value logic
// ---------------------------------------------------------------------------

export function isScorable(score) {
  return score?.decision === SCORABLE;
}

// Parse one scorer line, "- Salary: 120000  [+2.50]", into its parts.
// Returns { issue, option, value } with value null if no bracketed number.
export function parseScoreLine(line) {
  const raw = String(line || "").replace(/^\s*-\s*/, "");
  const m = raw.match(/^(.*?):\s*(.*?)\s*(?:\[\s*([+-]?\d+(?:\.\d+)?)\s*\])?\s*$/);
  if (!m) return { issue: raw, option: "", value: null };
  return {
    issue: m[1].trim(),
    option: m[2].trim(),
    value: m[3] !== undefined ? parseFloat(m[3]) : null,
  };
}

// The total and per-issue lines as seen by a particular viewer.
// viewer = { roleName, isProposer }
export function viewerScore(score, viewer = {}) {
  if (!score || !isScorable(score)) return { total: null, lines: [] };
  const { roleName, isProposer } = viewer;
  if (score.totals_by_role && roleName && roleName in score.totals_by_role) {
    return {
      total: score.totals_by_role[roleName],
      lines: score.lines_by_role?.[roleName] || [],
    };
  }
  if (isProposer) {
    return { total: score.total_for_proposer ?? score.total ?? null, lines: score.lines || [] };
  }
  return { total: score.total_for_receiver ?? null, lines: score.lines_for_receiver || [] };
}

// Value of a stored proposal to the viewer (null when the scorer gave none).
export function proposalValue(proposal, viewer) {
  if (!proposal?.score) return null;
  return viewerScore(proposal.score, viewer).total;
}

// "Beats your BATNA" threshold.
export function batnaThreshold(roleRP) {
  return roleRP ?? 0;
}

// A result is submittable when the scorer accepted it and the text hasn't been
// edited since it was scored (an edited offer must be re-calculated).
export function isStale(result, text) {
  return !!result && (result.text || "") !== (text || "").trim();
}

export function canSubmit(result, text) {
  if (!result || result.error) return false;
  if (isStale(result, text)) return false;
  if (!isScorable(result.score)) return false;
  return result.score.proposal_allowed !== false;
}

export function submitErrorMessage(result, text) {
  if (!(text || "").trim()) return "Please describe your proposal, then click Calculate.";
  if (!result || isStale(result, text)) return "Please click Calculate before submitting.";
  if (result.error) return "Scoring failed. Please try Calculate again.";
  if (!isScorable(result.score)) return "The scorer could not score this offer. Please revise it and Calculate again.";
  return "This offer can't be submitted as written.";
}

export function formatValue(value) {
  if (value === null || value === undefined || !isFinite(Number(value))) return "—";
  return Number(value).toFixed(2);
}

// Scorer issue ids are CamelCase ("PersonalBudget", "Non-competeClause");
// render them with spaces.
export function humanizeIssue(issue) {
  return String(issue || "")
    .replace(/_/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .trim();
}

// ---------------------------------------------------------------------------
// Score breakdown — the structured output of the scorer, for one viewer.
// ---------------------------------------------------------------------------

export function ScoreBreakdown({ score, lines, small = false }) {
  const textCls = small ? "text-xs" : "text-sm";
  if (!score) return null;

  const decision = score.decision;
  const scorable = decision === SCORABLE;
  const rejected = decision === REJECTED;

  // Terms the scorer understood. For a scorable offer these are the viewer's
  // lines; for a rejected/clarification offer only the proposer's partial
  // lines exist (and no one else ever sees those, since it can't be submitted).
  const rows = (lines && lines.length ? lines : (score.lines || [])).map(parseScoreLine);

  // Problems, with the issue each one is about where the scorer says so.
  const findings = (score.findings && score.findings.length)
    ? score.findings
    : (score.messages || [score.message]).filter(Boolean).map((message) => ({ message, decision }));
  const missing = score.missing_required || [];
  const novel = score.novel_terms || [];

  const statusCls = scorable
    ? "bg-green-100 text-green-800"
    : rejected ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800";
  const statusText = scorable ? "Scored" : rejected ? "Not scored yet" : "Clarification needed";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wide ${statusCls}`}>
          {statusText}
        </span>
        {score.relative_revision && (
          <span className={`${textCls} text-gray-500 italic`}>
            Applied as a change to your previous offer.
          </span>
        )}
      </div>

      {rows.length > 0 && (
        <div>
          {!scorable && (
            <p className={`${textCls} text-gray-500 mb-1`}>Terms understood so far:</p>
          )}
          <table className={`w-full ${textCls}`}>
            <thead>
              <tr className="text-left text-gray-500 uppercase text-[10px] tracking-wide">
                <th className="py-1 pr-2 font-bold">Issue</th>
                <th className="py-1 pr-2 font-bold">Term</th>
                <th className="py-1 pl-2 font-bold text-right">Value</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-gray-200">
                  <td className="py-1 pr-2 text-gray-700 font-medium align-top">{humanizeIssue(r.issue)}</td>
                  <td className="py-1 pr-2 text-gray-900 align-top">{r.option}</td>
                  <td className={`py-1 pl-2 text-right font-semibold whitespace-nowrap align-top ${
                    r.value === null ? "text-gray-400" : r.value >= 0 ? "text-green-700" : "text-red-600"
                  }`}>
                    {r.value === null ? "—" : `${r.value >= 0 ? "+" : ""}${r.value.toFixed(2)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rows.length === 0 && scorable && (
        <pre className={`whitespace-pre-wrap font-sans ${textCls} text-gray-700`}>
          {score.display_text || "No terms recognised."}
        </pre>
      )}

      {missing.length > 0 && (
        <div className={`${textCls}`}>
          <span className="text-gray-600 font-semibold mr-2">Still needed:</span>
          {missing.map((m) => (
            <span key={m} className="inline-block mr-1 mb-1 px-2 py-0.5 rounded bg-red-50 border border-red-200 text-red-700">
              {humanizeIssue(m)}
            </span>
          ))}
        </div>
      )}

      {!scorable && findings.length > 0 && (
        <ul className={`space-y-1 ${textCls}`}>
          {findings.map((f, i) => {
            const isReject = f.decision === REJECTED;
            return (
              <li key={i} className={`flex gap-2 rounded border p-2 ${
                isReject ? "bg-red-50 border-red-200 text-red-800" : "bg-amber-50 border-amber-200 text-amber-800"
              }`}>
                <span className="shrink-0 font-bold">{isReject ? "✗" : "?"}</span>
                <span>
                  {f.issue && <span className="font-semibold mr-1">{humanizeIssue(f.issue)}:</span>}
                  {f.message}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {score.relative_revision && score.revision_confirmation?.prompt && (
        <p className={`${textCls} text-blue-800 bg-blue-50 border border-blue-200 rounded p-2`}>
          {score.revision_confirmation.prompt}
        </p>
      )}

      {novel.length > 0 && (
        <p className={`${textCls} text-gray-500 italic`}>
          Recorded but not scored: {novel.join(", ")}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scoring calculator — free text in, structured score out.
// ---------------------------------------------------------------------------

export function ScoringCalculator({
  text,
  onTextChange,
  onCalculate,
  calculating = false,
  result = null,        // { requestId, text, score, error }
  roleRP,
  roleName,
  title,
  footer,               // e.g. the Submit Proposal button; rendered next to the value
  placeholder,
  emptyMessage = "Start by entering an idea to see what its value is to you.",
}) {
  const stale = isStale(result, text);
  const score = result?.score;
  const scored = !!result && !result.error && !stale && isScorable(score);
  const { total, lines } = scored ? viewerScore(score, { roleName, isProposer: true }) : { total: null, lines: [] };
  const threshold = batnaThreshold(roleRP);
  const canCalculate = !calculating && (text || "").trim().length > 0 && (!result || stale || result.error);
  const notScored = !!result && !stale && !result.error && !isScorable(score);
  const showResult = !!result && !stale;

  const submitKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canCalculate) {
      e.preventDefault();
      onCalculate();
    }
  };

  return (
    <div className="bg-blue-50 border border-black rounded-lg p-4">
      {title && <h3 className="text-2xl font-bold text-blue-900 mb-4">{title}</h3>}

      <div className="flex gap-4">
        {/* Left third: free-text offer + calculate */}
        <div className="w-1/3 flex-shrink-0 flex flex-col min-w-0">
          <label htmlFor="offer-text" className="block text-xs font-bold text-gray-700 uppercase mb-1">
            Your proposal
          </label>
          <textarea
            id="offer-text"
            value={text}
            onChange={(e) => onTextChange(e.target.value)}
            onKeyDown={submitKeyDown}
            disabled={calculating}
            rows={9}
            placeholder={placeholder || "Describe your offer in your own words, e.g.\nSalary: $70,000 per year\nPersonal budget: $5,000\nStarting date: June 1"}
            className="w-full flex-1 rounded border border-gray-300 bg-white p-3 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 disabled:bg-gray-100 resize-y"
          />
          <div className="flex items-center justify-between mt-2 gap-2">
            <p className="text-xs text-gray-500">
              {calculating
                ? "Scoring your offer…"
                : stale
                  ? "Text changed — calculate again."
                  : notScored
                    ? "Fix the points shown, then calculate again."
                    : ""}
            </p>
            <button
              type="button"
              onClick={onCalculate}
              disabled={!canCalculate}
              className={`px-4 py-2 rounded font-semibold text-sm transition-colors whitespace-nowrap ${
                canCalculate
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "bg-gray-300 text-gray-500 cursor-not-allowed"
              }`}
            >
              {calculating ? (
                <span className="inline-flex items-center gap-2">
                  <span className="inline-block h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  Calculating
                </span>
              ) : "Calculate"}
            </button>
          </div>
        </div>

        {/* Right two thirds: scorer response + value + actions, one panel.
            The label row matches the left column's so both top edges align. */}
        <div className="flex-1 min-w-0 flex flex-col">
          <span className="block text-xs font-bold text-gray-700 uppercase mb-1">What it's worth to you</span>
          <div className="flex-1 bg-white rounded-lg shadow-md p-4 flex flex-col">
          <div className="flex items-start justify-between gap-4 mb-3">
            <div className="min-w-0">
              <h3 className="text-lg font-semibold text-gray-700">Total Value</h3>
              <div className="text-4xl font-bold leading-tight">
                <span className={scored && total !== null ? "text-blue-600" : "text-gray-300"}>
                  {scored && total !== null ? total.toFixed(2) : "-.--"}
                </span>
              </div>
              {scored && total !== null ? (
                <div className={`text-sm font-semibold ${total >= threshold ? "text-green-600" : "text-red-600"}`}>
                  {total >= threshold ? "✓ Beats your BATNA!" : "✗ Below your BATNA"}
                </div>
              ) : (
                <p className="text-xs text-gray-500">
                  {notScored ? "No value until the offer is complete and valid." : "Calculate an offer to see its value."}
                </p>
              )}
            </div>
            {footer && <div className="flex-shrink-0">{footer}</div>}
          </div>

          <div className="border-t border-gray-200 pt-3 flex-1">
            {!showResult && !calculating && (
              <p className="text-sm text-gray-500 text-center py-4">{emptyMessage}</p>
            )}
            {calculating && !showResult && (
              <p className="text-sm text-gray-500 text-center py-4">Scoring your offer…</p>
            )}
            {showResult && (
              <>
                <h4 className="text-xs font-bold text-gray-600 uppercase mb-2">
                  {result.error ? "Scoring error" : "How the scorer read your offer"}
                </h4>
                {result.error ? (
                  <p className="text-sm text-red-600">{result.error}</p>
                ) : (
                  <ScoreBreakdown score={score} lines={lines} />
                )}
              </>
            )}
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Proposal contents — used by the pending card and history list.
// Shows the proposer's own words plus the scorer's breakdown for the viewer.
// ---------------------------------------------------------------------------

export function ProposalDetails({ proposal, viewer, small = false }) {
  const textCls = small ? "text-xs" : "text-sm";
  const { lines } = viewerScore(proposal?.score, viewer);

  return (
    <div className="space-y-3">
      <blockquote className={`border-l-4 border-blue-300 pl-3 whitespace-pre-wrap text-gray-800 ${textCls}`}>
        {proposal?.text || "—"}
      </blockquote>
      {proposal?.score && (
        <ScoreBreakdown score={proposal.score} lines={lines} small={small} />
      )}
    </div>
  );
}
