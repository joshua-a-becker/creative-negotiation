# Small Empirica updates

## Use the role-specific files

After assigning Candidate or Recruiter, load that role's JSON and survey YAML. Each role JSON keeps the existing `roles`/`tips` structure, but `roles` contains **one role only**. Render `roles[0].narrative` using the existing paragraph and bold support. Do not download the other role's material into the participant interface.

**Reviewed presentation — approved for publication on 10 September 2026:** single-asterisk Markdown was displayed literally in Empirica. The new presentation keeps the same JSON schema and uses ordinary paragraph breaks, literal `•` bullets, `1.`–`5.` numbered notes, existing double-asterisk bold, and small inline HTML tags for italics, payoff colors and underlined +2 values. `developer/role_presentation.py` applies the reviewed wording/layout to a copy of the original text. The HTML mockup uses that same presentation. The agreement sentence names the other role in italics and requires a positive total score for both parties. Original scenario files, payoff values and frozen simulations remain unchanged.

The researcher's Empirica screenshots confirmed inline italics, payoff colors, the indented example and list indentation render correctly. Bullet and numbered paragraphs use an explicit block `span` with `margin-left:1.5em; padding-left:1.25em; text-indent:-1.25em` to indent the marker and align wrapped lines under the text. This does not depend on the host's list styles.

11 September refinements: each main payoff bullet has a `br` line break before its neutral choice, without creating another item. Zero payoffs are blue and bold; both +2 and −2 are underlined. Notes 2, 4 and 5 use the latest reviewed wording. Note 4 is bold dark blue. Note 5 uses numeric blue bold 0. The italic offer example is indented like the worked budget example and ends “together with [list any job features you want to bring up].” These refinements still need a final visual check in Empirica after reloading.

If tags appear literally or colors are removed, check the reader's formatting support; **do not disable sanitization or enable arbitrary HTML**. Only the generated `em`, `strong`, `u`, `br` and indented/colored `span` formatting and four fixed colors (`#166534`, `#b91c1c`, `#1d4ed8`, `#1e3a8a`) are needed. No script, external asset or event handler is included in the narrative. The previous `role_markdown` function remains available for a bold-only fallback; apply the review wording edits too if using it. After an update, reload the role JSON; already-open sessions or pinned older commit URLs may still show the old text.

The previous combined `role_materials_200.json` remains only for compatibility with an earlier link. Use the new role-specific links for this survey.

## Replace the hardcoded introduction

Use `About_This_Activity.md` for **About This Activity**. It distinguishes the feedback activity's random bonus draw from the main study's agreement-based bonus. Changing a role JSON cannot replace text that is hardcoded in Empirica; paste this content into that component.

## Q11: one text box, job-feature names only

The 11 September decision replaces the earlier repeatable-row plan. Keep `q11` as `open_text`: participants list 3 job-feature names, optionally up to 5, in one box. Do not request reasons or justifications.

The YAML provides a two-line `hint` and a three-line `placeholder`. Show the hint above the box in gray, normal-weight text using `white-space: pre-line`. The hint should stay visible while typing; the placeholder disappears normally. Save only the participant's entered answer under `q11`, never the placeholder. Do not add new response fields or an Add another button.

The private mockup implements this. If the deployed reader still shows only “Your response…”, it must bind the existing textarea's `placeholder` to `question.placeholder` and display `question.hint`. The screenshot does not establish support for those optional presentation fields; updating YAML alone cannot force a reader that ignores them to display them.

## Role-specific wording and the counteroffer

Q2, Q9 and Q12 name the correct counterpart in each role's YAML. Q9's label contains three paragraphs: the role-specific introduction, the unchanged counteroffer, then “What offer would you make to respond to them?” Preserve these breaks with `white-space: pre-line` in the reader. The local mockup additionally shows the offer in a separate italic quotation panel. No arbitrary HTML or Markdown parsing is needed for the YAML survey.
