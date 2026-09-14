import { NoGameExitStep } from "./intro-exit/NoGameExitStep.jsx";
import { GameTerminatedExitStep } from "./intro-exit/GameTerminatedExitStep.jsx";
import Finished from "./intro-exit/Finished.jsx";
import { EmpiricaClassic } from "@empirica/core/player/classic";
import { EmpiricaContext } from "@empirica/core/player/classic/react";
import { EmpiricaMenu, EmpiricaParticipant } from "@empirica/core/player/react";
import React, { useState, createContext, useEffect, useRef, useMemo, useCallback } from "react";
import { Game } from "./Game";
import { CustomLobby } from "./intro-exit/CustomLobby";
import { DisplayNameEntry } from "./intro-exit/DisplayNameEntry.jsx";
import { AutoPlayerIdForm } from "./intro-exit/AutoPlayerIdForm.jsx";
import CustomConsent from './intro-exit/CustomConsent.jsx';
import { Demo } from './intro-exit/Demo.jsx';
import { Instructions } from './intro-exit/Instructions.jsx';
import { AttentionCheck } from './intro-exit/AttentionCheck.jsx';
import { NegotiationOutcome } from './intro-exit/NegotiationOutcome.jsx';
import { BatchFullExitStep } from './intro-exit/BatchFullExitStep.jsx';
import {FollowupQuestion} from './intro-exit/FollowupQuestion.jsx';
import DailyIframe from "@daily-co/daily-js";
import { stopAllTrackedStreams } from "./mediaTracks";

// Create context for Daily.co call management (includes media stream)
export const DailyCallContext = createContext(null);

