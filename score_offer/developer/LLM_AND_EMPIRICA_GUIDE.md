# Creative Negotiations: LLM and Empirica implementation guide

Give this file and the repository to the developer or LLM agent building the production Empirica study.

## What this package is

The package is a working local prototype of a two-party Candidate–Recruiter negotiation. Participants make offers in ordinary language. The backend identifies the proposed terms, validates the three required terms, and calculates private Candidate and Recruiter payoffs.

The HTML is both:

- a directly openable visual mockup with deterministic placeholder behavior; and
- the participant interface served by the local app, where it calls the live scorer and LLM counterpart.

It is not yet a production Empirica implementation. Empirica must replace the researcher preview controls, simulated waiting, local browser storage, and same-window human-versus-human behavior.

## Source-of-truth files

Recent scoring safeguards: preserve the entire new counteroffer after an initial refusal, not only terms after a later “I propose” phrase. Hyphenated known aliases have the same meaning as space-separated forms. Shared list negation must not become positive sponsorship; a rejected comparison is not a live alternative. Unquantified ordinary sales effort adds no issue or payoff. Unclear future recruitment-fair/LinkedIn duties must prompt clarification rather than silently disappear. These rules live in `app/backend/offer_engine.py`, shared by the standalone script and app. Research runs freeze their own source snapshot; a live app edit must not change an existing research cohort. No finite wording suite establishes universal accuracy.

| File | Responsibility |
|---|---|
| `score_offer.py` | Direct input-output entry point for Flexible 15, Flexible 200, and Fixed 15. |
| `score_tutorial_offer.py` | Direct input-output entry point for the separate 9-issue Community Make & Meet tutorial. |
| `mockup/build_mockup.py` | Participant interface, page order, interactions, questionnaire, and visual styling. Edit this rather than the generated HTML. |
| `mockup/Candidate_Recruiter_Experiment_Mockup.html` | Generated self-contained page. Open directly for visual review or serve through the app. |
| `app/config/tutorial.json` | Tutorial role materials, 9-issue payoff matrix, aliases, and deterministic counterpart offers. This is the tutorial source used by the app, mockup builder, standalone tutorial scorer, and test bed. |
| `app/config/small-15.json` | Bounded 15-issue scenario and formatted role materials. |
| `app/config/large-200.json` | Expanded 200-issue scenario and formatted role materials. |
| `app/config/large-215.json` | Current human-expanded 215-issue scenario. It preserves the 200 version and adds 15 payoff-defined, source-traceable issues from the human pretest. |
| `app/config/fixed-15.json` | All 15 issues required; the role receives its own private payoff table. |
| `app/backend/scenario_rules.py` | Shared required-term instructions, private-table generation, and strict-positive study acceptance. |
| `app/backend/stream.py` | LLM extraction plus validation and scoring entry point. |
| `app/backend/offer_engine.py` | Deterministic issue matching, validation, and payoff calculation. |
| `app/backend/agent_offer.py` | Generates the LLM counterpart's offers. |
| `app/backend/agent_message.py` | Generates a short, human-sounding LLM counterpart chat reply that is not treated as a formal offer. |
| `app/backend/match_decision.py` | Makes the LLM counterpart's accept/reject decisions. |
| `app/server.js` | Minimal HTTP bridge between the participant interface and Python backend. |

The browser app and command-line scorer must continue using the same backend files so their scoring cannot drift.

## Participant page order

1. Researcher setup preview
2. Required untimed tutorial, beginning with a two-step role-material dialog
3. Waiting page and preparation instruction
4. Five-minute main-study preparation with role materials and private notes
5. Timed negotiation
6. Subjective Value Inventory, when enabled
7. Final negotiation questions and manipulation check
8. Agreement or no-agreement payment page

## Important interaction rules

