You review package $package of $plan, which Codex just changed in the working tree. Do not edit any file except
the verdict file.
Verdict file: $verdict
Read only that package row and the sections of $plan, of the 00-overview.md next to it (when there is one) and of
docs/design/time-and-source-routing.md it names
(grep -n first, then read only those lines). Run git status --short and git diff --stat, then git diff -- <file>
for each changed file; read hunks, not whole files.
Check: 1) the row's acceptance is met and a test covers it that runs and would fail without the change (a test
that is skipped, by `importorskip` or a skip mark, or whose assert holds either way is FIX); 2) only the
row's files changed, plus small helpers you name, plus kept test files edited only because this row's change or
an earlier package of this plan broke them (each edit drops an import or a case of deleted code, or moves an assert
or a request to the plan's new behaviour; a weakened test of kept behaviour, or an assert moved to code behaviour
that spec/ and the row do not state, is FIX); 3) the rules below; 4) no decision in spec/decisions.md is
broken (grep the N number you need, do not read the whole file); 5) no new logic: behaviour the row and spec/ do
not state (a rule, condition, default, threshold, error case, event or field) is PLAN, not PASS or FIX.
$rules
The tool already ran the acceptance check on the changed tests and the fast test suite, and both passed; do not
run tests. So every edit in the tree is one those checks may need: never ask to remove or revert an edit (a test
change, a handler, a fixture) unless you show with path:line that the checks still pass without it (removing one
route can turn a 404 into a 405, for example). An edit that is harmless but not needed is not a FIX.
$earlier
When Codex's answer says a check needs an edit an earlier finding asked to remove, verify it in the code; ask
again only with path:line that shows Codex is wrong.
Write the verdict file exactly like this:
line 1: VERDICT: PASS   or   VERDICT: FIX   or   VERDICT: PLAN
Use PLAN only when the code cannot be judged because the plan or the spec is the problem: the row is unclear, it
contradicts spec/ or another part, or it asks for something the code base cannot have. Then also write $note in
English: 1) what the row asks; 2) the problem with path:line in the plan, spec/ or the code; 3) what Codex did;
4) the options and the one you recommend. The plan check decides it from spec/ or asks the owner.
if PASS, line 2: COMMIT: <short English commit message>
if FIX, then a numbered list of at most 10 items, each "path:line - problem - expected". Nothing else.
Be strict on correctness and acceptance; ignore style nits.
Never run ./dev (it starts a new run).
