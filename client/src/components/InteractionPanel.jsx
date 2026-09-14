import React from "react";
import { VideoChat } from "./VideoChat";

export function InteractionPanel({ profileComponent }) {
  return (
    <div className="w-full h-full flex flex-col bg-gray-300 px-1 py-6">
      {/* Floating white panel with profile and video */}
      <div className="flex-1 bg-white rounded-lg shadow-md overflow-hidden flex flex-col">
        {/* Profile bar at top */}
        {profileComponent}

        {/* Video fills remaining space */}
        <div className="flex-1 overflow-hidden px-1">
          <VideoChat />
        </div>
      </div>
    </div>
  );
}