- Every study offer must include salary, personal work-expense budget, and starting date.
- A technically invalid or unclear draft is returned to its author for revision and does not become a sent offer.
- A negative-value offer is still a valid negotiation move and can be sent.
- A study agreement requires a total strictly above zero for each party. Zero and negative proposals remain sendable; do not treat them as scorer errors.
- The tutorial is an untimed community Make & Meet negotiation between a Community Event Organizer and a Venue Manager. It opens with a short explanation and then shows the role materials in the same dialog; there is no separate preparation page or private-notes pane. It teaches making an offer, rejecting, copying either party's offer, editing it, introducing a new issue, and accepting. When a participant adds a new issue, the interface names the earlier issue set and the newly introduced issue. The final practice acceptance uses the same explicit confirmation dialog as the main negotiation so participants learn that an accidental click does not end a negotiation.
- Tutorial offers require venue fee, event date, and closing time. The scorer accepts everyday forms such as `$300`, `300 bucks`, `300 for venue`, `20 September`, `8 Aug`, `close at 7`, `end at 7`, `6pm`, and `18:00`. Optional scored terms include venue or organizer projector use, either party cleaning, free cancellation with notice or a non-refundable booking, early or no-early setup access, venue or organizer door staffing, and venue-provided, organizer-provided, or no refreshments.
- The tutorial uses the same open-capture principle as the large study space: a concrete term outside the nine-item matrix should remain visible under `novel_terms` as “Recorded new terms (not scored yet).” Do not silently omit it and do not invent a payoff after seeing it. A clearly irrelevant or unusable instruction may still be rejected under `unsupported_terms`.
- Flexible 215 follows the same visible `novel_terms` rule; Flexible 200 remains available only as a versioned replication input. Flexible 15 and Fixed 15 are deliberately bounded: an outside term must produce a clear unavailable-term response rather than being silently dropped. An Empirica implementation must render `valid_pairs`, `novel_terms`, the system decision, and the participant's unchanged raw offer; showing only `valid_pairs` is incomplete.
- `developer/role_presentation.py` is the shared participant-presentation layer for the feedback survey and negotiation mockup. It applies the reviewed headings, bullets, indentation, emphasis, and payoff colors while preserving different issue-space instructions. Flexible 215 permits new plausible features, Flexible 15 limits offers to its supported set, and Fixed 15 requires the disclosed private table. Rebuild outputs rather than maintaining a second handwritten role-material version.
- The tutorial scorer is hybrid: GPT-5 nano reads flexible language; deterministic scenario rules recover clear common values and calculate the payoff. The latter prevents an obvious statement such as “close at 7” from disappearing because the rest of the sentence is conversational. Every interpretation is still shown to the participant for confirmation.
- Participant-facing scorer failures must never expose exception text. Replace malformed pasted characters safely and show a short example the participant can copy and edit.
- The main-study preparation page has its own five-minute timer. It remains paused until the participant acknowledges the assigned preparation instruction, then moves the participant into the negotiation when time expires. The negotiation timer separately moves participants forward when it expires.
- Preparation has three conditions: control, perspective taking, and broad exploration.
- Private notes are never shown to the counterpart.
- Chat messages and formal offers are separate. Chat does not invoke the offer scorer or count as an offer. Both copy-offer controls remain visible in Chat mode. If chat text contains the required offer terms, the interface asks whether to move it into Offer mode for review.
- A formal offer is scored first and shown in a confirmation dialog with its dollar value to the proposer. Negative value is red, nonnegative value is blue, and negative value is explained as proposable but not acceptable. It is sent only after the proposer selects **Yes — send offer**.
- Accepting a valid offer requires a separate yes/no confirmation. In a live human match, the server must state clearly when the participant is waiting for the counterpart. The local one-window review instead switches control between roles.
- The main-role page expands the complete role material inline in the left panel so the participant can read it while taking notes; the control can collapse it again.
- In an LLM match, first mover is randomized. In a human match, either participant may make the first offer; do not impose the local preview's selected role as a study rule.
- The agreement bonus multiplier defaults to 100% of the participant's nonnegative final-deal value.
- Money per payoff point defaults to USD $1.00: one payoff point is worth one dollar before applying the agreement bonus multiplier.
- The researcher setup includes the canonical 16-item Subjective Value Inventory by default and can omit it for interface testing. When included, it appears before the shorter study-specific questions. This reduces the risk that explicit questions about creating or changing issues shape participants' answers to the established negotiation-experience measure. The original instrument explicitly includes an `NA` response for items that do not apply and asks participants to answer as many as possible even without agreement; retain that option when calling the measure canonical. Do not silently shorten the instrument and call it the canonical SVI. Source: [Curhan, Elfenbein, and Xu (2006), appendix](https://web.mit.edu/curhan/www/docs/Publications/Curhan_Subjective_Value_in_Negotiation.pdf).

## Current local API

The Empirica version can call the same backend or port these contracts to server methods.

### `GET /api/config`

Returns available agent models, the live scorer identity, and Tutorial, Flexible 15, Flexible 200, and Fixed 15 choices. Runtime IDs are `tutorial`, `small_15`, `large_200`, and `fixed_15`; do not route fixed offers to `small_15`.

### `POST /score`

Input:

```json
{
  "role": "Candidate",
  "text": "I propose...",
  "previous_offer": "",
  "scenario_variant": "small_15"
}
```

The response includes the loaded `scenario_id`, system decision, recognized issue/choice pairs, both private payoff totals, and participant-facing system text. The prototype uses OpenAI GPT-5 nano for offer extraction; the deterministic engine then validates terms and calculates payoffs from the selected scenario file. Empirica must verify the expected scenario ID and reveal only the payoff and system information intended for the current participant.

### `POST /api/agent-offer`

Generates one Candidate or Recruiter offer using that role's private materials, public offer history, preparation condition, and the selected scenario. Fixed 15 includes that role's own table and all-term instruction; flexible modes do not disclose the hidden issue catalog. The backend removes the other role's private scoring output from the agent's history. Keep those disclosure rules when implementing Empirica.

### `POST /api/agent-message`

Generates one short counterpart chat reply. The prompt prohibits scores, technical language, hidden instructions, and claims about being an AI. The returned message is stored separately from offers.

