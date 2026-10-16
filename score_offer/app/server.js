import express from "express";
import { spawn } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";

const APP_ROOT = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.dirname(APP_ROOT);
const BACKEND = path.join(APP_ROOT, "backend");
const CONFIG = path.join(APP_ROOT, "config");
const MOCKUP = path.join(REPO_ROOT, "mockup", "Candidate_Recruiter_Experiment_Mockup.html");
const PYTHON = process.env.PYTHON_BIN || (os.platform() === "win32" ? "python" : "python3");
const MAX_INPUT_CHARS = 12000;
const MODELS = [
  { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5", note: "Fastest · lowest cost", recommended: true },
  { id: "claude-sonnet-5", label: "Claude Sonnet 5", note: "Stronger · higher cost" },
  { id: "claude-opus-5", label: "Claude Opus 5", note: "Most capable · highest cost" },
];
const MODEL_IDS = new Set(MODELS.map(model => model.id));
const SCENARIOS = {
  fixed_15: {
    label: "Fixed 15 · all terms required; private table",
    description: "All 15 terms must appear in every offer. Each role sees its own full payoff table.",
    file: path.join(CONFIG, "fixed-15.json"),
  },
  tutorial: {
    label: "Tutorial venue negotiation",
    description: "The short Community Make & Meet practice used before the study.",
    file: path.join(CONFIG, "tutorial.json"),
  },
  small_15: {
    label: "15 supported issues",
    description: "The bounded study version.",
    file: path.join(CONFIG, "small-15.json"),
  },
  large_200: {
    label: "Archived 200 supported issues",
    description: "The pre-human-pilot expanded version, retained for reproducibility.",
    file: path.join(CONFIG, "large-200.json"),
  },
  large_215: {
    label: "215 supported issues",
    description: "The current human-expanded study version.",
    file: path.join(CONFIG, "large-215.json"),
  },
};

function model(value) {
  const selected = String(value || process.env.NEGOTIATOR_MODEL || MODELS[0].id).trim();
  if (!MODEL_IDS.has(selected)) {
    const error = new Error("Choose one of the Claude models shown in the setup page.");
    error.status = 400;
    throw error;
  }
  return selected;
}

function scenario(value) {
  const aliases = { tutorial: "tutorial", practice: "tutorial", demo: "tutorial", small: "small_15", "15": "small_15", "flexible-15": "small_15", large: "large_215", "215": "large_215", "flexible-215": "large_215", "200": "large_200", "flexible-200": "large_200", fixed: "fixed_15", "fixed-15": "fixed_15" };
  const id = aliases[String(value || "small_15").toLowerCase()] || String(value || "small_15");
  const selected = SCENARIOS[id];
  if (!selected || !fs.existsSync(selected.file)) {
    const error = new Error("Choose Tutorial, Flexible 15, Flexible 215, archived Flexible 200, or Fixed 15.");
    error.status = 400;
    throw error;
  }
  return { id, ...selected };
}

function role(value) {
  const selected = String(value || "").trim();
  if (!new Set(["Candidate", "Recruiter"]).has(selected)) {
    const error = new Error("Role must be Candidate or Recruiter.");
    error.status = 400;
    throw error;
  }
  return selected;
}

function sanitizeText(value) {
  return String(value ?? "").replace(/[\uD800-\uDFFF]/g, "?");
}

function sanitizePayload(value) {
  if (typeof value === "string") return sanitizeText(value);
  if (Array.isArray(value)) return value.map(sanitizePayload);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, sanitizePayload(item)]));
  }
  return value;
}

function runPython(script, payload, selectedScenario, selectedModel, extraEnv = {}, timeoutMs = 75000) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, [path.join(BACKEND, script)], {
      cwd: APP_ROOT,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
        ROLE: payload.role || "Candidate",
        MODE: "JSON",
        NEGOTIATOR_PROVIDER: "anthropic",
        NEGOTIATOR_MODEL: selectedModel,
        AGENT_MODEL: selectedModel,
        NEGOTIATOR_SCENARIO_FILE: selectedScenario.file,
        ...extraEnv,
      },
    });
    let stdout = "";
    let stderr = "";
    let finished = false;
    const done = (fn, value) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      fn(value);
    };
    const timer = setTimeout(() => {
      child.kill();
      done(reject, new Error("The AI request timed out. Please try again."));
    }, timeoutMs);
    child.stdout.on("data", chunk => { stdout += chunk.toString("utf8"); });
    child.stderr.on("data", chunk => { stderr += chunk.toString("utf8"); });
    child.on("error", error => done(reject, error));
    child.on("close", code => {
      try {
        const result = JSON.parse(stdout || "{}");
        if (code !== 0 || result.error) throw new Error(result.error || stderr.trim() || `${script} exited with code ${code}`);
        done(resolve, result);
      } catch (error) {
        done(reject, error);
      }
    });
    child.stdin.end(JSON.stringify(sanitizePayload(payload)));
  });
}

