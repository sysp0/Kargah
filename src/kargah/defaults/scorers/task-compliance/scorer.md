+++
description = "Did the build deliver exactly what the ticket asked, and only that?"
agents = ["implement"]
harness = "claude"
model = "claude-haiku-5-5"
passing_score = 1.0
sampling_rate = 0
self_improvement = true
[[labels]]
value = "compliant"
score = 1.0
description = "The change delivers the ticket's request, scoped to it."
[[labels]]
value = "partial"
score = 0.5
description = "Delivers part of the request or adds unrequested scope."
[[labels]]
value = "non_compliant"
score = 0.0
description = "Does not deliver the request."
+++
Compare the diff and the agent's reply against the ticket. Judge only what is written in front of you: the ticket,
the prompt the agent got, its reply and the diff. Do not assume anything that is not shown. Pick the one label that
fits best and explain in one paragraph, naming the file or line that decided it.
