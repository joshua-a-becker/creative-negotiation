import { ClassicListenersCollector } from "@empirica/core/admin/classic";
import fetch from "node-fetch";
import { execSync, execFile } from "child_process";
import { createHash } from "crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import os from "os";
import path from "path";

// import rolesData from "./roles.json" assert { type: "json" };
// const roles = rolesData.roles;

export const Empirica = new ClassicListenersCollector();

// ============================================================================
// OFFER SCORING — bridge to the python scorer (score_offer.py, see scorerScriptPath)
//
// player.calculateHistory is a chat-like vector:
//   { kind: "request",  id, text, role, previousText, timestamp }   (client)
//   { kind: "response", requestId, text, role, score, error, mock, timestamp } (server)
// When the last item is a request we score it and append the response. `score`
// is the scorer's JSON (score_offer.py --json), untouched; see
// negotiationDisplay.jsx for the fields the UI reads.
//
// The python scorer is the default. SCORER_MOCK=1 swaps in a mock that returns
// data in the same shape (no API key / network needed). A call takes ~8-10s.
// ============================================================================

const SCORER_ENABLED = process.env.SCORER_MOCK !== "1";
const SCORER_TIMEOUT_MS = 45000;

// Where score_offer.py lives. The scorer is NOT part of the Empirica bundle
// (`empirica bundle` packs only .empirica/, server/dist and client/dist, and
// `empirica serve` runs this code from a hashed temp dir), so it is uploaded
// separately to a fixed place: ~/score_offer/ in the home of the user the
// server runs as (/root/score_offer on the live host, /home/<user>/score_offer
// locally). SCORER_SCRIPT overrides; the last two entries cover dev mode, where
// the server runs from server/ and the scorer sits at the repo root.
const SCORER_HOME_PATH = path.join(os.homedir(), "score_offer", "score_offer.py");

function scorerScriptPath() {
  if (process.env.SCORER_SCRIPT) return process.env.SCORER_SCRIPT;
  const candidates = [
    SCORER_HOME_PATH,
    path.resolve(process.cwd(), "../score_offer.py"),
    path.resolve(process.cwd(), "score_offer.py"),
  ];
  return candidates.find((c) => existsSync(c)) || null;
}

{
  const found = scorerScriptPath();
  if (found) console.log(`[scorer] using ${found}`);
  else console.warn(`[scorer] score_offer.py not found; expected at ${SCORER_HOME_PATH} (or set SCORER_SCRIPT)`);
}

// The scorer's scenarios know two roles, Candidate and Recruiter. Map this
// app's role names onto them: an exact match wins, then SCORER_ROLE_MAP
// (JSON, e.g. {"Party A":"Candidate","Party B":"Recruiter"}), then a name
// containing "recruit"/"employer"/"company" → Recruiter, else Candidate.
function scorerRoleFor(roleName) {
  const name = String(roleName || "");
  if (name === "Candidate" || name === "Recruiter") return name;
  if (process.env.SCORER_ROLE_MAP) {
    try {
      const mapped = JSON.parse(process.env.SCORER_ROLE_MAP)[name];
      if (mapped) return mapped;
    } catch (err) { console.error("[scorer] SCORER_ROLE_MAP is not valid JSON", err); }
  }
  const guess = /recruit|employer|company|firm/i.test(name) ? "Recruiter" : "Candidate";
  console.warn(`[scorer] role "${name}" is not a scorer role; using ${guess}`);
  return guess;
}

function runPythonScorer({ text, role, previousText, issueSpace, scenarioFile }) {
  return new Promise((resolve, reject) => {
    const script = scorerScriptPath();
    if (!script) {
      reject(new Error(`Scorer not found at ${SCORER_HOME_PATH} (upload the score_offer folder there, or set SCORER_SCRIPT)`));
      return;
    }
    const args = [script, "--json", "--role", scorerRoleFor(role), "--text", text];
    if (previousText) args.push("--previous-offer", previousText);
    // The scenario (issues, ranges, payoffs) comes from the role JSON's
    // scenario_url, fetched at game start; --issue-space is the fallback.
    if (scenarioFile) args.push("--scenario-file", scenarioFile);
    const space = issueSpace || process.env.SCORER_ISSUE_SPACE;
    if (space) args.push("--issue-space", space);
    execFile(
      process.env.SCORER_PYTHON || "python3",
      args,
      { timeout: SCORER_TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024, env: process.env },
      (err, stdout, stderr) => {
        if (err) {
          reject(new Error(stderr?.trim() || err.message));
          return;
        }
        try {
          resolve(JSON.parse(stdout));
        } catch (parseErr) {
          reject(new Error(`Scorer returned non-JSON output: ${stdout.slice(0, 200)}`));
        }
      }
    );
  });
}

