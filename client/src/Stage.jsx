import {
  usePlayer,
  usePlayers,
  useStage,
  useGame,
} from "@empirica/core/player/classic/react";
import { Loading } from "@empirica/core/player/react";
import React, { useContext, useEffect } from "react";
import { DailyCallContext } from "./App";
//import { InteractiveDemo } from "./components/InteractiveDemo";
import { ReadRole } from "./components/ReadRole";
import { ReadyToNegotiate } from "./components/ReadyToNegotiate";
import { VideoNegotiate } from "./components/VideoNegotiate";

export function Stage({ profileComponent }) {
  const player = usePlayer();
  const players = usePlayers();
  const stage = useStage();
  const game = useGame();
  const { teardownCall } = useContext(DailyCallContext);

  const stageName = stage.get("name");

  // The prep stages show no video, so fully release the Daily call and the local
  // camera/mic here: the recording indicator goes dark and nothing is recorded.
  // VideoChat re-acquires media and rejoins the game room when the negotiation
  // stage mounts it. (This effect must run before any early return below to keep
  // hook order stable.)
  const isPrepStage =
    stageName === "Read Negotiation Role" || stageName === "Ready To Negotiate";
  useEffect(() => {
    if (isPrepStage) teardownCall();
  }, [isPrepStage, teardownCall]);

  // Force submit if game was force-quit
  useEffect(() => {
    if (game.get("forceQuit") === true && !player.stage.get("submit")) {
      player.stage.set("submit", true);
    }
  }, [game.get("forceQuit"), player]);

  // Heartbeat: append a timestamp every 60 seconds
  useEffect(() => {
    const tick = () => {
      const existing = player.get("heartbeat") || [];
      player.set("heartbeat", [...existing, Date.now()]);
    };
    tick(); // record immediately on mount
    const interval = setInterval(tick, 60000);
    return () => clearInterval(interval);
  }, []);

  if (player.stage.get("submit")) {
    if (players.length === 1) {
      return <Loading />;
    }

    return (
      <div className="text-center text-gray-400 pointer-events-none">
        Please wait for other player(s).
      </div>
    );
  }

  // Render component based on stage name
  if (stageName === "Interactive Demo") {
    //return <InteractiveDemo profileComponent={profileComponent} />;
  }

  if (stageName === "Read Negotiation Role") {
    return <ReadRole profileComponent={profileComponent} />;
  }

  if (stageName === "Ready To Negotiate") {
    return <ReadyToNegotiate profileComponent={profileComponent} />;
  }

  if (stageName === "Time To Negotiate") {
    return <VideoNegotiate profileComponent={profileComponent} />;
  }

  // Default fallback
  return (
    <div className="text-center text-gray-400">
      Unknown stage: {stageName}
    </div>
  );
}
