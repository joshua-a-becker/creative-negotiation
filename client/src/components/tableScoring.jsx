// ---------------------------------------------------------------------------
// Table-based ("determinate") scoring — the standard negotiation setup, as an
// alternative to the free-text python scorer (negotiationDisplay.jsx).
// Ported from workshop-app's multiple_choice table.
//
// Selected by the treatment factor scoringMode: "table". Each role's
// determinatescoretable (role JSON) is stored on the player as roleScoresheet:
//   { Issue: [{ option, score }, …], … }
// Options are listed in the same order for every role, so a proposal stores
// the chosen option's index per issue ({ Issue: optionIndex }) and each player
// values it against their own sheet. Keep tableValue in sync with
// proposalValueForPlayer in server/src/callbacks.js.
// ---------------------------------------------------------------------------

import React from "react";
import { batnaThreshold, formatValue } from "./negotiationDisplay";

// scoringMode has no default: a treatment must set it to "table" or
// "freetext", and anything else is a misconfiguration we fail loudly on.
export const SCORING_MODES = ["table", "freetext"];

export function isTableMode(treatment) {
  const mode = treatment?.scoringMode;
  if (!SCORING_MODES.includes(mode)) {
    throw new Error(`Treatment factor scoringMode must be "table" or "freetext" (got ${JSON.stringify(mode)})`);
  }
  return mode === "table";
}

// Every issue has an option chosen.
export function tableComplete(roleScoresheet, selection) {
  return Object.keys(roleScoresheet || {}).every((issue) => {
    const idx = selection?.[issue];
    return idx !== undefined && idx !== null;
  });
}

// Value of a selection / proposal's options. Unchosen issues contribute nothing.
export function tableValue(roleScoresheet, selection) {
  return Object.entries(roleScoresheet || {}).reduce((sum, [issue, options]) => {
    const idx = selection?.[issue];
    if (idx === undefined || idx === null) return sum;
    return sum + (options?.[idx]?.score || 0);
  }, 0);
}

// The `options` payload stored on a proposal: one option index per issue.
export function buildTableOptions(roleScoresheet, selection) {
  const options = {};
  Object.keys(roleScoresheet || {}).forEach((issue) => {
    options[issue] = selection[issue];
  });
  return options;
}

const fmtScore = (score) => `${score >= 0 ? "+" : ""}${score}`;

function ChoiceTableHeader() {
  return (
    <div className="flex items-center px-3 py-1">
      <span className="text-xs font-bold text-gray-700 uppercase flex-shrink-0 w-[120px]">Issue</span>
      <span className="text-xs font-bold text-gray-700 uppercase flex-1">Option</span>
      <span className="text-xs font-bold text-gray-700 uppercase flex-shrink-0 w-[80px] text-right">Value</span>
    </div>
  );
}

// One block per issue, one radio row per option.
function ChoiceTableRows({ roleScoresheet, selection = {}, onSelectionChange }) {
  return (
    <>
      {Object.entries(roleScoresheet).map(([issue, options]) => {
        const idx = selection[issue];
        return (
          <div key={issue} className="flex bg-white rounded border border-blue-300">
            <div className="flex-shrink-0 w-[120px] px-3 py-1 text-sm font-semibold text-gray-800 border-r border-gray-100">
              {issue}
            </div>
            <div className="flex-1 divide-y divide-gray-100">
              {options.map((opt, i) => {
                const isChecked = idx === i;
                return (
                  <label
                    key={i}
                    className={`flex items-center px-3 py-1 cursor-pointer hover:bg-blue-50 ${isChecked ? "bg-blue-50" : ""}`}
                  >
                    <span className={`text-sm flex-1 ${isChecked ? "font-semibold text-gray-900" : "text-gray-800"}`}>
                      {opt.option}
                    </span>
                    <span className="flex items-center justify-end flex-shrink-0 w-[80px]">
                      <input
                        type="radio"
                        name={`mc-table-${issue}`}
                        checked={isChecked}
                        onChange={() => onSelectionChange({ ...selection, [issue]: i })}
                        className="w-4 h-4 text-blue-600 focus:ring-2 focus:ring-blue-500 cursor-pointer mr-2"
                      />
                      <span className={`text-sm font-bold w-[32px] text-center ${isChecked ? "text-blue-600" : "text-gray-400"}`}>
                        {fmtScore(opt.score)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}
    </>
  );
}

// Calculator (blue box): the payoff table with one choice per issue, plus the
// live total and a footer (e.g. Submit Proposal) beside it.
export function TableScoringCalculator({
  roleScoresheet,
  selection = {},
  onSelectionChange,
  roleRP,
  title,
  footer,
}) {
  const complete = tableComplete(roleScoresheet, selection);
  const value = tableValue(roleScoresheet, selection);
  const threshold = batnaThreshold(roleRP);

  // No table for this role (e.g. the role JSON has no determinatescoretable).
  if (!roleScoresheet || Object.keys(roleScoresheet).length === 0) {
    return (
      <div className="bg-blue-50 border border-black rounded-lg p-4">
        {title && <h3 className="text-2xl font-bold text-blue-900 mb-4">{title}</h3>}
        <p className="text-sm text-red-600">No scoring table is available for your role.</p>
      </div>
    );
  }

  return (
    <div className="bg-blue-50 border border-black rounded-lg p-4">
      {title && <h3 className="text-2xl font-bold text-blue-900 mb-4">{title}</h3>}

      <div className="flex gap-4">
        <div className="flex-1 min-w-0">
          <ChoiceTableHeader />
          <div className="space-y-1.5">
            <ChoiceTableRows
              roleScoresheet={roleScoresheet || {}}
              selection={selection}
              onSelectionChange={onSelectionChange}
            />
          </div>
        </div>

        <div className="flex-shrink-0 w-[180px] flex flex-col pt-7">
          <div className="text-center bg-white rounded-lg p-4 shadow-md w-full">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Total Value</h3>
            <div className="text-4xl font-bold mb-3">
              <span className={complete ? "text-blue-600" : "text-gray-300"}>
                {complete ? formatValue(value) : "-.--"}
              </span>
            </div>
            {complete ? (
              <div className={`text-sm font-semibold ${value >= threshold ? "text-green-600" : "text-red-600"}`}>
                {value >= threshold ? "✓ Beats your best alternative!" : "✗ Below your best alternative"}
              </div>
            ) : (
              <p className="text-xs text-gray-500">Choose an option for every issue.</p>
            )}
          </div>
          {footer && <div className="mt-4 w-full flex justify-center">{footer}</div>}
        </div>
      </div>
    </div>
  );
}

// Proposal contents for the pending card and history: each issue's chosen
// option and what it's worth to the viewer.
export function TableProposalDetails({ roleScoresheet, proposal, small = false }) {
  const textCls = small ? "text-xs" : "text-sm";
  return (
    <div className="space-y-1">
      {Object.entries(roleScoresheet || {}).map(([issue, options]) => {
        const chosen = options?.[proposal?.options?.[issue]];
        return (
          <div key={issue} className={`flex items-center ${textCls}`}>
            <span className="text-gray-700 font-medium mr-1">{issue}:</span>
            <span className="text-gray-900">{chosen ? chosen.option : "—"}</span>
            {chosen && (
              <span className="ml-2 text-gray-500">({fmtScore(chosen.score)})</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