// Mock scorer: reads "issue: term" lines and assigns deterministic values so the
// UI has something structured to render. Same output shape as score_offer.py.
function mockScore({ text, role }) {
  const hash = (str) => {
    let h = 0;
    for (const ch of str) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return h;
  };
  const valueFor = (issue, option, salt) => {
    const h = hash(`${issue}|${option}|${salt}`);
    return Math.round(((h % 900) / 100 - 3) * 100) / 100; // -3.00 .. +5.99
  };
  const fmt = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;

  const pairs = [];
  const unrecognised = [];
  text.split(/\n|;/).map((s) => s.trim()).filter(Boolean).forEach((chunk) => {
    const m = chunk.match(/^(.+?)\s*[:=\-–]\s*(.+)$/);
    if (m) pairs.push([m[1].trim(), m[2].trim()]);
    else unrecognised.push(chunk);
  });

  const base = { proposer_role: role, receiver_role: "counterpart", mock: true };

  if (pairs.length === 0) {
    const messages = ["I couldn't find any terms. Write one term per line as \"issue: value\". (Mock scorer — the real scorer is not wired yet.)"];
    return {
      ...base,
      decision: "rejected",
      messages,
      message: messages.join("\n"),
      lines: [],
      lines_for_receiver: [],
      valid_pairs: {},
      total: 0,
      total_for_proposer: null,
      total_for_receiver: null,
      proposal_allowed: false,
      novel_terms: [],
      display_text: `Invalid Offer:\n- ${messages[0]}\nNo score calculated.`,
    };
  }

  let total = 0;
  let receiverTotal = 0;
  const lines = [];
  const linesReceiver = [];
  const validPairs = {};
  pairs.forEach(([issue, option]) => {
    const v = valueFor(issue, option, role);
    const r = valueFor(issue, option, "receiver");
    total += v;
    receiverTotal += r;
    validPairs[issue] = option;
    lines.push(`- ${issue}: ${option}  [${fmt(v)}]`);
    linesReceiver.push(`- ${issue}: ${option}  [${fmt(r)}]`);
  });
  total = Math.round(total * 100) / 100;
  receiverTotal = Math.round(receiverTotal * 100) / 100;

  return {
    ...base,
    decision: "scorable",
    messages: [],
    message: "",
    lines,
    lines_for_receiver: linesReceiver,
    valid_pairs: validPairs,
    total,
    total_for_proposer: total,
    total_for_receiver: receiverTotal,
    proposal_allowed: true,
    novel_terms: unrecognised,
    display_text:
      lines.join("\n") +
      `\nTotal: ${fmt(total)}` +
      (unrecognised.length ? "\nRecorded new terms (not scored yet):\n" + unrecognised.map((t) => `- ${t}`).join("\n") : ""),
  };
}

async function scoreOffer({ text, role, previousText, issueSpace, scenarioFile }) {
  if (SCORER_ENABLED) return runPythonScorer({ text, role, previousText, issueSpace, scenarioFile });
  return mockScore({ text, role });
}

// ----------------------------------------------------------------------------
// Role data loading. `roleDataURL` may list several URLs/paths separated by
// commas or whitespace (e.g. one file per role). Each JSON has the Empirica
// shape { roles: [...], tips } and may add:
//   scenario_url  URL of the scorer's scenario JSON (issues/ranges/payoffs)
//   scenario      the same, inline
//   scorer_role   name of this role inside the scenario (defaults to role_name)
// ----------------------------------------------------------------------------

