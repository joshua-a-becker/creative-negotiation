import React, { useState } from "react";
import { Button } from "../components/Button.jsx";
import { useGame } from "@empirica/core/player/classic/react";

export function Instructions({ next }) {
  const game = useGame();
  const [section, setSection] = useState(1);
  const [visibleCount, setVisibleCount] = useState(1);

  const playerCount = game.get("treatment")?.playerCount || 3;
  const otherPlayers = playerCount - 1;

  const section1 = [
    <>In this activity, you must reach agreement with <span className="font-bold">{otherPlayers} other player{otherPlayers !== 1 ? "s" : ""}</span> on the terms of a hypothetical job offer.</>,
    <>You will be assigned a role with private information about which terms give you points, with some terms giving <span className="font-bold text-red-600">negative points</span>.</>,
    <>You make proposals <span className="font-bold">in your own words</span>. The system reads each proposal and tells you what it is worth to you before you submit it.</>,
    <>You will seek to reach agreement on a proposal whose total value to you is <span className="font-bold text-green-600">positive</span>.</>,
    <>After the activity, you will receive a <span className="font-bold">bonus payment</span> equal to the number of points you earn (1 point = £1.00).</>,
  ];

  const section2 = [
    <>You will be provided with a platform for <span className="font-bold">making and voting</span> on proposals. You may need to vote on many proposals to reach agreement.</>,
    <>You can make proposals, vote on others proposals, and modify proposals.</>,
    <>You can make, modify, and vote on <span className="font-bold">as many proposals as you need</span> to reach agreement.</>,
    <>When a proposal passes with <span className="font-bold">100% yes votes</span>, you will have the option to finalize that proposal or keep looking for a better option.</>,
    <>You will now complete a short practice negotiation about booking a community event venue, to show how the app works.</>,
  ];

  const bullets = section === 1 ? section1 : section2;
  const maxBullets = Math.max(section1.length, section2.length);
  const allVisible = visibleCount >= bullets.length;

  function handleNext() {
    if (!allVisible) {
      setVisibleCount(visibleCount + 1);
    } else if (section === 1) {
      setSection(2);
      setVisibleCount(1);
    } else {
      next();
    }
  }

  let buttonLabel = "Next";
  if (allVisible && section === 1) buttonLabel = "Next Page";
  if (allVisible && section === 2) buttonLabel = "Continue";

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full p-8 md:p-12">
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2 tracking-wide uppercase">
            Instructions
          </h1>
          <div className="w-24 h-1 bg-indigo-600 mx-auto rounded-full"></div>
        </div>

        <div className="p-2" style={{ minHeight: `${maxBullets * 4.5}rem` }}>
          <ul className="space-y-5">
            {bullets.slice(0, visibleCount).map((text, i) => (
              <li key={`${section}-${i}`} className="flex items-start gap-3">
                <span className="text-indigo-600 text-xl mt-0.5 flex-shrink-0 font-bold">&rsaquo;</span>
                <p className="text-lg leading-relaxed text-gray-800">{text}</p>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-8 flex items-center justify-between">
          <span className="text-sm text-gray-400">
            Page {section} of 2
          </span>
          <Button handleClick={handleNext} autoFocus>
            <span className="text-lg px-4">{buttonLabel}</span>
          </Button>
        </div>
      </div>
    </div>
  );
}