// Generate participant key - uses studentId from URL if present, otherwise random string
function generateParticipantKey() {
  const urlParams = new URLSearchParams(window.location.search);
  const studentId = urlParams.get("studentId");

  if (studentId) {
    // Format today's date as YYYYMMDD
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    const dateStr = `${year}${month}${day}`;

    return `${studentId}_${dateStr}`;
  }

  // Fallback to random 20-character alphanumeric string
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < 20; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export default function App() {
  const urlParams = new URLSearchParams(window.location.search);

  // Generate random participantKey if missing and devKey is "oandi"
  let playerKey = urlParams.get("participantKey") || "";
  const devKey = urlParams.get("devKey") || "";

  // If studentId is present, generate participantKey from it
  const studentId = urlParams.get("studentId");
  if (!playerKey && studentId) {
    playerKey = generateParticipantKey();
    urlParams.set("participantKey", playerKey);
    const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
    window.history.replaceState({}, "", newUrl);
  }

  console.log(devKey)
  if (!playerKey && devKey === "oandi") {
    // Generate 15 digit random alphanumeric string
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    playerKey = Array.from({ length: 15 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
    console.log("Generated random participantKey:", playerKey);

    // Add the generated participantKey to the URL
    urlParams.set("participantKey", playerKey);
    const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
    window.history.replaceState({}, "", newUrl);
  }

  // If still no participantKey, show invalid URL page
  if (!playerKey) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-100">
        <div className="text-center p-8 bg-white rounded-lg shadow-lg max-w-md">
          <h1 className="text-3xl font-bold text-red-600 mb-4">Invalid URL</h1>
          <p className="text-gray-700 mb-2">
            We're sorry, you have reached this page via an invalid URL.  Please contact the study administrator for more information.
          </p>
        </div>
      </div>
    );
  }


  const { protocol, host } = window.location;
  const url = `${protocol}//${host}/query`;

  // Daily.co call state management
  const [mediaStream, setMediaStream] = useState(null);
  const callObjectRef = useRef(null);
  const [callJoinData, setCallJoinData] = useState(null);
  const [hasJoinedCall, setHasJoinedCall] = useState(false);
  const participantTracksRef = useRef({});

  const [callState, setCallState] = useState({
    remoteStreams: {},
    participantNames: {},
    participantRepStatus: {},
    participantVideoStates: {},
    participantAudioStates: {},
    isRecording: false,
    isTranscribing: false,
    localVideoTrack: null,
  });

  // Track audio/video enabled state and VideoChat mount state
  const [isAudioEnabled, setIsAudioEnabled] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(false);
  const [isVideoChatMounted, setIsVideoChatMounted] = useState(false);
  // Authoritative override: when true, force mic + camera off regardless of the
  // per-toggle state (used by the welcome modal so it wins the mount-time race
  // with VideoChat re-asserting the player's saved state).
  const [mediaLocked, setMediaLocked] = useState(false);

  // Use refs for state that event handlers need to access
  const callStateRef = useRef(callState);
  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  function introSteps({ game, player }) {

    // console.log("game")
    console.log("batchFullEndingMessage")
    // console.log(game)
    player.set("batchFullEndingMessage", game?.get("treatment")?.batchFullEndingMessage);

    // convenience function
    const skipIntro = urlParams.get("skipIntro");
    
    
    const introSteps = []

    if (skipIntro == "T") {
      const randomAnimal = ["lion","tiger","bear","elephant","giraffe","zebra","monkey","panda","kangaroo","wolf"][Math.floor(Math.random()*10)];

      const displayName = player.get("displayName") ?? randomAnimal;

      player.set("displayName", displayName);

      return []
    }

    // CustomConsent is now a multi-page flow (Introduction + Time Commitment +
    // Consent) with its own page-progress persistence, so the first standalone
    // intro step after it is Instructions.
    introSteps.push(Instructions)
    introSteps.push(AttentionCheck)
    introSteps.push(Demo)
    introSteps.push(DisplayNameEntry)

    return introSteps;
  }

  function exitSteps({ game, player }) {
    const endedReason = player?.get("ended");
    console.log("Ended reason: " + endedReason)
    // Check if player failed to be assigned to a game
    if (endedReason === "game terminated") {
      return [GameTerminatedExitStep];
    }

    if (endedReason === "no more games") {
      // Batch hit capacity — all slots filled
      return [BatchFullExitStep];
    }

    if (["lobby timed out", "No games available", "game failed"].includes(endedReason)) {
      // Return different exit steps for players who didn't get into a game
      return [NoGameExitStep];
    }

    return [FollowupQuestion, NegotiationOutcome];
  }
  


  // Daily.co call initialization and joining
  // IMPORTANT: This effect joins the call ONCE and only once per App instance
  // hasJoinedCall is never reset to false - the call persists across VideoChat mount/unmount
  // This ensures the call stays connected as users navigate between stages
  useEffect(() => {
    console.log("UPDATED-2026-05-29")
    // Wait for all required data before joining
    if (!mediaStream || !callJoinData || hasJoinedCall) {
      return;
    }

    const { roomUrl, meetingToken, displayName, participantIdentifier } = callJoinData;

    if (!roomUrl || !meetingToken) {
      return;
    }

    // console.log("App.jsx: All data available, initializing Daily.co call");
    // console.log("RoomUrl:", roomUrl, "Token:", meetingToken ? "present" : "absent", "DisplayName:", displayName);

    // Clean up any existing instances first
    const existingCall = DailyIframe.getCallInstance();
    if (existingCall) {
      // console.log("Destroying existing Daily call object before creating new one.");
      try {
        existingCall.destroy();
      } catch (e) {
        console.error("Error destroying existing call:", e);
      }
    }

    // Async initialization function
    const initializeCall = async () => {
      // Extract media tracks
      let audioTrack = null;
      let videoTrack = null;

      if (mediaStream) {
        [audioTrack] = mediaStream.getAudioTracks();
        [videoTrack] = mediaStream.getVideoTracks();
        // console.log("Media tracks retrieved - Audio:", audioTrack, "Video:", videoTrack);
      } else {
        console.error("No media stream found");
        return;
      }

      // Create fresh call object
      // console.log("Creating Daily call object");
      const callObject = DailyIframe.createCallObject();
      callObjectRef.current = callObject;

      // --- Event Handlers ---
      // Helper to upsert remote participant streams from current state
      const upsertRemoteStream = (p) => {
        if (p.local) return;

        const tracks = [];
        const v = p.tracks?.video;
        const a = p.tracks?.audio;

        // Log track states for debugging
        // console.log(`[Daily Track States] ${p.userData?.displayName || p.session_id}:`, {
        //   videoState: v?.state,
        //   videoTrackExists: !!v?.track,
        //   videoEnabled: v?.track?.enabled,
        //   videoReadyState: v?.track?.readyState,
        //   audioState: a?.state,
        //   audioTrackExists: !!a?.track,
        //   audioEnabled: a?.track?.enabled,
        //   audioReadyState: a?.track?.readyState,
        // });

        if (v?.track) tracks.push(v.track);
        if (a?.track) tracks.push(a.track);

        if (!tracks.length) {
          // console.log(`[Daily] No tracks available for ${p.userData?.displayName || p.session_id}, skipping stream update`);
          return;
        }

        setCallState(prev => {
          // Check if we already have a stream for this participant
          const existingStream = prev.remoteStreams[p.session_id];

          if (existingStream) {
            // Compare existing stream with new tracks to see if update is needed
            const existingVideoTracks = existingStream.getVideoTracks();
            const existingAudioTracks = existingStream.getAudioTracks();
            const existingVideoId = existingVideoTracks[0]?.id;
            const existingAudioId = existingAudioTracks[0]?.id;
            const existingVideoState = existingVideoTracks[0]?.readyState;
            const existingAudioState = existingAudioTracks[0]?.readyState;

            const newVideoId = v?.track?.id;
            const newAudioId = a?.track?.id;
            const newVideoState = v?.track?.readyState;
            const newAudioState = a?.track?.readyState;

            // Check what changed
            const trackCountChanged = tracks.length !== (existingVideoTracks.length + existingAudioTracks.length);
            const videoTrackChanged = existingVideoId !== newVideoId;
            const audioTrackChanged = existingAudioId !== newAudioId;
            const videoStateImproved = existingVideoState === 'ended' && newVideoState === 'live';
            const audioStateImproved = existingAudioState === 'ended' && newAudioState === 'live';

            // Skip update if nothing meaningful changed
            if (!trackCountChanged && !videoTrackChanged && !audioTrackChanged &&
                !videoStateImproved && !audioStateImproved) {
              return prev; // Stream is unchanged, skip update
            }

            // Log what triggered the update
            const reasons = [];
            if (trackCountChanged) reasons.push('track count changed');
            if (videoTrackChanged) reasons.push('video track changed');
            if (audioTrackChanged) reasons.push('audio track changed');
            if (videoStateImproved) reasons.push('video state improved');
            if (audioStateImproved) reasons.push('audio state improved');
            console.log(`[Daily] Updating stream for ${p.userData?.displayName || p.session_id} - ${reasons.join(', ')}`);
          } else {
            console.log(`[Daily] Creating FIRST stream for ${p.userData?.displayName || p.session_id}`);
          }

          console.log(`[Daily] Upserting remote stream for ${p.userData?.displayName || p.session_id}:`, {
            sessionId: p.session_id,
            trackCount: tracks.length,
            videoState: v?.state,
            audioState: a?.state,
            videoTrackId: v?.track?.id,
            audioTrackId: a?.track?.id,
            videoReadyState: v?.track?.readyState,
            audioReadyState: a?.track?.readyState,
          });

          return {
            ...prev,
            remoteStreams: {
              ...prev.remoteStreams,
              [p.session_id]: new MediaStream(tracks)
            },
            participantNames: {
              ...prev.participantNames,
              [p.session_id]: p.userData?.displayName || "Participant"
            },
            participantVideoStates: {
              ...prev.participantVideoStates,
              [p.session_id]: v?.state || "unknown"
            },
            participantAudioStates: {
              ...prev.participantAudioStates,
              [p.session_id]: a?.state || "unknown"
            },
          };
        });
      };

      const handleJoined = async () => {
        // console.log("Joined meeting.");
        const participants = callObject.participants();

        const local = participants.local;

        // console.log("window saving participants")
        window.participants = participants;

        // Bootstrap remote participants from current state (handles joining second)
        Object.entries(participants).forEach(([id, p]) => {
          if (id !== "local") {
            console.log(`[Daily] Bootstrapping remote participant ${p.userData?.displayName || id}:`, {
              sessionId: id,
              videoState: p?.tracks?.video?.state,
              audioState: p?.tracks?.audio?.state,
            });
            upsertRemoteStream(p);
          }
        });

        // Poll for remote participants with playable tracks (backup mechanism)
        // This catches cases where participant-updated doesn't fire or fires before tracks are ready
        // Also handles rejoiners since events don't fire reliably for them

        // Fast polling for first 10 seconds (initial join scenario)
        const fastPollInterval = setInterval(() => {
          const currentParticipants = callObject.participants();
          const participantNames = Object.entries(currentParticipants)
            .filter(([id]) => id !== "local")
            .map(([id, p]) => p.userData?.displayName || id);
          // console.log(`[Daily] Fast polling - found ${Object.keys(currentParticipants).length - 1} remote participants:`, participantNames);
          Object.entries(currentParticipants).forEach(([id, p]) => {
            if (id !== "local") {
              // console.log(`[Daily] Checking participant ${p.userData?.displayName || id}`);
              const hasPlayableVideo = p.tracks?.video?.state === "playable";
              const hasPlayableAudio = p.tracks?.audio?.state === "playable";
              const hasVideoTrack = p.tracks?.video?.track;
              const hasAudioTrack = p.tracks?.audio?.track;
              const videoState = p.tracks?.video?.state;
              const audioState = p.tracks?.audio?.state;

              // Always update video and audio state, even if not playable
              if (videoState || audioState) {
                setCallState((prev) => ({
                  ...prev,
                  participantVideoStates: {
                    ...prev.participantVideoStates,
                    [id]: videoState
                  },
                  participantAudioStates: {
                    ...prev.participantAudioStates,
                    [id]: audioState
                  }
                }));
              }

              // if (hasPlayableVideo || hasPlayableAudio || hasVideoTrack || hasAudioTrack) {
                // console.log("Poll found tracks for:", id, "video:", hasPlayableVideo, "audio:", hasPlayableAudio);
                upsertRemoteStream(p);
              // }
            }
          });
        }, 500); // Poll every 500ms

        // After 10 seconds, switch to slow polling to catch rejoiners
        setTimeout(() => {
          clearInterval(fastPollInterval);
          // console.log("Switching to slow polling for rejoiners");

          // Slow polling continues indefinitely to catch people who rejoin
          setInterval(() => {
            const currentParticipants = callObject.participants();
            const currentRemoteIds = Object.keys(currentParticipants).filter(id => id !== "local");

            // console.log(`[Daily] Slow polling - checking ${currentRemoteIds.length} participants`);

            // Add new/rejoined participants
            Object.entries(currentParticipants).forEach(([id, p]) => {
              if (id !== "local") {
                // console.log(`[Daily Slow Poll] Participant ${p.userData?.displayName || id}:`, {
                //   sessionId: id,
                //   videoState: p.tracks?.video?.state,
                //   audioState: p.tracks?.audio?.state,
                //   hasVideoTrack: !!p.tracks?.video?.track,
                //   hasAudioTrack: !!p.tracks?.audio?.track,
                //   videoTrackId: p.tracks?.video?.track?.id,
                //   audioTrackId: p.tracks?.audio?.track?.id,
                // });
                const hasPlayableVideo = p.tracks?.video?.state === "playable";
                const hasPlayableAudio = p.tracks?.audio?.state === "playable";
                const hasVideoTrack = p.tracks?.video?.track;
                const hasAudioTrack = p.tracks?.audio?.track;
                const videoState = p.tracks?.video?.state;
                const audioState = p.tracks?.audio?.state;

                // Always update video and audio state, even if not playable
                if (videoState || audioState) {
                  setCallState((prev) => ({
                    ...prev,
                    participantVideoStates: {
                      ...prev.participantVideoStates,
                      [id]: videoState
                    },
                    participantAudioStates: {
                      ...prev.participantAudioStates,
                      [id]: audioState
                    }
                  }));
                }

                if (hasPlayableVideo || hasPlayableAudio || hasVideoTrack || hasAudioTrack) {
                  upsertRemoteStream(p);
                }
              }
            });

            // Clean up participants with dead/ended tracks (e.g., after browser refresh)
            const deadSessionIds = [];
            Object.entries(currentParticipants).forEach(([id, p]) => {
              if (id !== "local") {
                const videoTrackEnded = p.tracks?.video?.track?.readyState === "ended";
                const audioTrackEnded = p.tracks?.audio?.track?.readyState === "ended";

                // If both tracks are ended (or the only track present is ended), mark for removal
                if (videoTrackEnded && audioTrackEnded) {
                  console.log(`[Daily] Detected dead stream for ${p.userData?.displayName || id} - both tracks ended`);
                  deadSessionIds.push(id);
                } else if (videoTrackEnded && !p.tracks?.audio?.track) {
                  console.log(`[Daily] Detected dead stream for ${p.userData?.displayName || id} - video track ended, no audio`);
                  deadSessionIds.push(id);
                } else if (audioTrackEnded && !p.tracks?.video?.track) {
                  console.log(`[Daily] Detected dead stream for ${p.userData?.displayName || id} - audio track ended, no video`);
                  deadSessionIds.push(id);
                }
              }
            });

            // Remove dead streams
            if (deadSessionIds.length > 0) {
              setCallState((prev) => {
                const newRemoteStreams = { ...prev.remoteStreams };
                const newParticipantNames = { ...prev.participantNames };
                const newParticipantRepStatus = { ...prev.participantRepStatus };
                const newParticipantVideoStates = { ...prev.participantVideoStates };

                deadSessionIds.forEach(sessionId => {
                  delete newRemoteStreams[sessionId];
                  delete newParticipantNames[sessionId];
                  delete newParticipantRepStatus[sessionId];
                  delete newParticipantVideoStates[sessionId];
                });

                return {
                  ...prev,
                  remoteStreams: newRemoteStreams,
                  participantNames: newParticipantNames,
                  participantRepStatus: newParticipantRepStatus,
                  participantVideoStates: newParticipantVideoStates,
                };
              });
            }

            // Clean up participants who are no longer in the call
            setCallState((prev) => {
              const staleSessionIds = Object.keys(prev.remoteStreams).filter(
                sessionId => !currentRemoteIds.includes(sessionId)
              );

              if (staleSessionIds.length === 0) {
                return prev; // No cleanup needed
              }

              // console.log("Cleaning up stale participants:", staleSessionIds);

              const newRemoteStreams = { ...prev.remoteStreams };
              const newParticipantNames = { ...prev.participantNames };
              const newParticipantRepStatus = { ...prev.participantRepStatus };
              const newParticipantVideoStates = { ...prev.participantVideoStates };

              staleSessionIds.forEach(sessionId => {
                delete newRemoteStreams[sessionId];
                delete newParticipantNames[sessionId];
                delete newParticipantRepStatus[sessionId];
                delete newParticipantVideoStates[sessionId];
              });

              return {
                ...prev,
                remoteStreams: newRemoteStreams,
                participantNames: newParticipantNames,
                participantRepStatus: newParticipantRepStatus,
                participantVideoStates: newParticipantVideoStates,
              };
            });
          }, 2000); // Poll every 2 seconds (slow but catches rejoiners)
        }, 10000);

        if (local) {
          const displayName = local.userData?.displayName || "You";
          setCallState((prev) => ({
            ...prev,
            participantNames: {
              ...prev.participantNames,
              [local.session_id]: displayName,
            },
          }));
        }

        try {
          // await callObject.startRecording({
          //   type: "cloud",
          //   layout: {
          //     preset: 'custom',
          //     composition_params: {
          //       'videoSettings.showParticipantLabels': true,
          //     },
          //   },
          // });

          await callObject.startRecording({
            type: "raw-tracks",
          });

          setCallState((prev) => ({ ...prev, isRecording: true }));
          console.log("RAW TRACKS Recording started in Daily Cloud.");
        } catch (err) {
          console.error("Failed to start recording:", err);
        }

        // Start transcription
        try {
          await callObject.startTranscription();
          setCallState((prev) => ({ ...prev, isTranscribing: true }));
          // console.log("Transcription started.");
        } catch (err) {
          console.error("Failed to start transcription:", err);
        }
      };

      const handleTrackStarted = (ev) => {
        // console.log("handleTrackStarted fired!", ev);
        const { participant, track } = ev;
        // console.log(`[Daily] Track started for ${participant.userData?.displayName || participant.session_id}:`, {
        //   trackKind: track.kind,
        //   isLocal: participant.local,
        //   sessionId: participant.session_id,
        // });

        if (participant.local) {
          if (track.kind === "video") {
            setCallState((prev) => ({ ...prev, localVideoTrack: track }));
          }
        } else {
          const sessionId = participant.session_id;

          // Initialize track storage for this participant if needed
          if (!participantTracksRef.current[sessionId]) {
            participantTracksRef.current[sessionId] = { video: null, audio: null };
          }

          // Store the track
          if (track.kind === "video") {
            participantTracksRef.current[sessionId].video = track;
          } else if (track.kind === "audio") {
            participantTracksRef.current[sessionId].audio = track;
          }

          // Create MediaStream with all available tracks
          const tracks = [];
          if (participantTracksRef.current[sessionId].video) {
            tracks.push(participantTracksRef.current[sessionId].video);
          }
          if (participantTracksRef.current[sessionId].audio) {
            tracks.push(participantTracksRef.current[sessionId].audio);
          }

          if (tracks.length > 0) {
            setCallState((prev) => ({
              ...prev,
              remoteStreams: {
                ...prev.remoteStreams,
                [sessionId]: new MediaStream(tracks),
              },
              participantNames: {
                ...prev.participantNames,
                [sessionId]: participant.userData?.displayName || "Participant",
              },
            }));
          }
        }
      };

      const handleParticipantLeft = (ev) => {
        const { session_id } = ev.participant;

        // Clean up track references
        delete participantTracksRef.current[session_id];

        setCallState((prev) => {
          const newRemoteStreams = { ...prev.remoteStreams };
          const newParticipantNames = { ...prev.participantNames };
          const newParticipantRepStatus = { ...prev.participantRepStatus };
          const newParticipantVideoStates = { ...prev.participantVideoStates };

          delete newRemoteStreams[session_id];
          delete newParticipantNames[session_id];
          delete newParticipantRepStatus[session_id];
          delete newParticipantVideoStates[session_id];

          return {
            ...prev,
            remoteStreams: newRemoteStreams,
            participantNames: newParticipantNames,
            participantRepStatus: newParticipantRepStatus,
            participantVideoStates: newParticipantVideoStates,
          };
        });
      };

      const handleLeftMeeting = async () => {
        // Use ref to get current state values
        if (callStateRef.current.isRecording) {
          try {
            await callObject.stopRecording();
            // console.log("Recording stopped and saved in Daily Cloud.");
          } catch (err) {
            console.error("Failed to stop recording:", err);
          }
        }
        if (callStateRef.current.isTranscribing) {
          try {
            await callObject.stopTranscription();
            // console.log("Transcription stopped.");
          } catch (err) {
            console.error("Failed to stop transcription:", err);
          }
        }
      };

      const handleTranscriptionStarted = (event) => {
        // console.log("Transcription started:", event);
        setCallState((prev) => ({ ...prev, isTranscribing: true }));
      };

      const handleTranscriptionStopped = (event) => {
        // console.log("Transcription stopped:", event);
        setCallState((prev) => ({ ...prev, isTranscribing: false }));
      };

      const handleTranscriptionError = (event) => {
        console.error("[Daily] Transcription error:", event);
        setCallState((prev) => ({ ...prev, isTranscribing: false }));
      };

      const handleTranscriptionMessage = (event) => {
        // console.log("Transcription message:", event);
      };

      const handleParticipantJoined = (ev) => {
        console.log(`[Daily Event] participant-joined:`, {
          name: ev.participant.userData?.displayName || ev.participant.session_id,
          sessionId: ev.participant.session_id,
          videoState: ev.participant.tracks?.video?.state,
          audioState: ev.participant.tracks?.audio?.state,
          hasVideoTrack: !!ev.participant.tracks?.video?.track,
          hasAudioTrack: !!ev.participant.tracks?.audio?.track,
        });
        upsertRemoteStream(ev.participant);
      };

      const handleParticipantUpdated = (ev) => {
        const p = ev.participant;
        console.log(`[Daily Event] participant-updated:`, {
          name: p.userData?.displayName || p.session_id,
          sessionId: p.session_id,
          videoState: p.tracks?.video?.state,
          audioState: p.tracks?.audio?.state,
          hasVideoTrack: !!p.tracks?.video?.track,
          hasAudioTrack: !!p.tracks?.audio?.track,
        });
        upsertRemoteStream(ev.participant);
      };

      // Attach listeners (these will be cleaned up if call object is destroyed)
      callObject.on("joined-meeting", handleJoined);
      callObject.on("participant-joined", handleParticipantJoined);
      callObject.on("participant-updated", handleParticipantUpdated);
      callObject.on("track-started", handleTrackStarted);
      callObject.on("participant-left", handleParticipantLeft);
      callObject.on("left-meeting", handleLeftMeeting);
      callObject.on("transcription-started", handleTranscriptionStarted);
      callObject.on("transcription-stopped", handleTranscriptionStopped);
      callObject.on("transcription-error", handleTranscriptionError);
      callObject.on("transcription-message", handleTranscriptionMessage);

      // Join the call
      const state = callObject.meetingState?.();
      if (state !== "joining" && state !== "joined") {
        console.log("Joining meeting at:", roomUrl, "with display name:", displayName);

        const joinConfig = {
          url: roomUrl,
          token: meetingToken,
          userName: participantIdentifier + " (" + displayName + ")",
          userData: {
            displayName: displayName,
          },
          audioSource: audioTrack,
          videoSource: videoTrack,
          startAudioOff: true,
          startVideoOff: true,
        };

        try {
          console.log("Calling callObject.join() with config:", joinConfig);
          callObject.join(joinConfig)
            .then(() => {
              console.log("Join promise resolved successfully");
              setHasJoinedCall(true);
            })
            .catch((error) => {
              console.error("Join promise rejected:", error);
            });
        } catch (error) {
          console.error("Synchronous error during join:", error);
        }
      } else {
        console.log("Skipping join - already in state:", state);
      }

      // Return cleanup function for event listeners
      return () => {
        callObject.off("joined-meeting", handleJoined);
        callObject.off("participant-joined", handleParticipantJoined);
        callObject.off("participant-updated", handleParticipantUpdated);
        callObject.off("track-started", handleTrackStarted);
        callObject.off("participant-left", handleParticipantLeft);
        callObject.off("left-meeting", handleLeftMeeting);
        callObject.off("transcription-started", handleTranscriptionStarted);
        callObject.off("transcription-stopped", handleTranscriptionStopped);
        callObject.off("transcription-error", handleTranscriptionError);
        callObject.off("transcription-message", handleTranscriptionMessage);
      };
    };

    // Call the async initialization function with a small delay
    let cleanupListeners = null;
    const timeoutId = setTimeout(async () => {
      cleanupListeners = await initializeCall();
    }, 100);

    // Cleanup function
    return () => {
      clearTimeout(timeoutId);
      // Clean up event listeners if they were attached
      if (cleanupListeners) {
        cleanupListeners();
      }
      // Note: We don't destroy the call object here because we want it to persist
      // The call will be cleaned up when the App component unmounts
    };

  }, [mediaStream, callJoinData, hasJoinedCall]);

  // Control Daily.co audio/video tracks based on toggle state and VideoChat mount state
  useEffect(() => {
    const callObject = callObjectRef.current;
    if (!callObject || !hasJoinedCall) {
      return;
    }

    // Only enable tracks if not force-locked off, VideoChat is mounted, AND the
    // individual toggle is enabled.
    const shouldEnableAudio = !mediaLocked && isVideoChatMounted && isAudioEnabled;
    const shouldEnableVideo = !mediaLocked && isVideoChatMounted && isVideoEnabled;

    console.log("Updating track states:", {
      isVideoChatMounted,
      isAudioEnabled,
      isVideoEnabled,
      shouldEnableAudio,
      shouldEnableVideo,
    });

    try {
      callObject.setLocalAudio(shouldEnableAudio);
      callObject.setLocalVideo(shouldEnableVideo);
    } catch (err) {
      console.error("Failed to update track states:", err);
    }
  }, [isAudioEnabled, isVideoEnabled, isVideoChatMounted, hasJoinedCall, mediaLocked]);

  // Create stable callback for registering call data (only call once)
  // Only updates if critical join data changes (roomUrl, token, displayName)
  const registerCallData = useCallback((data) => {
    setCallJoinData((prevData) => {
      // Only update if critical data has changed
      // Note: roomUrl and displayName should never change during a game session
      if (!prevData ||
          prevData.roomUrl !== data.roomUrl ||
          prevData.meetingToken !== data.meetingToken ||
          prevData.displayName !== data.displayName) {
        console.log("App.jsx: Call data registered/updated", data);
        return data;
      }
      console.log("App.jsx: Call data unchanged, skipping update");
      return prevData;
    });
  }, []);

  // Log remote streams state whenever it changes
  useEffect(() => {
    const { remoteStreams, participantNames, participantVideoStates } = callState;
    const streamCount = Object.keys(remoteStreams).length;

    if (streamCount > 0) {
      // console.log(Date.now());
      // console.log(`[App.jsx Remote Streams] Total: ${streamCount}`);
      Object.entries(remoteStreams).forEach(([sessionId, stream]) => {
        //const videoTracks = stream.getVideoTracks();
        // const audioTracks = stream.getAudioTracks();
        // console.log(`  - ${participantNames[sessionId] || 'Unknown'} (${sessionId}):`, {
        //   videoState: participantVideoStates[sessionId],
        //   hasVideoTrack: videoTracks.length > 0,
        //   videoTrackEnabled: videoTracks[0]?.enabled,
        //   videoTrackReadyState: videoTracks[0]?.readyState,
        //   hasAudioTrack: audioTracks.length > 0,
        //   audioTrackEnabled: audioTracks[0]?.enabled,
        // });
      });
    }
  }, [callState.remoteStreams, callState.participantNames, callState.participantVideoStates]);

  // Function to refresh a remote participant's stream by forcing Daily.co to re-fetch
  const refreshRemoteParticipant = useCallback((sessionId) => {
    console.log(`[Daily] Manually refreshing participant stream: ${sessionId}`);
    const callObject = callObjectRef.current;
    if (!callObject) {
      console.warn('[Daily] Cannot refresh - no call object');
      return;
    }

    try {
      const participants = callObject.participants();
      const participant = participants[sessionId];

      if (!participant) {
        console.warn(`[Daily] Cannot refresh - participant ${sessionId} not found`);
        return;
      }

      // Force remove the old stream
      setCallState(prev => {
        const newRemoteStreams = { ...prev.remoteStreams };
        delete newRemoteStreams[sessionId];

        console.log(`[Daily] Removed stale stream for ${sessionId}, will re-add from current state`);

        return {
          ...prev,
          remoteStreams: newRemoteStreams,
        };
      });

      // Re-add the stream from current Daily.co state after a brief delay
      setTimeout(() => {
        const currentParticipants = callObject.participants();
        const currentParticipant = currentParticipants[sessionId];

        if (currentParticipant) {
          const tracks = [];
          const v = currentParticipant.tracks?.video;
          const a = currentParticipant.tracks?.audio;

          if (v?.state === "playable" && v.track) tracks.push(v.track);
          if (a?.state === "playable" && a.track) tracks.push(a.track);

          if (tracks.length > 0) {
            setCallState(prev => ({
              ...prev,
              remoteStreams: {
                ...prev.remoteStreams,
                [sessionId]: new MediaStream(tracks)
              },
            }));
            console.log(`[Daily] Re-added refreshed stream for ${sessionId} with ${tracks.length} tracks`);
          } else {
            console.warn(`[Daily] No playable tracks available for ${sessionId} after refresh`);
          }
        }
      }, 500);
    } catch (error) {
      console.error('[Daily] Error refreshing participant:', error);
    }
  }, [setCallState]);

  // Fully release the Daily call AND the local getUserMedia capture. Used by the
  // prep stages (Read Negotiation Role / Ready To Negotiate), which show no video:
  // this stops the cloud recording/transcription and — by stopping the local
  // tracks — extinguishes the browser camera/mic indicator. VideoChat re-acquires
  // media and rejoins on its own when the negotiation stage mounts it.
  // Idempotent: safe to call when already torn down.
  const teardownCall = useCallback(async () => {
    const callObject = callObjectRef.current;
    if (callObject) {
      // Guard each step independently: stopRecording/stopTranscription/leave are
      // async network calls that can reject, and a rejection must NOT skip
      // destroy(). Daily holds its own (cloned) camera track internally, and only
      // destroy() releases it — if we skip it, the browser camera indicator stays
      // lit even after we stop our own mediaStream tracks below.
      try {
        if (callStateRef.current.isRecording) await callObject.stopRecording();
      } catch (err) { console.error("teardownCall: stopRecording failed", err); }
      try {
        if (callStateRef.current.isTranscribing) await callObject.stopTranscription();
      } catch (err) { console.error("teardownCall: stopTranscription failed", err); }

      // Defensively stop the local tracks Daily is holding (its own clones of the
      // camera/mic) before leaving, in case destroy() doesn't release them.
      try {
        const local = callObject.participants?.()?.local;
        if (local?.tracks) {
          Object.values(local.tracks).forEach((t) => {
            t?.persistentTrack?.stop?.();
            t?.track?.stop?.();
          });
        }
      } catch (err) { console.error("teardownCall: stopping local Daily tracks failed", err); }

      try {
        await callObject.leave();
      } catch (err) { console.error("teardownCall: leave failed", err); }
      try {
        callObject.destroy();
      } catch (err) { console.error("teardownCall: destroy failed", err); }
    }

    callObjectRef.current = null;
    participantTracksRef.current = {};

    // Stop the local capture tracks (functional updater avoids a stale closure).
    setMediaStream((prev) => {
      prev?.getTracks().forEach((track) => track.stop());
      return null;
    });

    // Force-stop EVERY getUserMedia stream the app ever opened — the current
    // mediaStream plus any orphans (device-selector preview, retries, double
    // mounts). The browser indicator only clears once all tracks read "ended".
    stopAllTrackedStreams();

    setCallState({
      remoteStreams: {},
      participantNames: {},
      participantRepStatus: {},
      participantVideoStates: {},
      participantAudioStates: {},
      isRecording: false,
      isTranscribing: false,
      localVideoTrack: null,
    });
    setHasJoinedCall(false);
  }, []);

  // Create context value object with useMemo to prevent unnecessary re-renders
  // Note: setMediaStream and setCallState are stable (from useState), so don't need to be in deps
  // Note: registerCallData is stable (from useCallback with empty deps)
  const dailyCallContextValue = useMemo(() => ({
    mediaStream,
    setMediaStream,
    callObject: callObjectRef.current,
    callState,
    setCallState,
    registerCallData,
    refreshRemoteParticipant,
    isAudioEnabled,
    setIsAudioEnabled,
    isVideoEnabled,
    setIsVideoEnabled,
    setIsVideoChatMounted,
    mediaLocked,
    setMediaLocked,
    teardownCall,
  }), [mediaStream, callState, registerCallData, refreshRemoteParticipant, teardownCall, isAudioEnabled, isVideoEnabled, mediaLocked]);

  return (
    <EmpiricaParticipant url={url} ns={playerKey} modeFunc={EmpiricaClassic}>
      <DailyCallContext.Provider value={dailyCallContextValue}>
        <div className="relative">
          <EmpiricaMenu position="bottom-left" />
          <div>
            <EmpiricaContext playerCreate={AutoPlayerIdForm} finished={Finished}
             lobby={CustomLobby}
            introSteps={introSteps} exitSteps={exitSteps}  consent={CustomConsent} disableConsent={false} >
              <Game />
            </EmpiricaContext>
          </div>
        </div>
      </DailyCallContext.Provider>
    </EmpiricaParticipant>
  );
}