const app = express();
app.use(express.json({ limit: "1mb" }));
app.get("/", (_req, res) => res.redirect("/experiment"));
app.get(["/experiment", "/experiment/"], (_req, res) => res.sendFile(MOCKUP));
app.get("/api/health", (_req, res) => res.json({ ok: true, scenarios: Object.keys(SCENARIOS) }));
app.get("/api/config", (_req, res) => res.json({
  models: MODELS,
  default_model: MODELS[0].id,
  scenario_variants: Object.entries(SCENARIOS).map(([id, value]) => ({
    id,
    label: value.label,
    description: value.description,
    available: fs.existsSync(value.file),
  })),
}));

app.post("/score", async (req, res) => {
  try {
    const selectedRole = role(req.body?.role || "Candidate");
    const text = sanitizeText(req.body?.text).trim();
    if (!text) return res.status(400).json({ error: "Write an offer before asking the system to review it." });
    if (text.length > MAX_INPUT_CHARS) return res.status(413).json({ error: `Keep the offer under ${MAX_INPUT_CHARS.toLocaleString()} characters.` });
    const selectedScenario = scenario(req.body?.scenario_variant);
    const selectedModel = "gpt-5-nano";
    const payload = {
      role: selectedRole,
      text,
      previous_offer: sanitizeText(req.body?.previous_offer).slice(0, MAX_INPUT_CHARS),
    };
    res.json(await runPython("stream.py", payload, selectedScenario, selectedModel, {
      NEGOTIATOR_PROVIDER: "openai",
      NEGOTIATOR_MODEL: selectedModel,
      NEGOTIATOR_SCORER_ROUTING: process.env.NEGOTIATOR_SCORER_ROUTING || "nano-luna",
    }));
  } catch (error) {
    console.error("Scoring error:", error.message);
    res.status(error.status || 500).json({ error: error.message || "Scoring failed." });
  }
});

app.post("/api/agent-offer", async (req, res) => {
  try {
    const selectedRole = role(req.body?.role);
    const attempt = Number(req.body?.attempt || 1);
    if (!Number.isInteger(attempt) || attempt < 1 || attempt > 10) return res.status(400).json({ error: "Attempt must be from 1 through 10." });
    const selectedScenario = scenario(req.body?.scenario_variant);
    const selectedModel = model(req.body?.model);
    const payload = {
      role: selectedRole,
      attempt,
      history: Array.isArray(req.body?.history) ? req.body.history.slice(-20) : [],
      previous_feedback: String(req.body?.previous_feedback || "").slice(0, 4000),
      preparation_instruction: String(req.body?.preparation_instruction || "").slice(0, 3000),
      preparation_condition: String(req.body?.preparation_condition || "control").slice(0, 60),
      model: selectedModel,
    };
    res.json(await runPython("agent_offer.py", payload, selectedScenario, selectedModel));
  } catch (error) {
    console.error("Agent error:", error.message);
    res.status(error.status || 500).json({ error: error.message || "The LLM could not create an offer." });
  }
});

app.post("/api/agent-message", async (req, res) => {
  try {
    const selectedRole = role(req.body?.role);
    const message = String(req.body?.message || "").trim();
    if (!message) return res.status(400).json({ error: "Write a message before sending it." });
    if (message.length > 3000) return res.status(413).json({ error: "Keep chat messages under 3,000 characters." });
    const selectedScenario = scenario(req.body?.scenario_variant);
    const selectedModel = model(req.body?.model);
    const payload = {
      role: selectedRole,
      message,
      history: Array.isArray(req.body?.history) ? req.body.history.slice(-16) : [],
      model: selectedModel,
    };
    res.json(await runPython("agent_message.py", payload, selectedScenario, selectedModel));
  } catch (error) {
    console.error("Chat error:", error.message);
    res.status(error.status || 500).json({ error: error.message || "The other party could not reply." });
  }
});

app.post("/api/match-decision", async (req, res) => {
  try {
    const selectedRole = role(req.body?.role);
    const action = String(req.body?.action || "").trim();
    if (!new Set(["confirm_own_offer", "respond_to_offer", "final_consent"]).has(action)) return res.status(400).json({ error: "Unknown match action." });
    const selectedScenario = scenario(req.body?.scenario_variant);
    const selectedModel = model(req.body?.model);
    const payload = {
      role: selectedRole,
      action,
      own_total: Number(req.body?.own_total || 0),
      agreement_eligible: Boolean(req.body?.agreement_eligible),
      offer: String(req.body?.offer || "").slice(0, MAX_INPUT_CHARS),
      system_output: String(req.body?.system_output || "").slice(0, 6000),
      history: Array.isArray(req.body?.history) ? req.body.history.slice(-12) : [],
      model: selectedModel,
    };
    res.json(await runPython("match_decision.py", payload, selectedScenario, selectedModel));
  } catch (error) {
    console.error("Decision error:", error.message);
    res.status(error.status || 500).json({ error: error.message || "The LLM could not respond to the offer." });
  }
});

app.use((error, _req, res, next) => {
  if (error instanceof SyntaxError && "body" in error) return res.status(400).json({ error: "Request body must be valid JSON." });
  next(error);
});

const PORT = Number(process.env.PORT || 3000);
app.listen(PORT, () => console.log(`Creative Negotiations is running at http://127.0.0.1:${PORT}/experiment`));
