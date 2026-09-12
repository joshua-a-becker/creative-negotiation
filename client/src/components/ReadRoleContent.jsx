import React, { useState, useRef } from "react";
import { usePlayer, useGame } from "@empirica/core/player/classic/react";
import { RoleNarrative } from "./RoleNarrative";
import { ScoringCalculator } from "./negotiationDisplay";
import { useOfferScoring } from "./useOfferScoring";

export function ReadRoleContent({ profileComponent }) {
  const player = usePlayer();
  const game = useGame();
  const tips = game.get("tips") || "";
  const roleName = player.get("roleName");
  const roleNarrative = player.get("roleNarrative");
  const roleScoresheet = player.get("roleScoresheet");
  const roleBATNA = player.get("roleBATNA");
  const roleRP = player.get("roleRP");
  const [showFade, setShowFade] = useState(false);
  const scrollContainerRef = useRef(null);
  const { offerText, setOfferText, calculating, scoreResult, calculate } = useOfferScoring({ role: roleName });

  // Handle scroll to show/hide fade
  const handleScroll = () => {
    if (scrollContainerRef.current) {
      const scrollTop = scrollContainerRef.current.scrollTop;
      setShowFade(scrollTop > 10);
    }
  };

  if (!roleName || !roleNarrative) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <p className="text-gray-500">Loading your role...</p>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col bg-gray-50">
      {/* Profile bar at top - sticky */}
      <div className="sticky top-0 z-20 bg-gray-50">
        {profileComponent}
      </div>

      {/* Fade overlay at top - only show when scrolled, positioned below profile border */}
      {showFade && (
        <div className="absolute top-[3.6rem] left-0 right-0 h-8 bg-gradient-to-b from-gray-50 to-transparent pointer-events-none z-10"></div>
      )}

      {/* Main content */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto relative"
      >
        <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">

        {/* Prominent header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg shadow-lg p-8 text-center mb-8">
          <h1 className="text-4xl font-bold tracking-tight">
            It's Time to Prepare for Your Negotiation
          </h1>
        </div>

        {/* Instructions at top */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-8">
          <h2 className="text-xl font-bold text-blue-900 mb-3">How Negotiations Activities Work</h2>
          <p className="text-gray-700 leading-relaxed">
            This activity is based off a standard MBA classroom exercise.
          </p><br/>
          <p>
            You have been assigned a specific role with unique objectives and priorities.
          </p><br/>
          <p>
            Review your narrative below to understand your interests, goals, and points. During the negotiation, work together with the other participants to find a deal that everyone will accept.
          </p><br/>
          <ul className="list-disc list-outside pl-5 space-y-2 mt-2">
            <li><strong>What determines how much I earn?</strong> Points earned from any agreement become your bonus on Prolific (1 point = £1.00). No agreement means no bonus.</li>
            <li><strong>How can we reach an agreement?</strong> All three people must accept the same final proposal, which must be submitted officially in the system. A verbal agreement is not enough! You may need to submit and vote on multiple proposals to reach agreement.</li>
            <li><strong>What happens if we don't reach an agreement?</strong> If your group does not reach an agreement, everyone will keep working from home. This outcome is worth 0 points. (No bonus.)</li>
            <li><strong>What if my group is incomplete?</strong> If someone quits or stops responding, you may end the game early by clicking the 'quit' button.</li>
            <li><strong>How should I prepare?</strong> Get into character! Think about how you would introduce yourself, what you want, and how you might advocate for your best outcome.</li>
          </ul>
        </div>

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

          {/* 3. Practice scoring: try offers in your own words, see their value */}
          <ScoringCalculator
            title="Scoring Calculator"
            text={offerText}
            onTextChange={setOfferText}
            onCalculate={calculate}
            calculating={calculating}
            result={scoreResult}
            roleRP={roleRP}
            roleName={roleName}
            emptyMessage="Try out an offer to see what it would be worth to you. Nothing you type here is shared with the other side."
          />

          {/* 4. Tips on Negotiation Section */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">
              Tips on Negotiation
            </h3>
            <div className="prose prose-gray max-w-none" dangerouslySetInnerHTML={{ __html: tips }} />
          </div>
        </div>
      </div>
    </div>
  );
}
