import {
  usePlayer,
  useRound,
  useStage,
} from "@empirica/core/player/classic/react";
import React from "react";
import { Avatar } from "./components/Avatar";
import { Timer } from "./components/Timer";

export function Profile() {
  const player = usePlayer();
  const round = useRound();
  const stage = useStage();

  const score = player.get("score") || 0;

  // Check for dev mode or devKey URL parameter
  const isDevMode = process.env.NODE_ENV === 'development' ||
    new URLSearchParams(window.location.search).get('devKey') === 'oandi';

  // Dev mode skip stage handler
  const handleSkipStage = () => {
    player.stage.set("submit", true);
  };

  // Side columns size to content (left is empty, right is the dev-only skip
  // button) so the timer gets the full remaining width of the narrow panel.
  return (
    <div className="w-full px-3 py-0.5 text-gray-500 grid grid-cols-[auto_1fr_auto] items-center border-b border-gray-300">
      <div className="leading-tight">
        <div className="text-empirica-500 font-medium">
          {/*stage ? stage.get("name") : ""*/}
        </div>
      </div>

      <Timer />

     <div className="flex space-x-3 items-center justify-end">
        {/* Dev-only Skip Stage button */}
        {isDevMode && (
          <button
            onClick={handleSkipStage}
            className="text-white bg-red-600 px-1.5 py-0 text-xs leading-tight font-medium rounded hover:bg-red-700 transition-colors border border-red-700"
            title="Skip stage (dev only)"
          >
            x
          </button>
        )}
      </div>
    </div>
  );
}
