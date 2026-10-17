import React, { useState, useEffect } from "react";
import { usePlayer, useGame } from "@empirica/core/player/classic/react";
import { RoleNarrative } from "./RoleNarrative";
import { ScoringCalculator } from "./negotiationDisplay";
import { isTableMode, TableScoringCalculator } from "./tableScoring";
import { useOfferScoring } from "./useOfferScoring";
import { NotesBox } from "./NotesBox";

export function ReadRoleContent({ profileComponent }) {
  const player = usePlayer();
  const game = useGame();
  const tips = game.get("tips") || "";
  const readRoleInstructions = game.get("readRoleInstructions") || "";
  const roleName = player.get("roleName");
  const roleNarrative = player.get("roleNarrative");
  const roleBATNA = player.get("roleBATNA");
  const roleRP = player.get("roleRP");
  const tableMode = isTableMode(game.get("treatment"));
  const roleScoresheet = player.get("roleScoresheet");
  const [selection, setSelection] = useState({}); // table-mode practice calculator
  const [showFade, setShowFade] = useState(false);
  const [moreBelow, setMoreBelow] = useState(false);
  const { offerText, setOfferText, calculating, scoreResult, calculate } = useOfferScoring({ role: roleName });

  // The page scrolls as a whole; show the fade under the profile bar once scrolled.
  useEffect(() => {
    // ...and one at the bottom of the window while there's more page below.
    const handleScroll = () => {
      setShowFade(window.scrollY > 10);
      const doc = document.documentElement;
      setMoreBelow(window.scrollY + window.innerHeight < doc.scrollHeight - 4);
    };
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleScroll);
    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleScroll);
    };
  }, [roleNarrative, tips, scoreResult, calculating, selection]);

  if (!roleName || !roleNarrative) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <p className="text-gray-500">Loading your role...</p>
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen bg-gray-50">
      {/* Profile bar at top - sticky */}
      <div className="sticky top-0 z-20 bg-gray-50">
        {profileComponent}
      </div>

      {/* Fade overlay at top - only show when scrolled, positioned below profile border */}
      {showFade && (
        <div className="fixed top-[3.6rem] left-0 right-[22rem] h-8 bg-gradient-to-b from-gray-50 to-transparent pointer-events-none z-10"></div>
      )}

      {/* Main content scrolls with the page; right padding leaves room for the fixed notes column */}
      {moreBelow && (
        <div className="fixed bottom-0 left-0 right-[22rem] h-16 bg-gradient-to-t from-gray-50 to-transparent pointer-events-none z-10"></div>
      )}

      <div className="pr-[22rem]">
        <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">

        {/* Prominent header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg shadow-lg p-8 text-center mb-8">
          <h1 className="text-4xl font-bold tracking-tight">
            It's Time to Prepare for Your Negotiation
          </h1>
        </div>

        {/* Instructions at top: readrole_instructions (HTML) from the role JSON; hidden when absent */}
        {readRoleInstructions.trim() && (
          <>
            {/* prose gives the first heading a top margin; the box's padding is enough */}
            <style>{`.readrole-instructions > :first-child { margin-top: 0; } .readrole-instructions > :last-child { margin-bottom: 0; }`}</style>
            <div
              className="readrole-instructions bg-blue-50 border border-blue-200 rounded-lg p-6 mb-8 prose prose-gray max-w-none"
              dangerouslySetInnerHTML={{ __html: readRoleInstructions }}
            />
          </>
        )}

          {/* 1. Narrative Section */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">
              Your Role
            </h3>
            <div className="prose prose-gray max-w-none text-gray-700 leading-relaxed">
              <RoleNarrative>{roleNarrative}</RoleNarrative>
            </div>
          </div>

          {/* 2. What if I don't reach agreement? (BATNA) */}
          {/*(roleBATNA || roleRP !== undefined) && (
            <div className="bg-white rounded-lg shadow-sm p-4">
              <h4 className="text-base font-bold text-gray-900 mb-2">
                What if I don't reach agreement?
              </h4>
              {roleBATNA && (
                <p className="text-sm text-gray-700 mb-1">{roleBATNA}</p>
              )}
              {roleRP !== undefined && (
                <p className="text-sm text-gray-700">
                  <br/>If you don't reach agreement, you will earn <span className="font-bold">{roleRP} points</span>.
                </p>
              )}
            </div>
          )*/}

          {/* 3. Practice scoring: try offers, see their value */}
          {tableMode ? (
            <TableScoringCalculator
              title="Scoring Calculator"
              roleScoresheet={roleScoresheet}
              selection={selection}
              onSelectionChange={setSelection}
              roleRP={roleRP}
            />
          ) : (
            <ScoringCalculator
              title="Scoring Calculator"
              text={offerText}
              onTextChange={setOfferText}
              onCalculate={calculate}
              calculating={calculating}
              result={scoreResult}
              roleRP={roleRP}
              roleName={roleName}
              placeholder={game.get("treatment")?.mainPlaceholderText}
              emptyMessage="Try out an offer to see what it would be worth to you. Nothing you type here is shared with the other side."
            />
          )}

          {/* 4. Tips on Negotiation Section */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">
              Tips on Negotiation
            </h3>
            <div className="prose prose-gray max-w-none" dangerouslySetInnerHTML={{ __html: tips }} />
          </div>
        </div>
      </div>

      {/* Notes column: fixed in place while the page scrolls */}
      <aside className="fixed right-8 top-[5.6rem] bottom-8 w-80 z-10 bg-white rounded-lg shadow-md p-4 flex flex-col">
        <h3 className="text-lg font-bold text-gray-900 mb-2">Your Notes</h3>
        <p className="text-xs text-gray-500 mb-3">Your notes will still be here during the negotiation.</p>
        <NotesBox className="flex-1" />
      </aside>
    </div>
  );
}
