You review package $package of $plan, a UI row Codex just changed in the working tree. Do not edit any file except
the verdict file.
Verdict file: $verdict
Read only: that package row and the sections of $plan it names, the UI spec $ui_spec, $design, and the diff
(git status --short, git diff --stat, then git diff -- <file> for each changed file; hunks, not whole files).
Screenshots the tool just took of the running app (desktop 1440 x 900), one per item of the spec's "Capture" list:
$shots
Open every screenshot with Read and look at it.
Check:
1) every item of the spec's Layout, Texts and States is in the screenshots and the code: blocks in the stated order
   and lines, the exact Persian texts, the loading, empty and error states;
2) the look follows $design: its tokens and component classes, no new colour, size or radius, aligned fields,
   nothing overlapping, cut off, or overflowing, no horizontal scroll, consistent spacing;
3) right to left: blocks start on the right, labels sit with their fields, codes and URLs are left to right,
   logical CSS only (no left/right in new CSS), directional icons mirrored;
4) the UX rules: the spec's "UX rules applied" list, and the pre-delivery checklist of the ui-ux-pro-max skill
   ($skill/references/pro-rules.md, grep the checklist; skip the mobile and touch items, this UI is desktop only);
   a skill rule that conflicts with $design or with RTL Persian loses;
5) only the row's files and $shots_spec changed; the spec's tests assert the stated texts, not a constant;
6) no new behaviour: a field, rule, default or message that the row, the UI spec and spec/ do not state is PLAN.
$rules
The tool already built the UI and ran the smoke specs and $shots_spec; they passed. Do not run tests or the browser.
$earlier
Write the verdict file exactly like this:
line 1: VERDICT: PASS   or   VERDICT: FIX   or   VERDICT: PLAN
Use PLAN only when the row, the UI spec or $design is the problem; then also write $note in English: 1) what the
row asks; 2) the problem with path:line; 3) what Codex did; 4) the options and the one you recommend.
if PASS, line 2: COMMIT: <short English commit message>
if FIX, then a numbered list of at most 10 items, each "path:line or screenshot name - problem - expected".
Nothing else. Judge what the user sees; ignore code style.
Never run ./dev (it starts a new run).
