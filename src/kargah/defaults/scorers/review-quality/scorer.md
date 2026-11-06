+++
description = "Was the review specific, correct and complete for the change it saw?"
agents = ["review"]
harness = "claude"
model = "claude-haiku-5-5"
passing_score = 1.0
sampling_rate = 0
self_improvement = true
[[labels]]
value = "useful"
score = 1.0
description = "Findings are specific, correct for the diff, and nothing important is missed."
[[labels]]
value = "weak"
score = 0.5
description = "Vague, partly wrong, or misses an obvious problem."
[[labels]]
value = "useless"
score = 0.0
description = "Wrong, empty, or ignores the diff."
+++
You see the ticket, the review prompt, the reviewer's reply and, when shown, the diff. Judge the review, not the code:
are its must-fix items real and specific, and does a PASS fit the change? Pick the one label that fits best and
explain in one paragraph.