function fetchJSON(urlOrPath) {
  const text = urlOrPath.startsWith("http")
    ? execSync(`curl -sfL "${urlOrPath}"`, { maxBuffer: 16 * 1024 * 1024 }).toString()
    : readFileSync(urlOrPath, "utf8");
  return JSON.parse(text);
}

function loadRolesData(roleDataURL) {
  const sources = String(roleDataURL || "").split(/[,\s]+/).filter(Boolean);
  const merged = { roles: [], tips: "", scenario: null, scenarioUrl: "" };
  for (const src of sources) {
    const data = fetchJSON(src);
    const roles = Array.isArray(data.roles) ? data.roles : (data.role_name ? [data] : []);
    for (const role of roles) {
      merged.roles.push({ ...role, scorer_role: role.scorer_role || data.scorer_role || role.role_name });
    }
    if (!merged.tips && data.tips) merged.tips = data.tips;
    if (!merged.scenario && data.scenario) merged.scenario = data.scenario;
    if (!merged.scenarioUrl && data.scenario_url) merged.scenarioUrl = data.scenario_url;
    console.log(`Loaded ${roles.length} role(s) from ${src}`);
  }
  return merged;
}

// Materialise the scorer scenario as a file the python script can read.
// Cached by content hash under the OS temp dir; a changed scenario gets a new file.
function writeScenarioFile(scenario, scenarioUrl) {
  let json;
  if (scenario) json = JSON.stringify(scenario);
  else if (scenarioUrl) json = JSON.stringify(fetchJSON(scenarioUrl));
  else return "";
  const dir = path.join(os.tmpdir(), "creative-negotiation-scenarios");
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${createHash("sha1").update(json).digest("hex")}.json`);
  if (!existsSync(file)) writeFileSync(file, json);
  return file;
}

// NOTE: Empirica attribute listeners receive (ctx, { player, <key> }) — the
// event context comes first, the payload second.
Empirica.on("player", "calculateHistory", async (_ctx, { player, calculateHistory }) => {
  const history = Array.isArray(calculateHistory) ? calculateHistory : [];
  const last = history[history.length - 1];
  if (!last || last.kind !== "request" || !last.id) return;
  // Already answered (e.g. a replay of the same vector).
  if (history.some((e) => e.kind === "response" && e.requestId === last.id)) return;

  const text = String(last.text || "").trim();
  const previousText = String(last.previousText || "");
  // A request may name a built-in issue space (the intro tutorial sends
  // "tutorial"); it then scores with that scenario and the role it asked for.
  // Otherwise: the scenario file materialised at game start from the role
  // JSON's scenario_url, with scorerIssueSpace (15 | 200 | fixed-15) as the
  // treatment-level fallback, and the player's scorer role.
  const scenarioOverride = String(last.scenario || "");
  const scenarioFile = scenarioOverride ? "" : (player.get("scorerScenarioFile") || "");
  const issueSpace = scenarioOverride || player.currentGame?.get("treatment")?.scorerIssueSpace;
  const role = scenarioOverride
    ? (last.role || "Candidate")
    : (player.get("scorerRole") || last.role || player.get("roleName") || "");
  console.log(`[scorer] request ${last.id} from player ${player.id} (${role}), ${text.length} chars, ${SCORER_ENABLED ? "python" : "mock"}`);

  const started = Date.now();
  const response = { kind: "response", requestId: last.id, text, role, scenario: last.scenario || null, mock: !SCORER_ENABLED, timestamp: Date.now() };
  try {
    response.score = await scoreOffer({ text, role, previousText, issueSpace, scenarioFile });
    console.log(`[scorer] request ${last.id} → ${response.score?.decision} in ${Date.now() - started}ms`);
    response.error = null;
  } catch (err) {
    console.error(`[scorer] request ${last.id} failed:`, err);
    response.score = null;
    response.error = String(err?.message || err);
  }

  // Re-read before appending: the client may have added another request while
  // the scorer was running, and we must not clobber it.
  const current = player.get("calculateHistory") || [];
  if (current.some((e) => e.kind === "response" && e.requestId === last.id)) return;
  player.set("calculateHistory", [...current, response]);
});

// Value of a stored proposal to a given player, mirroring viewerScore() in
// client/src/components/negotiationDisplay.jsx.
function proposalValueForPlayer(proposal, player) {
  const score = proposal?.score;
  if (!score || score.decision !== "scorable") return null;
  const roleName = player.get("roleName");
  if (score.totals_by_role && roleName in score.totals_by_role) return score.totals_by_role[roleName];
  if (proposal.submittedBy === player.id) return score.total_for_proposer ?? score.total ?? null;
  return score.total_for_receiver ?? null;
}

Empirica.onRoundEnded(({ round }) => {
  const game = round.currentGame;
  const history = round.get("proposalHistory") || [];
  const finalProposal = history.length > 0 ? history[history.length - 1] : null;

  // Check if agreement was reached (all players voted to finalize)
  const finalVotes = finalProposal?.finalVotes || {};
  const playerCount = game.get("treatment")?.playerCount || game.players.length;
  const finalVoteCount = Object.keys(finalVotes).length;
  const allFinalized = finalVoteCount === playerCount &&
                      Object.values(finalVotes).every(vote => vote === "finalize");
  const reachedAgreement = finalProposal && allFinalized;

  console.log("onRoundEnded - Agreement check:", {
    historyLength: history.length,
    finalVoteCount,
    playerCount,
    allFinalized,
    reachedAgreement
  });

  // Calculate and save bonus for each player
  game.players.forEach((player) => {
    let bonus = 0;

    if (reachedAgreement) {
      // Player's value from the finalized proposal, as computed by the scorer.
      bonus = proposalValueForPlayer(finalProposal, player) ?? 0;
    } else {
      // No agreement reached, use BATNA (reservation price)
      bonus = player.get("roleRP") || 0;
    }

    player.set("bonus", bonus);
    console.log(`Player ${player.id} bonus: ${bonus} (agreement: ${reachedAgreement})`);
  });

  // Save whether agreement was reached to the round
  round.set("agreementReached", reachedAgreement);
  
});

Empirica.onGameStart(({ game }) => {


  const roleDataURL = game.get("treatment").roleDataURL;
  const rolesData = loadRolesData(roleDataURL);
  const roles = rolesData.roles;

  // Store tips in game state for client access
  game.set("tips", rolesData.tips || "");

  // Scorer scenario (issues, ranges, payoffs) travels with the role JSON.
  let scorerScenarioFile = "";
  try {
    scorerScenarioFile = writeScenarioFile(rolesData.scenario, rolesData.scenarioUrl);
    if (scorerScenarioFile) console.log(`Scorer scenario ready: ${scorerScenarioFile} (${rolesData.scenarioUrl || "inline"})`);
    else console.warn("No scenario_url/scenario in role data; scorer will use its default issue space");
  } catch (err) {
    console.error("Failed to load scorer scenario:", err);
  }
  game.set("scorerScenarioUrl", rolesData.scenarioUrl || "");

  console.log(`Fetched ${roles.length} roles from ${roleDataURL}`);

  // Create Daily.co room for this game
  (async () => {
    const d = new Date();
    const today = `${d.getFullYear()}_${String(d.getMonth()+1).padStart(2,'0')}_${String(d.getDate()).padStart(2,'0')}`;
    const DAILY_API_KEY = "d9ff4a046f2a0c3571efa7655fbf80907ad2ffd4d7c89cae0a89e89424d63642";
    const roomName = `${game.id}_video_room_${today}`;

    console.log("Creating Daily.co room for game:", game.id);
    try {
      const roomExp = Math.round(Date.now() / 1000) + 60 * 60 * 4; // 4 hour expiry

      // Create the Daily room
      const res = await fetch("https://api.daily.co/v1/rooms", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${DAILY_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: roomName,
          properties: {
            exp: roomExp,
            enable_recording: "raw-tracks",
            enable_transcription_storage: true,
          },
        }),
      });

      const data = await res.json();

      if (!data.url) {
        console.error("Failed to create Daily room:", data);
        return;
      }

      // Save the room URL to the game
      game.set("roomUrl", data.url);
      // Empirica.flush();
      console.log(`Room created for game: ${data.url}`);

      console.log("Creating meeting tokens for players");
      // Create meeting tokens for each player with transcription permissions
      const tokenPromises = game.players.map(async (player) => {
        try {
          const displayName = player.get("displayName") 
          const user_name = player.get("displayName")  + " - " + `Player ${player.id}`;

          const tokenRes = await fetch("https://api.daily.co/v1/meeting-tokens", {
            method: "POST",
            headers: {
              Authorization: `Bearer ${DAILY_API_KEY}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              properties: {
                room_name: roomName,
                user_name: user_name,
                user_id: player.id,
                is_owner: false,
                permissions: {
                  canAdmin: ["transcription"]
                },
                exp: roomExp,
              },
            }),
          });

          const tokenData = await tokenRes.json();

          if (tokenData.token) {
            player.set("dailyMeetingToken", tokenData.token);
            // Empirica.flush();
            console.log(`Created token for player ${displayName}`);
          } else {
            console.error(`Failed to create token for player ${displayName}:`, tokenData);
          }
        } catch (err) {
          console.error(`Error creating token for player ${player.id}:`, err);
        }
      });

      await Promise.all(tokenPromises);
      // Empirica.flush();
      console.log(`Tokens generated for ${game.players.length} players`);
    } catch (error) {
      console.error("Failed to create Daily room or tokens:", error);
    }
  })();


  // STANDARD GAME SETUP HERE

  const readRoleTime = game.get("treatment")?.readRoleTime ?? 300;
  const negotiateTime = game.get("treatment")?.negotiateTime ?? 1800;


  // Randomly assign roles to players
  // Shuffle players array
  const players = [...game.players];
  for (let i = players.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [players[i], players[j]] = [players[j], players[i]];
  }

  // Assign roles by cycling through roles array
  // Store role data in individual player variables for client access
  players.forEach((player, index) => {
    if (roles.length > 0) {
      const assignedRole = roles[index % roles.length];
      player.set("roleName", assignedRole.role_name);
      player.set("roleNarrative", assignedRole.narrative);
      player.set("roleScoresheet", assignedRole.scoresheet);
      player.set("roleBATNA", assignedRole.BATNA);
      player.set("roleRP", assignedRole.RP);
      player.set("scorerRole", assignedRole.scorer_role || assignedRole.role_name);
      player.set("scorerScenarioFile", scorerScenarioFile);
      console.log(`Assigned role "${assignedRole.role_name}" to player ${player.id}`);
    } else {
      console.warn(`No roles available to assign to player ${player.id}`);
    }
  });

  // initialize rounds and stages
  const round = game.addRound({
    name: "Negotiation Game",
  });

  // add interactive demo here
  // round.addStage({
  //   name: "Interactive Demo",
  //   duration: 1200, // 20 minutes
  // });

  round.addStage({
    name: "Read Negotiation Role",
    duration: readRoleTime,
  });

  round.addStage({
    name: "Ready To Negotiate",
    duration: 15,
  });

  round.addStage({
    name: "Time To Negotiate",
    duration: negotiateTime,
  });

  console.log("game started?")

});

// Handle stage start for video stages
Empirica.onStageStart(({ stage }) => {

  console.log("stage starting")

  // this code block keeps track of whether players have left the game
  // piggybacking on daily.co tracking
  // Initialize timestamps for all players at stage start
  const game = stage.round.currentGame;
  const initialTimestamps = {};
  game.players.forEach(player => {
    initialTimestamps[player.id] = Date.now();
  });
  game.set("participantTimestamps", initialTimestamps);

  // ── Interactive Demo stage: initialize shared demo state ──────────────────
  if (stage.get("name") === "Interactive Demo") {
    // Shuffle player order for focal sequence
    const playerIds = game.players.map(p => p.id);
    for (let i = playerIds.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [playerIds[i], playerIds[j]] = [playerIds[j], playerIds[i]];
    }
    stage.round.set("demo_focal_order", playerIds);
    stage.round.set("demoProposalHistory", []); // separate key — never touches the real proposalHistory
    console.log("Interactive Demo initialized, focal order:", playerIds);
  }

  // Monitor Daily.co participant presence every 5 seconds

});