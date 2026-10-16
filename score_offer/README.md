# Creative Negotiations

This repository is a research prototype for negotiation in ordinary language. It recognizes the terms in an offer, checks whether the offer can be scored, and calculates private payoffs. If you want to review the prototype, adapt it for another study, or build an Empirica implementation, start with these three parts:

| What to open | What it does |
|---|---|
| **Visual mockup:** `mockup/Candidate_Recruiter_Experiment_Mockup.html` | Opens directly in a browser and shows the intended participant pages, layout, tutorial, and negotiation flow. Its counterpart replies are prewritten, so use it for visual review. |
| **Input-output scorers:** `score_offer.py` and `score_tutorial_offer.py` | Score one typed offer without starting the app. The first uses the Candidate–Recruiter study scenario; the second always uses the Community Make & Meet tutorial. Both use the same scoring engine as the app. |
| **Playable app:** `RUN_APP.cmd` | Combines the participant interface with the live scorer and an optional LLM counterpart. It includes the tutorial, chat and offers, confirmation, private notes, and the exit survey. |

## Test one offer directly

The study scorer supports Flexible 15, the current human-expanded Flexible 215, the archived Flexible 200, and Fixed 15:

```text
python score_offer.py
python score_offer.py --role Recruiter --issue-space 215
python score_offer.py --role Candidate --issue-space fixed-15
python score_offer.py --role Candidate --issue-space 15 --text "I propose a $60,000 salary, a $10,000 personal work-expense budget, and a June 15 start date."
```

The tutorial scorer always loads the separate 9-issue venue-practice scenario:

```text
python score_tutorial_offer.py
python score_tutorial_offer.py --text "300 for the venue on September 15 next year, closing at 9pm, with early setup access."
python score_tutorial_offer.py --text "300 bucks for the venue on 15 Sep, end at 9, and include projector use."
```

Add `--json` to either command to see the recognized scenario ID, issue choices, system decision, and both payoff totals. If `--text` is omitted, the script asks you to paste an offer.

The main scorer uses GPT-5 nano first and asks GPT-5.6 Luna for one independent check of difficult or dense offers. Code then calculates the payoffs; the models do not assign points themselves. The JSON records which model was used and why. Negative values remain valid proposals. The tutorial keeps its separate scenario and interpretation rules.

The scenario files are deliberately separate. Each file contains its role text, aliases, allowed values, and payoff matrix:

| Scenario | File | Standalone command |
|---|---|---|
| Tutorial: 9 venue issues | `app/config/tutorial.json` | `python score_tutorial_offer.py` |
| Main study: 15 issues | `app/config/small-15.json` | `python score_offer.py --issue-space 15` |
| Main study: current 215 issues | `app/config/large-215.json` | `python score_offer.py --issue-space 215` |
| Archived large version: 200 issues | `app/config/large-200.json` | `python score_offer.py --issue-space 200` |
| Fixed 15: all terms required; private own-payoff table | `app/config/fixed-15.json` | `python score_offer.py --issue-space fixed-15` |

Flexible versions require salary, personal budget, and starting date; Fixed 15 requires every listed term. Zero and negative offers can be proposed, but an agreement requires a total above zero for each party.

Each result includes its scenario ID. This makes a wrong-scenario configuration visible instead of silently applying the wrong payoff table. Both scorers combine flexible AI language interpretation with stable validation and payoff rules in `app/backend/offer_engine.py`; fixes there apply to the standalone scripts and the app.

In the tutorial, the nine stored issues are scored from `app/config/tutorial.json`. A plausible additional term outside that matrix is retained as a recorded new term with no points, rather than disappearing or receiving a payoff invented after the offer was made.

## Run the playable app

1. Install [Node.js](https://nodejs.org/) and [Python](https://www.python.org/downloads/). During Python installation, select **Add Python to PATH**.
2. Add an OpenAI key using the format below.
3. Double-click `RUN_APP.cmd`.

The app opens at:

```text
http://127.0.0.1:3000/experiment
```

OpenAI GPT-5 nano is used for live offer scoring. An Anthropic key is optional and is needed only when you choose the live LLM-counterpart preview. The app defaults to USD $1.00 per payoff point, a 100% agreement-bonus multiplier, and the full 16-item Subjective Value Inventory. The current 215-issue and archived 200-issue configurations cap the paid agreement bonus at $15 while retaining the uncapped payoff score in the exported research data.

## Main files

Participant role materials, feedback-survey items, and the updated survey preview are in [`experiment materials/`](experiment%20materials/README.md). That folder includes raw JSON/YAML links for loading the materials in Empirica.

| Path | Purpose |
|---|---|
| `score_offer.py` | One-off scorer for Flexible 15, Flexible 200, or Fixed 15. |
| `score_tutorial_offer.py` | One-off scorer for the 9-issue tutorial scenario. |
| `RUN_APP.cmd` | Starts the playable prototype. |
| `mockup/` | Browser-ready visual mockup and its builder. |
| `app/` | App server, shared scoring engine, LLM counterpart, and scenario files. |
| `developer/LLM_AND_EMPIRICA_GUIDE.md` | Detailed handoff for a developer or AI coding agent building the Empirica version. |

## Notes

- For hand-offs to an AI coding agent, provide `developer/LLM_AND_EMPIRICA_GUIDE.md`. It explains the page flow, important rules, backend calls, and what still needs to be built in Empirica.
- Provide your own API keys. `.gitignore` prevents local key files from being uploaded. Each file contains one key on one plain-text line:

  ```text
  app/openai_key.txt
  sk-your-openai-key-here

  app/anthropic_key.txt
  sk-ant-your-anthropic-key-here
  ```
