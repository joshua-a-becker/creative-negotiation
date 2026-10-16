# Experiment materials

The current **200-issue Candidate–Recruiter scenario** and its feedback survey. Role text starts from `app/config/large-200.json`, with the reviewed feedback-material edits in `developer/role_presentation.py`: a shorter budget explanation, budget placed next to its worked example, selective bullets and five numbered scoring notes. Role names/examples are italicized; positive points are green, +2 is underlined, and negative points are red. The agreement sentence explicitly names the counterpart. Payoff values and frozen scenario files are unchanged. The researcher approved this version for publication on 10 September 2026. See `EMPIRICA_INTEGRATION.md` for the remaining external-renderer compatibility check. The survey keeps the attached mockup's 15 questions.

## Raw links for Empirica

| Material | Raw URL |
|---|---|
| Candidate role | [candidate_role_materials_200.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/candidate_role_materials_200.json) |
| Recruiter role | [recruiter_role_materials_200.json](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/recruiter_role_materials_200.json) |
| Survey when the participant is **Candidate** | [candidate_feedback_survey.yaml](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/candidate_feedback_survey.yaml) |
| Survey when the participant is **Recruiter** | [recruiter_feedback_survey.yaml](https://raw.githubusercontent.com/SamQuinto/Creative-Negotiations-Materials/refs/heads/main/recruiter_feedback_survey.yaml) |

Randomly assign a role, show only that role's `narrative`, and load its matching survey. Two survey files keep Q2, Q9 and Q12 role-specific without requiring a new YAML branching feature.

**Public participant materials, private development:** the raw links above use the separate public `Creative-Negotiations-Materials` repository. This development repository remains private. Each role JSON uses the existing schema but contains one role only. The old combined JSON is retained only for link compatibility. The researcher HTML and Q12 answer key stay private. Never put a GitHub token in a participant-facing URL or browser bundle.

## Same file formats as the existing materials

- **JSON:** top-level `roles` and `tips`; each role has `role_name`, Markdown `narrative`, `RP`, and `scoresheet`. `RP` is 0. `scoresheet` is deliberately empty: this is a narrative-discovery feedback task, so participants must not receive the hidden 200-issue menu. Use the shared app scorer—not this narrative-only file—to calculate offer values.
- **YAML:** top-level `scales` and `questions`; existing `likert`, `single_select`, `multi_select`, and `open_text` question types. Yes/No choices are quoted strings. No new conditional syntax or researcher answer-key fields are included.
- **Written answers:** Q6 asks for three required terms. Q11 uses one standard `open_text` box for 3–5 job-feature names only, one per line, without reasons or justifications. Its gray hint and three-line placeholder are in the mockup and YAML; see `EMPIRICA_INTEGRATION.md` if the external reader ignores those presentation fields.
- **Instructions:** `tips` contains the existing feedback-task instructions and bonus notice as HTML, not an added negotiation-strategy intervention. Show these to participants and keep the role-reading confirmation and review-materials button shown in the mockup. Required/optional wording must be respected by the survey host; the example schema does not itself implement all validation rules.

Open `Mockup - Creative Negotiations Feedback Survey.html` locally for the complete two-page visual preview. It includes researcher controls and a clearly labelled Q12 answer key; **do not serve that preview as the participant survey**. The raw survey YAML files contain only participant questions and options. The JSON/YAML follow the supplied formats; the actual Empirica loader is maintained separately.

## Updating

Edit approved role materials in `app/config/large-200.json`. Edit survey wording/layout in the HTML. Then, from the repository root:

```text
python developer/build_experiment_materials.py
python developer/test_experiment_materials.py
```

The builder refreshes the HTML's embedded roles and exports both YAML files and the JSON. It needs only Python's standard library; no API calls or keys. For a launched study, pin the raw URLs to a commit instead of `refs/heads/main` so later edits cannot change participants' materials mid-study.

After checking an update, copy the two role-specific JSONs, both survey YAMLs, `About_This_Activity.md`, and `EMPIRICA_INTEGRATION.md` to the public materials repository and commit them there. Keep the old combined JSON current while its compatibility link remains available. Do not publish the researcher HTML or answer key. Public publication is separate from rebuilding the private preview.
