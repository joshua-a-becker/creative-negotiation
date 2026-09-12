import React, { useState, useEffect, useContext } from "react";
import { Button } from "../components/Button.jsx";
import { MediaPermissionGate } from "../components/MediaPermissionGate.jsx";
import { DailyCallContext } from "../App.jsx";

import { usePlayer } from "@empirica/core/player/classic/react";

export function DisplayNameEntry({ next }) {
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const { setMediaStream } = useContext(DailyCallContext);

  const player = usePlayer();

  const urlParams = new URLSearchParams(window.location.search);

  // Extract all URL parameters except participantKey
  for (const [key, value] of urlParams.entries()) {
    if (key !== "participantKey") {
      player.set(key, value);
      console.log("setting " + key + " : " + value)
    }
  }


  // Get stored device IDs if they exist (for page refresh)
  const storedVideoDeviceId = player?.get("videoDeviceId");
  const storedAudioDeviceId = player?.get("audioDeviceId");

  console.log("student ID: " + player.get("studentId"))

  const handleSubmit = () => {
    if (!displayName.trim()) {
      setError("Please enter a display name");
      return;
    }

    if (displayName.trim().length < 2) {
      setError("Display name must be at least 2 characters");
      return;
    }

    if (displayName.trim().length > 20) {
      setError("Display name must be 20 characters or less");
      return;
    }

    // Save display name to player data
    player.set("displayName", displayName.trim());
    next();
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  // Handle permissions granted with device IDs
  const handlePermissionsGranted = (stream, videoDeviceId, audioDeviceId, audioEnabled, videoEnabled) => {
    setMediaStream(stream);

    // Store device IDs in player data for later use
    if (videoDeviceId) {
      player.set("videoDeviceId", videoDeviceId);
    }
    if (audioDeviceId) {
      player.set("audioDeviceId", audioDeviceId);
    }

    // Persist the mic/camera choice from the gate so it flows into the game.
    // When the gate provides an explicit choice, honor it; otherwise seed a
    // default only when unset (never clobbering a prior choice). Matches VideoChat's
    // history format, so VideoChat's own default-write becomes a no-op fallback.
    if (audioEnabled !== undefined) {
      player.set("audioEnabled", audioEnabled);
      player.set("audioHistory", [[audioEnabled ? "on" : "off", Date.now()]]);
    } else if (player.get("audioEnabled") === undefined) {
      player.set("audioEnabled", true);
      player.set("audioHistory", [["on", Date.now()]]);
    }
    if (videoEnabled !== undefined) {
      player.set("videoEnabled", videoEnabled);
      player.set("videoHistory", [[videoEnabled ? "on" : "off", Date.now()]]);
    } else if (player.get("videoEnabled") === undefined) {
      player.set("videoEnabled", true);
      player.set("videoHistory", [["on", Date.now()]]);
    }
  };

  return (
    <MediaPermissionGate
      onPermissionsGranted={handlePermissionsGranted}
      storedVideoDeviceId={storedVideoDeviceId}
      storedAudioDeviceId={storedAudioDeviceId}
      storedAudioEnabled={player?.get("audioEnabled")}
      storedVideoEnabled={player?.get("videoEnabled")}
    >
      <div className="mt-3 sm:mt-5 p-10 max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold text-gray-900 mb-6 text-center">
          Welcome to the Study!
        </h2>

        <div className="text-sm text-gray-700 space-y-4 mb-8">
          <p>
            Before we begin, we'd like you to choose a display name that will be visible to your teammates during the video calls.
          </p>
          <p>
            <strong>Please enter a display name, e.g. your first name.</strong>
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <label htmlFor="displayName" className="block text-sm font-medium text-gray-700 mb-2">
              Display Name
            </label>
            <input
              type="text"
              id="displayName"
              value={displayName}
              onChange={(e) => {
                setDisplayName(e.target.value);
                setError(""); // Clear error when user types
              }}
              onKeyPress={handleKeyPress}
              placeholder="Enter your display name..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              maxLength={20}
              autoFocus
            />
            {error && (
              <p className="mt-1 text-sm text-red-600">{error}</p>
            )}
          </div>

          <div className="text-center pt-4">
            <Button handleClick={handleSubmit}>
              Continue
            </Button>
          </div>
        </div>
      </div>
    </MediaPermissionGate>
  );
}