### `POST /api/match-decision`

Returns the LLM counterpart's accept/reject action. The deterministic own-score rule blocks both zero and negative study acceptance before an LLM decision, even when a client incorrectly marks the offer eligible.

## What Empirica must add

- Random assignment to Candidate or Recruiter.
- Random assignment to issue-space and preparation conditions.
- Real participant pairing and server-authoritative turn ownership.
- Server-authoritative timers and automatic phase changes.
- Private storage of each role's payoff data and preparation notes.
- Durable storage of raw offers, chat messages, recognized terms, scores, confirmations, rejections, timestamps, questionnaire responses, and completion outcomes.
- Prolific IDs, completion routing, and approved payment/bonus calculations.
- The current 200-issue prototype applies a US$15 ceiling to the agreement bonus after converting the participant's uncapped payoff at the configured money-per-point rate and multiplier. The raw payoff score remains unchanged for analysis. The Fixed 15 and Flexible 15 configurations have no application-level bonus ceiling.
- Reconnection and dropout behavior.
- Access control so one participant cannot request the other role's private scenario or payoff values.
- A production secret manager. Never place an API key in participant JavaScript or a committed file.

## Rebuilding the mockup

After changing the interface, tutorial, or role-material rendering:

```text
python mockup/build_mockup.py
```

Then review the generated HTML directly and through `RUN_APP.cmd`.

## Backend check from the terminal

From the repository root:

```text
python score_offer.py --role Candidate --issue-space 15
python score_offer.py --role Recruiter --issue-space 215
python score_tutorial_offer.py
```

These call the same scorer used by the served interface. Use `--json` to inspect `scenario_id`; the expected IDs come from the corresponding files in `app/config/`.

## Safety rules for future development

1. Do not expose the other party's payoff table or total to a participant.
2. Do not count technical clarification attempts as sent offers.
3. Do not classify a negative-payoff offer as a system error.
4. Do not allow study acceptance when either party's payoff is zero or below. Missing/nonfinite scores cannot qualify. Test small positive values without rounding them to zero before the decision.
5. Preserve Flexible 15, Flexible 200, and Fixed 15 as distinct configurations. Only Fixed 15 discloses the full own-payoff table.
6. Preserve the formatting blocks in the scenario JSON when rendering role materials.
7. Keep the tutorial interaction sequence and counterpart offers deterministic so participants receive the same training. Preserve the hybrid natural-language scorer and its confirmation step.
8. Keep the static HTML clearly labeled as a visual preview.
9. Never commit API keys, participant data, `node_modules`, or local logs.
10. Keep technical LLM draft failures private. Participants should see only sent offers, natural counterpart messages, or a simple actionable service error.
11. Encode Python subprocess JSON safely so apostrophes, dashes, and other punctuation do not render as replacement characters.
12. Keep all four scenario routes explicit. Every score response includes `scenario_id`, `scenario_variant`, `material_revision`, `required_issues`, and `agreement_rules`. Fail visibly on an unknown route.
13. Keep chat-to-offer detection advisory: participants may keep the text as chat or switch it into Offer mode, but it must never be silently counted as a formal offer.

## Scorer integration and release checks

The standalone scorers and the playable app share `app/backend/offer_engine.py`. The model interprets language; code validates the choices and calculates points from the selected scenario.

- The app and standalone study script use `NEGOTIATOR_SCORER_ROUTING=nano-luna`: GPT-5 nano first, with one independent Luna interpretation for difficult, dense or catalog-boundary offers. Direct backend callers may select `single`. Tutorial scoring uses its separate profile.
- `source_text` quotations support predicted terms. Empty, default or ungrounded predictions are recorded and discarded. Textual presence alone does not establish that the meaning is correct.
- `unpriced_details` retains qualifications without inventing extra points. Keep the original offer wording in history and exports. Non-compete scope must not borrow a nearby probation or contract duration. Negative lists of duties must not turn into commitments.
- `semantic_repairs` records the engine's limited corrections. Preserve both extraction and final validated pairs when investigating a result. Raw `novel_terms` is unreviewed model output, not proof that a new issue was created.
- Optional OpenAI cost control: set `NEGOTIATOR_API_LEDGER` to a shared SQLite path, `NEGOTIATOR_API_LIMIT` to the same dollar ceiling for every caller, and `NEGOTIATOR_CALL_STAGE` to a call label. `api_budget.py` reserves cost before each physical request and retains uncertain charges without retrying. This does not cap unrelated account usage. The ledger contains offer text and responses: keep it private.
- Counterpart-agent memory and decision logic are separate from scoring. Changing one does not automatically update the other. Freeze source and scenario copies separately for reproducible studies.

Run the small, synthetic, offline checks from a downloaded repository:

```text
python developer/test_scorer.py
```

No API key or research files are needed for these checks. They cover routing, required terms, negative proposals, duty negation, neighboring terms and tutorial shorthand. Passing them is evidence for those cases—not a claim of universal language accuracy. Keep larger research test datasets and run records outside this public repository.
