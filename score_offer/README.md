# Creative Negotiations — experiment materials

Current materials for the Candidate–Recruiter negotiation project. This public repository contains participant role materials and surveys, plus the Empirica scorer runtime and scoring scenarios linked below. Participant data, API keys, analysis files, and internal planning documents are not included.

## Current materials

### Feedback pre-test

| Material | Raw file |
|---|---|
| Candidate role materials | [candidate_role_materials_200.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/candidate_role_materials_200.json) |
| Recruiter role materials | [recruiter_role_materials_200.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/recruiter_role_materials_200.json) |
| Candidate feedback survey | [candidate_feedback_survey.yaml](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/candidate_feedback_survey.yaml) |
| Recruiter feedback survey | [recruiter_feedback_survey.yaml](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/recruiter_feedback_survey.yaml) |
| Hardcoded activity introduction | [About_This_Activity.md](About_This_Activity.md) |

Load only the role JSON and survey YAML matching the participant's assigned role.

The `_200` role filenames are retained so existing Empirica raw links continue to work. Their contents are the current reviewed role materials.

These are the expanded-task narratives. For the Fixed-15 condition, the experiment must instead use the fixed version and show that participant's own full payoff table; do not reuse an open-ended narrative and call it Fixed 15. The scorer, current scenario files, developer guide, and minimal offline replication are in the [main prototype repository](https://github.com/SamQuinto/Creative-Negotiations).

### Post-negotiation surveys

| Use | Empirica YAML | Interactive preview |
|---|---|---|
| Classroom exercise | [class_post_negotiation_survey.yaml](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/class_post_negotiation_survey.yaml) | [Open preview](https://raw.githack.com/SamQuinto/Creative-Negotiations-Materials/main/class_post_negotiation_survey_preview.html) |
| Prolific Fixed-15 versus Latent-215 study | [prolific_post_negotiation_survey.yaml](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/prolific_post_negotiation_survey.yaml) | [Open preview](https://raw.githack.com/SamQuinto/Creative-Negotiations-Materials/main/prolific_post_negotiation_survey_preview.html) |

The HTML files are visual, interactive previews only. They do not save or transmit responses.

### Empirica scorer and scenarios

[Open the public Empirica folder](empirica/). **Download everything inside that folder, including `app/`.** It now contains both Python commands, the current 215-issue scenario, and the complete shared scoring engine. No other repository folder is needed to run the scorers. [The short setup guide](empirica/README.md) includes a no-key installation check.

[Detailed instructions, extra tests, the preview, and other scenario exports](empirica-support/) are kept separately. The optional preview also uses `developer/`. The exact engine revision and file hashes are in the [runtime manifest](empirica-support/runtime_manifest.json). This is a folder cleanup; the scoring logic and payoffs are unchanged.

| Backend scenario | Public raw JSON |
|---|---|
| Fixed 15 | [fixed-15.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/main/empirica-support/scenarios/fixed-15.json) |
| Flexible 15 | [flexible-15.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/main/empirica-support/scenarios/flexible-15.json) |
| Flexible 215 | [flexible-215.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/main/empirica/flexible-215.json) |
| Tutorial | [tutorial.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/main/empirica-support/scenarios/tutorial.json) |

These complete scoring files include both roles' payoffs and the issue catalogue. They are publicly inspectable, not participant-facing role files; load them server-side and do not send the complete files to participants' browsers. The visible `readrole_instructions` test placeholder still needs replacing before participant collection. The main prototype repository remains private.

## Which survey to use

- **Classroom:** a short teaching and reflection survey for the Control versus Perspective Taking exercise. It compares an open-ended negotiation with a predefined-issue exercise such as New Recruit and supports discussion of strategy, learning, and how negotiations became stuck or resumed progress.
- **Prolific:** the research survey for Fixed-15 versus Latent-215. It includes the full Subjective Value Inventory, perceived realism and role engagement, Creative Process Engagement, Creative Self-Efficacy, offer-strategy reflection, and the plain-language “felt stuck” module.

Issue generation, issue redefinition, issue diversity, agreement, time, offers, payoffs, joint gains, and Pareto efficiency come from behavioral experiment logs rather than survey self-reports.

## Implementation notes

- [EMPIRICA_INTEGRATION.md](EMPIRICA_INTEGRATION.md) explains role rendering, conditional survey branching, and feedback-survey display requirements.
- [SURVEY_MEASURE_NOTES.md](SURVEY_MEASURE_NOTES.md) records measure sources and which items were developed for this project.
- For a live study, replace `refs/heads/main` in raw links with the approved commit ID so later edits cannot change materials during data collection.
