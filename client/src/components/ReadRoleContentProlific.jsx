import React, { useState, useRef } from "react";
import { usePlayer, useGame } from "@empirica/core/player/classic/react";
import { RoleNarrative } from "./RoleNarrative";

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
  const [selectedOptions, setSelectedOptions] = useState({});

  // Handle scroll to show/hide fade
  const handleScroll = () => {
    if (scrollContainerRef.current) {
      const scrollTop = scrollContainerRef.current.scrollTop;
      setShowFade(scrollTop > 10);
    }
  };

  // Calculate current total points
  const calculateTotalPoints = () => {
    return Object.entries(roleScoresheet).reduce((sum, [category]) => {
      const optionIdx = selectedOptions[category] ?? 1; // Default to exclude (index 1)
      return sum + (roleScoresheet[category]?.[optionIdx]?.score || 0);
    }, 0);
  };

  if (!roleName || !roleNarrative || !roleScoresheet) {
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
            Review your narrative carefully to understand your interests and goals. Then examine the scoresheet to see how
            different outcomes affect your final score. During negotiation, work with other participants to find
            mutually beneficial solutions.
          </p><br/>
          <p>
            Your goal is to reach an agreement that maximizes your score based on your role's scoresheet, which is shown below.
          </p><br/>
          <p>
            Your bonus will be equal to the points you get!  1 point = $1 dollar.
          </p>
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
          {(roleBATNA || roleRP !== undefined) && (
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
          )}

          {/* 3. Scoring Section */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="text-2xl font-bold text-blue-900 mb-4">Scoring</h3>

            {/* Table Header */}
            <div className="flex items-center px-4 py-2 mb-1">
              <span className="w-8"></span> {/* Checkbox space */}
              <span className="text-xs font-bold text-gray-700 uppercase flex-shrink-0 w-[140px]">
                Feature
              </span>
              <span className="text-xs font-bold text-gray-700 uppercase flex-shrink-0 w-[80px] text-center">
                Points
              </span>
              <span className="text-xs font-bold text-gray-700 uppercase flex-1 ml-4">
                Reason
              </span>
            </div>

            {/* Main content area with rows and total points side by side */}
            <div className="flex gap-6">
              {/* Left side: Scoresheet rows (2/3 width) */}
              <div className="flex-[9] space-y-2">
                {Object.entries(roleScoresheet)
                  .sort(([, optionsA], [, optionsB]) => optionsB[0].score - optionsA[0].score)
                  .map(([category, options]) => {
                  const includeOption = options[0];
                  const isChecked = selectedOptions[category] === 0;

                  return (
                    <div key={category} className="flex items-center bg-white rounded px-4 py-2.5 border border-blue-300">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={(e) => {
                          setSelectedOptions(prev => {
                            if (e.target.checked) {
                              return { ...prev, [category]: 0 };
                            } else {
                              return { ...prev, [category]: 1 };
                            }
                          });
                        }}
                        className="w-5 h-5 text-blue-600 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer mr-3"
                      />
                      <span className="text-sm font-semibold text-gray-800 flex-shrink-0 w-[140px]">
                        {category.replace(/_/g, " ")}
                      </span>
                      <span className={`text-base font-bold flex-shrink-0 w-[80px] text-center ${
                        isChecked
                          ? (includeOption.score >= 0 ? 'text-blue-600' : 'text-red-600')
                          : 'text-gray-400'
                      }`}>
                        {includeOption.score >= 0 ? '+' : ''}{includeOption.score} pts
                      </span>
                      <span className="text-sm text-gray-600 flex-1 ml-4">
                        {includeOption.reason}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Right side: Total Points (1/3 width) */}
              <div className="flex-[4] flex flex-col items-center justify-start">
                <div className="text-center bg-white rounded-lg p-6 shadow-md w-full">
                  <h3 className="text-lg font-semibold text-gray-700 mb-2">Total Points</h3>
                  <div className="text-5xl font-bold mb-4">
                    <span className="text-blue-600">
                      {calculateTotalPoints().toFixed(2)}
                    </span>
                  </div>
                  {roleRP !== undefined && (
                    <div className={`text-sm font-semibold ${
                      calculateTotalPoints() >= roleRP ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {calculateTotalPoints() >= roleRP ? '✓ Beats your BATNA!' : '✗ Below your BATNA'}
                    </div>
                  )}
                </div>

                <div className="mt-6 w-full">
                  <button
                    onClick={() => setSelectedOptions({})}
                    className="w-full px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors text-sm font-medium"
                  >
                    Reset All
                  </button>
                </div>
              </div>
            </div>
          </div>

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
